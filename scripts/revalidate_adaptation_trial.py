"""Replay saved adaptation verdicts against a verified package, without API calls."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from cs30.evaluation.adaptation_applicability import always_assessed_ids
from cs30.evaluation.judge_runtime import validate_output_against_request
from cs30.evaluation.level_adaptation import build_adaptation_request, validate_adaptation_output
from cs30.evaluation.level_profiles import load_profile_checklist_package
from cs30.evaluation.v2_generation_models import (
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeRequest,
)


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def replay(root: Path, profiles_path: Path) -> dict:
    """Rebuild policy-bound validation contexts; do not rewrite old requests/scores."""
    package = load_profile_checklist_package(profiles_path)
    profiles = {profile.level.value: profile for profile in package.profiles}
    checklists = {checklist.level.value: checklist for checklist in package.checklists}
    rows = []
    hashes = {"profile_package": hashlib.sha256(profiles_path.read_bytes()).hexdigest()}
    for folder in sorted(root.glob("thinking-*")):
        level = folder.name.removeprefix("thinking-")
        config_path = folder / "judge-config.json"
        configuration = JudgeConfiguration.model_validate_json(
            config_path.read_text(encoding="utf-8")
        )
        for result_path in sorted((folder / "adaptation").glob("*-results.jsonl")):
            generator = result_path.name.removesuffix("-results.jsonl")
            request_path = result_path.with_name(generator + "-requests.jsonl")
            input_path = root / "subset" / generator / "inputs.jsonl"
            source_requests = {
                row["request_id"]: JudgeRequest.model_validate(row)
                for row in read_rows(request_path)
            }
            items = {
                (row["question"], row["answer"]): GenerationEvaluationInput.model_validate(row)
                for row in read_rows(input_path)
            }
            for path in (config_path, result_path, request_path, input_path):
                hashes[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
            for envelope in read_rows(result_path):
                original = source_requests[envelope["request_id"]]
                payload = original.payload
                item = items[(payload["question"], payload["answer"])]
                evaluated_level = payload["target_profile"]["level"]
                checklist = checklists[evaluated_level]
                bound = build_adaptation_request(
                    item,
                    profiles[evaluated_level],
                    checklist,
                    configuration,
                    evaluated_level=checklist.level,
                    criterion_order=[row["criterion_id"] for row in payload["checklist"]],
                    profile_package=package,
                )
                # This must be the same historical task, plus the explicit policy binding.
                comparison = dict(bound.payload)
                comparison.pop("applicability_policy")
                if comparison != payload:
                    raise ValueError("historical request differs from the supplied frozen package")
                raw = copy.deepcopy(envelope.get("output") or envelope.get("raw_output"))
                always = always_assessed_ids(bound)
                violations = [
                    row["criterion_id"]
                    for row in (raw or {}).get("criteria", [])
                    if row["criterion_id"] in always and row["verdict"] == "not_applicable"
                ]
                error = None
                try:
                    if raw is None:
                        raise ValueError("saved result has no output")
                    # The probe has a new request ID because the policy is now input-bound.
                    raw["request_id"] = bound.request_id
                    validate_output_against_request(raw, bound)
                    validate_adaptation_output(
                        raw, request=bound, answer=item.answer or "", checklist=checklist
                    )
                except ValueError as exc:
                    error = str(exc)
                rows.append(
                    {
                        "thinking_level": level,
                        "generator": generator,
                        "source_request_id": original.request_id,
                        "validation_request_id": bound.request_id,
                        "question_id": item.question_id,
                        "evaluated_level": evaluated_level,
                        "always_assessed_verdicts": len(always),
                        "invalid_not_applicable_ids": violations,
                        "would_be_rejected": error is not None,
                        "error": error,
                    }
                )
    if not rows:
        raise ValueError("no saved adaptation outputs found")
    summary = {}
    for level in sorted({row["thinking_level"] for row in rows}):
        subset = [row for row in rows if row["thinking_level"] == level]
        summary[level] = {
            "requests": len(subset),
            "would_be_rejected": sum(row["would_be_rejected"] for row in subset),
            "always_assessed_verdicts": sum(row["always_assessed_verdicts"] for row in subset),
            "invalid_verdicts": dict(
                Counter(
                    criterion for row in subset for criterion in row["invalid_not_applicable_ids"]
                )
            ),
        }
    return {
        "profile_package_sha256": package.package_sha256,
        "api_calls": 0,
        "new_cost_usd": 0,
        "retry_calls": 0,
        "summary": summary,
        "source_hashes": hashes,
        "results": rows,
        "note": "Offline validation only. Original verdicts, request files and scores unchanged.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root, out = args.trial_root.resolve(), args.out.resolve()
    if out == root or root in out.parents:
        parser.error("use a new output directory outside the original trial")
    report = replay(root, args.profiles)
    out.mkdir(parents=True, exist_ok=False)
    (out / "replay.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Offline adaptation applicability replay", "", "No API calls or retry calls.", ""]
    for level, values in report["summary"].items():
        lines.append(
            f"- {level}: {values['would_be_rejected']}/{values['requests']} requests rejected; "
            f"{values['always_assessed_verdicts']} always-assessed verdicts checked; "
            f"violations {values['invalid_verdicts']}."
        )
    lines += [
        "",
        "Rejected outputs would enter the existing live retry path. "
        "No verdict is changed here; the saved trial remains historical evidence.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
