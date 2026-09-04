"""Small-to-big source trace-back for one retrievable chunk."""

from __future__ import annotations

import hashlib

from cs30.contracts import Chunk, OpenStaxDocument


def resolve_small_to_big(
    document: OpenStaxDocument,
    chunk: Chunk,
) -> dict[str, object]:
    """Resolve a small chunk to its exact source span and structural parent."""

    if chunk.document_id != document.document_id:
        raise ValueError("chunk document_id does not match the supplied document")
    recovered = document.text[chunk.char_start : chunk.char_end]
    if recovered != chunk.text:
        raise ValueError("chunk text does not match its document character span")

    parent_start = int(chunk.metadata["parent_char_start"])
    parent_end = int(chunk.metadata["parent_char_end"])
    if parent_start > chunk.char_start or parent_end < chunk.char_end:
        raise ValueError("small-to-big parent span does not contain the chunk")
    parent_text = document.text[parent_start:parent_end]
    if not parent_text:
        raise ValueError("small-to-big parent span is empty")

    expected_hash = "sha256:" + hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
    if chunk.metadata.get("text_hash") != expected_hash:
        raise ValueError("chunk text_hash does not match its text")

    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "chapter_id": chunk.chapter_id,
        "section_ids": chunk.metadata.get("section_ids", ""),
        "source_locator": chunk.metadata["source_locator"],
        "small_char_start": chunk.char_start,
        "small_char_end": chunk.char_end,
        "small_text": chunk.text,
        "small_text_hash": expected_hash,
        "parent_scope": chunk.metadata["parent_scope"],
        "parent_char_start": parent_start,
        "parent_char_end": parent_end,
        "parent_text": parent_text,
        "parent_source_block_ids": chunk.metadata["parent_source_block_ids"],
        "recovered_text_matches": True,
    }
