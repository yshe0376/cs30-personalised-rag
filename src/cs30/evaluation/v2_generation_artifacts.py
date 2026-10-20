"""Hash-bound adapters from M7 generation artifacts into M8 evaluation inputs.

This module consumes teammate-owned contracts without redefining or mutating them.
It fails closed on identity, coverage, status, citation, and provenance mismatches.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cs30.contracts import StudentLevel

from .condition_statistics import verify_dev_lambda_selection
from .level_profiles import canonical_json_sha256
from .models import PersonalisationEligibility
from .open_answer_models import OpenAnswerScore
from .v2_generation_models import (
    CorrectnessScoreBinding,
    EvaluationEvidence,
    ExperimentArm,
    GenerationEvaluationInput,
    GenerationRunStatus,
)

FROZEN_DEV_LAMBDA_GRID = (0.0, 0.1, 0.2, 0.35, 0.5)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _index(rows: Sequence[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key, ""))
        if not value:
            raise ValueError(f"{label}: missing {key}")
        if value in result:
            raise ValueError(f"{label}: duplicate {key}={value}")
        result[value] = row
    return result


def _assert_exact_coverage(expected: set[str], actual: set[str], label: str) -> None:
    if expected != actual:
        raise ValueError(
            f"{label} coverage mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _split_model(model: str) -> tuple[str, str]:
    family, separator, revision = model.partition(":")
    return family, revision if separator else "unspecified"


def _validate_manifest_hashes(
    manifest: Mapping[str, Any],
    *,
    expected_path: Path,
    records_path: Path,
    answers_path: Path,
    gold_path: Path,
    lambda_selection_path: Path,
) -> None:
    prepared = manifest.get("prepared_inputs") or {}
    input_hashes = prepared.get("input_sha256") or {}
    declared_gold = input_hashes.get("gold.jsonl")
    if declared_gold != file_sha256(gold_path):
        raise ValueError("run manifest Gold hash does not match the supplied Gold bytes")
    declared_lambda = input_hashes.get("lambda_selection.json")
    if declared_lambda != file_sha256(lambda_selection_path):
        raise ValueError("run manifest lambda-selection hash does not match the supplied bytes")
    output_hashes = manifest.get("output_sha256") or {}
    for filename, path in (
        ("expected_experiment.json", expected_path),
        ("generation_records.jsonl", records_path),
        ("saved_answers.jsonl", answers_path),
    ):
        declared = output_hashes.get(filename)
        if declared is None:
            raise ValueError(f"run manifest is missing output_sha256[{filename!r}]")
        if declared != file_sha256(path):
            raise ValueError(f"run manifest hash mismatch for {filename}")


def _validate_condition_trace(case: Mapping[str, Any], record: Mapping[str, Any]) -> float:
    condition = ExperimentArm(str(case["condition_id"]))
    reranked = condition in {
        ExperimentArm.P0R1_RERANKING_ONLY,
        ExperimentArm.P1R1_COMBINED,
    }
    personalised = condition in {
        ExperimentArm.P1R0_PROMPT_ONLY,
        ExperimentArm.P1R1_COMBINED,
    }
    rerank_trace = record.get("rerank_trace")
    if reranked:
        if not isinstance(rerank_trace, dict) or not rerank_trace.get("enabled"):
            raise ValueError(f"{case['run_id']}: R1 cell is missing an enabled rerank trace")
        lambda_weight = float(rerank_trace.get("effective_lambda", 0.0))
        if lambda_weight <= 0.0:
            raise ValueError(f"{case['run_id']}: R1 cell requires positive effective lambda")
    else:
        if rerank_trace is not None:
            raise ValueError(f"{case['run_id']}: R0 cell must not contain a rerank trace")
        lambda_weight = 0.0
    generation_trace = record.get("generation_trace") or {}
    if bool(generation_trace.get("prompt_personalised")) != personalised:
        raise ValueError(f"{case['run_id']}: prompt personalisation disagrees with condition")
    effective_level = generation_trace.get("effective_level")
    if personalised and effective_level != case["student_level"]:
        raise ValueError(f"{case['run_id']}: personalised prompt has the wrong effective level")
    if not personalised and effective_level is not None:
        raise ValueError(f"{case['run_id']}: P0 prompt must not have an effective level")
    return lambda_weight


def adapt_m7_generation_artifacts(
    *,
    expected_path: Path,
    records_path: Path,
    answers_path: Path,
    run_manifest_path: Path,
    gold_path: Path,
    eligibility_path: Path,
    lambda_selection_path: Path,
) -> tuple[list[GenerationEvaluationInput], dict[str, Any]]:
    """Validate one complete M7 bundle and return M8-owned evaluation records."""

    expected = _read_json(expected_path)
    manifest = _read_json(run_manifest_path)
    lambda_selection = _read_json(lambda_selection_path)
    if expected.get("schema_version") != "0.2":
        raise ValueError("expected experiment must use GenerationExperiment schema 0.2")
    expected_rows = list(expected.get("cases") or [])
    expected_question_ids = {str(row.get("question_id", "")) for row in expected_rows}
    gold_hash = file_sha256(gold_path)
    if expected.get("gold_sha256") != gold_hash:
        raise ValueError("expected experiment Gold hash does not match supplied Gold bytes")
    _validate_manifest_hashes(
        manifest,
        expected_path=expected_path,
        records_path=records_path,
        answers_path=answers_path,
        gold_path=gold_path,
        lambda_selection_path=lambda_selection_path,
    )
    if lambda_selection.get("schema_version") != "0.2":
        raise ValueError("lambda selection must use schema 0.2")
    if lambda_selection.get("selected_on_split") != "dev":
        raise ValueError("lambda selection must be frozen on Dev")
    if lambda_selection.get("objective") != "largest_positive_lambda_within_1pt_of_baseline":
        raise ValueError("lambda selection uses an unsupported objective")
    if float(lambda_selection.get("noninferiority_margin", -1)) != 0.01:
        raise ValueError("lambda selection must use the frozen one-percentage-point margin")
    selection_gold_hash = str(lambda_selection.get("gold_sha256") or "")
    if len(selection_gold_hash) != 64 or any(
        character not in "0123456789abcdef" for character in selection_gold_hash
    ):
        raise ValueError("lambda selection must bind its own Gold with a SHA-256 digest")
    gold_rows = _read_jsonl(gold_path)
    candidate_lambdas = tuple(
        float(value) for value in lambda_selection.get("candidate_lambdas") or []
    )
    if candidate_lambdas != FROZEN_DEV_LAMBDA_GRID:
        raise ValueError(
            "lambda selection candidate grid differs from the frozen Dev grid "
            f"{list(FROZEN_DEV_LAMBDA_GRID)}"
        )
    metric_rows = list(lambda_selection.get("metrics") or [])
    metrics_by_lambda: dict[float, dict[str, Any]] = {}
    selection_identities: set[tuple[str, str]] | None = None
    for row in metric_rows:
        candidate = float(row["lambda_weight"])
        if candidate in metrics_by_lambda:
            raise ValueError(f"lambda selection repeats metric row for lambda={candidate}")
        case_count = int(row.get("case_count", 0))
        if case_count < 1:
            raise ValueError(f"lambda={candidate} must report a positive case_count")
        if "mean_span_coverage" not in row:
            raise ValueError(f"lambda={candidate} is missing mean_span_coverage")
        cases_for_candidate = list(row.get("cases") or [])
        if not cases_for_candidate:
            raise ValueError(f"lambda={candidate} must include its per-question case records")
        identities = [
            (str(case.get("question_id", "")), str(case.get("level", "")))
            for case in cases_for_candidate
        ]
        identity_set = set(identities)
        if (
            len(cases_for_candidate) != case_count
            or len(identities) != len(identity_set)
            or any(not question_id for question_id, _level in identities)
        ):
            raise ValueError(f"lambda={candidate} case rows must be unique and match case_count")
        invalid_levels = sorted(
            {level for _question_id, level in identity_set}
            - {level.value for level in StudentLevel}
        )
        if invalid_levels:
            raise ValueError(f"lambda={candidate} uses unsupported levels: {invalid_levels}")
        levels_by_question = {
            question_id: {
                level
                for observed_question, level in identity_set
                if observed_question == question_id
            }
            for question_id, _level in identity_set
        }
        incomplete = sorted(
            question_id
            for question_id, levels in levels_by_question.items()
            if levels != {level.value for level in StudentLevel}
        )
        if incomplete:
            raise ValueError(
                f"lambda={candidate} does not contain all three levels for questions: {incomplete}"
            )
        try:
            observed_hits = [case["complete_hit"] for case in cases_for_candidate]
            observed_coverage = [float(case["span_coverage"]) for case in cases_for_candidate]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"lambda={candidate} has invalid per-question metrics") from exc
        if any(type(value) is not bool for value in observed_hits):
            raise ValueError(f"lambda={candidate} complete_hit values must be booleans")
        if any(not 0.0 <= value <= 1.0 for value in observed_coverage):
            raise ValueError(f"lambda={candidate} span_coverage values must be in [0, 1]")
        recomputed_hit_rate = sum(observed_hits) / case_count
        recomputed_span_coverage = sum(observed_coverage) / case_count
        declared_hit_rate = float(row["complete_hit_rate"])
        declared_span_coverage = float(row["mean_span_coverage"])
        if not math.isfinite(declared_hit_rate) or not math.isfinite(declared_span_coverage):
            raise ValueError(f"lambda={candidate} aggregate metrics must be finite")
        if abs(declared_hit_rate - recomputed_hit_rate) > 1e-12:
            raise ValueError(f"lambda={candidate} complete_hit_rate does not match its cases")
        if abs(declared_span_coverage - recomputed_span_coverage) > 1e-12:
            raise ValueError(f"lambda={candidate} mean_span_coverage does not match its cases")
        if selection_identities is None:
            selection_identities = identity_set
        elif identity_set != selection_identities:
            raise ValueError("lambda candidates must use the same internal question/level cases")
        metrics_by_lambda[candidate] = row
    if set(metrics_by_lambda) != set(candidate_lambdas):
        raise ValueError("lambda metric coverage must exactly match candidate_lambdas")
    case_counts = {int(row["case_count"]) for row in metrics_by_lambda.values()}
    if len(case_counts) != 1:
        raise ValueError("every lambda candidate must use the same case_count")
    complete_hit_rates = {
        candidate: float(row["complete_hit_rate"])
        for candidate, row in metrics_by_lambda.items()
    }
    lambda_verification = verify_dev_lambda_selection(
        complete_hit_rates=complete_hit_rates,
        selected_lambda=float(lambda_selection["lambda_weight"]),
        margin=0.01,
    )
    for row in lambda_verification["candidates"]:
        source = metrics_by_lambda[float(row["lambda"])]
        row["case_count"] = int(source["case_count"])
        row["mean_span_coverage"] = float(source["mean_span_coverage"])
    cases = _index(expected_rows, "run_id", "expected experiment")
    logical_cells = [
        (
            str(case.get("question_id", "")),
            str(case.get("student_level", "")),
            str(case.get("condition_id", "")),
        )
        for case in expected_rows
    ]
    if len(logical_cells) != len(set(logical_cells)):
        raise ValueError("expected experiment repeats a question/level/condition cell")
    required_cells = {
        (level.value, condition.value) for level in StudentLevel for condition in ExperimentArm
    }
    observed_by_question = {
        question_id: {
            (level, condition)
            for observed_question, level, condition in logical_cells
            if observed_question == question_id
        }
        for question_id in expected_question_ids
    }
    incomplete_questions = sorted(
        question_id
        for question_id, observed in observed_by_question.items()
        if observed != required_cells
    )
    records = _index(_read_jsonl(records_path), "run_id", "generation records")
    answers = _index(_read_jsonl(answers_path), "run_id", "saved answers")
    _assert_exact_coverage(set(cases), set(records), "generation records")
    _assert_exact_coverage(set(cases), set(answers), "saved answers")
    gold = _index(gold_rows, "question_id", "Gold")
    eligibility_rows = _index(_read_jsonl(eligibility_path), "question_id", "eligibility")
    expected_questions = {str(case["question_id"]) for case in cases.values()}
    _assert_exact_coverage(expected_questions, set(eligibility_rows), "eligibility")
    missing_gold = expected_questions - set(gold)
    if missing_gold:
        raise ValueError(f"Gold is missing expected questions: {sorted(missing_gold)}")

    roles_by_question_level: dict[tuple[str, str], dict[str, str]] = {}
    for run_id, case in cases.items():
        condition = ExperimentArm(str(case["condition_id"]))
        if condition not in {
            ExperimentArm.P0R1_RERANKING_ONLY,
            ExperimentArm.P1R1_COMBINED,
        }:
            continue
        candidates = (records[run_id].get("rerank_trace") or {}).get("candidates") or []
        role_map: dict[str, str] = {}
        for candidate in candidates:
            chunk_id = str(candidate.get("chunk_id") or "")
            role = str(candidate.get("role") or "")
            if not chunk_id or not role:
                raise ValueError(f"{run_id}: R1 candidates require nonempty chunk_id and role")
            if chunk_id in role_map:
                raise ValueError(f"{run_id}: R1 candidates repeat chunk_id={chunk_id}")
            role_map[chunk_id] = role
        key = (str(case["question_id"]), str(case["student_level"]))
        shared_roles = roles_by_question_level.setdefault(key, {})
        for chunk_id, role in role_map.items():
            existing_role = shared_roles.get(chunk_id)
            if existing_role is not None and existing_role != role:
                raise ValueError(
                    f"{run_id}: R1 Role labels disagree for chunk {chunk_id} in "
                    f"question/level {key[0]}/{key[1]}"
                )
            shared_roles[chunk_id] = role

    source_hash = file_sha256(records_path)
    source_run_hash = file_sha256(run_manifest_path)
    seed = (manifest.get("client") or {}).get("seed")
    converted: list[GenerationEvaluationInput] = []
    for run_id, case in cases.items():
        record = records[run_id]
        saved = answers[run_id]
        identity_fields = (
            "run_id",
            "question_id",
            "condition_id",
            "student_level",
            "generator_model",
        )
        for field in identity_fields:
            if record.get(field) != case.get(field) or saved.get(field) != case.get(field):
                raise ValueError(
                    f"{run_id}: {field} differs across expected, trace, and saved answer"
                )
        for field in ("status", "answer", "error"):
            if record.get(field) != saved.get(field):
                raise ValueError(f"{run_id}: {field} differs between trace and saved answer")
        try:
            status = GenerationRunStatus(str(saved["status"]))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{run_id}: unsupported run status") from exc
        lambda_weight = _validate_condition_trace(case, record)
        answer_payload = saved.get("answer")
        answer_text = (
            answer_payload.get("explanation") if isinstance(answer_payload, dict) else None
        )
        answer_hash = (
            hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
            if answer_text is not None
            else None
        )
        citations = (
            list(answer_payload.get("citations") or []) if isinstance(answer_payload, dict) else []
        )
        abstained = status is GenerationRunStatus.ABSTAINED
        technical_failure = status.is_technical_failure
        if (
            status in {GenerationRunStatus.ANSWERED, GenerationRunStatus.ABSTAINED}
            and not answer_text
        ):
            raise ValueError(f"{run_id}: completed status requires explanation text")
        if technical_failure and answer_text is not None:
            raise ValueError(f"{run_id}: technical failure must not contain answer text")
        evidence_bundle = record.get("evidence") or {}
        role_key = (str(case["question_id"]), str(case["student_level"]))
        roles = roles_by_question_level.get(role_key)
        if roles is None:
            raise ValueError(
                f"{run_id}: no R1 Role-label trace is available for {role_key[0]}/{role_key[1]}"
            )
        evidence = [
            EvaluationEvidence(
                evidence_id=str(item["chunk_id"]),
                text=str(item["text"]),
                rank=int(item["rank"]),
                role=roles.get(str(item["chunk_id"])),
                source_locator=item.get("source_locator"),
            )
            for item in evidence_bundle.get("evidence_items") or []
        ]
        missing_roles = sorted(item.evidence_id for item in evidence if item.role is None)
        if missing_roles:
            raise ValueError(
                f"{run_id}: evidence chunks are missing Role labels from the paired R1 trace: "
                f"{missing_roles}"
            )
        evidence_ids = {item.evidence_id for item in evidence}
        unknown_citations = set(citations) - evidence_ids
        if unknown_citations:
            raise ValueError(
                f"{run_id}: citations reference unsupplied evidence: {sorted(unknown_citations)}"
            )
        family, revision = _split_model(str(case["generator_model"]))
        failure_reason = None
        if technical_failure:
            failure_reason = str(saved.get("error") or status.value)
        eligibility = PersonalisationEligibility(
            str(eligibility_rows[str(case["question_id"])]["eligibility"])
        )
        prompt_sha256 = (record.get("generation_trace") or {}).get("prompt_sha256")
        if prompt_sha256 is not None:
            prompt_sha256 = str(prompt_sha256)
        if not technical_failure and prompt_sha256 is None:
            raise ValueError(f"{run_id}: completed generation is missing prompt_sha256")
        identity_hash = canonical_json_sha256(
            {
                "source_run_sha256": source_run_hash,
                "run_id": run_id,
                "answer_sha256": answer_hash,
                "source_status": status.value,
            }
        )
        converted.append(
            GenerationEvaluationInput(
                evaluation_id=f"evaluation-{identity_hash[:24]}",
                run_id=run_id,
                question_id=str(case["question_id"]),
                question=str(gold[str(case["question_id"])]["question"]),
                answer=answer_text,
                target_level=str(case["student_level"]),
                condition=str(case["condition_id"]),
                lambda_weight=lambda_weight,
                generation_model_family=family,
                generation_model_revision=revision,
                source_split=str(gold[str(case["question_id"])].get("split") or "dev"),
                generation_seed=seed,
                prompt_sha256=prompt_sha256,
                eligibility=eligibility,
                evidence=evidence,
                citation_ids=citations,
                source_status=status,
                abstained=abstained,
                technical_failure=technical_failure,
                failure_reason=failure_reason,
                source_artifact_sha256=source_hash,
                source_run_sha256=source_run_hash,
                answer_sha256=answer_hash,
            )
        )
    selected_lambda = float(lambda_selection["lambda_weight"])
    observed_r1 = {
        item.lambda_weight
        for item in converted
        if item.condition in {ExperimentArm.P0R1_RERANKING_ONLY, ExperimentArm.P1R1_COMBINED}
    }
    if observed_r1 != {selected_lambda}:
        raise ValueError("R1 cells do not all use the lambda selected by the frozen Dev artifact")
    adapter_manifest = {
        "schema_version": "1.0",
        "adapter": "m7-generation-0.2-to-m8-evaluation-1.0",
        "matrix_version": expected.get("matrix_version"),
        "gold_sha256": gold_hash,
        "source_run_sha256": source_run_hash,
        "input_sha256": {
            "expected_experiment": file_sha256(expected_path),
            "generation_records": source_hash,
            "saved_answers": file_sha256(answers_path),
            "run_manifest": file_sha256(run_manifest_path),
            "eligibility": file_sha256(eligibility_path),
            "lambda_selection": file_sha256(lambda_selection_path),
        },
        "record_count": len(converted),
        "question_count": len(expected_question_ids),
        "matrix_complete": not incomplete_questions,
        "incomplete_matrix_question_ids": incomplete_questions,
        "status_counts": dict(Counter(item.source_status.value for item in converted)),
        "lambda_selection": lambda_verification,
        "lambda_selection_gold_sha256": selection_gold_hash,
        "reportable": False,
        "claim_boundary": "Validated development adapter output; not a formal evaluation result.",
    }
    return converted, adapter_manifest


def _generator_model_id(item: GenerationEvaluationInput) -> str:
    if item.generation_model_revision == "unspecified":
        return item.generation_model_family
    return f"{item.generation_model_family}:{item.generation_model_revision}"


def _score_identity_sha256(inputs: Sequence[GenerationEvaluationInput]) -> str:
    return canonical_json_sha256(
        sorted(
            (
                {
                    "evaluation_id": item.evaluation_id,
                    "run_id": item.run_id,
                    "answer_sha256": item.answer_sha256,
                    "source_status": item.source_status.value,
                }
                for item in inputs
            ),
            key=lambda row: row["evaluation_id"],
        )
    )


def correctness_rubric_set_sha256(scores: Iterable[OpenAnswerScore]) -> str:
    """Hash the exact per-question correctness rubrics used for answered rows."""

    by_question: dict[str, str] = {}
    for score in scores:
        if score.run_status != GenerationRunStatus.ANSWERED.value:
            continue
        if score.rubric_sha256 is None:
            raise ValueError(f"{score.run_id}: answered score is missing a rubric hash")
        previous = by_question.setdefault(score.question_id, score.rubric_sha256)
        if previous != score.rubric_sha256:
            raise ValueError(
                f"{score.question_id}: correctness scores use conflicting rubric hashes"
            )
    if not by_question:
        raise ValueError("correctness scores contain no answered-question rubrics")
    return canonical_json_sha256(
        [
            {"question_id": question_id, "rubric_sha256": rubric_sha256}
            for question_id, rubric_sha256 in sorted(by_question.items())
        ]
    )


def _validated_open_answer_scores(
    score_path: Path,
    inputs: Sequence[GenerationEvaluationInput],
    *,
    gold_sha256: str,
) -> dict[str, OpenAnswerScore]:
    """Validate handoff rows before a run-specific sidecar is created or consumed."""

    try:
        scores = [OpenAnswerScore.model_validate(row) for row in _read_jsonl(score_path)]
    except ValidationError as exc:
        raise ValueError(f"{score_path}: invalid open-answer score: {exc}") from exc
    by_identity = {(item.run_id, item.answer_sha256): item for item in inputs}
    if len(by_identity) != len(inputs):
        raise ValueError("adapted inputs repeat run_id + answer_sha256 within one scoring bundle")
    indexed = {(item.run_id, item.answer_sha256): item for item in scores}
    if len(indexed) != len(scores):
        raise ValueError("open-answer scores contain duplicate run/answer identities")
    _assert_exact_coverage(set(by_identity), set(indexed), "open-answer scores")
    result: dict[str, OpenAnswerScore] = {}
    for identity, score in indexed.items():
        source = by_identity[identity]
        run_id = source.run_id
        if score.gold_sha256 != gold_sha256:
            raise ValueError(f"{run_id}: score Gold hash mismatch")
        if (
            score.question_id != source.question_id
            or score.condition_id != source.condition.value
            or score.student_level.value != source.target_level.value
            or score.generator_model != _generator_model_id(source)
            or score.split != source.source_split
        ):
            raise ValueError(f"{run_id}: score identity differs from adapted input")
        if score.run_status != source.source_status.value:
            raise ValueError(f"{run_id}: score status differs from adapted input")
        expected_answer_hash = source.answer_sha256
        if score.answer_sha256 != expected_answer_hash:
            raise ValueError(f"{run_id}: score answer hash mismatch")
        if source.source_status is GenerationRunStatus.ANSWERED and score.rubric_sha256 is None:
            raise ValueError(f"{run_id}: answered score is missing a rubric hash")
        if source.source_status is not GenerationRunStatus.ANSWERED and not (
            score.score_status == "scored"
            and score.score == 0
            and score.scoring_source == "system"
        ):
            raise ValueError(f"{run_id}: non-answer status must have a system score of zero")
        result[source.evaluation_id] = score
    correctness_rubric_set_sha256(result.values())
    return result


def build_correctness_score_binding(
    score_path: Path,
    inputs: Sequence[GenerationEvaluationInput],
    *,
    evaluation_inputs_sha256: str,
    gold_sha256: str,
) -> CorrectnessScoreBinding:
    """Create an explicit M8 binding after validating every imported score row."""

    scores = _validated_open_answer_scores(score_path, inputs, gold_sha256=gold_sha256)
    source_runs = {item.source_run_sha256 for item in inputs}
    if None in source_runs or len(source_runs) != 1:
        raise ValueError("correctness-score binding requires exactly one source run")
    return CorrectnessScoreBinding(
        score_sha256=file_sha256(score_path),
        evaluation_inputs_sha256=evaluation_inputs_sha256,
        source_run_sha256=str(next(iter(source_runs))),
        gold_sha256=gold_sha256,
        record_count=len(scores),
        identity_set_sha256=_score_identity_sha256(inputs),
        rubric_set_sha256=correctness_rubric_set_sha256(scores.values()),
        generator_models=sorted({_generator_model_id(item) for item in inputs}),
        source_splits=sorted({item.source_split for item in inputs}),
    )


def write_correctness_score_binding(
    binding: CorrectnessScoreBinding,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(binding.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return path


def load_open_answer_scores(
    score_path: Path,
    inputs: Sequence[GenerationEvaluationInput],
    *,
    gold_sha256: str,
    binding_path: Path,
    evaluation_inputs_sha256: str,
) -> dict[str, OpenAnswerScore]:
    """Load correctness scores only when their M8 run binding matches exactly."""

    try:
        binding = CorrectnessScoreBinding.model_validate_json(
            binding_path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"{binding_path}: invalid correctness-score binding: {exc}") from exc
    scores = _validated_open_answer_scores(score_path, inputs, gold_sha256=gold_sha256)
    source_runs = {item.source_run_sha256 for item in inputs}
    expected_source_run = next(iter(source_runs)) if len(source_runs) == 1 else None
    expected = {
        "score_sha256": file_sha256(score_path),
        "evaluation_inputs_sha256": evaluation_inputs_sha256,
        "source_run_sha256": expected_source_run,
        "gold_sha256": gold_sha256,
        "record_count": len(inputs),
        "identity_set_sha256": _score_identity_sha256(inputs),
        "rubric_set_sha256": correctness_rubric_set_sha256(scores.values()),
        "generator_models": sorted({_generator_model_id(item) for item in inputs}),
        "source_splits": sorted({item.source_split for item in inputs}),
    }
    actual = binding.model_dump(mode="json")
    mismatches = [name for name, value in expected.items() if actual.get(name) != value]
    if mismatches:
        raise ValueError(
            "correctness-score binding differs from the current source run: "
            + ", ".join(mismatches)
        )
    return scores


def write_adapter_outputs(
    items: Sequence[GenerationEvaluationInput], manifest: Mapping[str, Any], output_dir: Path
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_path = output_dir / "generation_evaluation_inputs.jsonl"
    manifest_path = output_dir / "adapter_manifest.json"
    with inputs_path.open("w", encoding="utf-8", newline="\n") as stream:
        for item in items:
            stream.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")
    written_manifest = dict(manifest)
    written_manifest["output_sha256"] = {
        "generation_evaluation_inputs": file_sha256(inputs_path),
    }
    manifest_path.write_text(
        json.dumps(written_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"inputs": inputs_path, "manifest": manifest_path}
