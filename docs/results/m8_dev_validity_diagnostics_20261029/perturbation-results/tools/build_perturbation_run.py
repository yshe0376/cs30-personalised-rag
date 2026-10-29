"""Build the offline inputs for the approved 18-case perturbation audit (step 5).

No API key, no provider call. Writes a new folder only; refuses to overwrite.
Usage:
  python build_perturbation_run.py --repo REPO --scoring-package HANDOFF_DIR \
      --m7-dev-artifacts M7_ARTIFACTS_DIR --out NEW_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

CASES_REL = "docs/results/m8_dev_validity_diagnostics_20261029/perturbation-draft/cases.draft.jsonl"
CURATED_REL = (
    "docs/results/m8_dev_validity_diagnostics_20261029/perturbation-draft/curated_edits.v2.json"
)
RUBRICS_REL = "eval_inputs/m8/correctness-dev-rubrics-v0.1/rubrics.draft.jsonl"
EXPECTED_CURATED_SHA = "89799c12f5a1388eab4220d0835a1639fe9e19f5e6b6ea07d024253032c1a8ea"
EXPECTED_RUBRICS_SHA = "acd5ae48672abe0d2ef9849c042f1f7222263a94bfb027c71e79c57d3faf9f97"
EXPECTED_GOLD_SHA = "235c92a15c14ef0416ac2ad262628c5876b9ebdde03c7f51438d10536a2509d5"
JUDGE_TASKS = ("adaptation", "discrimination", "evidence_support")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path: Path, values: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--scoring-package", type=Path, required=True)
    parser.add_argument("--m7-dev-artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo, package, m7, out = (
        p.resolve() for p in (args.repo, args.scoring_package, args.m7_dev_artifacts, args.out)
    )
    if out.exists():
        raise SystemExit(f"{out} already exists; refusing to overwrite")
    sys.path.insert(0, str(repo / "src"))
    from cs30.evaluation import v2_generation_cli as cli
    from cs30.evaluation.open_answer_models import OpenAnswerExperiment, OpenAnswerRun
    from cs30.evaluation.v2_generation_models import GenerationEvaluationInput

    if sha(repo / CURATED_REL) != EXPECTED_CURATED_SHA:
        raise SystemExit("curated edit spec differs from the reviewed version in #220")
    if sha(repo / RUBRICS_REL) != EXPECTED_RUBRICS_SHA:
        raise SystemExit("Dev correctness rubrics differ from those used in full-Dev scoring")
    cases = rows(repo / CASES_REL)
    if len(cases) != 18 or len({c["case_id"] for c in cases}) != 18:
        raise SystemExit("expected 18 unique perturbation cases")

    manifest = json.loads((package / "handoff_manifest.json").read_text(encoding="utf-8"))
    batch_inputs = {b["batch"]: package / b["inputs"] for b in manifest["batches"]}
    items_by_batch = {
        name: {r["evaluation_id"]: r for r in rows(path)} for name, path in batch_inputs.items()
    }

    run_dirs = {}
    for run_dir in m7.glob("dev-*-run"):
        for r in rows(run_dir / "saved_answers.jsonl"):
            run_dirs[r["run_id"]] = (run_dir, r)
    gold_path = m7 / "converted" / "gold.jsonl"
    if sha(gold_path) != EXPECTED_GOLD_SHA:
        raise SystemExit("Gold differs from the full-Dev Gold")

    out.mkdir(parents=True)
    for sub in ("inputs", "requests", "correctness", "config"):
        (out / sub).mkdir()
    shutil.copy2(package / "judge-config.low.json", out / "config" / "judge-config.low.json")
    shutil.copy2(
        package / "profile_checklist.frozen.json", out / "config" / "profile_checklist.frozen.json"
    )
    shutil.copy2(gold_path, out / "correctness" / "gold.jsonl")
    shutil.copy2(repo / RUBRICS_REL, out / "correctness" / "rubrics.draft.jsonl")

    perturbed_inputs, saved_answers, expected_cases, case_map = [], [], [], []
    for case in cases:
        base = items_by_batch[case["source_batch"]][case["base_evaluation_id"]]
        if base["answer"] != case["original_answer"]:
            raise SystemExit(f"{case['case_id']}: original answer differs from the Dev input")
        perturbed = case["perturbed_answer"]
        if sha_bytes(perturbed.encode("utf-8")) != case["perturbed_answer_sha256"]:
            raise SystemExit(f"{case['case_id']}: perturbed answer hash mismatch")
        if sha_bytes(base["answer"].encode("utf-8")) != case["original_answer_sha256"]:
            raise SystemExit(f"{case['case_id']}: original answer hash mismatch")
        new_eval_id = "evaluation-" + case["case_id"]
        new_run_id = case["case_id"]
        item = dict(base)
        item.update(
            evaluation_id=new_eval_id,
            run_id=new_run_id,
            answer=perturbed,
            answer_sha256=case["perturbed_answer_sha256"],
        )
        GenerationEvaluationInput.model_validate(item)
        perturbed_inputs.append(item)

        run_dir, saved = run_dirs[base["run_id"]]
        if saved["answer"]["explanation"] != base["answer"]:
            raise SystemExit(f"{case['case_id']}: saved answer text differs from the Dev input")
        new_saved = json.loads(json.dumps(saved))
        new_saved["run_id"] = new_run_id
        new_saved["answer"]["explanation"] = perturbed
        OpenAnswerRun.model_validate(new_saved)
        saved_answers.append(new_saved)
        expected_cases.append(
            {
                k: new_saved[k]
                for k in (
                    "run_id",
                    "question_id",
                    "condition_id",
                    "student_level",
                    "generator_model",
                )
            }
        )
        case_map.append(
            {
                "case_id": case["case_id"],
                "target": case["target"],
                "generator": case["generator"],
                "difficulty_proposal": case.get("difficulty_proposal"),
                "source_batch": case["source_batch"],
                "base_evaluation_id": base["evaluation_id"],
                "base_run_id": base["run_id"],
                "perturbed_evaluation_id": new_eval_id,
                "perturbed_run_id": new_run_id,
                "target_level": base["target_level"],
                "condition": base["condition"],
                "original_answer_sha256": case["original_answer_sha256"],
                "perturbed_answer_sha256": case["perturbed_answer_sha256"],
                "source_m7_run_dir": run_dir.name,
            }
        )

    inputs_path = out / "inputs" / "perturbed_generation_evaluation_inputs.jsonl"
    write_jsonl(inputs_path, perturbed_inputs)
    cli._load_inputs(inputs_path)  # production reader must accept the file

    for task in JUDGE_TASKS:
        code = cli.main(
            [
                "prepare-judge-requests",
                "--inputs",
                str(inputs_path),
                "--profiles",
                str(out / "config" / "profile_checklist.frozen.json"),
                "--judge-config",
                str(out / "config" / "judge-config.low.json"),
                "--task",
                task,
                "--output",
                str(out / "requests" / f"{task}.requests.jsonl"),
            ]
        )
        if code not in (0, None):
            raise SystemExit(f"prepare-judge-requests failed for {task}: {code}")

    write_jsonl(out / "correctness" / "saved_answers.perturbed.jsonl", saved_answers)
    experiment = {
        "schema_version": "0.2",
        "matrix_version": "m8-perturbation-small-v2",
        "gold_sha256": EXPECTED_GOLD_SHA,
        "cases": expected_cases,
    }
    OpenAnswerExperiment.model_validate(experiment)
    write_json(out / "correctness" / "expected_experiment.perturbed.json", experiment)
    write_json(out / "case_map.json", case_map)

    request_counts = {
        task: len(rows(out / "requests" / f"{task}.requests.jsonl")) for task in JUDGE_TASKS
    }
    request_counts["correctness"] = len(saved_answers)
    files = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    write_json(
        out / "BUILD_MANIFEST.json",
        {
            "purpose": "M8 small perturbation audit, step 5 inputs (Dev-only synthetic answers)",
            "repo_commit_expected": (
                "45f53c2 (main after #220) or later with identical evaluation source"
            ),
            "curated_edits_sha256": EXPECTED_CURATED_SHA,
            "cases": 18,
            "request_counts": request_counts,
            "judge_settings": (
                "unchanged full-Dev configuration: gemini-3.1-flash-lite, thinking low, "
                "same prompts/profile/rubrics"
            ),
            "isolation": (
                "new evaluation/run IDs, fresh caches, separate results and attempt logs; "
                "no score enters primary Dev/Test"
            ),
            "paid_calls_during_build": 0,
            "files_sha256": files,
        },
    )
    print(json.dumps({"out": str(out), "request_counts": request_counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
