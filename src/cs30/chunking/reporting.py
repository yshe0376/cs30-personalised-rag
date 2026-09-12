"""Engineering statistics and traceability evidence for chunk outputs."""

from __future__ import annotations

import hashlib
import statistics
from bisect import bisect_right
from collections import Counter
from collections.abc import Sequence

from cs30.contracts import Chunk, OpenStaxDocument, TextBlock


def _crosses_chapter_boundary(chunk: Chunk) -> bool:
    source_chapter_ids = {
        chapter_id.strip()
        for chapter_id in chunk.metadata.get(
            "source_chapter_ids",
            chunk.chapter_id,
        ).split(",")
        if chapter_id.strip()
    }
    return len(source_chapter_ids) != 1 or chunk.chapter_id not in source_chapter_ids


def _text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _metadata_int(chunk: Chunk, key: str, default: int = 0) -> int:
    try:
        return int(chunk.metadata.get(key, str(default)))
    except ValueError:
        return default


def _source_block_ids(chunk: Chunk) -> list[str]:
    return [
        value.strip()
        for value in chunk.metadata.get("source_block_ids", "").split(",")
        if value.strip()
    ]


def build_chunk_statistics(
    chunks: Sequence[Chunk],
    *,
    documents: Sequence[OpenStaxDocument] | None = None,
    embedding_max_tokens: int | None = None,
) -> dict[str, object]:
    """Return engineering checks without claiming retrieval effectiveness."""

    if not chunks:
        raise ValueError("cannot report statistics for an empty chunk list")
    token_counts = [chunk.token_count for chunk in chunks]
    embedding_counts = [
        _metadata_int(chunk, "embedding_input_token_count", chunk.token_count)
        for chunk in chunks
    ]
    text_hashes = [_text_hash(chunk.text) for chunk in chunks]
    text_hash_counts = Counter(text_hashes)
    duplicate_text_groups = sum(count > 1 for count in text_hash_counts.values())
    included_types = chunks[0].metadata.get("include_types", "*")
    allowed_types = None if included_types == "*" else set(included_types.split(","))

    source_blocks = {
        (document.document_id, block.block_id): block
        for document in documents or ()
        for block in document.blocks
        if block.block_id is not None
    }
    referenced_ids = {
        (chunk.document_id, block_id)
        for chunk in chunks
        for block_id in _source_block_ids(chunk)
    }
    included_source_ids = {
        key
        for key, block in source_blocks.items()
        if allowed_types is None or block.content_type.value in allowed_types
    }
    missing_included_ids = sorted(included_source_ids - referenced_ids)
    leakage_count = sum(
        item["type"] == "filtered_content_leakage"
        for item in build_chunk_anomalies(
            chunks,
            documents=documents,
            embedding_max_tokens=embedding_max_tokens,
        )
    )
    overlong_ids = (
        []
        if embedding_max_tokens is None
        else [
            chunk.chunk_id
            for chunk, count in zip(chunks, embedding_counts, strict=True)
            if count > embedding_max_tokens
        ]
    )
    return {
        "chunk_count": len(chunks),
        "chapter_distribution": dict(Counter(chunk.chapter_id for chunk in chunks)),
        "token_length": {
            "min": min(token_counts),
            "mean": round(statistics.mean(token_counts), 2),
            "median": statistics.median(token_counts),
            "max": max(token_counts),
        },
        "embedding_input_token_length": {
            "min": min(embedding_counts),
            "mean": round(statistics.mean(embedding_counts), 2),
            "median": statistics.median(embedding_counts),
            "max": max(embedding_counts),
        },
        "empty_chunks": sum(not chunk.text.strip() for chunk in chunks),
        "duplicate_chunk_ids": len(chunks) - len({chunk.chunk_id for chunk in chunks}),
        "exact_duplicate_chunks": len(text_hashes) - len(set(text_hashes)),
        "exact_duplicate_text_groups": duplicate_text_groups,
        "duplicate_text_disposition": (
            "preserved_as_source_distinct_chunks_and_listed_in_anomalies"
        ),
        "short_chunks": sum(
            chunk.metadata.get("short_chunk") == "true" for chunk in chunks
        ),
        "oversized_chunks": sum(
            chunk.metadata.get("oversized_chunk") == "true" for chunk in chunks
        ),
        "cross_chapter_chunks": sum(
            _crosses_chapter_boundary(chunk) for chunk in chunks
        ),
        "filter": {
            "included_types": included_types,
            "source_block_count": len(source_blocks),
            "included_source_block_count": len(included_source_ids),
            "excluded_source_block_count": len(source_blocks) - len(included_source_ids),
            "referenced_source_block_count": len(referenced_ids),
            "filtered_content_leakage_count": leakage_count,
            "unmapped_included_block_count": len(missing_included_ids),
        },
        "embedding_limit": {
            "max_tokens": embedding_max_tokens,
            "status": "verified" if embedding_max_tokens is not None else "unverified",
            "overlong_input_count": len(overlong_ids) if embedding_max_tokens is not None else None,
            "disposition": (
                "listed_for_M5_truncation_review"
                if overlong_ids
                else "none_exceed_limit"
                if embedding_max_tokens is not None
                else "requires_M5_model_limit"
            ),
        },
        "note": "Engineering statistics only; no retrieval-effectiveness claim is made.",
    }


def build_chunk_anomalies(
    chunks: Sequence[Chunk],
    *,
    documents: Sequence[OpenStaxDocument] | None = None,
    embedding_max_tokens: int | None = None,
) -> list[dict[str, object]]:
    """Return deterministic, actionable corpus anomalies."""

    anomalies: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    chunks_by_hash: dict[str, list[Chunk]] = {}
    included_types = chunks[0].metadata.get("include_types", "*") if chunks else "*"
    allowed_types = None if included_types == "*" else set(included_types.split(","))
    source_blocks = {
        (document.document_id, block.block_id): block
        for document in documents or ()
        for block in document.blocks
        if block.block_id is not None
    }
    documents_by_id = {
        document.document_id: document for document in documents or ()
    }
    pending_excluded_blocks: dict[str, list[TextBlock]] = {}
    if allowed_types is not None:
        for (document_id, _), block in source_blocks.items():
            if block.content_type.value not in allowed_types:
                pending_excluded_blocks.setdefault(document_id, []).append(block)
        for blocks in pending_excluded_blocks.values():
            blocks.sort(key=lambda block: block.char_start)
    excluded_blocks_by_document = {
        document_id: (blocks, [block.char_end for block in blocks])
        for document_id, blocks in pending_excluded_blocks.items()
    }

    for chunk in chunks:
        if not chunk.text.strip():
            anomalies.append({"type": "empty_chunk", "chunk_id": chunk.chunk_id})
        if chunk.chunk_id in seen_ids:
            anomalies.append({"type": "duplicate_chunk_id", "chunk_id": chunk.chunk_id})
        seen_ids.add(chunk.chunk_id)

        actual_hash = _text_hash(chunk.text)
        chunks_by_hash.setdefault(actual_hash, []).append(chunk)
        if chunk.metadata.get("text_hash") != actual_hash:
            anomalies.append({"type": "text_hash_mismatch", "chunk_id": chunk.chunk_id})
        if _crosses_chapter_boundary(chunk):
            anomalies.append({"type": "cross_chapter_chunk", "chunk_id": chunk.chunk_id})

        leaked_blocks = {
            block_id
            for block_id in _source_block_ids(chunk)
            if (block := source_blocks.get((chunk.document_id, block_id))) is not None
            and allowed_types is not None
            and block.content_type.value not in allowed_types
        }
        document = documents_by_id.get(chunk.document_id)
        if document is not None and allowed_types is not None:
            excluded_blocks, excluded_ends = excluded_blocks_by_document.get(
                chunk.document_id, ([], [])
            )
            first_candidate = bisect_right(excluded_ends, chunk.char_start)
            for block in excluded_blocks[first_candidate:]:
                if block.char_start >= chunk.char_end:
                    break
                overlap_start = max(chunk.char_start, block.char_start)
                overlap_end = min(chunk.char_end, block.char_end)
                if (
                    overlap_start < overlap_end
                    and document.text[overlap_start:overlap_end].strip()
                    and block.block_id is not None
                ):
                    leaked_blocks.add(block.block_id)
        for block_id in sorted(leaked_blocks):
            block = source_blocks[(chunk.document_id, block_id)]
            anomalies.append(
                {
                    "type": "filtered_content_leakage",
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "block_id": block_id,
                    "content_type": block.content_type.value,
                }
            )

        embedding_count = _metadata_int(
            chunk, "embedding_input_token_count", chunk.token_count
        )
        if embedding_max_tokens is not None and embedding_count > embedding_max_tokens:
            anomalies.append(
                {
                    "type": "overlong_embedding_input",
                    "chunk_id": chunk.chunk_id,
                    "token_count": embedding_count,
                    "embedding_max_tokens": embedding_max_tokens,
                    "disposition": "M5_must_truncate_or_reconfigure_before_indexing",
                }
            )

    for text_hash, duplicate_chunks in sorted(chunks_by_hash.items()):
        if len(duplicate_chunks) < 2:
            continue
        anomalies.append(
            {
                "type": "exact_duplicate_text_group",
                "text_hash": text_hash,
                "chunk_ids": sorted(chunk.chunk_id for chunk in duplicate_chunks),
                "source_locations": sorted(
                    {
                        (
                            chunk.document_id,
                            chunk.chapter_id,
                            chunk.char_start,
                            chunk.char_end,
                        )
                        for chunk in duplicate_chunks
                    }
                ),
                "disposition": "preserved_because_source_locations_are_distinct",
            }
        )

    if documents is not None:
        referenced_ids = {
            (chunk.document_id, block_id)
            for chunk in chunks
            for block_id in _source_block_ids(chunk)
        }
        for (document_id, block_id), block in sorted(source_blocks.items()):
            if (
                (document_id, block_id) not in referenced_ids
                and (allowed_types is None or block.content_type.value in allowed_types)
            ):
                anomalies.append(
                    {
                        "type": "unmapped_included_block",
                        "block_id": block_id,
                        "document_id": document_id,
                        "content_type": block.content_type.value,
                    }
                )

    return sorted(
        anomalies,
        key=lambda item: (
            str(item["type"]),
            str(item.get("document_id", "")),
            str(item.get("chunk_id", "")),
            str(item.get("block_id", "")),
        ),
    )


def _traceback_selection(
    chunks: Sequence[Chunk], sample_count: int
) -> list[tuple[int, list[str]]]:
    """Select deterministic samples with required structural coverage."""

    if sample_count <= 0 or not chunks:
        return []
    reasons: dict[int, set[str]] = {}

    def add(index: int, reason: str) -> None:
        reasons.setdefault(index, set()).add(reason)

    chapter_indices: dict[tuple[str, str], list[int]] = {}
    for index, chunk in enumerate(chunks):
        chapter_indices.setdefault((chunk.document_id, chunk.chapter_id), []).append(index)
        if "equation" in chunk.metadata.get("content_types", "").split(","):
            add(index, "formula_or_equation")
        if chunk.metadata.get("short_chunk") == "true":
            add(index, "short_chunk")
        if _metadata_int(chunk, "min_source_block_token_count") < _metadata_int(
            chunk, "min_tokens"
        ):
            add(index, "short_source_block")
        if _metadata_int(chunk, "block_count") > 1:
            add(index, "cross_block")
    for indices in chapter_indices.values():
        add(indices[0], "chapter_start")
        add(indices[-1], "chapter_end")

    required_order = (
        "chapter_start",
        "chapter_end",
        "formula_or_equation",
        "short_source_block",
        "cross_block",
    )
    selected: list[int] = []
    for reason in required_order:
        for index in sorted(reasons):
            if reason in reasons[index] and index not in selected:
                selected.append(index)
                break
        if len(selected) >= sample_count:
            break

    count = min(len(chunks), sample_count)
    if count == 1:
        fill_indices = [0]
    else:
        fill_indices = sorted(
            {round(index * (len(chunks) - 1) / (count - 1)) for index in range(count)}
        )
    for index in fill_indices:
        add(index, "deterministic_spread")
        if index not in selected and len(selected) < sample_count:
            selected.append(index)
    for index in range(len(chunks)):
        if len(selected) >= sample_count:
            break
        add(index, "deterministic_fill")
        if index not in selected:
            selected.append(index)
    return [(index, sorted(reasons[index])) for index in sorted(selected)]


def build_traceability_samples(
    document: OpenStaxDocument,
    chunks: Sequence[Chunk],
    *,
    sample_count: int = 10,
) -> list[dict[str, object]]:
    """Select deterministic samples and verify document-wide character spans."""

    samples: list[dict[str, object]] = []
    for index, selection_reasons in _traceback_selection(chunks, sample_count):
        chunk = chunks[index]
        recovered = document.text[chunk.char_start : chunk.char_end]
        samples.append(
            {
                "chunk_id": chunk.chunk_id,
                "chapter_id": chunk.chapter_id,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "source_block_ids": chunk.metadata.get("source_block_ids", ""),
                "recovered_text_matches": recovered == chunk.text,
                "text_hash": chunk.metadata.get("text_hash", ""),
                "text_preview": chunk.text[:240],
                "selection_reasons": selection_reasons,
            }
        )
    return samples


def traceback_selection(
    chunks: Sequence[Chunk], sample_count: int
) -> list[tuple[int, list[str]]]:
    """Expose the deterministic corpus-wide trace-back selection."""

    return _traceback_selection(chunks, sample_count)
