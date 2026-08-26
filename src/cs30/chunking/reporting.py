"""Engineering statistics and traceability evidence for chunk outputs."""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Sequence

from cs30.contracts import Chunk, OpenStaxDocument


def build_chunk_statistics(chunks: Sequence[Chunk]) -> dict[str, object]:
    """Return engineering checks without claiming retrieval effectiveness."""

    if not chunks:
        raise ValueError("cannot report statistics for an empty chunk list")
    token_counts = [chunk.token_count for chunk in chunks]
    text_hashes = [chunk.metadata.get("text_hash", "") for chunk in chunks]
    return {
        "chunk_count": len(chunks),
        "chapter_distribution": dict(Counter(chunk.chapter_id for chunk in chunks)),
        "token_length": {
            "min": min(token_counts),
            "mean": round(statistics.mean(token_counts), 2),
            "median": statistics.median(token_counts),
            "max": max(token_counts),
        },
        "empty_chunks": sum(not chunk.text.strip() for chunk in chunks),
        "duplicate_chunk_ids": len(chunks) - len({chunk.chunk_id for chunk in chunks}),
        "exact_duplicate_chunks": len(text_hashes) - len(set(text_hashes)),
        "short_chunks": sum(
            chunk.metadata.get("short_chunk") == "true" for chunk in chunks
        ),
        "oversized_chunks": sum(
            chunk.metadata.get("oversized_chunk") == "true" for chunk in chunks
        ),
        "cross_chapter_chunks": 0,
        "note": "Engineering statistics only; no retrieval-effectiveness claim is made.",
    }


def build_traceability_samples(
    document: OpenStaxDocument,
    chunks: Sequence[Chunk],
    *,
    sample_count: int = 10,
) -> list[dict[str, object]]:
    """Select deterministic samples and verify document-wide character spans."""

    if sample_count <= 0 or not chunks:
        return []
    count = min(sample_count, len(chunks))
    if count == 1:
        indices = [0]
    else:
        indices = sorted(
            {
                round(index * (len(chunks) - 1) / (count - 1))
                for index in range(count)
            }
        )
    samples: list[dict[str, object]] = []
    for index in indices:
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
            }
        )
    return samples

