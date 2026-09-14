"""Evaluation helpers shared by gold-data consumers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_gold_samples(
    gold_path: str | Path, documents: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Load M3 gold samples and optionally replay spans against source documents."""

    records: list[dict[str, Any]] = []
    with Path(gold_path).open(encoding="utf-8") as input_file:
        for line_no, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if documents is not None:
                _validate_record_spans(record, documents, line_no)
            records.append(record)
    return records


def _validate_record_spans(
    record: dict[str, Any], documents: dict[str, str], line_no: int
) -> None:
    evidence_sets = record.get("gold_core_evidence_sets", [])
    spans = [span for evidence_set in evidence_sets for span in evidence_set]
    spans.extend(record.get("partial_evidence", []))

    for span in spans:
        document_id = span["document_id"]
        if document_id not in documents:
            raise ValueError(f"line {line_no}: missing source document {document_id}")
        document_text = documents[document_id]
        actual = document_text[span["char_start"] : span["char_end"]]
        if actual != span["verbatim_text"]:
            raise ValueError(f"line {line_no}: gold span does not replay")
