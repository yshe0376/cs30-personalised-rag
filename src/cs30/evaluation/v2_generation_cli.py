"""Command-line entry points for the M8 V2 generation evaluation extension."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cs30.contracts import StudentLevel
from cs30.generation.client import OllamaChatClient, OpenAIResponsesClient

from .adaptation_applicability import always_assessed_ids
from .condition_statistics import CONTRASTS, MetricObservation, paired_condition_contrasts
from .evaluation_audit import (
    load_bound_human_audit,
    prepare_calibration_and_audit,
)
from .evidence_support import build_evidence_support_request
from .gemini_judge_client import GeminiJudgeClient
from .judge_results import (
    assemble_judge_results,
    grouped_mean,
    load_judge_envelopes,
    load_judge_evaluation_outputs,
    summarize_discrimination_rows,
    write_judge_evaluation_outputs,
)
from .judge_runtime import (
    CachedJudgeRunner,
    StructuredJsonJudgeProvider,
    validate_output_against_request,
    write_judge_requests,
)
from .judge_validity import (
    ValidityThresholds,
    build_validity_report,
    semantic_judge_agreement,
    semantic_judge_signature,
)
from .level_adaptation import (
    adaptation_evaluation_levels,
    aggregate_adaptation,
    apply_adaptation_threshold,
    build_adaptation_request,
)
from .level_discrimination import build_discrimination_request
from .level_profiles import (
    eligible_levels,
    load_eligibility_package,
    load_profile_checklist_package,
)
from .models import PersonalisationEligibility
from .v2_generation_artifacts import (
    adapt_m7_generation_artifacts,
    build_correctness_score_binding,
    correctness_rubric_set_sha256,
    load_open_answer_scores,
    write_adapter_outputs,
    write_correctness_score_binding,
)
from .v2_generation_models import (
    EvaluationDecisionConfig,
    EvaluationMode,
    ExperimentArm,
    GenerationEvaluationInput,
    GenerationRunStatus,
    JudgeConfiguration,
    JudgeRequest,
    JudgeResultEnvelope,
    JudgeTask,
    LevelGuess,
    canonical_model_family,
)
from .v2_generation_reporting import (
    answer_text_diagnostics,
    build_v2_generation_report,
    generation_noise_floor,
    joint_correct_and_adapted_summary,
    paired_generation_noise_floor,
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


def _source_run_sha256(items: list[GenerationEvaluationInput]) -> str:
    source_runs = {item.source_run_sha256 for item in items}
    if None in source_runs or len(source_runs) != 1:
        raise ValueError("evaluation inputs must belong to exactly one hash-bound source run")
    return str(next(iter(source_runs)))


def _require_exact_answer_hashes(items: list[GenerationEvaluationInput]) -> None:
    if any(item.answer is not None and item.answer_sha256 is None for item in items):
        raise ValueError("evaluation inputs with answers require exact answer hashes")


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
    validate.add_argument("--eligibility-calibration-count", type=int)
    validate.add_argument(
        "--allow-eligibility-superset", action="store_true",
        help="allow labels beyond the Gold question set, independently of review status",
    )
    validate.add_argument(
        "--eligibility-review-waiver",
        type=Path,
        help="hash-bound PR #224 waiver; mutually exclusive with review evidence",
    )
    validate.add_argument(
        "--leader-calibration-record",
        type=Path,
        help="nonempty reviewed Leader calibration record whose bytes are hash-bound",
    )
    validate.add_argument(
        "--label-provenance-record",
        type=Path,
        help="nonempty label-provenance record whose bytes are hash-bound",
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
    prepare.add_argument(
        "--reverse-adaptation-criteria",
        action="store_true",
        help="prepare the registered checklist-order perturbation for adaptation only",
    )
    prepare.add_argument("--output", required=True, type=Path)

    run_judges = commands.add_parser(
        "run-judge-requests",
        help="execute prepared blinded requests with the configured structured-output provider",
    )
    run_judges.add_argument("--requests", required=True, type=Path)
    run_judges.add_argument("--judge-config", required=True, type=Path)
    run_judges.add_argument("--cache", required=True, type=Path)
    run_judges.add_argument("--output", required=True, type=Path)
    run_judges.add_argument(
        "--judge-execution-id",
        required=True,
        help="stable audited ID reused only when resuming the same judge execution",
    )
    run_judges.add_argument("--timeout", type=float, default=120.0)
    run_judges.add_argument(
        "--max-output-tokens",
        type=int,
        help="provider output limit; defaults to 8192 for Gemini and 2048 otherwise",
    )
    run_judges.add_argument(
        "--context-window",
        type=int,
        help="required Ollama context length; use 32768 for the approved local run",
    )
    run_judges.add_argument("--max-attempts", type=int, default=2)
    run_judges.add_argument(
        "--attempt-log",
        type=Path,
        help="append-only per-provider-attempt JSONL; defaults to OUTPUT_STEM.attempts.jsonl",
    )
    run_judges.add_argument(
        "--require-fresh-cache",
        action="store_true",
        help="refuse an existing nonempty cache for repeat or order-independence runs",
    )

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

    bind_scores = commands.add_parser(
        "bind-correctness-scores",
        help="bind one validated correctness-score file to one adapted source run",
    )
    bind_scores.add_argument("--inputs", required=True, type=Path)
    bind_scores.add_argument("--adapter-manifest", required=True, type=Path)
    bind_scores.add_argument("--scores", required=True, type=Path)
    bind_scores.add_argument("--output", required=True, type=Path)

    assemble = commands.add_parser("assemble-judge-results")
    assemble.add_argument("--inputs", required=True, type=Path)
    assemble.add_argument("--profiles", required=True, type=Path)
    assemble.add_argument("--judge-config", required=True, type=Path)
    assemble.add_argument("--judge-results", required=True, type=Path)
    assemble.add_argument(
        "--judge-execution-id",
        required=True,
        help="unique audited execution ID; repeat/order/second runs must use new IDs",
    )
    assemble.add_argument("--cross-level-evaluation-ids", type=Path)
    assemble.add_argument(
        "--mode",
        choices=[mode.value for mode in EvaluationMode],
        default=EvaluationMode.DEVELOPMENT.value,
    )
    assemble.add_argument(
        "--reverse-adaptation-criteria",
        action="store_true",
        help="assemble the registered reversed-checklist adaptation run",
    )
    assemble.add_argument("--output-dir", required=True, type=Path)

    validity = commands.add_parser("validity-report")
    validity.add_argument("--observations", required=True, type=Path)
    validity.add_argument("--inputs", type=Path)
    validity.add_argument("--judge-evaluation-dir", type=Path)
    validity.add_argument("--repeat-judge-evaluation-dir", type=Path)
    validity.add_argument("--order-judge-evaluation-dir", type=Path)
    validity.add_argument("--second-judge-evaluation-dir", type=Path)
    validity.add_argument(
        "--repeat-comparison-ids",
        type=Path,
        help="optional preregistered evaluation_id subset for the repeat run",
    )
    validity.add_argument(
        "--order-comparison-ids",
        type=Path,
        help="optional preregistered evaluation_id subset for the order run",
    )
    validity.add_argument(
        "--second-comparison-ids",
        type=Path,
        help="optional preregistered evaluation_id subset for the second-family run",
    )
    validity.add_argument("--output", required=True, type=Path)

    development = commands.add_parser("development-report")
    development.add_argument("--inputs", required=True, type=Path)
    development.add_argument("--adapter-manifest", required=True, type=Path)
    development.add_argument("--correctness-scores", type=Path)
    development.add_argument("--correctness-score-binding", type=Path)
    development.add_argument("--judge-evaluation-dir", type=Path)
    development.add_argument("--generation-repeat-inputs", type=Path)
    development.add_argument("--generation-repeat-adapter-manifest", type=Path)
    development.add_argument("--generation-repeat-correctness-scores", type=Path)
    development.add_argument("--generation-repeat-correctness-score-binding", type=Path)
    development.add_argument("--generation-repeat-judge-evaluation-dir", type=Path)
    development.add_argument("--validity-report", type=Path)
    development.add_argument("--input-validation", type=Path)
    development.add_argument("--human-audit-ratings", type=Path)
    development.add_argument("--human-audit-packet", type=Path)
    development.add_argument("--human-audit-manifest", type=Path)
    development.add_argument("--human-audit-private-key", type=Path)
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
    evidence_files = {
        "leader_calibration_record": args.leader_calibration_record,
        "label_provenance_record": args.label_provenance_record,
    }
    evidence_hashes: dict[str, str] = {}
    waiver_path = getattr(args, "eligibility_review_waiver", None)
    waiver = None
    if waiver_path is not None:
        from .v2_generation_models import EligibilityReviewWaiver

        waiver = EligibilityReviewWaiver.model_validate_json(waiver_path.read_bytes())
        if args.eligibility_calibration_count is not None or any(evidence_files.values()):
            raise ValueError("review waiver cannot be combined with claimed review evidence")
        evidence_hashes["eligibility_review_waiver"] = hashlib.sha256(
            waiver_path.read_bytes()
        ).hexdigest()
    else:
        for label, path in evidence_files.items():
            if path is None or not path.is_file() or not path.read_bytes().strip():
                raise ValueError(f"{label} must point to a nonempty evidence file")
            evidence_hashes[label] = hashlib.sha256(path.read_bytes()).hexdigest()
    eligibility = load_eligibility_package(
        args.eligibility,
        package_version=args.eligibility_version,
        gold_version=args.gold_version,
        gold_sha256=gold_sha256,
        calibration_question_count=args.eligibility_calibration_count,
        leader_calibration_record_sha256=evidence_hashes.get("leader_calibration_record"),
        label_provenance_record_sha256=evidence_hashes.get("label_provenance_record"),
        review_waiver=waiver,
        profile_package_sha256=profiles.package_sha256,
        expected_question_ids=question_ids,
        allow_superset=args.allow_eligibility_superset,
        require_resolved=args.reportable,
    )
    _write_json(
        args.output,
        {
            "schema_version": "1.0",
            "profile_package_version": profiles.package_version,
            "profile_package_sha256": profiles.package_sha256,
            "eligibility_package_version": eligibility.package_version,
            "eligibility_sha256": hashlib.sha256(args.eligibility.read_bytes()).hexdigest(),
            "gold_version": eligibility.gold_version,
            "gold_sha256": eligibility.gold_sha256,
            "question_count": len(question_ids),
            "question_ids": sorted(question_ids),
            "eligibility_evidence_sha256": evidence_hashes,
            "eligibility_human_calibrated": waiver is None,
            "eligibility_superset_allowed": args.allow_eligibility_superset,
            "eligibility_review_waiver": waiver.model_dump(mode="json") if waiver else None,
            "reportable_input_validation": bool(args.reportable),
            "valid": True,
        },
    )
    return 0


def _run_judge_requests(args: argparse.Namespace) -> int:
    if args.output.exists():
        raise ValueError("judge result output already exists")
    judge_execution_id = args.judge_execution_id.strip()
    if not judge_execution_id:
        raise ValueError("judge execution ID must not be empty")
    if args.timeout <= 0 or (args.max_output_tokens is not None and args.max_output_tokens <= 0):
        raise ValueError("judge timeout and output limit must be positive")
    if args.max_attempts <= 0:
        raise ValueError("judge attempts must be positive")
    try:
        configuration = JudgeConfiguration.model_validate_json(
            args.judge_config.read_text(encoding="utf-8")
        )
        requests = [JudgeRequest.model_validate(row) for row in _read_jsonl(args.requests)]
    except ValidationError as exc:
        raise ValueError(f"invalid judge execution input: {exc}") from exc
    request_ids = [request.request_id for request in requests]
    if not requests or len(request_ids) != len(set(request_ids)):
        raise ValueError("judge request file must contain unique nonempty request IDs")

    for request in requests:
        if request.task is JudgeTask.ADAPTATION:
            always_assessed_ids(request)
        if request.task is JudgeTask.EVIDENCE_SUPPORT and args.max_attempts < 2:
            raise ValueError("evidence support requires at least two application attempts")
    attempt_log = args.attempt_log or args.output.with_suffix(".attempts.jsonl")
    if attempt_log.resolve() in {
        path.resolve() for path in (args.requests, args.judge_config, args.cache, args.output)
    }:
        raise ValueError("judge attempt log must be separate from inputs, cache and result output")
    provider_name = configuration.provider.casefold()
    max_output_tokens = args.max_output_tokens or (8192 if provider_name == "gemini" else 2048)
    model_digest: str | None = None
    context_window: int | None = None
    if provider_name == "ollama":
        if args.context_window is None or args.context_window <= max_output_tokens + 512:
            raise ValueError(
                "Ollama judge requires --context-window with room for output and framing"
            )
        client = OllamaChatClient(
            configuration.model_revision,
            temperature=configuration.temperature,
            timeout_seconds=args.timeout,
            max_output_tokens=max_output_tokens,
            context_window=args.context_window,
            seed=configuration.seed or 0,
        )
        client.pin_model()
        if not client.model_digest:
            raise ValueError("Ollama judge did not expose a pinned model weights digest")
        model_digest = client.model_digest
        context_window = client.context_window
    elif provider_name == "openai":
        if args.context_window is not None:
            raise ValueError("--context-window is only supported by the Ollama judge")
        client = OpenAIResponsesClient(
            configuration.model_revision,
            temperature=configuration.temperature,
            timeout_seconds=args.timeout,
            max_output_tokens=max_output_tokens,
        )
    elif provider_name == "gemini":
        if args.context_window is not None:
            raise ValueError("--context-window is only supported by the Ollama judge")
        client = GeminiJudgeClient(
            configuration.model_revision,
            temperature=configuration.temperature,
            timeout_seconds=args.timeout,
            max_output_tokens=max_output_tokens,
            seed=configuration.seed,
            thinking_level=configuration.thinking_level or "high",
        )
    else:
        raise ValueError("judge configuration provider must be 'ollama', 'openai' or 'gemini'")
    provider = StructuredJsonJudgeProvider(client)
    runner = CachedJudgeRunner(
        args.cache,
        judge_execution_id=judge_execution_id,
        model_digest=model_digest,
        context_window=context_window,
        max_attempts=args.max_attempts,
        require_current_execution_cache=args.require_fresh_cache,
        attempt_log_path=attempt_log,
    )
    # Preflight: every reusable cached result must satisfy the current validators before
    # any provider call, so an outdated cache stops the run instead of being re-bought.
    for request in requests:
        runner.verify_cached(
            request, lambda raw, bound=request: validate_output_against_request(raw, bound)
        )
    results: list[JudgeResultEnvelope] = []
    for request in requests:
        results.append(
            runner.run(
                request,
                configuration,
                provider,
                lambda raw, bound=request: validate_output_against_request(raw, bound),
            )
        )
    if args.require_fresh_cache and any(result.cache_hit for result in results):
        raise ValueError("fresh judge execution unexpectedly reused a cached result")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(result.model_dump_json() + "\n" for result in results),
        encoding="utf-8",
    )
    return 3 if any(result.unresolved for result in results) else 0


def _prepare_requests(args: argparse.Namespace) -> int:
    items = _load_inputs(args.inputs)
    if args.mode == EvaluationMode.REPORTABLE.value:
        _source_run_sha256(items)
        _require_exact_answer_hashes(items)
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
                checklist = checklists[evaluated_level]
                criterion_order = None
                if args.reverse_adaptation_criteria:
                    criterion_order = [
                        criterion.criterion_id
                        for criterion in reversed(checklist.criteria)
                    ]
                request = build_adaptation_request(
                    item,
                    profiles[evaluated_level],
                    checklist,
                    configuration,
                    evaluated_level=evaluated_level,
                    criterion_order=criterion_order,
                    profile_package=package,
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
    items = _load_inputs(args.inputs)
    _source_run_sha256(items)
    _require_exact_answer_hashes(items)
    prepare_calibration_and_audit(
        items,
        args.output_dir,
        evaluation_inputs_sha256=hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
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


def _bind_correctness_scores(args: argparse.Namespace) -> int:
    items = _load_inputs(args.inputs)
    manifest = _load_json_object(args.adapter_manifest)
    inputs_sha256 = hashlib.sha256(args.inputs.read_bytes()).hexdigest()
    if manifest.get("output_sha256", {}).get("generation_evaluation_inputs") != inputs_sha256:
        raise ValueError("evaluation inputs do not match the adapter manifest hash")
    if manifest.get("source_run_sha256") != _source_run_sha256(items):
        raise ValueError("evaluation inputs do not match the adapter source run")
    binding = build_correctness_score_binding(
        args.scores,
        items,
        evaluation_inputs_sha256=inputs_sha256,
        gold_sha256=str(manifest["gold_sha256"]),
    )
    write_correctness_score_binding(binding, args.output)
    return 0


def _judge_response_fingerprint(envelope: JudgeResultEnvelope) -> str:
    """Return a cross-run identity that exposes reused provider responses."""

    if envelope.provider_response_id is not None:
        identity = {
            "kind": "provider_response_id",
            "value": envelope.provider_response_id,
        }
    elif envelope.completed_at_utc is not None:
        identity = {
            "kind": "completed_at_utc",
            "value": envelope.completed_at_utc,
        }
    else:
        raise ValueError("resolved judge response is missing provider response provenance")
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_judge_execution_records(
    envelopes: dict[str, JudgeResultEnvelope],
    *,
    judge_execution_id: str,
    provider_name: str,
) -> None:
    """Verify that cache provenance and local runtime identity are auditable."""

    if any(envelope.judge_execution_id is None for envelope in envelopes.values()):
        raise ValueError("judge results contain records without an execution ID")
    if any(
        envelope.cache_hit
        != (envelope.judge_execution_id != judge_execution_id)
        for envelope in envelopes.values()
    ):
        raise ValueError("judge cache-hit status does not match result execution IDs")
    current_execution_records = [
        envelope for envelope in envelopes.values() if not envelope.cache_hit
    ]
    if provider_name.casefold() != "ollama" or not current_execution_records:
        return
    model_digests = {envelope.model_digest for envelope in current_execution_records}
    context_windows = {envelope.context_window for envelope in current_execution_records}
    if None in model_digests or len(model_digests) != 1:
        raise ValueError("Ollama judge results require one pinned model weights digest")
    if None in context_windows or len(context_windows) != 1:
        raise ValueError("Ollama judge results require one pinned context window")


def _assemble_judge_results(args: argparse.Namespace) -> int:
    judge_execution_id = args.judge_execution_id.strip()
    if not judge_execution_id:
        raise ValueError("judge execution ID must not be empty")
    items = _load_inputs(args.inputs)
    source_run_hash = _source_run_sha256(items)
    _require_exact_answer_hashes(items)
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
    envelopes = load_judge_envelopes(args.judge_results)
    _validate_judge_execution_records(
        envelopes,
        judge_execution_id=judge_execution_id,
        provider_name=configuration.provider,
    )
    response_fingerprints = sorted(
        _judge_response_fingerprint(envelope)
        for envelope in envelopes.values()
        if not envelope.unresolved
    )
    result = assemble_judge_results(
        items,
        package,
        configuration,
        envelopes,
        cross_level_evaluation_ids=cross_level_ids,
        mode=EvaluationMode(args.mode),
        reverse_adaptation_criteria=args.reverse_adaptation_criteria,
    )
    write_judge_evaluation_outputs(
        result,
        args.output_dir,
        provenance={
            "evaluation_inputs_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
            "source_run_sha256": source_run_hash,
            "profile_package_sha256": package.package_sha256,
            "profile_physics_review_waived": package.physics_review_waiver is not None,
            "judge_configuration_sha256": hashlib.sha256(
                args.judge_config.read_bytes()
            ).hexdigest(),
            "judge_config_version": configuration.config_version,
            "judge_provider": configuration.provider,
            "judge_model_family": configuration.model_family,
            "judge_model_revision": configuration.model_revision,
            "judge_results_sha256": hashlib.sha256(args.judge_results.read_bytes()).hexdigest(),
            "judge_execution_id": judge_execution_id,
            "judge_cache_hit_count": sum(envelope.cache_hit for envelope in envelopes.values()),
            "judge_model_digests": sorted(
                {
                    envelope.model_digest
                    for envelope in envelopes.values()
                    if envelope.model_digest is not None
                }
            ),
            "judge_context_windows": sorted(
                {
                    envelope.context_window
                    for envelope in envelopes.values()
                    if envelope.context_window is not None
                }
            ),
            "judge_response_fingerprints": response_fingerprints,
            "cross_level_ids_sha256": (
                hashlib.sha256(args.cross_level_evaluation_ids.read_bytes()).hexdigest()
                if args.cross_level_evaluation_ids is not None
                else None
            ),
            "mode": args.mode,
            "reverse_adaptation_criteria": args.reverse_adaptation_criteria,
        },
    )
    return 0


def _validate_generation_repeat_judge(
    baseline_provenance: dict[str, Any],
    repeat_provenance: dict[str, Any],
    *,
    repeat_inputs_hash: str,
    repeat_source_run: str,
) -> None:
    """Bind the repeat batch's judge run to the Dev baseline's frozen judge setup.

    Mirrors the efficacy-comparison checks: a different profile package or a reversed
    checklist would mix judge-side changes into the generation noise floor.
    """

    if repeat_provenance.get("evaluation_inputs_sha256") != repeat_inputs_hash:
        raise ValueError("repeat judge evaluation is bound to different inputs")
    if repeat_provenance.get("source_run_sha256") != repeat_source_run:
        raise ValueError("repeat judge evaluation is bound to a different source run")
    for field in (
        "judge_configuration_sha256",
        "judge_config_version",
        "profile_package_sha256",
    ):
        if not baseline_provenance.get(field) or baseline_provenance.get(
            field
        ) != repeat_provenance.get(field):
            raise ValueError(
                f"generation baseline and repeat must use the same frozen judge {field}"
            )
    if (
        baseline_provenance.get("reverse_adaptation_criteria") is not False
        or repeat_provenance.get("reverse_adaptation_criteria") is not False
    ):
        raise ValueError("generation baseline and repeat must use the registered checklist order")


def _validate_generation_repeat_rubrics(
    baseline_scores: dict[str, Any],
    repeat_scores: dict[str, Any],
    baseline_items: list[GenerationEvaluationInput],
    repeat_items: list[GenerationEvaluationInput],
) -> None:
    """Require the repeat subset to use its matching Dev per-question rubrics."""

    repeat_question_ids = {item.question_id for item in repeat_items}
    baseline_question_ids = {item.question_id for item in baseline_items}
    missing_from_baseline = sorted(repeat_question_ids - baseline_question_ids)
    if missing_from_baseline:
        raise ValueError(
            "generation repeat contains questions missing from the Dev baseline: "
            + ", ".join(missing_from_baseline)
        )

    def rubric_by_question(
        item_scores: dict[str, Any],
        *,
        label: str,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for score in item_scores.values():
            if score.question_id not in repeat_question_ids:
                continue
            if score.rubric_sha256 is None:
                raise ValueError(
                    f"{label} question {score.question_id} has a score without a rubric"
                )
            previous = result.setdefault(score.question_id, score.rubric_sha256)
            if previous != score.rubric_sha256:
                raise ValueError(
                    f"{label} question {score.question_id} uses conflicting correctness rubrics"
                )
        missing = sorted(repeat_question_ids - set(result))
        if missing:
            raise ValueError(
                f"{label} has no score to establish the correctness rubric for: "
                + ", ".join(missing)
            )
        return result

    baseline_rubrics = rubric_by_question(baseline_scores, label="Dev baseline")
    repeat_rubrics = rubric_by_question(repeat_scores, label="generation repeat")
    for question_id in sorted(repeat_question_ids):
        if baseline_rubrics[question_id] != repeat_rubrics[question_id]:
            raise ValueError(
                f"generation baseline and repeat use different correctness rubrics for "
                f"question {question_id}"
            )


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected one JSON object")
    return value


def _judge_result_key(dimension: str, row: dict[str, Any]) -> str:
    evaluation_id = row.get("evaluation_id")
    if not isinstance(evaluation_id, str) or not evaluation_id:
        raise ValueError(f"{dimension} result is missing evaluation_id")
    suffix = ""
    if dimension == "adaptation":
        evaluated_level = row.get("evaluated_level")
        if not isinstance(evaluated_level, str) or not evaluated_level:
            raise ValueError("adaptation result is missing evaluated_level")
        suffix = f":{evaluated_level}"
    return f"{dimension}:{evaluation_id}{suffix}"


def _indexed_judge_rows(
    judge_data: dict[str, Any],
    dimension: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for raw in judge_data[dimension]:
        if not isinstance(raw, dict):
            raise ValueError(f"{dimension} output contains a non-object row")
        key = _judge_result_key(dimension, raw)
        if key in indexed:
            raise ValueError(f"{dimension} output contains duplicate comparison key {key}")
        indexed[key] = raw
    return indexed


def _assert_comparable_judge_runs(
    primary: dict[str, Any],
    comparison: dict[str, Any],
    *,
    purpose: str,
) -> None:
    primary_provenance = primary["manifest"].get("provenance", {})
    comparison_provenance = comparison["manifest"].get("provenance", {})
    for field in (
        "evaluation_inputs_sha256",
        "source_run_sha256",
        "profile_package_sha256",
    ):
        if (
            not primary_provenance.get(field)
            or primary_provenance.get(field) != comparison_provenance.get(field)
        ):
            raise ValueError(f"{purpose} judge run has different {field}")
    primary_execution = primary_provenance.get("judge_execution_id")
    comparison_execution = comparison_provenance.get("judge_execution_id")
    if not isinstance(primary_execution, str) or not isinstance(comparison_execution, str):
        raise ValueError(f"{purpose} comparison requires audited judge execution IDs")
    if primary_execution == comparison_execution:
        raise ValueError(f"{purpose} comparison must come from a separate judge execution")
    if purpose in {"repeat", "order"}:
        if primary_provenance.get("judge_configuration_sha256") != comparison_provenance.get(
            "judge_configuration_sha256"
        ):
            raise ValueError(f"{purpose} judge run must use the primary judge configuration")
        if (
            primary_provenance.get("judge_cache_hit_count") != 0
            or comparison_provenance.get("judge_cache_hit_count") != 0
        ):
            raise ValueError(
                f"{purpose} comparison requires fresh primary and comparison caches"
            )
        primary_fingerprints = set(primary_provenance.get("judge_response_fingerprints") or [])
        comparison_fingerprints = set(
            comparison_provenance.get("judge_response_fingerprints") or []
        )
        if not primary_fingerprints or not comparison_fingerprints:
            raise ValueError(f"{purpose} comparison requires provider response provenance")
        if primary_fingerprints.intersection(comparison_fingerprints):
            raise ValueError(f"{purpose} judge run reused provider responses from the primary run")
    if purpose == "repeat" and (
        primary_provenance.get("reverse_adaptation_criteria") is True
        or comparison_provenance.get("reverse_adaptation_criteria") is True
    ):
        raise ValueError("repeat judge runs must use the registered checklist order")
    if purpose == "order":
        if primary_provenance.get("reverse_adaptation_criteria") is True:
            raise ValueError("primary judge run must use the registered checklist order")
        if comparison_provenance.get("reverse_adaptation_criteria") is not True:
            raise ValueError("order judge run must use reversed adaptation criteria")
    if purpose == "second":
        primary_family = primary_provenance.get("judge_model_family")
        second_family = comparison_provenance.get("judge_model_family")
        if not isinstance(primary_family, str) or not isinstance(second_family, str):
            raise ValueError("second-judge comparison requires recorded model families")
        if canonical_model_family(primary_family) == canonical_model_family(second_family):
            raise ValueError("second judge must use a different model family")


def _semantic_pairs(
    primary: dict[str, Any],
    comparison: dict[str, Any],
    *,
    dimensions: tuple[str, ...],
    evidence_rate_tolerance: float,
    allowed_evaluation_ids: set[str] | None = None,
) -> list[tuple[str, str, str]]:
    pairs: list[tuple[str, str, str]] = []
    for dimension in dimensions:
        first = _indexed_judge_rows(primary, dimension)
        second = _indexed_judge_rows(comparison, dimension)
        if allowed_evaluation_ids is not None:
            first = {
                key: row
                for key, row in first.items()
                if row.get("evaluation_id") in allowed_evaluation_ids
            }
            second = {
                key: row
                for key, row in second.items()
                if row.get("evaluation_id") in allowed_evaluation_ids
            }
        if set(first) != set(second):
            missing = sorted(set(first) - set(second))
            extra = sorted(set(second) - set(first))
            raise ValueError(
                f"{dimension} comparison coverage mismatch; missing={missing}, extra={extra}"
            )
        for key in sorted(first):
            left = semantic_judge_signature(dimension, first[key])
            right = semantic_judge_signature(dimension, second[key])
            if semantic_judge_agreement(
                dimension,
                first[key],
                second[key],
                evidence_rate_tolerance=evidence_rate_tolerance,
            ):
                right = left
            pairs.append((key, left, right))
    return pairs


def _case_evaluation_id(case_id: str) -> str:
    dimension, remainder = case_id.split(":", 1)
    if dimension == "adaptation":
        evaluation_id, _ = remainder.rsplit(":", 1)
        return evaluation_id
    return remainder


def _comparison_coverage(
    pairs: list[tuple[str, str, str]],
    inputs_by_id: dict[str, GenerationEvaluationInput],
    *,
    require_conditions: bool,
) -> tuple[bool, int]:
    evaluation_ids = {_case_evaluation_id(pair[0]) for pair in pairs}
    rows = [inputs_by_id[evaluation_id] for evaluation_id in evaluation_ids]
    levels = {row.target_level for row in rows}
    conditions = {row.condition for row in rows}
    complete = levels == set(StudentLevel) and (
        not require_conditions or conditions == set(ExperimentArm)
    )
    return complete, len(evaluation_ids)


def _load_comparison_ids(
    path: Path,
    *,
    purpose: str,
    inputs_by_id: dict[str, GenerationEvaluationInput],
) -> set[str]:
    raw_ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    evaluation_ids = [evaluation_id for evaluation_id in raw_ids if evaluation_id]
    if not evaluation_ids:
        raise ValueError(f"{purpose} comparison ID file is empty")
    if len(evaluation_ids) != len(set(evaluation_ids)):
        raise ValueError(f"{purpose} comparison ID file contains duplicates")
    unknown = sorted(set(evaluation_ids) - set(inputs_by_id))
    if unknown:
        raise ValueError(f"{purpose} comparison ID file contains unknown IDs: {unknown}")
    ineligible = sorted(
        evaluation_id
        for evaluation_id in evaluation_ids
        if (
            inputs_by_id[evaluation_id].technical_failure
            or inputs_by_id[evaluation_id].abstained
            or inputs_by_id[evaluation_id].answer is None
        )
    )
    if ineligible:
        raise ValueError(
            f"{purpose} comparison IDs must reference answered evaluations: {ineligible}"
        )
    return set(evaluation_ids)


def _validity_report(args: argparse.Namespace) -> int:
    payload = _load_json_object(args.observations)
    if (args.inputs is None) != (args.judge_evaluation_dir is None):
        raise ValueError("validity binding requires --inputs and --judge-evaluation-dir together")
    comparison_dirs = {
        "repeat": args.repeat_judge_evaluation_dir,
        "order": args.order_judge_evaluation_dir,
        "second": args.second_judge_evaluation_dir,
    }
    comparison_id_paths = {
        "repeat": args.repeat_comparison_ids,
        "order": args.order_comparison_ids,
        "second": args.second_comparison_ids,
    }
    selectors_without_runs = sorted(
        purpose
        for purpose, path in comparison_id_paths.items()
        if path is not None and comparison_dirs[purpose] is None
    )
    if selectors_without_runs:
        raise ValueError(
            "comparison ID files require matching judge evaluation directories: "
            + ", ".join(selectors_without_runs)
        )
    if any(path is not None for path in comparison_dirs.values()) and args.inputs is None:
        raise ValueError("automatic validity comparisons require bound inputs and primary results")
    inputs_sha256 = None
    source_run_hash = None
    judge_manifest_sha256 = None
    comparison_manifest_sha256: dict[str, str] = {}
    comparison_ids_sha256: dict[str, str] = {}
    judge_data: dict[str, Any] | None = None
    comparison_data: dict[str, dict[str, Any]] = {}
    inputs_by_id: dict[str, GenerationEvaluationInput] = {}
    derived_p0r0_rows: list[tuple[StudentLevel, LevelGuess]] | None = None
    derived_surface_rows: list[tuple[StudentLevel, bool, int, bool]] | None = None
    if args.inputs is not None:
        items = _load_inputs(args.inputs)
        source_run_hash = _source_run_sha256(items)
        judge_data = load_judge_evaluation_outputs(args.judge_evaluation_dir)
        inputs_sha256 = hashlib.sha256(args.inputs.read_bytes()).hexdigest()
        judge_provenance = judge_data["manifest"].get("provenance", {})
        if judge_provenance.get("evaluation_inputs_sha256") != inputs_sha256:
            raise ValueError("judge evaluation is bound to different evaluation inputs")
        if judge_provenance.get("source_run_sha256") != source_run_hash:
            raise ValueError("judge evaluation is bound to a different source run")
        judge_manifest_sha256 = hashlib.sha256(
            (args.judge_evaluation_dir / "judge_evaluation_manifest.json").read_bytes()
        ).hexdigest()
        declared_provenance = payload.get("provenance")
        expected_provenance = {
            "evaluation_inputs_sha256": inputs_sha256,
            "source_run_sha256": source_run_hash,
            "judge_evaluation_manifest_sha256": judge_manifest_sha256,
        }
        if not isinstance(declared_provenance, dict) or any(
            declared_provenance.get(name) != value
            for name, value in expected_provenance.items()
        ):
            raise ValueError("validity observations are not bound to the current judge run")
        derived_p0r0_rows = [
            (
                StudentLevel(str(row["target_level"])),
                LevelGuess(str(row["predicted_level"])),
            )
            for row in judge_data["discrimination"]
            if row.get("condition") == ExperimentArm.P0R0_PLAIN.value
        ]
        threshold = payload.get("adaptation_pass_threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError("bound validity observations require adaptation_pass_threshold")
        threshold = float(threshold)
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("adaptation_pass_threshold must be between zero and one")
        inputs_by_id = {item.evaluation_id: item for item in items}
        answered_evaluation_ids = {
            item.evaluation_id
            for item in items
            if not item.technical_failure and not item.abstained and item.answer is not None
        }
        derived_surface_rows = []
        for row in judge_data["adaptation"]:
            if not row.get("is_target_level_evaluation"):
                continue
            item = inputs_by_id[str(row["evaluation_id"])]
            rate = row.get("criterion_pass_rate")
            if item.answer is None or rate is None:
                continue
            diagnostics = answer_text_diagnostics(item.answer)
            derived_surface_rows.append(
                (
                    item.target_level,
                    float(rate) >= threshold,
                    int(diagnostics["word_count"]),
                    bool(diagnostics["formula_present"]),
                )
            )
        for purpose, path in comparison_dirs.items():
            if path is None:
                continue
            data = load_judge_evaluation_outputs(path)
            _assert_comparable_judge_runs(judge_data, data, purpose=purpose)
            comparison_data[purpose] = data
            comparison_manifest_sha256[purpose] = hashlib.sha256(
                (path / "judge_evaluation_manifest.json").read_bytes()
            ).hexdigest()
            selection_path = comparison_id_paths[purpose]
            if selection_path is not None:
                selected_ids = _load_comparison_ids(
                    selection_path,
                    purpose=purpose,
                    inputs_by_id=inputs_by_id,
                )
                comparison_ids_sha256[purpose] = hashlib.sha256(
                    selection_path.read_bytes()
                ).hexdigest()
            else:
                selected_ids = answered_evaluation_ids
            comparison_data[purpose]["selected_evaluation_ids"] = selected_ids

    def triples(name: str) -> list[tuple[str, str, str]]:
        raw_rows = payload.get(name, [])
        if not isinstance(raw_rows, list):
            raise ValueError(f"{name} must be a list")
        rows: list[tuple[str, str, str]] = []
        for index, row in enumerate(raw_rows):
            if (
                not isinstance(row, list)
                or len(row) != 3
                or any(not isinstance(value, str) or not value for value in row)
            ):
                raise ValueError(f"{name}[{index}] must contain three non-empty strings")
            rows.append((row[0], row[1], row[2]))
        return rows

    def booleans(name: str) -> list[bool]:
        raw_values = payload.get(name, [])
        if not isinstance(raw_values, list) or any(
            not isinstance(value, bool) for value in raw_values
        ):
            raise ValueError(f"{name} must contain only JSON booleans")
        return list(raw_values)

    def boolean_field(name: str, *, default: bool = False) -> bool:
        value = payload.get(name, default)
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a JSON boolean")
        return value

    def non_negative_integer(name: str, *, default: int = 0) -> int:
        value = payload.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
        return value

    try:
        thresholds = ValidityThresholds.model_validate(payload["thresholds"])
        raw_p0r0 = payload.get("p0r0_rows", [])
        if not isinstance(raw_p0r0, list):
            raise ValueError("p0r0_rows must be a list")
        p0r0_rows = (
            derived_p0r0_rows
            if derived_p0r0_rows is not None
            else [
                (StudentLevel(row[0]), LevelGuess(row[1]))
                for row in raw_p0r0
                if isinstance(row, list) and len(row) == 2
            ]
        )
        if derived_p0r0_rows is None and len(p0r0_rows) != len(raw_p0r0):
            raise ValueError("p0r0_rows must contain [target_level, predicted_level] pairs")
        raw_surface_rows = payload.get("surface_rows", [])
        if not isinstance(raw_surface_rows, list):
            raise ValueError("surface_rows must be a list")
        surface_rows = derived_surface_rows
        if surface_rows is None:
            surface_rows = []
            for index, row in enumerate(raw_surface_rows):
                if (
                    not isinstance(row, list)
                    or len(row) != 4
                    or not isinstance(row[1], bool)
                    or isinstance(row[2], bool)
                    or not isinstance(row[2], int)
                    or row[2] < 0
                    or not isinstance(row[3], bool)
                ):
                    raise ValueError(f"surface_rows[{index}] has invalid field types")
                surface_rows.append(
                    (StudentLevel(row[0]), row[1], row[2], row[3])
                )
        require_perturbation = payload.get("require_perturbation", False)
        if not isinstance(require_perturbation, bool):
            raise ValueError("require_perturbation must be a JSON boolean")
        duplicate_rows = triples("duplicate_rows")
        order_pairs = triples("order_pairs")
        second_judge_pairs = triples("second_judge_pairs")
        order_coverage_complete = boolean_field("order_coverage_complete")
        second_judge_coverage_complete = boolean_field(
            "second_judge_coverage_complete"
        )
        order_case_count = non_negative_integer("order_case_count")
        second_judge_case_count = non_negative_integer("second_judge_case_count")
        if judge_data is not None and "repeat" in comparison_data:
            repeat_ids = comparison_data["repeat"]["selected_evaluation_ids"]
            repeat_pairs = _semantic_pairs(
                judge_data,
                comparison_data["repeat"],
                dimensions=("adaptation", "discrimination", "evidence_support"),
                evidence_rate_tolerance=0.0,
                allowed_evaluation_ids=repeat_ids,
            )
            duplicate_rows = []
            for case_id, first, second in repeat_pairs:
                evaluation_id = _case_evaluation_id(case_id)
                answer_sha256 = inputs_by_id[evaluation_id].answer_sha256
                if answer_sha256 is None:
                    raise ValueError("repeat comparison includes an answer without a hash")
                duplicate_rows.extend(
                    [
                        (case_id, answer_sha256, first),
                        (case_id, answer_sha256, second),
                    ]
                )
        if judge_data is not None and "order" in comparison_data:
            order_pairs = _semantic_pairs(
                judge_data,
                comparison_data["order"],
                dimensions=("adaptation",),
                evidence_rate_tolerance=thresholds.second_judge_max_evidence_rate_gap,
                allowed_evaluation_ids=comparison_data["order"][
                    "selected_evaluation_ids"
                ],
            )
            order_coverage_complete, order_case_count = _comparison_coverage(
                order_pairs,
                inputs_by_id,
                require_conditions=False,
            )
        if judge_data is not None and "second" in comparison_data:
            second_judge_pairs = _semantic_pairs(
                judge_data,
                comparison_data["second"],
                dimensions=("adaptation", "discrimination", "evidence_support"),
                evidence_rate_tolerance=thresholds.second_judge_max_evidence_rate_gap,
                allowed_evaluation_ids=comparison_data["second"][
                    "selected_evaluation_ids"
                ],
            )
            second_judge_coverage_complete, second_judge_case_count = _comparison_coverage(
                second_judge_pairs,
                inputs_by_id,
                require_conditions=True,
            )
        report = build_validity_report(
            thresholds,
            p0r0_rows=p0r0_rows,
            duplicate_rows=duplicate_rows,
            surface_rows=surface_rows,
            order_pairs=order_pairs,
            second_judge_pairs=second_judge_pairs,
            perturbation_detections=booleans("perturbation_detections"),
            require_perturbation=require_perturbation,
            order_coverage_complete=order_coverage_complete,
            second_judge_coverage_complete=second_judge_coverage_complete,
            order_case_count=order_case_count,
            second_judge_case_count=second_judge_case_count,
        )
    except (KeyError, TypeError, ValidationError, ValueError) as exc:
        raise ValueError(f"{args.observations}: invalid validity observations: {exc}") from exc
    report["provenance"] = {
        "observations_sha256": hashlib.sha256(args.observations.read_bytes()).hexdigest(),
        "evaluation_inputs_sha256": inputs_sha256,
        "source_run_sha256": source_run_hash,
        "judge_evaluation_manifest_sha256": judge_manifest_sha256,
        "comparison_judge_manifest_sha256": comparison_manifest_sha256,
        "comparison_evaluation_ids_sha256": comparison_ids_sha256,
        "binding_verified": inputs_sha256 is not None,
    }
    if inputs_sha256 is None:
        report["formal_use_allowed"] = False
        missing = list(report["failed_or_missing_required_checks"])
        missing.append("source_binding")
        report["failed_or_missing_required_checks"] = missing
    _write_json(args.output, report)
    return 0


def _eligibility_groups(
    items: list[GenerationEvaluationInput],
) -> dict[str, list[GenerationEvaluationInput]]:
    groups: dict[str, list[GenerationEvaluationInput]] = defaultdict(list)
    labels: dict[str, PersonalisationEligibility] = {}
    for item in items:
        if item.question_id in labels and labels[item.question_id] is not item.eligibility:
            raise ValueError(f"{item.question_id}: inconsistent eligibility across run cells")
        labels[item.question_id] = item.eligibility
        groups[item.eligibility.value].append(item)
    groups["all"] = items
    groups["full_and_endpoint_only"] = [
        item for item in items if item.target_level in eligible_levels(item.eligibility)
    ]
    return dict(groups)


def _eligibility_condition_contrasts(
    items: list[GenerationEvaluationInput],
    observations: list[MetricObservation],
    *,
    bootstrap_draws: int,
    bootstrap_seed: int,
    not_applicable_cells: dict[str, set[tuple[str, StudentLevel, ExperimentArm]]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the main adaptation scope separate from all-question diagnostics.

    Not-applicable cells (abstentions, technical failures and answers with nothing
    evaluable for a quality metric) are excluded from pairing rather than counted as
    missing; see ``_quality_not_applicable_cells``.
    """

    adaptation_metric = "adaptation_criterion_pass_rate"
    base_metrics = (
        {row.metric for row in observations}
        | {"strict_correct", adaptation_metric}
        | set(not_applicable_cells or {})
    )
    main_rows = []
    subset_rows = []
    for subset, rows in _eligibility_groups(items).items():
        cells = {(item.question_id, item.target_level, item.condition) for item in rows}
        selected = [
            row
            for row in observations
            if (row.question_id, row.target_level, row.condition) in cells
        ]
        # Restrict not-applicable cells to this subset so exclusions from other
        # eligibility labels never leak into its counts.
        subset_not_applicable = {
            metric: metric_cells & cells
            for metric, metric_cells in (not_applicable_cells or {}).items()
        }
        expected = {(item.question_id, item.target_level) for item in rows}
        contrasts = paired_condition_contrasts(
            selected,
            bootstrap_draws=bootstrap_draws,
            bootstrap_seed=bootstrap_seed,
            expected_question_levels={metric: expected for metric in base_metrics},
            not_applicable_cells=subset_not_applicable,
        )
        for contrast in contrasts:
            row = {**contrast, "eligibility_subset": subset}
            subset_rows.append(row)
            if (subset == "all" and row["metric"] != adaptation_metric) or (
                subset == "full_and_endpoint_only" and row["metric"] == adaptation_metric
            ):
                main_rows.append(row)
    return main_rows, subset_rows


def _quality_not_applicable_cells(
    items: list[GenerationEvaluationInput],
    *,
    adaptation_not_applicable_ids: frozenset[str],
    evidence_rows: list[dict[str, Any]],
    evidence_expected: bool = False,
) -> dict[str, set[tuple[str, StudentLevel, ExperimentArm]]]:
    """Cells that cannot receive a quality score for the saved answer.

    Abstentions and technical failures are not applicable to adaptation, bundle
    faithfulness and citation support, and never receive a quality score of zero.
    An answered cell is also not applicable to a metric when nothing in it was
    evaluable: no applicable checklist criterion for adaptation, or no evaluable claim
    for an evidence metric. Correctness is unaffected and keeps its system zeros.
    ``evidence_expected`` declares the task even when it produced no successful rows;
    an empty metric set then still identifies answered cells as missing downstream.
    """

    cell_by_id = {
        item.evaluation_id: (item.question_id, item.target_level, item.condition)
        for item in items
    }
    non_answers = {
        cell_by_id[item.evaluation_id]
        for item in items
        if item.technical_failure or item.abstained
    }
    cells = {
        "adaptation_criterion_pass_rate": non_answers
        | {cell_by_id[eid] for eid in adaptation_not_applicable_ids if eid in cell_by_id},
    }
    if not evidence_expected and not evidence_rows:
        # No evidence evaluation was supplied. Empty successful output alone cannot
        # establish this: all requests may instead be unresolved or not applicable.
        return cells
    cells["bundle_faithfulness"] = set(non_answers)
    cells["citation_support"] = set(non_answers)
    evaluable_fields = {
        "bundle_faithfulness": "evaluable_bundle_claim_count",
        "citation_support": "evaluable_citation_claim_count",
    }
    for row in evidence_rows:
        cell = cell_by_id.get(str(row.get("evaluation_id")))
        if cell is None:
            continue
        for metric, field in evaluable_fields.items():
            if row.get(metric) is None and row.get(field) == 0:
                cells[metric].add(cell)
    return cells


def _noise_floor_adaptation_applicable(
    item: GenerationEvaluationInput,
    adaptation: Mapping[str, Any],
) -> bool:
    """Match the main adaptation scope in the paired repeat comparison.

    Only full + endpoint_only questions enter, and never abstentions, technical
    failures or answers with no applicable checklist criterion.
    """

    nothing_evaluable = (
        adaptation.get("criterion_pass_rate") is None
        and adaptation.get("evaluable_criterion_count") == 0
    )
    return (
        not item.technical_failure
        and not item.abstained
        and item.target_level in eligible_levels(item.eligibility)
        and not nothing_evaluable
    )


def _applicability_summary(
    items: list[GenerationEvaluationInput],
    correctness_by_id: dict[str, int | None],
    adaptation_by_id: dict[str, float | None],
    *,
    adaptation_not_applicable_ids: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[GenerationEvaluationInput]] = defaultdict(list)
    for subset, subset_items in _eligibility_groups(items).items():
        for item in subset_items:
            groups[(subset, item.condition.value)].append(item)
    result = []
    labels = {value.value for value in PersonalisationEligibility}
    for (subset, condition), rows in sorted(groups.items()):
        correctness_values = [correctness_by_id.get(item.evaluation_id) for item in rows]
        correctness = [value for value in correctness_values if value is not None]
        strict_correct_count = sum(score == 2 for score in correctness)
        correctness_unresolved = len(rows) - len(correctness)
        substantive_rows = [
            item for item in rows if not item.technical_failure and not item.abstained
        ]
        adaptation = [
            adaptation_by_id[item.evaluation_id]
            for item in substantive_rows
            if adaptation_by_id.get(item.evaluation_id) is not None
        ]
        adaptation_expected = len(substantive_rows)
        not_applicable = sum(
            item.evaluation_id in adaptation_not_applicable_ids
            and adaptation_by_id.get(item.evaluation_id) is None
            for item in substantive_rows
        )
        adaptation_unresolved = adaptation_expected - len(adaptation) - not_applicable
        result.append(
            {
                "subset": subset,
                "eligibility": subset if subset in labels else None,
                "condition": condition,
                "answer_count": len(rows),
                "technical_failure_count": sum(item.technical_failure for item in rows),
                "correctness_scored_count": len(correctness),
                "correctness_unresolved_count": correctness_unresolved,
                "strict_correct_rate": (
                    strict_correct_count / len(rows)
                    if rows and correctness_unresolved == 0
                    else None
                ),
                "strict_correct_rate_bounds": [
                    strict_correct_count / len(rows) if rows else None,
                    (strict_correct_count + correctness_unresolved) / len(rows)
                    if rows
                    else None,
                ],
                "adaptation_expected_count": adaptation_expected,
                "adaptation_evaluable_count": len(adaptation),
                "adaptation_not_applicable_count": not_applicable,
                "adaptation_unresolved_count": adaptation_unresolved,
                "main_adaptation_answer_count": sum(
                    item.target_level in eligible_levels(item.eligibility) for item in rows
                ),
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
    if (args.correctness_scores is None) != (args.correctness_score_binding is None):
        raise ValueError(
            "--correctness-scores and --correctness-score-binding must be supplied together"
        )
    scores = {}
    if args.correctness_scores is not None:
        scores = load_open_answer_scores(
            args.correctness_scores,
            items,
            gold_sha256=str(manifest["gold_sha256"]),
            binding_path=args.correctness_score_binding,
            evaluation_inputs_sha256=actual_inputs_hash,
        )
    rubric_set_sha256 = (
        correctness_rubric_set_sha256(scores.values()) if scores else None
    )
    if (
        decision_config.correctness_rubric_set_sha256 is not None
        and rubric_set_sha256 is not None
        and rubric_set_sha256 != decision_config.correctness_rubric_set_sha256
    ):
        raise ValueError("correctness rubric set differs from decision config")

    input_validation = None
    if args.input_validation is not None:
        input_validation = _load_json_object(args.input_validation)
        validation_checks = {
            "valid": input_validation.get("valid") is True,
            "gold_sha256": input_validation.get("gold_sha256") == manifest.get("gold_sha256"),
            "eligibility_sha256": input_validation.get("eligibility_sha256")
            == manifest.get("input_sha256", {}).get("eligibility"),
            "question_count": input_validation.get("question_count")
            == manifest.get("question_count"),
        }
        if args.decision_config is not None:
            validation_checks["eligibility_definition_version"] = (
                input_validation.get("eligibility_package_version")
                == decision_config.eligibility_definition_version
            )
        failed = sorted(name for name, passed in validation_checks.items() if not passed)
        if failed:
            raise ValueError("input validation differs from adapted inputs: " + ", ".join(failed))
    correctness_rows = []
    correctness_by_id: dict[str, int | None] = {}
    observations = []
    unresolved = []
    for item in items:
        score = scores.get(item.evaluation_id)
        numeric = (
            0
            if item.source_status is not GenerationRunStatus.ANSWERED
            else (score.score if score and score.score_status == "scored" else None)
        )
        correctness_by_id[item.evaluation_id] = numeric
        correctness_rows.append(
            {
                "technical_failure": item.technical_failure,
                "abstained": item.abstained,
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
        if item.source_status is GenerationRunStatus.ANSWERED and (
            score is None or score.score_status != "scored"
        ):
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
        judge_provenance = judge_data["manifest"].get("provenance", {})
        if judge_provenance.get("evaluation_inputs_sha256") != actual_inputs_hash:
            raise ValueError("judge evaluation is bound to different evaluation inputs")
        if judge_provenance.get("source_run_sha256") != source_run_hash:
            raise ValueError("judge evaluation is bound to a different source run")
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
    adaptation_not_applicable_ids = frozenset(
        evaluation_id
        for evaluation_id, record in target_adaptation.items()
        if record.get("criterion_pass_rate") is None
        and record.get("evaluable_criterion_count") == 0
    )
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
    contrasts, eligibility_contrasts = _eligibility_condition_contrasts(
        items,
        observations,
        bootstrap_draws=args.bootstrap_draws,
        bootstrap_seed=args.bootstrap_seed,
        not_applicable_cells=_quality_not_applicable_cells(
            items,
            adaptation_not_applicable_ids=adaptation_not_applicable_ids,
            evidence_rows=evidence_rows,
            # The assembled judge directory covers all three tasks, including
            # unresolved requests and non-answers that require no judge call.
            evidence_expected=judge_data is not None,
        ),
    )
    validity = (
        _load_json_object(args.validity_report)
        if args.validity_report is not None
        else {"formal_use_allowed": False, "reason": "judge validation not supplied"}
    )
    if args.validity_report is not None:
        if judge_data is None:
            raise ValueError("a validity report requires the bound judge evaluation directory")
        validity_provenance = validity.get("provenance", {})
        expected_judge_manifest_hash = hashlib.sha256(
            (args.judge_evaluation_dir / "judge_evaluation_manifest.json").read_bytes()
        ).hexdigest()
        if validity_provenance.get("evaluation_inputs_sha256") != actual_inputs_hash:
            raise ValueError("validity report is bound to different evaluation inputs")
        if validity_provenance.get("source_run_sha256") != source_run_hash:
            raise ValueError("validity report is bound to a different source run")
        if (
            validity_provenance.get("judge_evaluation_manifest_sha256")
            != expected_judge_manifest_hash
        ):
            raise ValueError("validity report is bound to a different judge evaluation")
    if args.decision_config is not None and args.validity_report is not None:
        if validity.get("threshold_version") != decision_config.validity_threshold_version:
            raise ValueError("validity threshold version differs from decision config")
    if args.decision_config is not None and judge_data is not None:
        judge_version = judge_data["manifest"].get("provenance", {}).get("judge_config_version")
        if judge_version != decision_config.judge_config_version:
            raise ValueError("judge configuration version differs from decision config")
    audit_paths = (
        args.human_audit_ratings,
        args.human_audit_packet,
        args.human_audit_manifest,
        args.human_audit_private_key,
    )
    if any(path is not None for path in audit_paths) and not all(
        path is not None for path in audit_paths
    ):
        raise ValueError(
            "human audit requires ratings, packet, manifest, and private key together"
        )
    human_audit = None
    if args.human_audit_ratings is not None:
        expected_profile_hash = None
        if judge_data is not None:
            expected_profile_hash = judge_data["manifest"].get("provenance", {}).get(
                "profile_package_sha256"
            )
        human_audit = load_bound_human_audit(
            ratings_path=args.human_audit_ratings,
            audit_packet_path=args.human_audit_packet,
            manifest_path=args.human_audit_manifest,
            private_key_path=args.human_audit_private_key,
            expected_evaluation_inputs_sha256=actual_inputs_hash,
            expected_source_run_sha256=str(source_run_hash),
            expected_inputs=items,
            expected_profile_package_sha256=expected_profile_hash,
            expected_rubric_sha256=decision_config.human_audit_rubric_sha256,
        )
    joint_rows = [
        {
            "correctness_score": correctness_by_id.get(item.evaluation_id),
            "adaptation_passed": target_adaptation.get(item.evaluation_id, {}).get(
                "adaptation_passed"
            ),
            "technical_failure": item.technical_failure,
            "end_to_end_zero": item.source_status is not GenerationRunStatus.ANSWERED,
        }
        for item in items
        if item.target_level in eligible_levels(item.eligibility)
    ]
    repeat_paths = (
        args.generation_repeat_inputs,
        args.generation_repeat_adapter_manifest,
        args.generation_repeat_correctness_scores,
        args.generation_repeat_correctness_score_binding,
        args.generation_repeat_judge_evaluation_dir,
    )
    if any(path is not None for path in repeat_paths) and not all(
        path is not None for path in repeat_paths
    ):
        raise ValueError(
            "generation repeat comparison requires inputs, adapter manifest, correctness "
            "scores, score binding, and judge evaluation directory together"
        )
    paired_noise: dict[str, Any] = {
        "status": "not_supplied",
        "interpretation": (
            "A 30-question repeated generation batch is required to estimate generation noise; "
            "judge repeat agreement measures only judge variability."
        ),
    }
    repeat_provenance: dict[str, Any] | None = None
    if args.generation_repeat_inputs is not None:
        if not scores or judge_data is None:
            raise ValueError(
                "generation repeat comparison requires baseline correctness and judge outputs"
            )
        repeat_items = _load_inputs(args.generation_repeat_inputs)
        repeat_manifest = _load_json_object(args.generation_repeat_adapter_manifest)
        repeat_inputs_hash = hashlib.sha256(args.generation_repeat_inputs.read_bytes()).hexdigest()
        if (
            repeat_manifest.get("output_sha256", {}).get("generation_evaluation_inputs")
            != repeat_inputs_hash
        ):
            raise ValueError("repeat inputs do not match the repeat adapter manifest hash")
        repeat_source_run = repeat_manifest.get("source_run_sha256")
        if repeat_source_run == source_run_hash:
            raise ValueError("generation repeat batch must come from a distinct source run")
        if repeat_source_run is None or any(
            item.source_run_sha256 != repeat_source_run for item in repeat_items
        ):
            raise ValueError("repeat inputs do not match the repeat adapter source run")
        if repeat_manifest.get("gold_sha256") != manifest.get("gold_sha256"):
            raise ValueError("generation baseline and repeat must use the same Gold bytes")
        if repeat_manifest.get("input_sha256", {}).get("lambda_selection") != manifest.get(
            "input_sha256", {}
        ).get("lambda_selection"):
            raise ValueError("generation baseline and repeat must use the same frozen lambda")
        repeat_scores = load_open_answer_scores(
            args.generation_repeat_correctness_scores,
            repeat_items,
            gold_sha256=str(repeat_manifest["gold_sha256"]),
            binding_path=args.generation_repeat_correctness_score_binding,
            evaluation_inputs_sha256=repeat_inputs_hash,
        )
        _validate_generation_repeat_rubrics(
            scores,
            repeat_scores,
            items,
            repeat_items,
        )
        baseline_correctness_configs = {
            score.judge_config_sha256
            for score in scores.values()
            if score.judge_config_sha256 is not None
        }
        repeat_correctness_configs = {
            score.judge_config_sha256
            for score in repeat_scores.values()
            if score.judge_config_sha256 is not None
        }
        if len(baseline_correctness_configs) > 1 or len(repeat_correctness_configs) > 1:
            raise ValueError("each generation batch must use one frozen correctness judge")
        if repeat_correctness_configs != baseline_correctness_configs:
            raise ValueError("generation baseline and repeat must use the same correctness judge")
        repeat_judge = load_judge_evaluation_outputs(
            args.generation_repeat_judge_evaluation_dir
        )
        _validate_generation_repeat_judge(
            judge_data["manifest"].get("provenance", {}),
            repeat_judge["manifest"].get("provenance", {}),
            repeat_inputs_hash=repeat_inputs_hash,
            repeat_source_run=str(repeat_source_run),
        )
        repeat_adaptation_records = list(repeat_judge["adaptation"])
        if decision_config.adaptation_pass_threshold is not None:
            repeat_adaptation_records = [
                apply_adaptation_threshold(
                    record, threshold=decision_config.adaptation_pass_threshold
                )
                for record in repeat_adaptation_records
            ]
        repeat_target_adaptation = {
            str(record["evaluation_id"]): record
            for record in repeat_adaptation_records
            if record.get("is_target_level_evaluation")
        }

        def paired_row(
            item: GenerationEvaluationInput,
            item_scores: dict[str, Any],
            item_adaptation: dict[str, dict[str, Any]],
        ) -> dict[str, Any]:
            score = item_scores.get(item.evaluation_id)
            numeric = (
                0
                if item.source_status is not GenerationRunStatus.ANSWERED
                else (score.score if score and score.score_status == "scored" else None)
            )
            adaptation = item_adaptation.get(item.evaluation_id, {})
            return {
                "adaptation_applicable": _noise_floor_adaptation_applicable(
                    item, adaptation
                ),
                "run_id": item.run_id,
                "question_id": item.question_id,
                "target_level": item.target_level.value,
                "condition": item.condition.value,
                "generation_model_family": item.generation_model_family,
                "generation_model_revision": item.generation_model_revision,
                "correctness_score": numeric,
                "adaptation_criterion_pass_rate": adaptation.get("criterion_pass_rate"),
                "adaptation_passed": adaptation.get("adaptation_passed"),
            }

        strict_contrasts = {
            str(row["contrast"]): row
            for row in contrasts
            if row.get("metric") == "strict_correct"
            and int(row.get("paired_question_level_count", 0) or 0) > 0
        }
        main_comparison: dict[str, Any] | None = None
        primary_contrast = decision_config.primary_contrast
        if primary_contrast is not None and primary_contrast in strict_contrasts:
            treatment, control = CONTRASTS[primary_contrast]
            main_comparison = {
                "contrast": primary_contrast,
                "conditions": [treatment.value, control.value],
                "paired_cell_count": int(
                    strict_contrasts[primary_contrast]["paired_question_level_count"]
                ),
                "cell_count_source": "registered primary strict_correct contrast on Dev",
            }
        elif primary_contrast is None and strict_contrasts:
            main_comparison = {
                "contrast": None,
                "conditions": [],
                "paired_cell_count": min(
                    int(row["paired_question_level_count"])
                    for row in strict_contrasts.values()
                ),
                "cell_count_source": (
                    "smallest strict_correct contrast on Dev (no registered primary contrast)"
                ),
            }
        paired_noise = paired_generation_noise_floor(
            [paired_row(item, scores, target_adaptation) for item in items],
            [
                paired_row(item, repeat_scores, repeat_target_adaptation)
                for item in repeat_items
            ],
            correctness_delta=decision_config.correctness_noninferiority_delta,
            main_comparison=main_comparison,
            adaptation_threshold_frozen=decision_config.adaptation_pass_threshold is not None,
        )
        repeat_provenance = {
            "adapter_manifest": repeat_manifest,
            "evaluation_inputs_sha256": repeat_inputs_hash,
            "correctness_scores_sha256": hashlib.sha256(
                args.generation_repeat_correctness_scores.read_bytes()
            ).hexdigest(),
            "correctness_score_binding_sha256": hashlib.sha256(
                args.generation_repeat_correctness_score_binding.read_bytes()
            ).hexdigest(),
            "judge_evaluation_manifest": repeat_judge["manifest"],
        }
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
            | {
                "evaluation_id": item.evaluation_id,
                "question_id": item.question_id,
                "condition": item.condition.value,
                "lambda_weight": item.lambda_weight,
            }
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
        eligibility_condition_contrasts=eligibility_contrasts,
        lambda_evaluation=manifest.get("lambda_selection"),
        generation_noise={
            "paired_repeat_batch": paired_noise,
            "same_prompt_answer_mismatch_diagnostic": generation_noise_floor(items),
        },
        applicability_summary=_applicability_summary(
            items,
            correctness_by_id,
            adaptation_by_id,
            adaptation_not_applicable_ids=adaptation_not_applicable_ids,
        ),
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
            "correctness_score_binding_sha256": (
                hashlib.sha256(args.correctness_score_binding.read_bytes()).hexdigest()
                if args.correctness_score_binding is not None
                else None
            ),
            "correctness_rubric_set_sha256": rubric_set_sha256,
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
            "generation_repeat": repeat_provenance,
            "input_validation": input_validation,
            "input_validation_sha256": (
                hashlib.sha256(args.input_validation.read_bytes()).hexdigest()
                if args.input_validation is not None
                else None
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
            "human_audit_manifest_sha256": (
                hashlib.sha256(args.human_audit_manifest.read_bytes()).hexdigest()
                if args.human_audit_manifest is not None
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
        if args.command == "run-judge-requests":
            return _run_judge_requests(args)
        if args.command == "condition-stats":
            return _condition_stats(args)
        if args.command == "prepare-audit":
            return _prepare_audit(args)
        if args.command == "adapt-m7-artifacts":
            return _adapt_m7_artifacts(args)
        if args.command == "bind-correctness-scores":
            return _bind_correctness_scores(args)
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
