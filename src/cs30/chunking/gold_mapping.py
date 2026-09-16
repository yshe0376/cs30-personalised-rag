"""Versioned mapping from character-level gold spans to stable chunk IDs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from cs30.contracts import Chunk, OpenStaxDocument

GOLD_MAPPING_SCHEMA_VERSION = "1.0"
GOLD_MATCH_RULE_ID = "same_source_half_open_overlap"
GOLD_MATCH_RULE_VERSION = "1.0"
EXPECTED_GOLD_ANNOTATION_VERSION = "m3_gold_v0.1.1"


class GoldSpan(BaseModel):
    """One M3 evidence span expressed in normalised document coordinates."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    gold_span_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    question_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    text: str | None = None
    coverage_role: Literal["necessary", "alternative"] = "necessary"
    alternative_group_id: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_span(self) -> GoldSpan:
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if self.text is not None and len(self.text) != self.char_end - self.char_start:
            raise ValueError("text length must match the gold character span")
        if self.coverage_role == "alternative" and not self.alternative_group_id:
            raise ValueError("alternative evidence requires alternative_group_id")
        if self.coverage_role == "necessary" and self.alternative_group_id is not None:
            raise ValueError("necessary evidence must not set alternative_group_id")
        return self


def matching_rule() -> dict[str, object]:
    """Return the fixed rule handed to M1 for retrieval metrics."""

    rule = {
        "rule_id": GOLD_MATCH_RULE_ID,
        "rule_version": GOLD_MATCH_RULE_VERSION,
        "coordinate_system": "normalised_document_half_open_character_offsets",
        "predicate": (
            "same document_id and chapter_id, and "
            "max(gold.char_start, chunk.char_start) < "
            "min(gold.char_end, chunk.char_end)"
        ),
        "relevant_chunk_unit": (
            "A retrieved chunk is relevant to one gold span exactly when its "
            "chunk_id appears in that span's matching_chunk_ids."
        ),
        "multi_chunk_policy": (
            "All overlapping chunks are retained; coverage_status records whether "
            "their clipped union fully covers the gold span."
        ),
        "role_policy": (
            "M3 core OR-of-AND membership and partial-evidence membership are copied "
            "as source_metadata and are never inferred or modified by M4."
        ),
    }
    rule["rule_hash"] = _sha256_json(rule)
    return rule


def load_gold_spans(path: Path) -> list[GoldSpan]:
    """Load the fixed JSON or JSONL M3-to-M4 span format."""

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        payload: object = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("spans")
    if not isinstance(payload, list):
        raise ValueError("gold input must be a JSON list, a {'spans': [...]} object, or JSONL")
    spans = TypeAdapter(list[GoldSpan]).validate_python(payload)
    ids = [span.gold_span_id for span in spans]
    if len(ids) != len(set(ids)):
        raise ValueError("gold_span_id values must be unique")
    return spans


def load_normalized_gold_spans(path: Path) -> tuple[list[GoldSpan], str]:
    """Flatten M1-normalized Gold v0.2 without changing M3 semantics.

    Core OR-of-AND structure and partial-evidence membership are retained in
    string metadata. The M1 evaluation mapping remains span based, so this
    flattening does not alter how complete evidence paths are scored.
    """

    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError("normalized Gold input must contain at least one record")
    corpus_versions = {record.get("corpus_version") for record in records}
    if len(corpus_versions) != 1 or not next(iter(corpus_versions), None):
        raise ValueError("normalized Gold records must share one corpus_version")
    corpus_version = str(next(iter(corpus_versions)))
    annotation_versions = {
        record.get("gold_annotation_version") for record in records
    }
    if annotation_versions != {EXPECTED_GOLD_ANNOTATION_VERSION}:
        raise ValueError(
            "normalized Gold must be derived from "
            f"{EXPECTED_GOLD_ANNOTATION_VERSION}"
        )

    spans: list[GoldSpan] = []
    for record in records:
        if record.get("schema_version") != "0.2":
            raise ValueError("M4 requires M1-normalized Gold schema_version 0.2")
        question_id = str(record.get("question_id", ""))
        annotation_status = str(record.get("annotation_status", ""))
        core_sets = record.get("gold_core_evidence_sets")
        partial = record.get("partial_evidence")
        if not isinstance(core_sets, list) or not isinstance(partial, list):
            raise ValueError(f"invalid evidence lists for question {question_id!r}")

        for set_index, evidence_set in enumerate(core_sets):
            if not isinstance(evidence_set, list) or not evidence_set:
                raise ValueError(f"empty core evidence set for question {question_id!r}")
            for span_index, span in enumerate(evidence_set):
                spans.append(
                    _normalized_span(
                        span,
                        question_id=question_id,
                        annotation_status=annotation_status,
                        evidence_kind="core",
                        core_set_index=set_index,
                        span_index=span_index,
                    )
                )
        for span_index, span in enumerate(partial):
            spans.append(
                _normalized_span(
                    span,
                    question_id=question_id,
                    annotation_status=annotation_status,
                    evidence_kind="partial",
                    core_set_index=None,
                    span_index=span_index,
                )
            )

    ids = [span.gold_span_id for span in spans]
    if len(ids) != len(set(ids)):
        raise ValueError("span_id values must be unique across normalized Gold")
    return spans, corpus_version


def _normalized_span(
    payload: object,
    *,
    question_id: str,
    annotation_status: str,
    evidence_kind: str,
    core_set_index: int | None,
    span_index: int,
) -> GoldSpan:
    if not isinstance(payload, dict):
        raise ValueError(f"invalid Gold span for question {question_id!r}")
    span_id = str(payload.get("span_id", ""))
    if payload.get("resolution_status") != "resolved":
        raise ValueError(f"normalized Gold span is not resolved: {span_id}")
    start = payload.get("corpus_char_start")
    end = payload.get("corpus_char_end")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError(f"normalized Gold span has no corpus coordinates: {span_id}")
    metadata = {
        "source_schema_version": "0.2",
        "annotation_status": annotation_status,
        "gold_annotation_version": EXPECTED_GOLD_ANNOTATION_VERSION,
        "evidence_kind": evidence_kind,
        "span_index": str(span_index),
        "resolved_block_id": str(payload.get("resolved_block_id") or ""),
        "sufficiency": str(payload.get("sufficiency") or ""),
    }
    if core_set_index is not None:
        metadata["core_set_index"] = str(core_set_index)
    return GoldSpan(
        gold_span_id=span_id,
        question_id=question_id,
        document_id=str(payload.get("document_id", "")),
        chapter_id=str(payload.get("chapter_id", "")),
        char_start=start,
        char_end=end,
        text=str(payload.get("verbatim_text", "")),
        metadata=metadata,
    )


def _sha256_json(payload: object) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _coverage_length(intervals: Sequence[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    ordered = sorted(intervals)
    start, end = ordered[0]
    total = 0
    for next_start, next_end in ordered[1:]:
        if next_start > end:
            total += end - start
            start, end = next_start, next_end
        else:
            end = max(end, next_end)
    return total + end - start


def _relation(gold: GoldSpan, chunk: Chunk) -> str:
    if chunk.char_start == gold.char_start and chunk.char_end == gold.char_end:
        return "exact"
    if chunk.char_start <= gold.char_start and chunk.char_end >= gold.char_end:
        return "chunk_contains_gold"
    if gold.char_start <= chunk.char_start and gold.char_end >= chunk.char_end:
        return "chunk_within_gold"
    return "partial_overlap"


def map_gold_spans_to_chunks(
    gold_spans: Sequence[GoldSpan],
    chunks: Sequence[Chunk],
    *,
    corpus_id: str,
    chunk_config_id: str,
    documents: Sequence[OpenStaxDocument] | None = None,
    evidence_block_ids: Sequence[str] | None = None,
    require_full_coverage: bool = True,
) -> dict[str, object]:
    """Map spans deterministically and bind the result to one exact corpus."""

    if not corpus_id.strip() or not chunk_config_id.strip():
        raise ValueError("corpus_id and chunk_config_id must not be empty")
    if not gold_spans:
        raise ValueError("cannot build a mapping without gold spans")
    if not chunks:
        raise ValueError("cannot build a mapping without chunks")
    gold_ids = [span.gold_span_id for span in gold_spans]
    if len(gold_ids) != len(set(gold_ids)):
        raise ValueError("gold_span_id values must be unique")
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk_id values must be unique")
    evidence_validation = (
        validate_chunk_source_blocks(chunks, evidence_block_ids)
        if evidence_block_ids is not None
        else None
    )

    documents_by_id = {
        document.document_id: document for document in documents or ()
    }
    ordered_chunks = sorted(
        chunks, key=lambda item: (item.document_id, item.char_start, item.chunk_id)
    )
    entries: list[dict[str, object]] = []
    incomplete: list[str] = []

    ordered_gold = sorted(
        gold_spans, key=lambda item: (item.question_id, item.gold_span_id)
    )
    for gold in ordered_gold:
        document = documents_by_id.get(gold.document_id)
        source_text = gold.text
        if documents is not None and document is None:
            raise ValueError(f"gold span references unknown document_id: {gold.gold_span_id}")
        if document is not None:
            chapter = next(
                (item for item in document.chapters if item.chapter_id == gold.chapter_id),
                None,
            )
            if chapter is None:
                raise ValueError(f"gold span references unknown chapter_id: {gold.gold_span_id}")
            if gold.char_start < chapter.char_start or gold.char_end > chapter.char_end:
                raise ValueError(f"gold span falls outside its chapter: {gold.gold_span_id}")
            recovered = document.text[gold.char_start : gold.char_end]
            source_text = recovered
            if gold.text is not None and recovered != gold.text:
                raise ValueError(f"gold span text does not match its source: {gold.gold_span_id}")

        matches: list[dict[str, object]] = []
        intervals: list[tuple[int, int]] = []
        for chunk in ordered_chunks:
            if chunk.document_id != gold.document_id or chunk.chapter_id != gold.chapter_id:
                continue
            overlap_start = max(gold.char_start, chunk.char_start)
            overlap_end = min(gold.char_end, chunk.char_end)
            if overlap_start >= overlap_end:
                continue
            intervals.append((overlap_start, overlap_end))
            matches.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "relation": _relation(gold, chunk),
                    "overlap_char_start": overlap_start,
                    "overlap_char_end": overlap_end,
                    "overlap_char_count": overlap_end - overlap_start,
                }
            )

        gold_length = gold.char_end - gold.char_start
        covered_length = _coverage_length(intervals)
        if source_text is not None:
            covered_positions = [False] * gold_length
            for start, end in intervals:
                for position in range(start - gold.char_start, end - gold.char_start):
                    covered_positions[position] = True
            substantive_positions = [
                position for position, char in enumerate(source_text) if not char.isspace()
            ]
            substantive_count = len(substantive_positions)
            covered_substantive_count = sum(
                covered_positions[position] for position in substantive_positions
            )
            fully_covered = (
                substantive_count > 0
                and covered_substantive_count == substantive_count
            )
            coverage_ratio = (
                covered_substantive_count / substantive_count
                if substantive_count
                else 0.0
            )
            coverage_basis = "non_whitespace_source_characters"
        else:
            substantive_count = gold_length
            covered_substantive_count = covered_length
            fully_covered = covered_length == gold_length
            coverage_ratio = covered_length / gold_length
            coverage_basis = "all_characters_without_source_text"

        if fully_covered:
            coverage_status = "full"
        elif covered_substantive_count:
            coverage_status = "partial"
        else:
            coverage_status = "none"
        if coverage_status != "full":
            incomplete.append(gold.gold_span_id)
        entries.append(
            {
                "gold_span_id": gold.gold_span_id,
                "question_id": gold.question_id,
                "document_id": gold.document_id,
                "chapter_id": gold.chapter_id,
                "char_start": gold.char_start,
                "char_end": gold.char_end,
                "coverage_role": gold.coverage_role,
                "alternative_group_id": gold.alternative_group_id,
                "source_metadata": dict(sorted(gold.metadata.items())),
                "matching_chunk_ids": [match["chunk_id"] for match in matches],
                "chunk_matches": matches,
                "gold_char_count": gold_length,
                "covered_char_count": covered_length,
                "substantive_gold_char_count": substantive_count,
                "covered_substantive_char_count": covered_substantive_count,
                "coverage_ratio": round(coverage_ratio, 8),
                "coverage_basis": coverage_basis,
                "coverage_status": coverage_status,
            }
        )

    if require_full_coverage and incomplete:
        raise ValueError(
            "gold spans are not fully covered by the frozen corpus: "
            + ", ".join(incomplete)
        )

    rule = matching_rule()
    payload: dict[str, object] = {
        "schema_name": "cs30.chunking.gold_mapping",
        "schema_version": GOLD_MAPPING_SCHEMA_VERSION,
        "corpus_id": corpus_id,
        "chunk_config_id": chunk_config_id,
        "source_gold_hash": _sha256_json(
            [span.model_dump(mode="json") for span in ordered_gold]
        ),
        "matching_rule": rule,
        "gold_span_count": len(entries),
        "fully_covered_span_count": len(entries) - len(incomplete),
        "incomplete_gold_span_ids": incomplete,
        "entries": entries,
    }
    if evidence_validation is not None:
        payload["evidence_source_block_validation"] = evidence_validation
    payload["mapping_id"] = _sha256_json(payload)
    return payload


def validate_chunk_source_blocks(
    chunks: Sequence[Chunk],
    evidence_block_ids: Sequence[str],
) -> dict[str, object]:
    """Require chunk provenance to equal the prepared evidence-block set."""

    expected = list(evidence_block_ids)
    if not expected:
        raise ValueError("prepared corpus contains no eligible evidence blocks")
    if len(expected) != len(set(expected)):
        raise ValueError("prepared corpus contains duplicate evidence block IDs")

    referenced: list[str] = []
    for chunk in chunks:
        block_ids = [
            value.strip()
            for value in chunk.metadata.get("source_block_ids", "").split(",")
            if value.strip()
        ]
        if not block_ids:
            raise ValueError(f"chunk has no source_block_ids: {chunk.chunk_id}")
        referenced.extend(block_ids)

    duplicate_references = sorted(
        block_id for block_id, count in Counter(referenced).items() if count > 1
    )
    expected_set = set(expected)
    referenced_set = set(referenced)
    missing = sorted(expected_set - referenced_set)
    unexpected = sorted(referenced_set - expected_set)
    if missing or unexpected or duplicate_references:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unexpected:
            details.append(f"unexpected={','.join(unexpected)}")
        if duplicate_references:
            details.append(f"duplicated={','.join(duplicate_references)}")
        raise ValueError("chunk/evidence source-block mismatch: " + "; ".join(details))

    return {
        "status": "exact_set_match",
        "evidence_block_count": len(expected_set),
        "referenced_block_count": len(referenced_set),
    }


def build_evaluation_mapping(
    detailed_mapping: dict[str, object],
    *,
    corpus_version: str,
) -> dict[str, object]:
    """Build the M1-owned GoldChunkMapping v0.1 compatibility artifact."""

    from cs30.evaluation.mapping import GoldChunkMapping

    entries = detailed_mapping.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("detailed mapping contains no entries")
    mapping_id = str(detailed_mapping.get("mapping_id", ""))
    chunk_config_id = str(detailed_mapping.get("chunk_config_id", ""))
    if not mapping_id or not chunk_config_id or not corpus_version.strip():
        raise ValueError("mapping identities must not be empty")
    mapping_version = "mapping-" + mapping_id.removeprefix("sha256:")[:16]

    by_question: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("detailed mapping entry must be an object")
        question_id = str(entry.get("question_id", ""))
        span_id = str(entry.get("gold_span_id", ""))
        chunk_ids = entry.get("matching_chunk_ids")
        if not question_id or not span_id:
            raise ValueError("span mapping identities must not be empty")
        if not isinstance(chunk_ids, list):
            raise ValueError(f"span mapping has invalid matching chunks: {span_id}")
        if not chunk_ids or entry.get("coverage_status") != "full":
            continue
        by_question.setdefault(question_id, []).append(
            {
                "span_id": span_id,
                "acceptable_chunk_sets": [chunk_ids],
            }
        )

    if not by_question:
        raise ValueError("detailed mapping contains no fully covered questions")

    items = [
        {
            "schema_version": "0.1",
            "question_id": question_id,
            "corpus_version": corpus_version,
            "chunk_config_hash": chunk_config_id,
            "mapping_version": mapping_version,
            "spans": sorted(spans, key=lambda item: str(item["span_id"])),
        }
        for question_id, spans in sorted(by_question.items())
    ]
    artifact = GoldChunkMapping.model_validate(
        {
            "schema_version": "0.1",
            "mapping_version": mapping_version,
            "corpus_version": corpus_version,
            "chunk_config_hash": chunk_config_id,
            "items": items,
        }
    )
    return artifact.model_dump(mode="json")


def verify_mapping_identity(
    expected: dict[str, object], actual: dict[str, object]
) -> None:
    """Fail when corpus, gold data, rule, or the resulting mapping changed."""

    keys = (
        "mapping_id",
        "corpus_id",
        "chunk_config_id",
        "source_gold_hash",
    )
    changed = [key for key in keys if expected.get(key) != actual.get(key)]
    if changed:
        raise ValueError(
            "gold mapping identity mismatch: " + ", ".join(changed)
        )
