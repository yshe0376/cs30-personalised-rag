"""Command-line entry points for the M8 V2 generation evaluation extension."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cs30.contracts import StudentLevel

from .condition_statistics import MetricObservation, paired_condition_contrasts
from .evaluation_audit import (
    HumanAuditRating,
    prepare_calibration_and_audit,
    summarize_human_audit,
)
from .evidence_support import build_evidence_support_request
from .judge_results import (
    assemble_judge_results,
    grouped_mean,
    load_judge_envelopes,
    load_judge_evaluation_outputs,
    summarize_discrimination_rows,
    write_judge_evaluation_outputs,
)
from .judge_runtime import write_judge_requests
from .judge_validity import ValidityThresholds, build_validity_report
from .level_adaptation import (
    adaptation_evaluation_levels,
    aggregate_adaptation,
    apply_adaptation_threshold,
    build_adaptation_request,
)
from .level_discrimination import build_discrimination_request
from .level_profiles import load_eligibility_package, load_profile_checklist_package
from .v2_generation_artifacts import (
    adapt_m7_generation_artifacts,
    load_open_answer_scores,
    write_adapter_outputs,
)
from .v2_generation_models import (
    EvaluationDecisionConfig,
    EvaluationMode,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeTask,
    LevelGuess,
)
from .v2_generation_reporting import (
    answer_text_diagnostics,
    build_v2_generation_report,
    generation_noise_floor,
    joint_correct_and_adapted_summary,
    preferred_role_share,
    strict_correctness_summary,
    write_v2_generation_report,
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
    parser = argparse.ArgumentParser(
        prog="cs30-v2-generation-eval",
        description=(
            "Evaluate saved V2 generation artifacts. The legacy "
            "cs30-evaluate report-extension command remains V1-only."
        ),
    )
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

    adapt = commands.add_parser("adapt-m7-artifacts")
    adapt.add_argument("--expected-experiment", required=True, type=Path)
    adapt.add_argument("--generation-records", required=True, type=Path)
    adapt.add_argument("--saved-answers", required=True, type=Path)
    adapt.add_argument("--run-manifest", required=True, type=Path)
    adapt.add_argument("--gold", required=True, type=Path)
    adapt.add_argument("--eligibility", required=True, type=Path)
    adapt.add_argument("--lambda-selection", required=True, type=Path)
    adapt.add_argument("--output-dir", required=True, type=Path)

    assemble = commands.add_parser("assemble-judge-results")
    assemble.add_argument("--inputs", required=True, type=Path)
    assemble.add_argument("--profiles", required=True, type=Path)
    assemble.add_argument("--judge-config", required=True, type=Path)
    assemble.add_argument("--judge-results", required=True, type=Path)
    assemble.add_argument("--cross-level-evaluation-ids", type=Path)
    assemble.add_argument(
        "--mode",
        choices=[mode.value for mode in EvaluationMode],
        default=EvaluationMode.DEVELOPMENT.value,
    )
    assemble.add_argument("--output-dir", required=True, type=Path)

    validity = commands.add_parser("validity-report")
    validity.add_argument("--observations", required=True, type=Path)
    validity.add_argument("--output", required=True, type=Path)

    development = commands.add_parser("development-report")
    development.add_argument("--inputs", required=True, type=Path)
    development.add_argument("--adapter-manifest", required=True, type=Path)
    development.add_argument("--correctness-scores", type=Path)
    development.add_argument("--judge-evaluation-dir", type=Path)
    development.add_argument("--validity-report", type=Path)
    development.add_argument("--human-audit-ratings", type=Path)
    development.add_argument("--decision-config", type=Path)
    development.add_argument("--output-dir", required=True, type=Path)
    development.add_argument("--bootstrap-draws", type=int, default=2000)
    development.add_argument("--bootstrap-seed", type=int, default=5703)
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
        if item.technical_failure or item.abstained:
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


def _adapt_m7_artifacts(args: argparse.Namespace) -> int:
    items, manifest = adapt_m7_generation_artifacts(
        expected_path=args.expected_experiment,
        records_path=args.generation_records,
        answers_path=args.saved_answers,
        run_manifest_path=args.run_manifest,
        gold_path=args.gold,
        eligibility_path=args.eligibility,
        lambda_selection_path=args.lambda_selection,
    )
    write_adapter_outputs(items, manifest, args.output_dir)
    return 0


def _assemble_judge_results(args: argparse.Namespace) -> int:
    items = _load_inputs(args.inputs)
    package = load_profile_checklist_package(args.profiles)
    try:
        configuration = JudgeConfiguration.model_validate_json(
            args.judge_config.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"{args.judge_config}: invalid judge configuration: {exc}") from exc
    cross_level_ids = frozenset()
    if args.cross_level_evaluation_ids is not None:
        cross_level_ids = frozenset(
            line.strip()
            for line in args.cross_level_evaluation_ids.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        unknown = sorted(cross_level_ids - {item.evaluation_id for item in items})
        if unknown:
            raise ValueError(f"cross-level file references unknown evaluation IDs: {unknown}")
    result = assemble_judge_results(
        items,
        package,
        configuration,
        load_judge_envelopes(args.judge_results),
        cross_level_evaluation_ids=cross_level_ids,
        mode=EvaluationMode(args.mode),
    )
    write_judge_evaluation_outputs(
        result,
        args.output_dir,
        provenance={
            "evaluation_inputs_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
            "profile_package_sha256": package.package_sha256,
            "judge_configuration_sha256": hashlib.sha256(
                args.judge_config.read_bytes()
            ).hexdigest(),
            "judge_config_version": configuration.config_version,
            "judge_results_sha256": hashlib.sha256(args.judge_results.read_bytes()).hexdigest(),
            "cross_level_ids_sha256": (
                hashlib.sha256(args.cross_level_evaluation_ids.read_bytes()).hexdigest()
                if args.cross_level_evaluation_ids is not None
                else None
            ),
            "mode": args.mode,
        },
    )
    return 0


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected one JSON object")
    return value


def _validity_report(args: argparse.Namespace) -> int:
    payload = _load_json_object(args.observations)
    try:
        thresholds = ValidityThresholds.model_validate(payload["thresholds"])
        report = build_validity_report(
            thresholds,
            p0r0_guesses=[LevelGuess(value) for value in payload.get("p0r0_guesses", [])],
            duplicate_rows=[tuple(row) for row in payload.get("duplicate_rows", [])],
            surface_rows=[
                (StudentLevel(row[0]), bool(row[1]), int(row[2]), bool(row[3]))
                for row in payload.get("surface_rows", [])
            ],
            order_pairs=[tuple(row) for row in payload.get("order_pairs", [])],
            second_judge_pairs=[tuple(row) for row in payload.get("second_judge_pairs", [])],
            perturbation_detections=[
                bool(value) for value in payload.get("perturbation_detections", [])
            ],
            require_perturbation=bool(payload.get("require_perturbation", False)),
        )
    except (KeyError, TypeError, ValidationError) as exc:
        raise ValueError(f"{args.observations}: invalid validity observations: {exc}") from exc
    _write_json(args.output, report)
    return 0


def _applicability_summary(
    items: list[GenerationEvaluationInput],
    correctness_by_id: dict[str, int | None],
    adaptation_by_id: dict[str, float | None],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[GenerationEvaluationInput]] = defaultdict(list)
    for item in items:
        groups[(item.eligibility.value, item.condition.value)].append(item)
    result = []
    for (eligibility, condition), rows in sorted(groups.items()):
        correctness = [
            correctness_by_id[item.evaluation_id]
            for item in rows
            if correctness_by_id.get(item.evaluation_id) is not None
        ]
        adaptation = [
            adaptation_by_id[item.evaluation_id]
            for item in rows
            if adaptation_by_id.get(item.evaluation_id) is not None
        ]
        result.append(
            {
                "eligibility": eligibility,
                "condition": condition,
                "answer_count": len(rows),
                "technical_failure_count": sum(item.technical_failure for item in rows),
                "correctness_scored_count": len(correctness),
                "strict_correct_rate": (
                    sum(score == 2 for score in correctness) / len(correctness)
                    if correctness
                    else None
                ),
                "adaptation_evaluable_count": len(adaptation),
                "mean_adaptation_criterion_pass_rate": (
                    sum(adaptation) / len(adaptation) if adaptation else None
                ),
            }
        )
    return result


def _evidence_support_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("eligibility", "condition")
    bundle = grouped_mean(rows, "bundle_faithfulness", fields)
    citation = grouped_mean(rows, "citation_support", fields)
    citation_by_key = {tuple(str(row[field]) for field in fields): row for row in citation}
    result = []
    for row in bundle:
        key = tuple(str(row[field]) for field in fields)
        other = citation_by_key[key]
        result.append(
            {
                **row,
                "citation_evaluable_count": other["evaluable_count"],
                "mean_citation_support": other["mean_citation_support"],
            }
        )
    return result


def _development_report(args: argparse.Namespace) -> int:
    items = _load_inputs(args.inputs)
    manifest = json.loads(args.adapter_manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("adapter manifest must contain one JSON object")
    expected_inputs_hash = manifest.get("output_sha256", {}).get("generation_evaluation_inputs")
    actual_inputs_hash = hashlib.sha256(args.inputs.read_bytes()).hexdigest()
    if expected_inputs_hash != actual_inputs_hash:
        raise ValueError("evaluation inputs do not match the adapter manifest hash")
    source_run_hash = manifest.get("source_run_sha256")
    if source_run_hash is None or any(item.source_run_sha256 != source_run_hash for item in items):
        raise ValueError("evaluation inputs do not match the adapter source run")
    decision_config = EvaluationDecisionConfig(decision_version="development-unfrozen")
    if args.decision_config is not None:
        try:
            decision_config = EvaluationDecisionConfig.model_validate_json(
                args.decision_config.read_text(encoding="utf-8")
            )
        except ValidationError as exc:
            raise ValueError(f"{args.decision_config}: invalid decision config: {exc}") from exc
        selected_lambda = manifest.get("lambda_selection", {}).get("selected_lambda")
        lambda_artifact_hash = manifest.get("input_sha256", {}).get("lambda_selection")
        if decision_config.selected_lambda != selected_lambda:
            raise ValueError("decision config selected_lambda differs from adapter manifest")
        if decision_config.lambda_selection_artifact_sha256 != lambda_artifact_hash:
            raise ValueError("decision config lambda-selection hash differs from adapter manifest")
    scores = {}
    if args.correctness_scores is not None:
        scores = load_open_answer_scores(
            args.correctness_scores,
            items,
            gold_sha256=str(manifest["gold_sha256"]),
        )
    correctness_rows = []
    correctness_by_id: dict[str, int | None] = {}
    observations = []
    unresolved = []
    for item in items:
        score = scores.get(item.evaluation_id)
        numeric = score.score if score and score.score_status == "scored" else None
        correctness_by_id[item.evaluation_id] = numeric
        correctness_rows.append(
            {
                "technical_failure": item.technical_failure,
                "correctness_score": numeric,
            }
        )
        if numeric is not None:
            observations.append(
                MetricObservation(
                    question_id=item.question_id,
                    target_level=item.target_level,
                    condition=item.condition,
                    metric="strict_correct",
                    value=float(numeric == 2),
                )
            )
        if score is None or score.score_status != "scored":
            unresolved.append(
                {
                    "evaluation_id": item.evaluation_id,
                    "dimension": "correctness",
                    "reason": "score not supplied" if score is None else score.score_status,
                }
            )
    judge_data: dict[str, Any] | None = None
    if args.judge_evaluation_dir is not None:
        judge_data = load_judge_evaluation_outputs(args.judge_evaluation_dir)
        unresolved.extend(judge_data["unresolved"])
    else:
        unresolved.extend(
            {
                "evaluation_id": item.evaluation_id,
                "dimension": dimension,
                "reason": "judge output not supplied",
            }
            for item in items
            if not item.technical_failure and not item.abstained
            for dimension in ("adaptation", "discrimination", "evidence_support")
        )

    adaptation_records = list(judge_data["adaptation"]) if judge_data else []
    if decision_config.adaptation_pass_threshold is not None:
        adaptation_records = [
            apply_adaptation_threshold(record, threshold=decision_config.adaptation_pass_threshold)
            for record in adaptation_records
        ]
    target_adaptation = {
        str(record["evaluation_id"]): record
        for record in adaptation_records
        if record.get("is_target_level_evaluation")
    }
    adaptation_by_id = {
        evaluation_id: (
            float(record["criterion_pass_rate"])
            if record.get("criterion_pass_rate") is not None
            else None
        )
        for evaluation_id, record in target_adaptation.items()
    }
    discrimination_rows = list(judge_data["discrimination"]) if judge_data else []
    evidence_rows = list(judge_data["evidence_support"]) if judge_data else []
    for item in items:
        adaptation = target_adaptation.get(item.evaluation_id)
        if adaptation and adaptation.get("criterion_pass_rate") is not None:
            observations.append(
                MetricObservation(
                    question_id=item.question_id,
                    target_level=item.target_level,
                    condition=item.condition,
                    metric="adaptation_criterion_pass_rate",
                    value=float(adaptation["criterion_pass_rate"]),
                )
            )
    for row in evidence_rows:
        item = next(item for item in items if item.evaluation_id == row["evaluation_id"])
        for metric in ("bundle_faithfulness", "citation_support"):
            if row.get(metric) is not None:
                observations.append(
                    MetricObservation(
                        question_id=item.question_id,
                        target_level=item.target_level,
                        condition=item.condition,
                        metric=metric,
                        value=float(row[metric]),
                    )
                )
    contrasts = []
    if observations:
        contrasts = paired_condition_contrasts(
            observations,
            bootstrap_draws=args.bootstrap_draws,
            bootstrap_seed=args.bootstrap_seed,
        )
    validity = (
        _load_json_object(args.validity_report)
        if args.validity_report is not None
        else {"formal_use_allowed": False, "reason": "judge validation not supplied"}
    )
    if args.decision_config is not None and args.validity_report is not None:
        if validity.get("threshold_version") != decision_config.validity_threshold_version:
            raise ValueError("validity threshold version differs from decision config")
    if args.decision_config is not None and judge_data is not None:
        judge_version = judge_data["manifest"].get("provenance", {}).get("judge_config_version")
        if judge_version != decision_config.judge_config_version:
            raise ValueError("judge configuration version differs from decision config")
    human_audit = None
    if args.human_audit_ratings is not None:
        try:
            ratings = [
                HumanAuditRating.model_validate(row)
                for row in _read_jsonl(args.human_audit_ratings)
            ]
        except ValidationError as exc:
            raise ValueError(f"{args.human_audit_ratings}: invalid audit rating: {exc}") from exc
        human_audit = summarize_human_audit(ratings)
    joint_rows = [
        {
            "correctness_score": correctness_by_id.get(item.evaluation_id),
            "adaptation_passed": target_adaptation.get(item.evaluation_id, {}).get(
                "adaptation_passed"
            ),
        }
        for item in items
    ]
    report = build_v2_generation_report(
        mode=EvaluationMode.DEVELOPMENT,
        decision_config=decision_config,
        correctness=strict_correctness_summary(correctness_rows),
        adaptation=aggregate_adaptation(
            [record for record in adaptation_records if record.get("enters_main_adaptation_result")]
        ),
        discrimination=(
            summarize_discrimination_rows(discrimination_rows) if discrimination_rows else {}
        ),
        evidence_support=_evidence_support_summary(evidence_rows),
        mechanism_diagnostics=[
            preferred_role_share(item.evidence, item.target_level)
            | {"evaluation_id": item.evaluation_id}
            for item in items
        ],
        text_diagnostics=[
            answer_text_diagnostics(item.answer) | {"evaluation_id": item.evaluation_id}
            for item in items
            if item.answer is not None
        ],
        validity=validity,
        human_audit=human_audit,
        condition_contrasts=contrasts,
        lambda_evaluation=manifest.get("lambda_selection"),
        generation_noise=generation_noise_floor(items),
        applicability_summary=_applicability_summary(items, correctness_by_id, adaptation_by_id),
        joint_correct_and_adapted=joint_correct_and_adapted_summary(joint_rows),
        unresolved_items=unresolved,
        provenance={
            "adapter_manifest": manifest,
            "evaluation_inputs_sha256": actual_inputs_hash,
            "correctness_scores_sha256": (
                hashlib.sha256(args.correctness_scores.read_bytes()).hexdigest()
                if args.correctness_scores is not None
                else None
            ),
            "correctness_rubric_sha256_values": sorted(
                {
                    score.rubric_sha256
                    for score in scores.values()
                    if score.rubric_sha256 is not None
                }
            ),
            "correctness_judge_config_sha256_values": sorted(
                {
                    score.judge_config_sha256
                    for score in scores.values()
                    if score.judge_config_sha256 is not None
                }
            ),
            "judge_evaluation_manifest": (
                judge_data["manifest"] if judge_data is not None else None
            ),
            "validity_report_sha256": (
                hashlib.sha256(args.validity_report.read_bytes()).hexdigest()
                if args.validity_report is not None
                else None
            ),
            "human_audit_ratings_sha256": (
                hashlib.sha256(args.human_audit_ratings.read_bytes()).hexdigest()
                if args.human_audit_ratings is not None
                else None
            ),
            "decision_config_sha256": (
                hashlib.sha256(args.decision_config.read_bytes()).hexdigest()
                if args.decision_config is not None
                else None
            ),
        },
    )
    write_v2_generation_report(report, args.output_dir)
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
        if args.command == "adapt-m7-artifacts":
            return _adapt_m7_artifacts(args)
        if args.command == "assemble-judge-results":
            return _assemble_judge_results(args)
        if args.command == "validity-report":
            return _validity_report(args)
        if args.command == "development-report":
            return _development_report(args)
    except (FileNotFoundError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
