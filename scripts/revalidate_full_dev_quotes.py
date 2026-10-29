"""Offline revalidation of a full-Dev judge run under the answer-quote v2 policy.

No API client is constructed and no original file is written. For every job in the
run plan this script:

* re-checks every saved output that failed under the old exact-substring rule and
  recovers those that pass the current validators (correctness: the first saved
  attempt that passes; other tasks: the saved final response);
* reuses, after re-validating it, an existing success cache entry when another result
  row with the identical answer already succeeded;
* re-checks every previously accepted output with the current validators and drops any
  that now fail (for example evidence outputs listing supporting IDs for a
  non-supported claim), so they are retried instead of silently kept;
* proves cache coverage: the prepared cache must contain every request except exactly
  the ones listed for retry, otherwise the script stops before writing any command;
* writes prepared caches and retry commands. Re-running a job against its prepared
  cache therefore calls the API only for the listed unique requests.

With --analysis-only nothing runnable is written: the counts are computed, but no
prepared cache is copied and no paid command is emitted.

Usage (from the repository root, with this checkout's `src` first on the path):

    $env:PYTHONPATH = "src"
    python scripts/revalidate_full_dev_quotes.py --plan RUN_ROOT/run-plan.json --out NEW_DIR
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cs30
from cs30.evaluation.evidence_quotes import ANSWER_QUOTE_POLICY
from cs30.evaluation.judge_runtime import validate_output_against_request
from cs30.evaluation.open_answer_models import (
    JudgeAssessment,
    JudgeAttempt,
    OpenAnswerRubric,
    OpenAnswerRun,
)
from cs30.evaluation.open_answer_scoring import canonical_hash, validate_assessment
from cs30.evaluation.v2_generation_models import JudgeRequest, JudgeResultEnvelope

RETRY_SUFFIX = "-quote-v2-retry1"
COUNT_KEYS = (
    "original_unresolved",
    "recovered_offline",
    "covered_by_existing_cache",
    "still_unresolved",
    "accepted_now_invalid",
    "retry_requests",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def command_arguments(command: str) -> tuple[list[str], dict[str, str]]:
    """Literal single-quoted PowerShell arguments, as recorded in the run plan."""
    tokens = re.findall(r"'([^']*)'", command)
    options = {
        tokens[i]: tokens[i + 1]
        for i in range(len(tokens) - 1)
        if tokens[i].startswith("--") and not tokens[i + 1].startswith("--")
    }
    return tokens, options


class Rebase:
    def __init__(self, pairs: list[tuple[str, str]]):
        self.pairs = pairs

    def __call__(self, value: str) -> Path:
        for old, new in self.pairs:
            if value.startswith(old):
                value = new + value[len(old) :]
                break
        return Path(value.replace("\\", "/") if self.pairs else value)


class InputLedger:
    """Hash every input once, then prove nothing was modified."""

    def __init__(self) -> None:
        self.hashes: dict[Path, str] = {}

    def track(self, path: Path) -> Path:
        if path.is_file() and path not in self.hashes:
            self.hashes[path] = sha256_file(path)
        return path

    def verify(self) -> None:
        changed = [str(p) for p, h in self.hashes.items() if sha256_file(p) != h]
        if changed:
            raise RuntimeError(f"original inputs changed during revalidation: {changed}")


def error_category(message: str) -> str:
    text = message.lower()
    for needle, label in (
        ("absent from the complete original answer", "answer_quote"),
        ("exact answer substring", "answer_quote"),
        ("nonempty exact answer quote", "answer_quote"),
        ("must not identify supporting evidence", "non_supported_with_evidence"),
        ("quote outside the supplied evidence", "evidence_quote"),
        ("one quote per supporting id", "evidence_quote_coverage"),
        ("always-assessed", "always_assessed_not_applicable"),
        ("lacks support among the cited", "citation_binding"),
        ("validation error", "schema"),
        ("truncated", "truncated"),
        ("did not return valid json", "invalid_json"),
    ):
        if needle in text:
            return label
    return "other"


def _record(job, record_id, outcome, original="", current="", category=None, **extra):
    return {
        "job": job["number"],
        "batch": job["batch"],
        "task": job["task"],
        "record_id": record_id,
        "outcome": outcome,
        "category": category or error_category(current or original),
        "original_error": original,
        "current_error": current,
        **extra,
    }


def correctness_key(row: dict[str, Any]) -> str:
    """The scorer's cache key, rebuilt from the identities saved on every judged row."""
    return canonical_hash(
        {
            "prompt": row["judge_prompt_sha256"],
            "config": row["judge_config_sha256"],
            "gold": row["gold_sha256"],
            "rubric": row["rubric_sha256"],
        }
    )


def correctness_trace(row: dict[str, Any]) -> dict[str, str]:
    return {
        "judge_model": row["judge_model"],
        "judge_prompt_version": row["judge_prompt_version"],
        "judge_prompt_sha256": row["judge_prompt_sha256"],
        "judge_config_sha256": row["judge_config_sha256"],
    }


def revalidate_correctness(job, opts, rebase, out_dir, ledger, analysis_only):
    scores_path = ledger.track(rebase(opts["--output-dir"]) / "open_answer_scores.jsonl")
    runs_path = ledger.track(rebase(opts["--runs"]))
    rubrics_path = ledger.track(rebase(opts["--rubrics"]))
    original_cache = rebase(opts["--cache-dir"])
    prepared_cache = out_dir / "prepared" / job["batch"] / "correctness-cache"

    rubrics = {
        r["question_id"]: OpenAnswerRubric.model_validate(r) for r in read_jsonl(rubrics_path)
    }
    answers = {}
    for row in read_jsonl(runs_path):
        run = OpenAnswerRun.model_validate(row)
        if run.answer is not None:
            answers[run.run_id] = run.answer.explanation

    def checked_inputs(row):
        answer, rubric = answers.get(row["run_id"]), rubrics.get(row["question_id"])
        if answer is None or rubric is None:
            raise ValueError(f"{row['run_id']}: answer or rubric missing for revalidation")
        if hashlib.sha256(answer.encode("utf-8")).hexdigest() != row["answer_sha256"]:
            raise ValueError(f"{row['run_id']}: saved answer differs from the scored answer")
        if canonical_hash(rubric.model_dump(mode="json")) != row["rubric_sha256"]:
            raise ValueError(f"{row['run_id']}: rubric differs from the scored rubric")
        return answer, rubric

    rows = read_jsonl(scores_path)
    judged = [r for r in rows if r.get("scoring_source") == "judge"]
    # A key is already in the success cache exactly when some row with that key holds an
    # assessment: the scorer caches every assessed result and nothing else.
    assessed_by_key: dict[str, dict[str, Any]] = {}
    for row in judged:
        if row.get("assessment") is not None:
            assessed_by_key.setdefault(correctness_key(row), row)

    records, new_entries = [], {}
    statuses = Counter(r["score_status"] for r in rows)
    # Group failed rows by cache key: identical answers share one judge request, so a key
    # is either served from cache (existing or recovered) or retried, never both.
    failed_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["score_status"] == "judge_error":
            failed_by_key.setdefault(correctness_key(row), []).append(row)

    for key, group in failed_by_key.items():
        originals = {}
        for row in group:
            attempts = [JudgeAttempt.model_validate(a) for a in row["judge_attempts"]]
            originals[row["run_id"]] = (attempts, attempts[-1].error if attempts else "")
        if key in assessed_by_key:
            for row in group:
                records.append(
                    _record(
                        job,
                        row["run_id"],
                        "covered_by_existing_cache",
                        originals[row["run_id"]][1],
                        category="answer_already_scored",
                        cache_key=key,
                        cache_source_run_id=assessed_by_key[key]["run_id"],
                    )
                )
            continue
        recovered, last_error = None, ""
        for row in group:  # saved attempts of every row with this answer, in order
            attempts, _ = originals[row["run_id"]]
            answer, rubric = checked_inputs(row)
            for index, attempt in enumerate(attempts, start=1):
                if not isinstance(attempt.raw_output, str):
                    continue
                try:
                    candidate = JudgeAssessment.model_validate_json(attempt.raw_output)
                    validate_assessment(candidate, rubric, answer)
                except Exception as exc:  # noqa: BLE001 - every failure stays unresolved
                    last_error = f"{type(exc).__name__}: {exc}"
                    continue
                recovered = (row, index, candidate, attempts)
                break
            if recovered is not None:
                break
        if recovered is None:
            for row in group:
                records.append(
                    _record(
                        job,
                        row["run_id"],
                        "still_unresolved",
                        originals[row["run_id"]][1],
                        last_error,
                        cache_key=key,
                    )
                )
            continue
        source_row, index, candidate, attempts = recovered
        new_entries[key] = {
            "key": key,
            "trace": correctness_trace(source_row),
            "assessment": candidate.model_dump(),
            "attempts": [a.model_dump() for a in attempts],
            "answer_quote_policy": ANSWER_QUOTE_POLICY,
            "recovered_from_attempt": index,
            "recovered_from_run_id": source_row["run_id"],
        }
        for row in group:
            records.append(
                _record(job, row["run_id"], "recovered", originals[row["run_id"]][1], cache_key=key)
            )

    retry_keys = {r["cache_key"] for r in records if r["outcome"] == "still_unresolved"}
    if not analysis_only:
        if not original_cache.is_dir():
            raise FileNotFoundError(f"original correctness cache not found: {original_cache}")
        shutil.copytree(original_cache, prepared_cache)
        for key, payload in new_entries.items():
            target = prepared_cache / f"{key}.json"
            if target.exists():
                raise FileExistsError(f"{target}: recovered key unexpectedly already cached")
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        # Coverage proof: every judged key must be served from the prepared cache and pass
        # the current validator, except exactly the keys listed for retry.
        for row in judged:
            key = correctness_key(row)
            path = prepared_cache / f"{key}.json"
            if key in retry_keys:
                if path.exists():
                    raise ValueError(f"{key}: retry key is unexpectedly cached")
                continue
            if not path.exists():
                raise ValueError(
                    f"{row['run_id']}: judged answer {key} is not in the prepared cache; "
                    "the rerun would pay for it again"
                )
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("key") != key or saved.get("trace") != correctness_trace(row):
                raise ValueError(f"{path}: cache identity differs from the scored row")
            answer, rubric = checked_inputs(row)
            validate_assessment(JudgeAssessment.model_validate(saved["assessment"]), rubric, answer)

    summary = {
        "result_rows": len(rows),
        "original_unresolved": statuses["judge_error"],
        "needs_review_unchanged": statuses["needs_review"],
        "recovered_offline": sum(r["outcome"] == "recovered" for r in records),
        "covered_by_existing_cache": sum(
            r["outcome"] == "covered_by_existing_cache" for r in records
        ),
        "still_unresolved": sum(r["outcome"] == "still_unresolved" for r in records),
        "accepted_now_invalid": 0,
        "retry_requests": len(retry_keys),
        "coverage_verified": not analysis_only,
    }
    return summary, records, {"--cache-dir": str(prepared_cache)}


def revalidate_judge_task(job, opts, rebase, out_dir, ledger, analysis_only):
    requests = {
        r["request_id"]: JudgeRequest.model_validate(r)
        for r in read_jsonl(ledger.track(rebase(opts["--requests"])))
    }
    cache_rows = [
        JudgeResultEnvelope.model_validate(r)
        for r in read_jsonl(ledger.track(rebase(opts["--cache"])))
    ]
    results = [
        JudgeResultEnvelope.model_validate(r)
        for r in read_jsonl(ledger.track(rebase(opts["--output"])))
    ]
    result_ids = [r.request_id for r in results]
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != set(requests):
        raise ValueError(f"job {job['number']}: results do not cover every request exactly once")

    records, prepared, invalid = [], {}, set()

    def current_check(envelope) -> str | None:
        try:
            validate_output_against_request(envelope.output or {}, requests[envelope.request_id])
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return None

    # Accepted outputs, from the cache first and then any accepted result row whose
    # cache line is missing, so no previously accepted request is paid for again.
    rebuilt = 0
    for source, envelopes in (("cache", cache_rows), ("results", results)):
        for envelope in envelopes:
            if envelope.unresolved or envelope.request_id in prepared:
                continue
            if envelope.request_id in invalid:
                continue
            if envelope.request_id not in requests:
                raise ValueError(f"{envelope.request_id}: cached result has no request")
            error = current_check(envelope)
            if error is not None:
                invalid.add(envelope.request_id)
                records.append(_record(job, envelope.request_id, "accepted_now_invalid", "", error))
                continue
            prepared[envelope.request_id] = envelope.model_copy(update={"cache_hit": False})
            rebuilt += source == "results"

    unresolved = [e for e in results if e.unresolved]
    for envelope in unresolved:
        if envelope.request_id in prepared or envelope.request_id in invalid:
            raise ValueError(f"{envelope.request_id}: unresolved result is also accepted")
        try:
            if envelope.raw_output is None:
                raise ValueError(envelope.error or "no saved provider output")
            output = validate_output_against_request(
                envelope.raw_output, requests[envelope.request_id]
            )
        except Exception as exc:  # noqa: BLE001
            records.append(
                _record(
                    job, envelope.request_id, "still_unresolved", envelope.error or "", str(exc)
                )
            )
            continue
        prepared[envelope.request_id] = envelope.model_copy(
            update={
                "output": output.model_dump(mode="json"),
                "unresolved": False,
                "error": None,
                "answer_quote_policy": ANSWER_QUOTE_POLICY,
            }
        )
        records.append(
            _record(
                job,
                envelope.request_id,
                "recovered",
                envelope.error or "",
                category=error_category(envelope.error or ""),
            )
        )

    retry_ids = set(requests) - set(prepared)
    expected = {
        r["record_id"]
        for r in records
        if r["outcome"] in ("still_unresolved", "accepted_now_invalid")
    }
    if retry_ids != expected:
        raise ValueError(
            f"job {job['number']}: cache coverage mismatch; the rerun would call "
            f"{len(retry_ids)} requests but {len(expected)} are listed for retry"
        )
    target = out_dir / "prepared" / job["batch"] / f"{job['task']}.cache.jsonl"
    if not analysis_only:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            for envelope in prepared.values():
                JudgeResultEnvelope.model_validate(envelope.model_dump(mode="json"))
                stream.write(envelope.model_dump_json() + "\n")
    summary = {
        "requests": len(requests),
        "original_unresolved": len(unresolved),
        "recovered_offline": sum(r["outcome"] == "recovered" for r in records),
        "covered_by_existing_cache": 0,
        "still_unresolved": sum(r["outcome"] == "still_unresolved" for r in records),
        "accepted_now_invalid": len(invalid),
        "retry_requests": len(retry_ids),
        "accepted_rebuilt_from_results": rebuilt,
        "coverage_verified": True,
    }
    return summary, records, {"--cache": str(target)}


def retry_command(command: str, replacements: dict[str, str], out_dir: Path, job) -> str:
    tokens, _ = command_arguments(command)
    stem = f"{job['batch']}.{job['task']}"
    replacements = replacements | {
        "--attempt-log": str(out_dir / "retry-ledgers" / f"{stem}.attempts.jsonl"),
    }
    if job["task"] == "correctness":
        replacements["--output-dir"] = str(out_dir / "retry-results" / job["batch"] / "correctness")
    else:
        replacements["--output"] = str(
            out_dir / "retry-results" / job["batch"] / f"{job['task']}.results.jsonl"
        )
    # Edit the recorded command text in place so unquoted parts (for example
    # "-m cs30.evaluation.open_answer_cli") and every other argument stay identical.
    rewritten = command
    for option, value in replacements.items():
        pattern = re.compile(rf"'{re.escape(option)}' '[^']*'")
        if len(pattern.findall(rewritten)) != 1:
            raise ValueError(f"job {job['number']}: expected exactly one {option} argument")
        replacement = "'{}' '{}'".format(option, value.replace("'", "''"))
        rewritten = pattern.sub(lambda _, text=replacement: text, rewritten)
    execution = re.compile(r"'--judge-execution-id' '([^']*)'")
    if job["task"] != "correctness":
        if len(execution.findall(rewritten)) != 1:
            raise ValueError(f"job {job['number']}: expected one --judge-execution-id")
        rewritten = execution.sub(
            lambda m: f"'--judge-execution-id' '{m.group(1)}{RETRY_SUFFIX}'", rewritten
        )
    if tokens and tokens[0] not in rewritten:
        raise ValueError(f"job {job['number']}: executable lost while rewriting the command")
    return rewritten


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--rebase",
        nargs=2,
        action="append",
        default=[],
        metavar=("RECORDED_PREFIX", "LOCAL_PREFIX"),
        help="map recorded absolute paths to another location (testing)",
    )
    parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="count only: write no prepared cache and no runnable retry command",
    )
    args = parser.parse_args(argv)

    if args.out.exists() and any(args.out.iterdir()):
        parser.error(f"{args.out} already exists and is not empty")
    args.out.mkdir(parents=True, exist_ok=True)
    module_path = str(Path(cs30.__file__).resolve().parent)
    print(f"cs30 imported from: {module_path}")
    ledger = InputLedger()
    plan = json.loads(ledger.track(args.plan).read_text(encoding="utf-8"))
    rebase = Rebase([tuple(pair) for pair in args.rebase])

    jobs_out, all_records, commands = [], [], []
    for number, job in enumerate(plan["jobs"], start=1):
        job = {**job, "number": number}
        _, opts = command_arguments(job["command"])
        handler = revalidate_correctness if job["task"] == "correctness" else revalidate_judge_task
        summary, records, replacements = handler(
            job, opts, rebase, args.out, ledger, args.analysis_only
        )
        jobs_out.append({"job": number, "batch": job["batch"], "task": job["task"], **summary})
        all_records += records
        if summary["retry_requests"] and not args.analysis_only:
            commands.append(
                (
                    number,
                    job,
                    summary["retry_requests"],
                    retry_command(job["command"], replacements, args.out, job),
                )
            )
        print(
            f"job {number:2d} {job['batch']:15s} {job['task']:16s} "
            + "  ".join(f"{k.split('_')[0]} {summary[k]:4d}" for k in COUNT_KEYS)
        )

    ledger.verify()
    totals, by_task = Counter(), {}
    for row in jobs_out:
        bucket = by_task.setdefault(row["task"], Counter())
        for key in COUNT_KEYS:
            totals[key] += row[key]
            bucket[key] += row[key]
    summary = {
        "answer_quote_policy": ANSWER_QUOTE_POLICY,
        "api_calls": 0,
        "analysis_only": args.analysis_only,
        "cs30_imported_from": module_path,
        "plan_sha256": ledger.hashes[args.plan],
        "inputs_unchanged": True,
        "totals": dict(totals),
        "by_task": {task: dict(c) for task, c in by_task.items()},
        "jobs": jobs_out,
        "outcomes_by_category": {
            outcome: dict(Counter(r["category"] for r in all_records if r["outcome"] == outcome))
            for outcome in (
                "recovered",
                "covered_by_existing_cache",
                "still_unresolved",
                "accepted_now_invalid",
            )
        },
        "input_sha256": {str(p): h for p, h in ledger.hashes.items()},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    fields = [
        "job",
        "batch",
        "task",
        "record_id",
        "outcome",
        "category",
        "original_error",
        "current_error",
        "cache_key",
        "cache_source_run_id",
    ]
    with (args.out / "records.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_records)

    lines = [
        "# Answer-quote v2 offline revalidation",
        "",
        f"Policy: `{ANSWER_QUOTE_POLICY}`. API calls: 0. Original files verified unchanged.",
        "Mode: "
        + ("analysis only (nothing runnable written)." if args.analysis_only else "prepared."),
        "",
        "Row counts are result rows; *retry requests* are the unique API requests a rerun",
        "would make (identical correctness answers share one request).",
        "",
        "| Task | Unresolved rows | Recovered offline | Covered by existing cache |"
        " Still unresolved | Accepted, now invalid | Retry requests |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for task, c in [*by_task.items(), ("**total**", totals)]:
        lines.append(f"| {task} | " + " | ".join(str(c[k]) for k in COUNT_KEYS) + " |")
    lines += ["", "Per job: summary.json. Per record: records.csv.", ""]
    (args.out / "report.md").write_text("\n".join(lines), encoding="utf-8")

    if args.analysis_only:
        (args.out / "RETRY_COMMANDS.md").write_text(
            "# Analysis only\n\nNo prepared cache was written, so there is nothing safe to "
            "run. Re-run without --analysis-only to prepare caches and retry commands.\n",
            encoding="utf-8",
        )
    else:
        retry = [
            "# Targeted retry (PAID)",
            "",
            "Run only after the quote-policy PR is merged and pulled into the run folder, and",
            "after the Leader agrees. Cache coverage was verified: each command calls the API",
            "only for the listed number of unique requests. Outputs, caches and ledgers go to",
            "new locations; the original run is never modified.",
            "",
        ]
        for number, job, count, command in commands:
            retry += [
                f"## Job {number}: {job['batch']} {job['task']} ({count} requests)",
                "",
                "```powershell",
                command,
                "```",
                "",
            ]
        (args.out / "RETRY_COMMANDS.md").write_text("\n".join(retry), encoding="utf-8")
    print(
        f"\nTotal rows: unresolved {totals['original_unresolved']}, recovered "
        f"{totals['recovered_offline']}, covered {totals['covered_by_existing_cache']}, "
        f"still {totals['still_unresolved']}, accepted-now-invalid "
        f"{totals['accepted_now_invalid']}. Unique retry requests: {totals['retry_requests']}. "
        f"Wrote {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
