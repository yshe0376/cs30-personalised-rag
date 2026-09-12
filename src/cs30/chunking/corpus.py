"""Deterministic unified Retrieval Document corpus export."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter

from cs30.chunking.reporting import (
    build_chunk_anomalies,
    build_chunk_statistics,
    traceback_selection,
)
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

    payloads = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return TypeAdapter(list[Chunk]).validate_python(payloads)


def export_retrieval_corpus(
    documents: Sequence[OpenStaxDocument],
    chunks: Sequence[Chunk],
    output_dir: Path,
    *,
    rebuild_command: str,
    sample_count: int = 20,
    embedding_max_tokens: int | None = None,
    embedding_model_max_sequence_length: int | None = None,
    embedding_special_token_count: int | None = None,
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

    configuration_keys = (
        "candidate_id",
        "strategy",
        "chunker_version",
        "tokenizer_name",
        "target_tokens",
        "min_tokens",
        "max_tokens",
        "respect_section_boundaries",
        "enrich_embed_text",
        "reject_duplicate_text",
        "include_types",
    )
    configurations = sorted(
        {
            tuple(chunk.metadata.get(key, "") for key in configuration_keys)
            for chunk in ordered_chunks
        }
    )
    if len(configurations) != 1:
        raise ValueError("cannot export chunks produced by mixed chunk configurations")

    for chunk in ordered_chunks:
        document = documents_by_id.get(chunk.document_id)
        if document is None:
            raise ValueError(f"chunk references unknown document_id: {chunk.document_id}")
        if document.text[chunk.char_start : chunk.char_end] != chunk.text:
            raise ValueError(f"invalid chunk span: {chunk.chunk_id}")
        if "source_locator" not in chunk.metadata:
            raise ValueError(f"chunk has no source_locator: {chunk.chunk_id}")

    tracebacks: list[dict[str, object]] = []
    for index, selection_reasons in traceback_selection(ordered_chunks, sample_count):
        chunk = ordered_chunks[index]
        document = documents_by_id[chunk.document_id]
        traceback = resolve_small_to_big(document, chunk)
        traceback["selection_reasons"] = selection_reasons
        tracebacks.append(traceback)

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
    statistics_payload = build_chunk_statistics(
        ordered_chunks,
        documents=documents,
        embedding_max_tokens=embedding_max_tokens,
    )
    anomalies_payload = build_chunk_anomalies(
        ordered_chunks,
        documents=documents,
        embedding_max_tokens=embedding_max_tokens,
    )
    statistics_payload["traceback_sample_count"] = len(tracebacks)
    statistics_payload["traceback_validation"] = "fail_fast"
    statistics_payload["anomaly_count"] = len(anomalies_payload)
    statistics_payload["anomaly_distribution"] = dict(
        sorted(Counter(str(item["type"]) for item in anomalies_payload).items())
    )

    file_payloads = {
        "records.jsonl": _jsonl_bytes(record_payloads),
        "sample_records.jsonl": _jsonl_bytes(sample_payloads),
        "schema.json": _json_bytes(schema_payload),
        "statistics.json": _json_bytes(statistics_payload),
        "anomalies.json": _json_bytes(anomalies_payload),
        "traceback_records.json": _json_bytes(tracebacks),
    }
    for name, data in file_payloads.items():
        (output_dir / name).write_bytes(data)

    manifest = {
        "manifest_version": "1.1",
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
            dict(zip(configuration_keys, values, strict=True))
            for values in configurations
        ],
        "chunk_config_id": _sha256(
            _json_bytes(
                dict(zip(configuration_keys, configurations[0], strict=True))
            )
        ),
        "embedding": {
            "tokenizer_name": ordered_chunks[0].metadata["tokenizer_name"],
            "content_token_ceiling": embedding_max_tokens,
            "model_max_sequence_length": embedding_model_max_sequence_length,
            "special_token_count": embedding_special_token_count,
            "overlong_input_disposition": statistics_payload["embedding_limit"][
                "disposition"
            ],
        },
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


def verify_corpus_identity(
    expected: dict[str, object], actual: dict[str, object]
) -> None:
    """Fail when a rebuild changes any retrieval-relevant corpus identity."""

    keys = (
        "corpus_id",
        "record_count",
        "chapter_ids",
        "documents",
        "chunk_configurations",
        "chunk_config_id",
        "embedding",
    )
    changed = [key for key in keys if expected.get(key) != actual.get(key)]
    if changed:
        raise ValueError(
            "corpus rebuild identity mismatch: " + ", ".join(changed)
        )
