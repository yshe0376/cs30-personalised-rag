"""Strict JSONL loaders for the frozen W5 evaluation contracts."""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .models import EvaluationRunResult, GoldSample

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_gold_samples(
    path: str | Path,
    *,
    documents: dict[str, str] | None = None,
) -> list[GoldSample]:
    """Load Gold JSONL and optionally replay every span against canonical text."""

    samples = _load_jsonl(path, GoldSample)
    ids = [sample.question_id for sample in samples]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{Path(path)}: duplicate question_id values")
    if documents is not None:
        for line_number, sample in enumerate(samples, start=1):
            try:
                _validate_sample_spans(sample, documents)
            except ValueError as exc:
                raise ValueError(f"{Path(path)}:{line_number}: {exc}") from exc
    return samples


def load_run_results(path: str | Path) -> list[EvaluationRunResult]:
    """Load strict per-question run traces from JSONL."""

    results = _load_jsonl(path, EvaluationRunResult)
    ids = [result.run_id for result in results]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{Path(path)}: duplicate run_id values")
    return results


def _load_jsonl(path: str | Path, model: type[ModelT]) -> list[ModelT]:
    source = Path(path)
    loaded: list[ModelT] = []
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                loaded.append(model.model_validate(payload))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(f"{source}:{line_number}: {exc}") from exc
    return loaded


def _validate_sample_spans(sample: GoldSample, documents: dict[str, str]) -> None:
    spans = [
        span
        for evidence_set in sample.gold_core_evidence_sets
        for span in evidence_set
    ] + sample.partial_evidence
    for span in spans:
        document = documents.get(span.document_id)
        if document is None:
            raise ValueError(
                f"{span.span_id} references unknown document_id {span.document_id}"
            )
        if span.char_end > len(document):
            raise ValueError(f"{span.span_id} exceeds canonical document text")
        actual = document[span.char_start : span.char_end]
        if actual != span.verbatim_text:
            raise ValueError(f"{span.span_id} does not match canonical document text")
