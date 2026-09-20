"""Canonical bytes for v2 corpus and Manifest identity."""

from __future__ import annotations

from collections.abc import Sequence

from cs30.v2.contracts import Chunk
from cs30.v2.ids import canonical_json_bytes, sha256_bytes


def canonical_corpus_bytes(chunks: Sequence[Chunk]) -> bytes:
    """Serialize retrieval records without output paths or run-time fields."""

    ordered = sorted(
        chunks,
        key=lambda chunk: (
            chunk.textbook_id,
            chunk.document_id,
            chunk.chapter_id,
            chunk.chunk_id,
        ),
    )
    ids = [chunk.chunk_id for chunk in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("chunk_id values must be unique")
    return b"".join(
        canonical_json_bytes(chunk.model_dump(mode="json")) for chunk in ordered
    )


def corpus_hash(chunks: Sequence[Chunk]) -> str:
    return sha256_bytes(canonical_corpus_bytes(chunks))


def canonical_manifest_payload(manifest) -> dict[str, object]:
    payload = manifest.model_dump(mode="json", exclude={"manifest_hash"})
    # A caller may attach diagnostics to a runtime copy; only the persisted
    # contract fields participate in identity.
    payload.pop("runtime_diagnostics", None)
    return payload


def canonical_manifest_bytes(manifest) -> bytes:
    return canonical_json_bytes(canonical_manifest_payload(manifest))


def manifest_hash(manifest) -> str:
    return sha256_bytes(canonical_manifest_bytes(manifest))
