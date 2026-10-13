"""Adapt a validated v2 FAISS candidate for the shared retrieval service.

The production retriever still consumes the compact v1 ``artifact.json`` and
``chunks.json`` layout.  M5 candidates use the richer v2 contract instead.
This module creates a small, auditable compatibility view without duplicating
BM25, dense search, or RRF logic in evaluation notebooks.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cs30.contracts import IndexArtifact
from cs30.errors import ArtifactMismatchError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ArtifactMismatchError(f"v2 corpus record is missing {key!r}")
    return value


def materialise_v2_retrieval_view(
    *,
    v2_artifact: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    index_source: Path,
    output_dir: Path,
    query_instruction: str = "",
    query_prompt_name: str | None = None,
) -> IndexArtifact:
    """Create the exact layout consumed by ``build_real_retrieval_deps``.

    The adapter rejects identity, order, metric, and normalization mismatches.
    It copies the FAISS payload and emits deterministic JSON files; all ranking
    behavior remains owned by :mod:`cs30.retrieval.real`.
    """

    if v2_artifact.get("schema_version") != "2.0":
        raise ArtifactMismatchError("expected a schema_version=2.0 index artifact")
    if v2_artifact.get("index_type") not in {"faiss.IndexFlatIP", "faiss-flat-ip"}:
        raise ArtifactMismatchError("v2 adapter requires a FAISS IndexFlatIP artifact")
    if v2_artifact.get("similarity_metric") != "inner_product":
        raise ArtifactMismatchError("v2 adapter requires inner_product similarity")
    if v2_artifact.get("normalise_embeddings") is not True:
        raise ArtifactMismatchError("v2 adapter requires normalized embeddings")
    for field in ("embedding_model", "embedding_revision", "embedding_dimension"):
        if not v2_artifact.get(field):
            raise ArtifactMismatchError(f"v2 artifact is missing {field}")
    if not index_source.is_file():
        raise ArtifactMismatchError(f"FAISS index is missing: {index_source}")

    expected_ids = [str(value) for value in v2_artifact.get("chunk_ids", [])]
    actual_ids = [_required_text(record, "chunk_id") for record in records]
    if not expected_ids or expected_ids != actual_ids:
        raise ArtifactMismatchError("v2 artifact chunk_ids must exactly match corpus record order")
    if int(v2_artifact.get("chunk_count", 0)) != len(records):
        raise ArtifactMismatchError("v2 artifact chunk_count does not match corpus")

    output_dir.mkdir(parents=True, exist_ok=True)
    index_target = output_dir / "index.faiss"
    if index_source.resolve() != index_target.resolve():
        shutil.copyfile(index_source, index_target)

    chunk_map = []
    for position, record in enumerate(records):
        source = record.get("source_name") or record.get("provider") or record.get("document_id")
        if not isinstance(source, str) or not source.strip():
            raise ArtifactMismatchError("v2 corpus record is missing source identity")
        chunk_map.append(
            {
                "position": position,
                "chunk_id": actual_ids[position],
                "text": _required_text(record, "text"),
                "chapter_id": _required_text(record, "chapter_id"),
                "source": source,
            }
        )

    chunks_path = output_dir / "chunks.json"
    chunks_path.write_text(
        json.dumps(chunk_map, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    metadata = {
        "corpus_hash": str(v2_artifact["corpus_hash"]),
        "chunk_config_hash": str(v2_artifact["chunk_config_hash"]),
        "index_version": str(v2_artifact["index_version"]),
        "embedding_model": str(v2_artifact["embedding_model"]),
        "embedding_revision": str(v2_artifact["embedding_revision"]),
        "dimension": str(v2_artifact["embedding_dimension"]),
        "normalise_embeddings": "true",
        "similarity_metric": "inner_product",
        "index_file": str(index_target),
        "index_sha256": _sha256(index_target),
        "chunk_map": str(chunks_path),
        "chunk_map_sha256": _sha256(chunks_path),
        "query_instruction": query_instruction,
    }
    if query_prompt_name:
        metadata["query_prompt_name"] = query_prompt_name

    artifact = IndexArtifact(
        artifact_id=f"v2-compat-{v2_artifact['artifact_id']}",
        index_type="faiss-flat-ip",
        location=str(output_dir),
        chunk_count=len(records),
        metadata=metadata,
    )
    (output_dir / "artifact.json").write_text(
        artifact.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return artifact
