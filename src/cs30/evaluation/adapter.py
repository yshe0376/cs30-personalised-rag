"""Adapters from current and provisional team payloads to M8's stable core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cs30.generation.schema import AnswerPayload

from .models import Answerability, EvaluationRecord, ExecutionStatus


def _choice(gold: dict[str, Any]) -> str | None:
    value = gold.get("gold_choice", gold.get("correct_choice", gold.get("gold_answer")))
    if value in {"A", "B", "C", "D"}:
        return value
    choices = gold.get("choices")
    if isinstance(choices, dict) and isinstance(value, str):
        for label, text in choices.items():
            if text == value and label in {"A", "B", "C", "D"}:
                return label
    return None


def _answerability(gold: dict[str, Any]) -> Answerability:
    value = gold.get("answerability")
    if value is not None:
        aliases = {
            "unanswerable": Answerability.VERIFIED_UNANSWERABLE,
            "verified-unanswerable": Answerability.VERIFIED_UNANSWERABLE,
        }
        normalised = str(value)
        if normalised in aliases:
            return aliases[normalised]
        return Answerability(normalised)
    if "answerable" in gold:
        return (
            Answerability.ANSWERABLE
            if bool(gold["answerable"])
            else Answerability.VERIFIED_UNANSWERABLE
        )
    # ``in_scope`` is intentionally not converted. It does not prove that an
    # unaligned question is unanswerable against the frozen corpus.
    return Answerability.UNRESOLVED


def _gold_evidence_ids(gold: dict[str, Any]) -> list[str]:
    for key in ("gold_evidence_ids", "gold_chunk_ids"):
        value = gold.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    value = gold.get("gold_evidence")
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            identifier = item.get("chunk_id", item.get("evidence_id"))
            if identifier is not None:
                result.append(str(identifier))
    return result


def _failure_status(run: dict[str, Any]) -> ExecutionStatus:
    explicit = run.get("execution_status")
    if explicit is not None:
        return ExecutionStatus(str(explicit))

    if str(run.get("status", "completed")).lower() not in {"completed", "success", "passed"}:
        trace = run.get("trace") if isinstance(run.get("trace"), dict) else {}
        failure_text = " ".join(
            str(value)
            for value in (
                run.get("failure_type"),
                run.get("error"),
                trace.get("failure_types"),
                trace.get("generation_failures"),
            )
            if value
        ).lower()
        if "retriev" in failure_text or "index" in failure_text:
            return ExecutionStatus.RETRIEVAL_FAILURE
        if any(word in failure_text for word in ("parse", "json", "schema", "validation")):
            return ExecutionStatus.PARSE_FAILURE
        if any(word in failure_text for word in ("citation", "ground")):
            return ExecutionStatus.CITATION_FAILURE
        if any(word in failure_text for word in ("llm", "model", "api", "timeout", "generation")):
            return ExecutionStatus.GENERATION_CALL_FAILURE
        return ExecutionStatus.TECHNICAL_FAILURE

    citation_status = run.get("citation_integrity")
    validated = run.get("validated_answer")
    if isinstance(validated, dict):
        citation_status = validated.get("citation_status", citation_status)
    if citation_status == "failed":
        return ExecutionStatus.CITATION_FAILURE
    return ExecutionStatus.COMPLETED


def _raw_validity(run: dict[str, Any]) -> tuple[bool | None, bool | None]:
    raw = run.get("raw_model_output", run.get("raw_output"))
    if raw is None:
        return None, None
    if not isinstance(raw, str):
        return False, False
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return False, False
    try:
        AnswerPayload.model_validate(value)
    except ValidationError:
        return True, False
    return True, True


def _citation_status(run: dict[str, Any]) -> str:
    validated = run.get("validated_answer")
    if isinstance(validated, dict) and validated.get("citation_status") is not None:
        value = validated["citation_status"]
    else:
        value = run.get("citation_integrity", "unknown")
    return str(value) if value in {"passed", "failed", "skipped"} else "unknown"


def adapt_evaluation_record(
    run_payload: dict[str, Any],
    gold_payload: dict[str, Any] | None = None,
) -> EvaluationRecord:
    """Normalise current PipelineRun/BatchResult shapes without changing contracts."""

    envelope = run_payload
    if isinstance(envelope.get("run"), dict):
        run_payload = envelope["run"]
    embedded_gold = envelope.get("gold", envelope.get("sample"))
    gold = gold_payload or (embedded_gold if isinstance(embedded_gold, dict) else {})

    answer = run_payload.get("answer")
    answer = answer if isinstance(answer, dict) else {}
    retrieval = run_payload.get("retrieval")
    retrieval = retrieval if isinstance(retrieval, dict) else {}
    hits = retrieval.get("hits") if isinstance(retrieval.get("hits"), list) else []
    raw_json_valid, raw_schema_valid = _raw_validity(run_payload)

    question_id = run_payload.get("question_id", gold.get("question_id"))
    if question_id is None:
        raise ValueError("evaluation record requires question_id")

    repaired_output = run_payload.get("repaired_output")
    repair_used = run_payload.get("repair_used")
    if repair_used is None and repaired_output is not None:
        repair_used = True

    return EvaluationRecord(
        question_id=str(question_id),
        gold_choice=_choice(gold),
        answerability=_answerability(gold),
        gold_evidence_ids=_gold_evidence_ids(gold),
        predicted_choice=answer.get("final_choice"),
        abstained=answer.get("abstained"),
        citation_ids=list(answer.get("citations", [])),
        retrieved_chunk_ids=[
            str(hit["chunk_id"])
            for hit in hits
            if isinstance(hit, dict) and hit.get("chunk_id") is not None
        ],
        citation_status=_citation_status(run_payload),
        execution_status=_failure_status(run_payload),
        raw_json_valid=raw_json_valid,
        raw_schema_valid=raw_schema_valid,
        repair_used=repair_used,
        source_schema=str(envelope.get("source_schema", "pipeline-run-v1")),
        split=gold.get("split"),
        dataset_version=gold.get("dataset_version", gold.get("version")),
        error=run_payload.get("error"),
    )


def _read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{number}: each JSONL row must be an object")
            records.append(value)
        return records
    value = json.loads(text)
    if isinstance(value, dict):
        value = value.get("records", value.get("items", [value]))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path}: expected a JSON object or list of objects")
    return value


def load_evaluation_records(
    runs_path: Path,
    gold_path: Path | None = None,
) -> list[EvaluationRecord]:
    """Load saved runs and optionally join current M3 gold by ``question_id``."""

    gold_by_id: dict[str, dict[str, Any]] = {}
    if gold_path is not None:
        for row in _read_records(gold_path):
            question_id = row.get("question_id")
            if question_id is None:
                raise ValueError(f"{gold_path}: every gold row requires question_id")
            key = str(question_id)
            if key in gold_by_id:
                raise ValueError(f"{gold_path}: duplicate question_id: {key}")
            gold_by_id[key] = row

    records: list[EvaluationRecord] = []
    seen: set[str] = set()
    for row in _read_records(runs_path):
        envelope_run = row.get("run") if isinstance(row.get("run"), dict) else row
        question_id = envelope_run.get("question_id")
        if question_id is None:
            embedded = row.get("gold", row.get("sample"))
            question_id = embedded.get("question_id") if isinstance(embedded, dict) else None
        gold = gold_by_id.get(str(question_id)) if question_id is not None else None
        record = adapt_evaluation_record(row, gold)
        if record.question_id in seen:
            raise ValueError(f"{runs_path}: duplicate question_id: {record.question_id}")
        seen.add(record.question_id)
        records.append(record)
    return records
