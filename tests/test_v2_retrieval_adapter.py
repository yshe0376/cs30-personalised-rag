from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.errors import ArtifactMismatchError
from cs30.retrieval.v2_adapter import materialise_v2_retrieval_view


def _artifact() -> dict:
    return {
        "schema_version": "2.0",
        "artifact_id": "candidate-1",
        "index_type": "faiss.IndexFlatIP",
        "corpus_hash": "sha256:corpus",
        "chunk_config_hash": "sha256:chunks",
        "chunk_count": 2,
        "chunk_ids": ["chunk-1", "chunk-2"],
        "embedding_model": "example/model",
        "embedding_revision": "a" * 40,
        "embedding_dimension": 3,
        "similarity_metric": "inner_product",
        "normalise_embeddings": True,
        "index_version": "v2-index-1",
    }


def _records() -> list[dict]:
    return [
        {
            "chunk_id": "chunk-1",
            "text": "First chunk.",
            "chapter_id": "1",
            "source_name": "book-a",
        },
        {
            "chunk_id": "chunk-2",
            "text": "Second chunk.",
            "chapter_id": "2",
            "source_name": "book-b",
        },
    ]


def test_materialise_v2_retrieval_view(tmp_path: Path) -> None:
    source = tmp_path / "source.faiss"
    source.write_bytes(b"fake-faiss")

    artifact = materialise_v2_retrieval_view(
        v2_artifact=_artifact(),
        records=_records(),
        index_source=source,
        output_dir=tmp_path / "view",
        query_prompt_name="query",
    )

    assert artifact.metadata["embedding_revision"] == "a" * 40
    assert artifact.metadata["query_prompt_name"] == "query"
    assert (tmp_path / "view" / "index.faiss").read_bytes() == b"fake-faiss"
    chunks = json.loads((tmp_path / "view" / "chunks.json").read_text())
    assert [row["chunk_id"] for row in chunks] == ["chunk-1", "chunk-2"]


def test_adapter_rejects_chunk_order_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.faiss"
    source.write_bytes(b"fake-faiss")
    records = list(reversed(_records()))

    with pytest.raises(ArtifactMismatchError, match="record order"):
        materialise_v2_retrieval_view(
            v2_artifact=_artifact(),
            records=records,
            index_source=source,
            output_dir=tmp_path / "view",
        )
