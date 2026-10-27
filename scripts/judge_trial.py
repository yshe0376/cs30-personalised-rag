"""Small paid Gemini judge trial for M8 (Dev, four judge tasks, thinking high vs low).

Runs the existing M8 commands on the same ~20 Dev cells for correctness, adaptation,
discrimination and evidence support, once per thinking level. Client attempts and
application retries are logged. SDK-internal HTTP retries
are not individually observable; the provider bill remains authoritative. Writes:

  report.md       summary to paste into the PR (tokens, failures, retries, cost, projection)
  calls.csv       one row per client attempt
  spotcheck.md    each selected answer with the judge verdicts, for manual review
  summary.json    the same numbers in machine-readable form

Re-running with the same --out reuses completed output files and success caches.
Incomplete work can require another call; usage is logged immediately for auditing.
Use --offline first: it runs the whole pipeline without calling
Gemini (every judge call fails on purpose), to check paths and inputs at no cost.

Usage (from the repository root, with the project's virtual environment):

  python path/to/judge_trial.py --m7-root path/to/artifacts/m7-readiness-20261026 \
      --out path/to/W8/judge-trial-20261027 --offline

Paid execution is refused unless --allow-paid is supplied explicitly by the operator.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# Gemini 3.1 Flash-Lite paid tier, USD per million tokens; thinking is billed as output.
PRICE_INPUT = 0.25
PRICE_OUTPUT = 1.50
GENERATORS = {"gpt-oss": "a741d960ae90", "llama": "8ab0fdcd4d62", "gemma": "4abc260aaf58"}
JUDGE_TASKS = ("adaptation", "discrimination", "evidence_support")
TASKS = ("correctness", *JUDGE_TASKS)

CALLS: list[dict] = []
CONTEXT: dict = {}


def require_paid_opt_in(offline: bool, allow_paid: bool) -> None:
    """Never start paid execution without an explicit command-line opt-in."""
    if not offline and not allow_paid:
        raise ValueError(
            "Paid calls disabled. Use --offline for free checks; "
            "--allow-paid is required for paid execution."
        )


def cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * PRICE_INPUT + output_tokens * PRICE_OUTPUT) / 1_000_000


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def run_dir(root: Path, kind: str, digest: str) -> Path:
    matches = [p for p in root.glob(f"{kind}-{digest}*-run") if p.is_dir()]
    if len(matches) != 1:
        raise SystemExit(f"expected one {kind} run for {digest}, found {matches}")
    return matches[0]


def cli(main, argv: list[str], ok_codes: tuple[int, ...] = (0,)) -> int:
    code = main(argv)
    if code not in ok_codes:
        raise SystemExit(f"command failed ({code}): {' '.join(argv[:1])}")
    return code


def install_call_logger(offline: bool, log_path: Path) -> None:
    from cs30.evaluation import gemini_judge_client as module

    original = module.GeminiJudgeClient.complete

    def logged(self, prompt, text_format):
        record = {**CONTEXT, "thinking_level": self.thinking_level}
        started = time.perf_counter()
        try:
            if offline:
                raise RuntimeError("offline check: no API call made")
            response = original(self, prompt, text_format)
        except Exception as exc:
            record.update(
                api_ok=False,
                error=f"{type(exc).__name__}: {str(exc)[:200]}",
                input_tokens=0,
                output_tokens=0,
                thought_tokens=0,
                finish=None,
            )
            raise
        else:
            record.update(
                api_ok=True,
                error="",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                thought_tokens=int(getattr(response, "thought_tokens", 0)),
                finish=response.done_reason,
            )
            return response
        finally:
            record["seconds"] = round(time.perf_counter() - started, 2)
            record["cost_usd"] = cost(record["input_tokens"], record["output_tokens"])
            CALLS.append(record)
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")

    module.GeminiJudgeClient.complete = logged


def select_cells(adapted: dict[str, list[dict]], count: int, seed: int) -> list[dict]:
    """Spread cells over generators, levels and conditions; answered, main-scope only."""

    rng = random.Random(seed)
    combos = [
        (generator, level, condition)
        for generator in GENERATORS
        for level in ("beginner", "intermediate", "advanced")
        for condition in ("P0R0_plain", "P1R0_prompt_only", "P0R1_reranking_only", "P1R1_combined")
    ]
    rng.shuffle(combos)
    chosen: list[dict] = []
    used_questions: dict[str, set[str]] = defaultdict(set)
    for generator, level, condition in combos:
        if len(chosen) == count:
            break
        pool = [
            row
            for row in adapted[generator]
            if row["source_status"] == "answered"
            and row["target_level"] == level
            and row["condition"] == condition
            and row["eligibility"] in {"full", "endpoint_only"}
            and row["question_id"] not in used_questions[generator]
        ]
        if not pool:
            continue
        row = rng.choice(pool)
        used_questions[generator].add(row["question_id"])
        chosen.append({**row, "_generator": generator})
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--m7-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cells", type=int, default=20)
    parser.add_argument("--levels", nargs="+", default=["high", "low"])
    parser.add_argument(
        "--model", choices=["gemini-3.1-flash-lite"], default="gemini-3.1-flash-lite"
    )
    parser.add_argument("--seed", type=int, default=5703)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--allow-paid", action="store_true", help="explicitly permit paid API calls"
    )
    args = parser.parse_args()
    try:
        require_paid_opt_in(args.offline, args.allow_paid)
    except ValueError as exc:
        parser.error(str(exc))

    repo = args.repo.resolve()
    sys.path.insert(0, str(repo / "src"))
    from cs30.evaluation.open_answer_cli import main as answers_main
    from cs30.evaluation.v2_generation_cli import main as v2_main

    profiles = repo / "docs/evaluation/level-profile-v1/profile_checklist.frozen.json"
    rubrics = repo / "eval_inputs/m8/correctness-dev-rubrics-v0.1/rubrics.draft.jsonl"
    eligibility = repo / "docs/evaluation/eligibility-v1/personalisation_eligibility_v1.jsonl"
    for required in (profiles, rubrics, eligibility):
        if not required.is_file():
            raise SystemExit(f"missing {required}; pull the latest main first")
    if not args.offline and not (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    ):
        raise SystemExit("set GEMINI_API_KEY (a billing-enabled key) before the paid trial")
    if args.offline:
        os.environ.setdefault("GEMINI_API_KEY", "offline-placeholder")

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    mode = "offline" if args.offline else "paid"
    marker = out / "MODE.txt"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() != mode:
        raise SystemExit(
            f"{out} already holds a {marker.read_text(encoding='utf-8').strip()} run; "
            "use a different --out folder for the paid trial"
        )
    marker.write_text(mode, encoding="utf-8")
    root = args.m7_root.resolve()

    # 1. Adapt all six M7 batches (Dev and repeat for three generators).
    adapted: dict[str, list[dict]] = {}
    batch_dirs: dict[str, Path] = {}
    for generator, digest in GENERATORS.items():
        for kind in ("dev", "repeat"):
            run = run_dir(root, kind, digest)
            prepared = root / f"{kind}-{digest}-prepared"
            target = out / "adapted" / f"{kind}-{generator}"
            if not (target / "generation_evaluation_inputs.jsonl").is_file():
                cli(
                    v2_main,
                    [
                        "adapt-m7-artifacts",
                        "--expected-experiment",
                        str(run / "expected_experiment.json"),
                        "--generation-records",
                        str(run / "generation_records.jsonl"),
                        "--saved-answers",
                        str(run / "saved_answers.jsonl"),
                        "--run-manifest",
                        str(run / "run_manifest.json"),
                        "--gold",
                        str(prepared / "gold.jsonl"),
                        "--eligibility",
                        str(eligibility),
                        "--lambda-selection",
                        str(prepared / "lambda_selection.json"),
                        "--output-dir",
                        str(target),
                    ],
                )
            batch_dirs[f"{kind}-{generator}"] = run
            if kind == "dev":
                adapted[generator] = read_jsonl(target / "generation_evaluation_inputs.jsonl")

    # 2. Select the trial cells and write per-generator subsets.
    selection_path = out / "selection.json"
    if selection_path.is_file():
        selected = json.loads(selection_path.read_text(encoding="utf-8"))
    else:
        selected = select_cells(adapted, args.cells, args.seed)
        selection_path.write_text(
            json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if len(selected) != args.cells:
        raise SystemExit("saved/selected cell count differs from --cells")
    by_generator: dict[str, list[dict]] = defaultdict(list)
    for row in selected:
        by_generator[row["_generator"]].append(row)

    subsets: dict[str, dict[str, Path]] = {}
    for generator, rows in by_generator.items():
        digest = GENERATORS[generator]
        run = batch_dirs[f"dev-{generator}"]
        folder = out / "subset" / generator
        run_ids = {row["run_id"] for row in rows}
        write_jsonl(
            folder / "inputs.jsonl",
            [{key: value for key, value in row.items() if key != "_generator"} for row in rows],
        )
        write_jsonl(
            folder / "saved_answers.jsonl",
            [row for row in read_jsonl(run / "saved_answers.jsonl") if row["run_id"] in run_ids],
        )
        matrix = json.loads((run / "expected_experiment.json").read_text(encoding="utf-8"))
        matrix["cases"] = [case for case in matrix["cases"] if case["run_id"] in run_ids]
        (folder / "expected_experiment.json").write_text(json.dumps(matrix), encoding="utf-8")
        subsets[generator] = {
            "inputs": folder / "inputs.jsonl",
            "answers": folder / "saved_answers.jsonl",
            "matrix": folder / "expected_experiment.json",
            "gold": root / f"dev-{digest}-prepared" / "gold.jsonl",
        }

    # 3. Run the four tasks per thinking level, logging every Gemini call.
    calls_path = out / "calls.jsonl"
    install_call_logger(args.offline, calls_path)
    if calls_path.is_file():
        CALLS.extend(read_jsonl(calls_path))
    request_counts: Counter = Counter()
    outcomes: dict[tuple[str, str], Counter] = defaultdict(Counter)
    judge_results: dict[tuple[str, str, str], list[dict]] = {}
    correctness_rows: dict[tuple[str, str], list[dict]] = {}
    for level in args.levels:
        level_dir = out / f"thinking-{level}"
        config = level_dir / "judge-config.json"
        level_dir.mkdir(parents=True, exist_ok=True)
        config.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "config_version": f"gemini-judge-trial-{level}",
                    "provider": "gemini",
                    "model_family": "gemini",
                    "model_revision": args.model,
                    "temperature": 1.0,
                    "seed": 5703,
                    "thinking_level": level,
                    "prompt_version": "prompt-v1",
                    "output_schema_version": "1.0",
                    "local_model": False,
                    "data_approval": "approved",
                }
            ),
            encoding="utf-8",
        )
        for generator, paths in subsets.items():
            CONTEXT.clear()
            CONTEXT.update(task="correctness", generator=generator)
            target = level_dir / "correctness" / generator
            if not (target / "open_answer_scores.jsonl").is_file():
                cli(
                    answers_main,
                    [
                        "score",
                        "--gold",
                        str(paths["gold"]),
                        "--rubrics",
                        str(rubrics),
                        "--runs",
                        str(paths["answers"]),
                        "--expected-manifest",
                        str(paths["matrix"]),
                        "--output-dir",
                        str(target),
                        "--provider",
                        "gemini",
                        "--model",
                        args.model,
                        "--thinking-level",
                        level,
                        "--cache-dir",
                        str(level_dir / "correctness-cache"),
                    ],
                    ok_codes=(0, 3),
                )  # 3 = some cells need review or hit a judge error
            rows = read_jsonl(target / "open_answer_scores.jsonl")
            correctness_rows[(level, generator)] = rows
            needing_judge = [row for row in rows if row.get("scoring_source") != "rule"]
            request_counts[(level, "correctness")] += len(needing_judge)
            for row in needing_judge:
                outcomes[(level, "correctness")][row["score_status"]] += 1
            for task in JUDGE_TASKS:
                CONTEXT.clear()
                CONTEXT.update(task=task, generator=generator)
                requests = level_dir / task / f"{generator}-requests.jsonl"
                results = level_dir / task / f"{generator}-results.jsonl"
                if not requests.is_file():
                    cli(
                        v2_main,
                        [
                            "prepare-judge-requests",
                            "--inputs",
                            str(paths["inputs"]),
                            "--profiles",
                            str(profiles),
                            "--judge-config",
                            str(config),
                            "--task",
                            task,
                            "--output",
                            str(requests),
                        ],
                    )
                if not results.is_file():
                    cli(
                        v2_main,
                        [
                            "run-judge-requests",
                            "--requests",
                            str(requests),
                            "--judge-config",
                            str(config),
                            "--cache",
                            str(level_dir / task / "cache.jsonl"),
                            "--output",
                            str(results),
                            "--judge-execution-id",
                            f"trial-{level}-{task}-{generator}",
                        ],
                        ok_codes=(0, 3),
                    )
                request_rows = read_jsonl(requests)
                envelopes = read_jsonl(results)
                request_counts[(level, task)] += len(request_rows)
                judge_results[(level, task, generator)] = list(
                    zip(request_rows, envelopes, strict=True)
                )
                for envelope in envelopes:
                    outcomes[(level, task)][
                        "unresolved" if envelope["unresolved"] else "resolved"
                    ] += 1
            write_jsonl(calls_path, CALLS)

    # 4. Exact full-Dev request counts (no API calls), for the projection.
    full_counts: Counter = Counter()
    projection_dir = out / "projection"
    for batch, run in batch_dirs.items():
        kind, generator = batch.split("-", 1)
        inputs = out / "adapted" / batch / "generation_evaluation_inputs.jsonl"
        target = projection_dir / "correctness" / batch
        if not (target / "open_answer_scores.jsonl").is_file():
            cli(
                answers_main,
                [
                    "score",
                    "--gold",
                    str(root / f"{kind}-{GENERATORS[generator]}-prepared" / "gold.jsonl"),
                    "--rubrics",
                    str(rubrics),
                    "--runs",
                    str(run / "saved_answers.jsonl"),
                    "--expected-manifest",
                    str(run / "expected_experiment.json"),
                    "--output-dir",
                    str(target),
                    "--provider",
                    "none",
                ],
                ok_codes=(0, 3),
            )  # 3 = cells left for the judge, as expected
        # Identical (question, answer) pairs share one cached judge call within a batch.
        full_counts["correctness"] += len(
            {
                (row["question_id"], row["answer_sha256"])
                for row in read_jsonl(target / "open_answer_scores.jsonl")
                if row["score_status"] == "needs_review"
            }
        )
        any_config = out / f"thinking-{args.levels[0]}" / "judge-config.json"
        for task in JUDGE_TASKS:
            requests = projection_dir / task / f"{batch}-requests.jsonl"
            if not requests.is_file():
                cli(
                    v2_main,
                    [
                        "prepare-judge-requests",
                        "--inputs",
                        str(inputs),
                        "--profiles",
                        str(profiles),
                        "--judge-config",
                        str(any_config),
                        "--task",
                        task,
                        "--output",
                        str(requests),
                    ],
                )
            full_counts[task] += len(read_jsonl(requests))

    # 5. Summaries.
    summary: dict = {
        "offline": args.offline,
        "model": args.model,
        "cells": len(selected),
        "price_usd_per_million": {"input": PRICE_INPUT, "output_incl_thinking": PRICE_OUTPUT},
        "levels": {},
        "full_dev_requests": dict(full_counts),
    }
    for level in args.levels:
        level_summary = {}
        total_projection = 0.0
        for task in TASKS:
            calls = [c for c in CALLS if c["thinking_level"] == level and c["task"] == task]
            requests = request_counts[(level, task)]
            spent = sum(c["cost_usd"] for c in calls)
            per_request = spent / requests if requests else None
            projected = per_request * full_counts[task] if per_request is not None else None
            total_projection += projected or 0.0
            ok = [c for c in calls if c["api_ok"]]
            level_summary[task] = {
                "requests": requests,
                "api_calls": len(calls),
                "api_errors": len(calls) - len(ok),
                "extra_attempts": max(len(calls) - requests, 0),
                "outcomes": dict(outcomes[(level, task)]),
                "mean_input_tokens": statistics.mean(c["input_tokens"] for c in ok) if ok else None,
                "mean_output_tokens_incl_thinking": statistics.mean(c["output_tokens"] for c in ok)
                if ok
                else None,
                "mean_thought_tokens": statistics.mean(c["thought_tokens"] for c in ok)
                if ok
                else None,
                "truncated_calls": sum(1 for c in ok if c["finish"] == "length"),
                "spent_usd": spent,
                "cost_per_request_usd": per_request,
                "full_dev_requests": full_counts[task],
                "projected_full_dev_usd": projected,
            }
        level_summary["total_spent_usd"] = sum(
            c["cost_usd"] for c in CALLS if c["thinking_level"] == level
        )
        level_summary["projected_full_dev_usd"] = total_projection
        summary["levels"][level] = level_summary
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with (out / "calls.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = [
            "thinking_level",
            "task",
            "generator",
            "api_ok",
            "finish",
            "input_tokens",
            "output_tokens",
            "thought_tokens",
            "cost_usd",
            "seconds",
            "error",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(CALLS)

    def money(value):
        return "n/a" if value is None else f"USD {value:.4f}"

    def number(value):
        return "n/a" if value is None else f"{value:,.0f}"

    lines = [
        "## M8 judge trial" + (" (OFFLINE CHECK, no API calls)" if args.offline else ""),
        "",
        f"Model `{args.model}`, temperature 1.0, {len(selected)} Dev cells "
        f"({', '.join(f'{g}: {len(r)}' for g, r in by_generator.items())}) across levels and "
        "conditions, main-scope eligibility. Same cells for every task and thinking level. "
        f"Price: USD {PRICE_INPUT}/M input, USD {PRICE_OUTPUT}/M output including thinking "
        "(USD list price). Client attempts are logged, not SDK-internal HTTP retries.",
        "",
    ]
    for level in args.levels:
        s = summary["levels"][level]
        lines += [
            f"### thinking `{level}`",
            "",
            "| Task | Requests | API calls | Extra attempts | API errors | Unresolved | "
            "Mean input | Mean output (incl. thinking) | Mean thinking | Truncated | Spent | "
            "Per request | Full-Dev requests | Projected full Dev |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for task in TASKS:
            t = s[task]
            unresolved = sum(v for k, v in t["outcomes"].items() if k not in {"scored", "resolved"})
            lines.append(
                f"| {task} | {t['requests']} | {t['api_calls']} | {t['extra_attempts']} | "
                f"{t['api_errors']} | {unresolved} | {number(t['mean_input_tokens'])} | "
                f"{number(t['mean_output_tokens_incl_thinking'])} | "
                f"{number(t['mean_thought_tokens'])} | {t['truncated_calls']} | "
                f"{money(t['spent_usd'])} | {money(t['cost_per_request_usd'])} | "
                f"{t['full_dev_requests']:,} | {money(t['projected_full_dev_usd'])} |"
            )
        lines += [
            "",
            f"Spent at `{level}`: **{money(s['total_spent_usd'])}**. "
            f"Projected full Dev scoring at `{level}` (all six batches, four tasks): "
            f"**{money(s['projected_full_dev_usd'])}**.",
            "",
        ]
    lines += [
        "Notes:",
        "- Full-Dev request counts are exact: identical answers share one request, as in the "
        "real run; correctness excludes cells scored by deterministic rules and non-answers.",
        "- The projection scales the measured cost per request and already includes observed "
        "retries. Validity checks (repeat and order-reversed runs) cost about the adaptation "
        "per-request price times the size of each comparison subset, which the Leader has not "
        "fixed yet; a second judge from another family is not priced here.",
        "- Calls that failed without usage are counted as zero; "
        "the provider bill is authoritative.",
        "- This is a runtime and cost trial, not judge calibration.",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")

    # 6. Spot-check file: each answer with the verdicts from every task and level.
    spot = ["# Spot check", "", "Read each answer and check that the verdicts look reasonable.", ""]
    for number_, row in enumerate(selected, 1):
        generator = row["_generator"]
        spot += [
            f"## {number_}. {generator} · {row['target_level']} · {row['condition']} · "
            f"{row['eligibility']} · `{row['question_id']}`",
            "",
            f"**Answer:** {(row.get('answer') or '')[:1200]}",
            "",
        ]
        for level in args.levels:
            spot.append(f"**thinking {level}**")
            for score in correctness_rows.get((level, generator), []):
                if score["run_id"] == row["run_id"]:
                    spot.append(
                        f"- correctness: score {score.get('score')} ({score['score_status']}, "
                        f"{score['scoring_source']}) — {str(score.get('reason'))[:300]}"
                    )
            for task in JUDGE_TASKS:
                for request, envelope in judge_results.get((level, task, generator), []):
                    if request.get("payload", {}).get("answer") == row.get("answer"):
                        verdict = envelope.get("output") or {"unresolved": envelope.get("error")}
                        spot.append(f"- {task}: `{json.dumps(verdict, ensure_ascii=False)[:600]}`")
            spot.append("")
    (out / "spotcheck.md").write_text("\n".join(spot), encoding="utf-8")

    print((out / "report.md").read_text(encoding="utf-8"))
    print(f"Files written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
