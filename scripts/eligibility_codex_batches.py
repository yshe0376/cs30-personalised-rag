"""Prepare Codex eligibility-labelling batches and collect their outputs.

  python scripts/eligibility_codex_batches.py prepare --profile PROFILE.json \
      --term-convention TERMS.txt --gold GOLD.jsonl --run-dir RUN \
      [--question-ids IDS.txt] [--batch-size 20] [--seed N]
  python scripts/eligibility_codex_batches.py collect --run-dir RUN \
      --annotator-id ID --calibration-version V

prepare writes RUN/workdir (the only folder Codex sees), RUN/prompts and RUN/manifest.json.
collect validates RUN/workdir/output/*.jsonl, maps verdicts to labels and writes
RUN/eligibility_sidecar.jsonl plus RUN/needs_review.jsonl.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "docs" / "evaluation" / "eligibility-v1" / "prompt"
LEVELS = ("beginner", "intermediate", "advanced")
CRITERIA = {
    "intermediate_check": ("I1", "I2", "I3"),
    "beginner_criteria": ("B1", "B2", "B3", "B4"),
    "advanced_criteria": ("A1", "A2", "A3", "A4"),
}
ALWAYS_ASSESSED = {"B1", "B2", "B4", "A1", "A4"}
VERDICTS = {"pass", "fail", "not_applicable", "uncertain"}
DEMANDS = {"identify_or_name", "explain_why_or_how", "calculate", "other"}
FIELDS = (
    "question_id",
    "question_demand",
    "intermediate_reference_answer",
    "intermediate_check",
    "beginner_criteria",
    "advanced_criteria",
    "gold_answer_concern",
    "gold_answer_concern_note",
    "reason",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_profile_block(package: dict) -> str:
    profiles = {profile["level"]: profile for profile in package["profiles"]}
    checklists = {checklist["level"]: checklist for checklist in package["checklists"]}
    parts: list[str] = []
    for level in LEVELS:
        profile = profiles[level]
        parts.append(
            f"## {level.capitalize()} profile\n\n"
            f"Student positioning: {profile['student_positioning']}\n\n"
            f"Assumed physics background:\n{_bullets(profile['assumed_physics_background'])}\n\n"
            "Assumed mathematics background:\n"
            f"{_bullets(profile['assumed_mathematics_background'])}\n\n"
            "Terms allowed without explanation:\n"
            f"{_bullets(profile['terms_allowed_without_explanation'])}\n\n"
            f"Acceptable inference span: {profile['acceptable_inference_span']}\n\n"
            f"Omittable steps:\n{_bullets(profile['omittable_intermediate_steps'])}\n\n"
            f"Helpful writing patterns:\n{_bullets(profile['helpful_writing_patterns'])}\n\n"
            f"Harmful writing patterns:\n{_bullets(profile['harmful_writing_patterns'])}"
        )
    for level in LEVELS:
        lines = [
            f"{item['criterion_id']}: {item['description']}"
            for item in checklists[level]["criteria"]
        ]
        parts.append(f"## {level.capitalize()} checklist\n\n" + "\n\n".join(lines))
    return "\n\n".join(parts)


def input_row(gold_row: dict) -> dict:
    seen: set[str] = set()
    evidence: list[str] = []
    for evidence_set in gold_row["gold_core_evidence_sets"]:
        for span in evidence_set:
            if span["span_id"] not in seen:
                seen.add(span["span_id"])
                evidence.append(span["verbatim_text"])
    # Only these fields reach Codex: no question type, difficulty, split, notes or answers.
    return {
        "question_id": gold_row["question_id"],
        "question": gold_row["question"],
        "reference_answer": gold_row["gold_answer_text"],
        "evidence": evidence,
    }


def prepare(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    if run_dir.exists():
        raise SystemExit(f"{run_dir} already exists; use a new run directory")
    package = json.loads(args.profile.read_text(encoding="utf-8"))
    gold_rows = {row["question_id"]: row for row in read_jsonl(args.gold)}
    if args.question_ids:
        wanted = [
            line.strip() for line in args.question_ids.read_text(encoding="utf-8").splitlines()
        ]
        wanted = [question_id for question_id in wanted if question_id]
        unknown = sorted(set(wanted) - gold_rows.keys())
        if unknown:
            raise SystemExit(f"question IDs not in Gold: {unknown}")
    else:
        wanted = sorted(gold_rows)
    order = sorted(set(wanted))
    random.Random(args.seed).shuffle(order)
    batches = [order[i : i + args.batch_size] for i in range(0, len(order), args.batch_size)]

    workdir = run_dir / "workdir"
    (workdir / "input").mkdir(parents=True)
    (workdir / "output").mkdir()
    (run_dir / "prompts").mkdir()
    rules = (
        (HERE / "RULES.template.md")
        .read_text(encoding="utf-8")
        .replace("{{PROFILE_AND_CHECKLIST}}", render_profile_block(package))
        .replace("{{TERM_CONVENTION}}", args.term_convention.read_text(encoding="utf-8").strip())
    )
    (workdir / "RULES.md").write_text(rules, encoding="utf-8", newline="\n")
    shutil.copyfile(HERE / "output_schema.json", workdir / "output_schema.json")
    task_template = (HERE / "TASK_PROMPT.md").read_text(encoding="utf-8")
    batch_ids: list[str] = []
    for number, question_ids in enumerate(batches, start=1):
        batch_id = f"batch_{number:02d}"
        batch_ids.append(batch_id)
        write_jsonl(
            workdir / "input" / f"{batch_id}.jsonl", [input_row(gold_rows[q]) for q in question_ids]
        )
        (run_dir / "prompts" / f"{batch_id}.txt").write_text(
            task_template.replace("{{BATCH_ID}}", batch_id), encoding="utf-8", newline="\n"
        )
    manifest = {
        "schema_version": "1.0",
        "rules_template_sha256": sha256_file(HERE / "RULES.template.md"),
        "rules_rendered_sha256": sha256_file(workdir / "RULES.md"),
        "task_prompt_template_sha256": sha256_file(HERE / "TASK_PROMPT.md"),
        "output_schema_sha256": sha256_file(HERE / "output_schema.json"),
        "term_convention_sha256": sha256_file(args.term_convention),
        "profile_file_sha256": sha256_file(args.profile),
        "profile_package_sha256": package.get("package_sha256"),
        "profile_frozen": package.get("frozen"),
        "gold_sha256": sha256_file(args.gold),
        "seed": args.seed,
        "batch_size": args.batch_size,
        "batches": {batch_id: batch for batch_id, batch in zip(batch_ids, batches, strict=True)},
        "codex": {"model": None, "reasoning_effort": None, "cli_version": None},
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(order)} questions in {len(batches)} batches -> {run_dir}")
    if package.get("frozen") is not True:
        print("WARNING: profile package is not frozen; use this run as a pilot only")
    return 0


def validate(output: dict) -> list[str]:
    errors: list[str] = []
    if tuple(output) != FIELDS:
        errors.append(f"fields must be exactly {FIELDS} in order")
        if set(output) != set(FIELDS):
            return errors
    if output["question_demand"] not in DEMANDS:
        errors.append("invalid question_demand")
    if not str(output["intermediate_reference_answer"]).strip():
        errors.append("empty intermediate_reference_answer")
    for field, expected in CRITERIA.items():
        items = output[field]
        if (
            not isinstance(items, list)
            or tuple(item.get("criterion_id") for item in items) != expected
        ):
            errors.append(f"{field} must list {expected} in order")
            continue
        for item in items:
            criterion = item["criterion_id"]
            if list(item) != ["criterion_id", "note", "verdict"]:
                errors.append(f"{criterion}: keys must be criterion_id, note, verdict")
            if not str(item.get("note", "")).strip():
                errors.append(f"{criterion}: empty note")
            verdict = item.get("verdict")
            allowed = {"pass", "not_applicable"} if field == "intermediate_check" else VERDICTS
            if verdict not in allowed:
                errors.append(f"{criterion}: verdict {verdict!r} not allowed")
            if criterion in ALWAYS_ASSESSED and verdict == "not_applicable":
                errors.append(f"{criterion}: always assessed, cannot be not_applicable")
    if not isinstance(output["gold_answer_concern"], bool):
        errors.append("gold_answer_concern must be boolean")
    elif output["gold_answer_concern"] and not output["gold_answer_concern_note"]:
        errors.append("gold_answer_concern requires a note")
    elif not output["gold_answer_concern"] and output["gold_answer_concern_note"] is not None:
        errors.append("gold_answer_concern_note must be null when there is no concern")
    if not str(output["reason"]).strip():
        errors.append("empty reason")
    return errors


def map_label(output: dict) -> tuple[str, list[str]]:
    """Return the eligibility label and the reasons it needs human review."""

    def side(field: str) -> tuple[bool, bool]:
        verdicts = {item["verdict"] for item in output[field]}
        return "fail" in verdicts, "uncertain" in verdicts

    beginner_fail, beginner_uncertain = side("beginner_criteria")
    advanced_fail, advanced_uncertain = side("advanced_criteria")
    if beginner_fail and advanced_fail:
        label = "full"
    elif beginner_fail or advanced_fail or beginner_uncertain or advanced_uncertain:
        # Ties resolve to endpoint_only: doubtful questions stay in the main result
        # but out of the strict full subset.
        label = "endpoint_only"
    else:
        label = "none"
    review: list[str] = []
    if beginner_uncertain or advanced_uncertain:
        review.append("uncertain_verdict")
    if output["gold_answer_concern"]:
        review.append("gold_answer_concern")
    return label, review


def collect(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    problems: dict[str, list[str]] = {}
    sidecar: list[dict] = []
    review_rows: list[dict] = []
    for batch_id, expected_ids in manifest["batches"].items():
        path = run_dir / "workdir" / "output" / f"{batch_id}.jsonl"
        if not path.is_file():
            problems[batch_id] = ["missing output file"]
            continue
        try:
            outputs = read_jsonl(path)
        except json.JSONDecodeError as exc:
            problems[batch_id] = [f"invalid JSON: {exc}"]
            continue
        observed_ids = [output.get("question_id") for output in outputs]
        if observed_ids != expected_ids:
            problems[batch_id] = ["question_ids or their order differ from the input batch"]
            continue
        for output in outputs:
            errors = validate(output)
            if errors:
                problems[output["question_id"]] = errors
                continue
            label, review = map_label(output)
            sidecar.append(
                {
                    "schema_version": "1.0",
                    "question_id": output["question_id"],
                    "eligibility": label,
                    "reason": output["reason"],
                    "annotator_id": args.annotator_id,
                    "calibration_version": args.calibration_version,
                }
            )
            if review:
                review_rows.append(
                    {"question_id": output["question_id"], "eligibility": label, "review": review}
                )
    if problems:
        # A stale sidecar from an earlier successful collect must not survive a failed one.
        for name in ("eligibility_sidecar.jsonl", "needs_review.jsonl"):
            (run_dir / name).unlink(missing_ok=True)
        (run_dir / "collect_errors.json").write_text(
            json.dumps(problems, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{len(problems)} batches or questions failed validation; see collect_errors.json")
        return 1
    sidecar.sort(key=lambda row: row["question_id"])
    write_jsonl(run_dir / "eligibility_sidecar.jsonl", sidecar)
    write_jsonl(run_dir / "needs_review.jsonl", review_rows)
    counts = Counter(row["eligibility"] for row in sidecar)
    print(f"labels: {dict(sorted(counts.items()))}; needs review: {len(review_rows)}")
    print(f"eligibility_sidecar.jsonl sha256 {sha256_file(run_dir / 'eligibility_sidecar.jsonl')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--profile", required=True, type=Path)
    prep.add_argument("--term-convention", required=True, type=Path)
    prep.add_argument("--gold", required=True, type=Path)
    prep.add_argument("--run-dir", required=True, type=Path)
    prep.add_argument("--question-ids", type=Path)
    prep.add_argument("--batch-size", type=int, default=20)
    prep.add_argument("--seed", type=int, default=20261024)
    coll = commands.add_parser("collect")
    coll.add_argument("--run-dir", required=True, type=Path)
    coll.add_argument("--annotator-id", required=True)
    coll.add_argument("--calibration-version", required=True)
    args = parser.parse_args(argv)
    return prepare(args) if args.command == "prepare" else collect(args)


if __name__ == "__main__":
    sys.exit(main())
