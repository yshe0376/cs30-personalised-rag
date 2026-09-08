"""Adapters from current and provisional team payloads to M8's stable core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cs30.generation.schema import AnswerPayload

from .models import Answerability, EvaluationRecord, EvidenceReference, ExecutionStatus


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


def _output_validity(output: object) -> tuple[bool | None, bool | None]:
    if output is None:
        return None, None
    if not isinstance(output, str):
        return False, False
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return False, False
    try:
        AnswerPayload.model_validate(value)
    except ValidationError:
        return True, False
    return True, True


def _first_present(payload: dict[str, Any], *keys: str) -> object | None:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _non_negative_int(value: object, *, default: int = 0) -> int:
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return default


def _sent_evidence(run: dict[str, Any], hits: list[Any]) -> list[EvidenceReference]:
    bundle = run.get("evidence_bundle")
    items = bundle.get("evidence_items") if isinstance(bundle, dict) else None
    if not isinstance(items, list):
        items = hits

    result: list[EvidenceReference] = []
    for item in items:
        if not isinstance(item, dict) or item.get("chunk_id") is None:
            continue
        chunk_id = str(item["chunk_id"])
        result.append(
            EvidenceReference(
                evidence_id=str(item.get("evidence_id", chunk_id)),
                chunk_id=chunk_id,
                source=str(item["source"]) if item.get("source") is not None else None,
                source_locator=(
                    str(item["source_locator"]) if item.get("source_locator") is not None else None
                ),
            )
        )
    return result


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
    validated = run_payload.get("validated_answer")
    if not isinstance(answer, dict) and isinstance(validated, dict):
        answer = validated.get("answer")
    answer = answer if isinstance(answer, dict) else {}
    retrieval = run_payload.get("retrieval")
    retrieval = retrieval if isinstance(retrieval, dict) else {}
    hits = retrieval.get("hits") if isinstance(retrieval.get("hits"), list) else []
    metadata = run_payload.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    trace = run_payload.get("trace")
    trace = trace if isinstance(trace, dict) else {}
    raw_output = _first_present(
        run_payload, "raw_model_output", "raw_output", "first_output", "initial_output"
    )
    repaired_output = _first_present(
        run_payload,
        "repaired_model_output",
        "repaired_output",
        "post_repair_output",
    )
    raw_json_valid, raw_schema_valid = _output_validity(raw_output)
    repaired_json_valid, repaired_schema_valid = _output_validity(repaired_output)

    question_id = run_payload.get("question_id", gold.get("question_id"))
    if question_id is None:
        raise ValueError("evaluation record requires question_id")

    repair_used = run_payload.get("repair_used")
    if repair_used is None and repaired_output is not None:
        repair_used = True
    attempts = _non_negative_int(
        _first_present(run_payload, "generation_attempts", "attempts")
        or metadata.get("generation_attempts")
        or trace.get("generation_attempts")
    )
    retry_count = _non_negative_int(run_payload.get("retry_count"), default=max(0, attempts - 1))
    repair_count = _non_negative_int(
        run_payload.get("repair_count"),
        default=1 if repair_used else 0,
    )
    sent_evidence = _sent_evidence(run_payload, hits)
    retrieval_mode = retrieval.get("mode")
    mode = (
        retrieval_mode
        or run_payload.get("retrieval_mode")
        or trace.get("retrieval_mode")
        or run_payload.get("mode")
    )
    condition_id = run_payload.get("condition_id", metadata.get("condition_id"))
    provenance = retrieval.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    corpus_version = (
        run_payload.get("corpus_version")
        or trace.get("corpus_version")
        or metadata.get("corpus_version")
        or provenance.get("corpus_hash")
    )

    return EvaluationRecord(
        question_id=str(question_id),
        gold_choice=_choice(gold),
        answerability=_answerability(gold),
        gold_evidence_ids=_gold_evidence_ids(gold),
        predicted_choice=answer.get("final_choice"),
        abstained=answer.get("abstained"),
        citation_ids=list(answer.get("citations", [])),
        sent_evidence=sent_evidence,
        retrieved_chunk_ids=[
            str(hit["chunk_id"])
            for hit in hits
            if isinstance(hit, dict) and hit.get("chunk_id") is not None
        ],
        citation_status=_citation_status(run_payload),
        execution_status=_failure_status(run_payload),
        raw_json_valid=raw_json_valid,
        raw_schema_valid=raw_schema_valid,
        repaired_json_valid=repaired_json_valid,
        repaired_schema_valid=repaired_schema_valid,
        retry_count=retry_count,
        repair_count=repair_count,
        repair_used=repair_used,
        source_schema=str(envelope.get("source_schema", "pipeline-run-v1")),
        mode=str(mode) if mode is not None else None,
        condition_id=str(condition_id) if condition_id is not None else None,
        split=gold.get("split", run_payload.get("split", metadata.get("split"))),
        dataset_version=gold.get(
            "dataset_version",
            gold.get(
                "version",
                run_payload.get("dataset_version", metadata.get("dataset_version")),
            ),
        ),
        corpus_version=str(corpus_version) if corpus_version is not None else None,
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
