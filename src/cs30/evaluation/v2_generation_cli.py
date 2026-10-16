"""Command-line entry points for the M8 V2 generation evaluation extension."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .condition_statistics import MetricObservation, paired_condition_contrasts
from .evaluation_audit import prepare_calibration_and_audit
from .evidence_support import build_evidence_support_request
from .judge_runtime import write_judge_requests
from .level_adaptation import adaptation_evaluation_levels, build_adaptation_request
from .level_discrimination import build_discrimination_request
from .level_profiles import load_eligibility_package, load_profile_checklist_package
from .v2_generation_models import (
    EvaluationMode,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeTask,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def _load_inputs(path: Path) -> list[GenerationEvaluationInput]:
    try:
        rows = [GenerationEvaluationInput.model_validate(row) for row in _read_jsonl(path)]
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid generation-evaluation input: {exc}") from exc
    evaluation_ids = [row.evaluation_id for row in rows]
    if len(evaluation_ids) != len(set(evaluation_ids)):
        raise ValueError(f"{path}: duplicate evaluation_id values")
    return rows


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cs30-v2-generation-eval")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-inputs")
    validate.add_argument("--profiles", required=True, type=Path)
    validate.add_argument("--eligibility", required=True, type=Path)
    validate.add_argument("--gold", required=True, type=Path)
    validate.add_argument("--gold-version", required=True)
    validate.add_argument("--eligibility-version", required=True)
    validate.add_argument("--eligibility-calibration-count", required=True, type=int)
    validate.add_argument("--calibrated-with-leader", required=True, action="store_true")
    validate.add_argument(
        "--labels-created-without-model-answers",
        required=True,
        action="store_true",
    )
    validate.add_argument("--reportable", action="store_true")
    validate.add_argument("--output", required=True, type=Path)

    prepare = commands.add_parser("prepare-judge-requests")
    prepare.add_argument("--inputs", required=True, type=Path)
    prepare.add_argument("--profiles", required=True, type=Path)
    prepare.add_argument("--judge-config", required=True, type=Path)
    prepare.add_argument("--task", required=True, choices=[task.value for task in JudgeTask])
    prepare.add_argument(
        "--cross-level-evaluation-ids",
        type=Path,
        help=(
            "optional text file with one personalised evaluation_id per line to assess "
            "against all three checklists; P0R0 is always assessed against all three"
        ),
    )
    prepare.add_argument(
        "--mode",
        choices=[mode.value for mode in EvaluationMode],
        default=EvaluationMode.DEVELOPMENT.value,
    )
    prepare.add_argument("--output", required=True, type=Path)

    stats = commands.add_parser("condition-stats")
    stats.add_argument("--observations", required=True, type=Path)
    stats.add_argument("--bootstrap-draws", type=int, default=2000)
    stats.add_argument("--bootstrap-seed", type=int, default=5703)
    stats.add_argument("--output", required=True, type=Path)

    audit = commands.add_parser("prepare-audit")
    audit.add_argument("--inputs", required=True, type=Path)
    audit.add_argument("--output-dir", required=True, type=Path)
    audit.add_argument("--calibration-size", type=int, default=10)
    audit.add_argument("--audit-size", type=int, default=20)
    audit.add_argument("--seed", type=int, default=5703)
    return parser


def _validate_inputs(args: argparse.Namespace) -> int:
    profiles = load_profile_checklist_package(args.profiles)
    gold_bytes = args.gold.read_bytes()
    gold_sha256 = hashlib.sha256(gold_bytes).hexdigest()
    question_ids = [str(row["question_id"]) for row in _read_jsonl(args.gold)]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("Gold contains duplicate question_id values")
    eligibility = load_eligibility_package(
        args.eligibility,
        package_version=args.eligibility_version,
        gold_version=args.gold_version,
        gold_sha256=gold_sha256,
        calibration_question_count=args.eligibility_calibration_count,
        calibrated_with_leader=args.calibrated_with_leader,
        labels_created_without_model_answers=args.labels_created_without_model_answers,
        expected_question_ids=question_ids,
        require_resolved=args.reportable,
    )
    _write_json(
        args.output,
        {
            "schema_version": "1.0",
            "profile_package_version": profiles.package_version,
            "profile_package_sha256": profiles.package_sha256,
            "eligibility_package_version": eligibility.package_version,
            "gold_version": eligibility.gold_version,
            "gold_sha256": eligibility.gold_sha256,
            "question_count": len(question_ids),
            "reportable_input_validation": bool(args.reportable),
            "valid": True,
        },
    )
    return 0


def _prepare_requests(args: argparse.Namespace) -> int:
    items = _load_inputs(args.inputs)
    package = load_profile_checklist_package(args.profiles)
    try:
        configuration = JudgeConfiguration.model_validate_json(
            args.judge_config.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"{args.judge_config}: invalid judge configuration: {exc}") from exc
    profiles = {profile.level: profile for profile in package.profiles}
    checklists = {checklist.level: checklist for checklist in package.checklists}
    task = JudgeTask(args.task)
    mode = EvaluationMode(args.mode)
    cross_level_ids = set()
    if args.cross_level_evaluation_ids is not None:
        cross_level_ids = {
            line.strip()
            for line in args.cross_level_evaluation_ids.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        known_ids = {item.evaluation_id for item in items}
        unknown_ids = sorted(cross_level_ids - known_ids)
        if unknown_ids:
            raise ValueError(f"cross-level file references unknown evaluation IDs: {unknown_ids}")
    requests = {}
    for item in items:
        if item.technical_failure:
            continue
        if task is JudgeTask.ADAPTATION:
            evaluated_levels = adaptation_evaluation_levels(
                item,
                cross_level_evaluation_ids=frozenset(cross_level_ids),
            )
            for evaluated_level in evaluated_levels:
                request = build_adaptation_request(
                    item,
                    profiles[evaluated_level],
                    checklists[evaluated_level],
                    configuration,
                    evaluated_level=evaluated_level,
                    mode=mode,
                )
                requests.setdefault(request.request_id, request)
            continue
        elif task is JudgeTask.DISCRIMINATION:
            request = build_discrimination_request(
                item,
                package.profiles,
                configuration,
                mode=mode,
            )
        else:
            request = build_evidence_support_request(item, configuration, mode=mode)
        requests.setdefault(request.request_id, request)
    write_judge_requests(list(requests.values()), args.output)
    return 0


def _condition_stats(args: argparse.Namespace) -> int:
    try:
        observations = [
            MetricObservation.model_validate(row) for row in _read_jsonl(args.observations)
        ]
    except ValidationError as exc:
        raise ValueError(f"{args.observations}: invalid metric observation: {exc}") from exc
    result = paired_condition_contrasts(
        observations,
        bootstrap_draws=args.bootstrap_draws,
        bootstrap_seed=args.bootstrap_seed,
    )
    _write_json(args.output, {"schema_version": "1.0", "contrasts": result})
    return 0


def _prepare_audit(args: argparse.Namespace) -> int:
    prepare_calibration_and_audit(
        _load_inputs(args.inputs),
        args.output_dir,
        calibration_size=args.calibration_size,
        audit_size=args.audit_size,
        seed=args.seed,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-inputs":
            return _validate_inputs(args)
        if args.command == "prepare-judge-requests":
            return _prepare_requests(args)
        if args.command == "condition-stats":
            return _condition_stats(args)
        if args.command == "prepare-audit":
            return _prepare_audit(args)
    except (FileNotFoundError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
