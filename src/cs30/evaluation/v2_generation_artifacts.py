"""Hash-bound adapters from M7 generation artifacts into M8 evaluation inputs.

This module consumes teammate-owned contracts without redefining or mutating them.
It fails closed on identity, coverage, status, citation, and provenance mismatches.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import PersonalisationEligibility
from .open_answer_models import OpenAnswerScore
from .v2_generation_models import (
    EvaluationEvidence,
    ExperimentArm,
    GenerationEvaluationInput,
    GenerationRunStatus,
)


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
) -> None:
    prepared = manifest.get("prepared_inputs") or {}
    input_hashes = prepared.get("input_sha256") or {}
    declared_gold = input_hashes.get("gold.jsonl")
    if declared_gold != file_sha256(gold_path):
        raise ValueError("run manifest Gold hash does not match the supplied Gold bytes")
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
) -> tuple[list[GenerationEvaluationInput], dict[str, Any]]:
    """Validate one complete M7 bundle and return M8-owned evaluation records."""

    expected = _read_json(expected_path)
    manifest = _read_json(run_manifest_path)
    if expected.get("schema_version") != "0.2":
        raise ValueError("expected experiment must use GenerationExperiment schema 0.2")
    gold_hash = file_sha256(gold_path)
    if expected.get("gold_sha256") != gold_hash:
        raise ValueError("expected experiment Gold hash does not match supplied Gold bytes")
    _validate_manifest_hashes(
        manifest,
        expected_path=expected_path,
        records_path=records_path,
        answers_path=answers_path,
        gold_path=gold_path,
    )
    cases = _index(list(expected.get("cases") or []), "run_id", "expected experiment")
    records = _index(_read_jsonl(records_path), "run_id", "generation records")
    answers = _index(_read_jsonl(answers_path), "run_id", "saved answers")
    _assert_exact_coverage(set(cases), set(records), "generation records")
    _assert_exact_coverage(set(cases), set(answers), "saved answers")
    gold = _index(_read_jsonl(gold_path), "question_id", "Gold")
    eligibility_rows = _index(_read_jsonl(eligibility_path), "question_id", "eligibility")
    expected_questions = {str(case["question_id"]) for case in cases.values()}
    _assert_exact_coverage(expected_questions, set(eligibility_rows), "eligibility")
    missing_gold = expected_questions - set(gold)
    if missing_gold:
        raise ValueError(f"Gold is missing expected questions: {sorted(missing_gold)}")

    source_hash = file_sha256(records_path)
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
        rerank_candidates = (record.get("rerank_trace") or {}).get("candidates") or []
        roles = {str(item["chunk_id"]): item.get("role") for item in rerank_candidates}
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
        converted.append(
            GenerationEvaluationInput(
                evaluation_id=f"evaluation-{run_id}",
                run_id=run_id,
                question_id=str(case["question_id"]),
                question=str(gold[str(case["question_id"])]["question"]),
                answer=answer_text,
                target_level=str(case["student_level"]),
                condition=str(case["condition_id"]),
                lambda_weight=lambda_weight,
                generation_model_family=family,
                generation_model_revision=revision,
                generation_seed=seed,
                eligibility=eligibility,
                evidence=evidence,
                citation_ids=citations,
                source_status=status,
                abstained=abstained,
                technical_failure=technical_failure,
                failure_reason=failure_reason,
                source_artifact_sha256=source_hash,
            )
        )
    adapter_manifest = {
        "schema_version": "1.0",
        "adapter": "m7-generation-0.2-to-m8-evaluation-1.0",
        "matrix_version": expected.get("matrix_version"),
        "gold_sha256": gold_hash,
        "input_sha256": {
            "expected_experiment": file_sha256(expected_path),
            "generation_records": source_hash,
            "saved_answers": file_sha256(answers_path),
            "run_manifest": file_sha256(run_manifest_path),
            "eligibility": file_sha256(eligibility_path),
        },
        "record_count": len(converted),
        "status_counts": dict(Counter(item.source_status.value for item in converted)),
        "reportable": False,
        "claim_boundary": "Validated development adapter output; not a formal evaluation result.",
    }
    return converted, adapter_manifest


def load_open_answer_scores(
    score_path: Path,
    inputs: Sequence[GenerationEvaluationInput],
    *,
    gold_sha256: str,
) -> dict[str, OpenAnswerScore]:
    """Load handoff scores and bind each row to the exact adapted answer."""

    try:
        scores = [OpenAnswerScore.model_validate(row) for row in _read_jsonl(score_path)]
    except ValidationError as exc:
        raise ValueError(f"{score_path}: invalid open-answer score: {exc}") from exc
    by_run = {item.run_id: item for item in inputs}
    indexed = {item.run_id: item for item in scores}
    if len(indexed) != len(scores):
        raise ValueError("open-answer scores contain duplicate run IDs")
    _assert_exact_coverage(set(by_run), set(indexed), "open-answer scores")
    for run_id, score in indexed.items():
        source = by_run[run_id]
        if score.gold_sha256 != gold_sha256:
            raise ValueError(f"{run_id}: score Gold hash mismatch")
        if (
            score.question_id != source.question_id
            or score.condition_id != source.condition.value
            or score.student_level.value != source.target_level.value
        ):
            raise ValueError(f"{run_id}: score identity differs from adapted input")
        if score.run_status != source.source_status.value:
            raise ValueError(f"{run_id}: score status differs from adapted input")
        expected_answer_hash = (
            hashlib.sha256(source.answer.encode("utf-8")).hexdigest()
            if source.answer is not None
            else None
        )
        if score.answer_sha256 != expected_answer_hash:
            raise ValueError(f"{run_id}: score answer hash mismatch")
    return indexed


def write_adapter_outputs(
    items: Sequence[GenerationEvaluationInput], manifest: Mapping[str, Any], output_dir: Path
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_path = output_dir / "generation_evaluation_inputs.jsonl"
    manifest_path = output_dir / "adapter_manifest.json"
    with inputs_path.open("w", encoding="utf-8", newline="\n") as stream:
        for item in items:
            stream.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")
    manifest_path.write_text(
        json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"inputs": inputs_path, "manifest": manifest_path}
