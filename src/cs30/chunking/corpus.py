"""Deterministic unified Retrieval Document corpus export."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter

from cs30.chunking.reporting import build_chunk_statistics
from cs30.chunking.traceback import resolve_small_to_big
from cs30.contracts import Chunk, OpenStaxDocument


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _jsonl_bytes(payloads: Sequence[dict[str, object]]) -> bytes:
    return b"".join(
        (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        for payload in payloads
    )


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sample_indices(length: int, count: int) -> list[int]:
    if length <= 0 or count <= 0:
        return []
    count = min(length, count)
    if count == 1:
        return [0]
    return sorted({round(index * (length - 1) / (count - 1)) for index in range(count)})


def load_retrieval_corpus(path: Path) -> list[Chunk]:
    """Load the one JSONL corpus consumed by both Dense and BM25."""

    payloads = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return TypeAdapter(list[Chunk]).validate_python(payloads)


def export_retrieval_corpus(
    documents: Sequence[OpenStaxDocument],
    chunks: Sequence[Chunk],
    output_dir: Path,
    *,
    rebuild_command: str,
    sample_count: int = 20,
) -> dict[str, object]:
    """Export one reproducible Chunk JSONL corpus plus schema and evidence."""

    if not documents:
        raise ValueError("cannot export a corpus without documents")
    if not chunks:
        raise ValueError("cannot export a corpus without chunks")
    if not rebuild_command.strip():
        raise ValueError("rebuild_command must not be empty")

    documents_by_id = {document.document_id: document for document in documents}
    if len(documents_by_id) != len(documents):
        raise ValueError("document_id values must be unique")

    ordered_chunks = sorted(
        chunks,
        key=lambda chunk: (chunk.document_id, chunk.char_start, chunk.chunk_id),
    )
    if len({chunk.chunk_id for chunk in ordered_chunks}) != len(ordered_chunks):
        raise ValueError("chunk_id values must be unique")

    for chunk in ordered_chunks:
        document = documents_by_id.get(chunk.document_id)
        if document is None:
            raise ValueError(f"chunk references unknown document_id: {chunk.document_id}")
        if document.text[chunk.char_start : chunk.char_end] != chunk.text:
            raise ValueError(f"invalid chunk span: {chunk.chunk_id}")
        if "source_locator" not in chunk.metadata:
            raise ValueError(f"chunk has no source_locator: {chunk.chunk_id}")

    tracebacks: list[dict[str, object]] = []
    for index in _sample_indices(len(ordered_chunks), sample_count):
        chunk = ordered_chunks[index]
        document = documents_by_id[chunk.document_id]
        tracebacks.append(resolve_small_to_big(document, chunk))

    output_dir.mkdir(parents=True, exist_ok=True)
    record_payloads = [chunk.model_dump(mode="json") for chunk in ordered_chunks]
    sample_payloads = [
        record_payloads[index] for index in _sample_indices(len(ordered_chunks), sample_count)
    ]
    schema_payload = {
        "schema_name": "cs30.contracts.Chunk",
        "schema_version": "1.0",
        "json_schema": Chunk.model_json_schema(),
    }
    statistics_payload = build_chunk_statistics(ordered_chunks)
    statistics_payload["traceback_sample_count"] = len(tracebacks)
    statistics_payload["all_sampled_spans_match"] = all(
        item["recovered_text_matches"] for item in tracebacks
    )

    file_payloads = {
        "records.jsonl": _jsonl_bytes(record_payloads),
        "sample_records.jsonl": _jsonl_bytes(sample_payloads),
        "schema.json": _json_bytes(schema_payload),
        "statistics.json": _json_bytes(statistics_payload),
        "traceback_records.json": _json_bytes(tracebacks),
    }
    for name, data in file_payloads.items():
        (output_dir / name).write_bytes(data)

    configurations = sorted(
        {
            (
                chunk.metadata.get("candidate_id", "main"),
                chunk.metadata.get("strategy", ""),
                chunk.metadata.get("chunker_version", ""),
                chunk.metadata.get("tokenizer_name", ""),
                chunk.metadata.get("target_tokens", ""),
                chunk.metadata.get("min_tokens", ""),
                chunk.metadata.get("max_tokens", ""),
                chunk.metadata.get("include_types", "*"),
            )
            for chunk in ordered_chunks
        }
    )
    manifest = {
        "manifest_version": "1.0",
        "corpus_id": _sha256(file_payloads["records.jsonl"]),
        "record_schema": "cs30.contracts.Chunk@1.0",
        "record_count": len(ordered_chunks),
        "chapter_ids": sorted({chunk.chapter_id for chunk in ordered_chunks}),
        "documents": [
            {
                "document_id": document.document_id,
                "document_hash": document.document_hash,
                "parser_version": document.parser_version,
            }
            for document in sorted(documents, key=lambda item: item.document_id)
        ],
        "chunk_configurations": [
            {
                "candidate_id": values[0],
                "strategy": values[1],
                "chunker_version": values[2],
                "tokenizer_name": values[3],
                "target_tokens": values[4],
                "min_tokens": values[5],
                "max_tokens": values[6],
                "include_types": values[7],
            }
            for values in configurations
        ],
        "consumers": {
            "dense": "records.jsonl",
            "bm25": "records.jsonl",
            "text_field": "text",
            "metadata_field": "metadata",
        },
        "files": {
            name: {"sha256": _sha256(data), "bytes": len(data)}
            for name, data in sorted(file_payloads.items())
        },
        "rebuild_command": rebuild_command,
        "note": "Engineering corpus only; no retrieval-effectiveness claim is made.",
    }
    (output_dir / "manifest.json").write_bytes(_json_bytes(manifest))
    return manifest
