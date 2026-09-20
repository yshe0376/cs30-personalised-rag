"""Regression tests for the completed W5 M4 handoff."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.chunking import build_evaluation_mapping, load_normalized_gold_spans
from cs30.chunking.gold_mapping import validate_chunk_source_blocks
from cs30.contracts import Chunk


def _chunk(chunk_id: str, block_ids: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="book",
        chapter_id="1",
        text="Evidence",
        source="fixture://book",
        char_start=0,
        char_end=8,
        token_count=1,
        metadata={"source_block_ids": block_ids},
    )


def test_evidence_source_block_validation_requires_an_exact_set() -> None:
    result = validate_chunk_source_blocks(
        [_chunk("chunk-1", "block-1,block-2")],
        ["block-1", "block-2"],
    )
    assert result == {
        "status": "exact_set_match",
        "evidence_block_count": 2,
        "referenced_block_count": 2,
    }


@pytest.mark.parametrize(
    ("chunks", "match"),
    [
        ([_chunk("chunk-1", "block-1")], "missing=block-2"),
        ([_chunk("chunk-1", "block-1,block-3")], "unexpected=block-3"),
        (
            [_chunk("chunk-1", "block-1"), _chunk("chunk-2", "block-1,block-2")],
            "duplicated=block-1",
        ),
    ],
)
def test_evidence_source_block_validation_rejects_mismatch(
    chunks: list[Chunk], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_chunk_source_blocks(chunks, ["block-1", "block-2"])


def test_evaluation_mapping_requires_explicit_full_coverage() -> None:
    detailed = {
        "mapping_id": "sha256:mapping",
        "chunk_config_id": "sha256:config",
        "entries": [
            {
                "question_id": "covered",
                "gold_span_id": "span-covered",
                "matching_chunk_ids": ["chunk-1"],
                "coverage_status": "full",
            },
            {
                "question_id": "legacy-missing-status",
                "gold_span_id": "span-legacy",
                "matching_chunk_ids": ["chunk-2"],
            },
        ],
    }

    mapping = build_evaluation_mapping(detailed, corpus_version="corpus-v1")

    assert [item["question_id"] for item in mapping["items"]] == ["covered"]


def test_normalized_gold_must_come_from_m3_v0_1_1(tmp_path: Path) -> None:
    record = {
        "schema_version": "0.2",
        "question_id": "question-1",
        "corpus_version": "corpus-v1",
        "gold_annotation_version": "m3_gold_v0.1.1",
        "annotation_status": "m3_initial",
        "gold_core_evidence_sets": [
            [
                {
                    "span_id": "span-1",
                    "document_id": "book",
                    "chapter_id": "1",
                    "corpus_char_start": 0,
                    "corpus_char_end": 8,
                    "verbatim_text": "Evidence",
                    "resolution_status": "resolved",
                    "resolved_block_id": "block-1",
                    "sufficiency": "core_sufficient",
                }
            ]
        ],
        "partial_evidence": [],
    }
    path = tmp_path / "gold_v0_2.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    spans, corpus_version = load_normalized_gold_spans(path)

    assert corpus_version == "corpus-v1"
    assert spans[0].metadata["gold_annotation_version"] == "m3_gold_v0.1.1"

    record["gold_annotation_version"] = "m3_gold_v0.1"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="m3_gold_v0.1.1"):
        load_normalized_gold_spans(path)
