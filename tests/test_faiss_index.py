"""Tests for the FAISS index builder."""

from pathlib import Path

import numpy as np
import pytest

from cs30.contracts import Chunk
from cs30.errors import IndexUnavailableError
from cs30.indexing import faiss_index
from cs30.ports import IndexBuilder


class FakeSentenceTransformer:
    """Small deterministic stand-in for SentenceTransformer."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.device = "cpu"

    def encode(
        self,
        texts: list[str],
        convert_to_numpy: bool = True,
    ) -> np.ndarray:
        """Return deterministic 4-dimensional vectors."""

        vectors = []

        for index, _text in enumerate(texts):
            vector = np.array(
                [
                    float(index + 1),
                    float(index + 2),
                    float(index + 3),
                    float(index + 4),
                ],
                dtype=np.float32,
            )
            vectors.append(vector)

        return np.vstack(vectors)


def make_test_chunks() -> list[Chunk]:
    """Create small valid chunks for indexing tests."""

    text_1 = "Force causes acceleration."
    text_2 = "Energy can be transferred between objects."

    return [
        Chunk(
            chunk_id="chunk_001",
            document_id="doc_001",
            chapter_id="1",
            text=text_1,
            source="openstax",
            char_start=0,
            char_end=len(text_1),
            token_count=4,
            metadata={
                "strategy": "block_greedy_nearest_target",
                "chunker_version": "test-chunker-1.0",
                "tokenizer_name": "test-tokenizer",
                "target_tokens": "500",
                "min_tokens": "250",
                "max_tokens": "750",
                "respect_section_boundaries": "true",
                "document_hash": "test-document-hash",
                "parser_version": "test-parser-1.0",
                "section_id": "1.1",
            },
        ),
        Chunk(
            chunk_id="chunk_002",
            document_id="doc_001",
            chapter_id="1",
            text=text_2,
            source="openstax",
            char_start=100,
            char_end=100 + len(text_2),
            token_count=7,
            metadata={
                "strategy": "block_greedy_nearest_target",
                "chunker_version": "test-chunker-1.0",
                "tokenizer_name": "test-tokenizer",
                "target_tokens": "500",
                "min_tokens": "250",
                "max_tokens": "750",
                "respect_section_boundaries": "true",
                "document_hash": "test-document-hash",
                "parser_version": "test-parser-1.0",
                "section_id": "1.2",
            },
            embed_text=(
                "Chapter 1, Section 1.2. "
                + text_2
            ),
        ),
    ]


def make_builder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> faiss_index.FaissIndexBuilder:
    """Create a builder using the fake embedding model."""

    monkeypatch.setattr(
        faiss_index,
        "SentenceTransformer",
        FakeSentenceTransformer,
    )

    return faiss_index.FaissIndexBuilder(
        model_name="fake-embedding-model",
        index_dir=str(tmp_path),
    )


def test_build_creates_faiss_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Building should create a valid FAISS index."""

    chunks = make_test_chunks()

    builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    artifact = builder.build(chunks)

    assert artifact.chunk_count == 2
    assert artifact.index_type == "faiss-flat-ip"

    assert builder.index.ntotal == 2
    assert builder.index.d == 4


def test_build_creates_required_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Building should persist index, mapping, and manifest files."""

    builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    builder.build(make_test_chunks())

    assert (tmp_path / "index.faiss").exists()
    assert (tmp_path / "chunks.json").exists()
    assert (tmp_path / "artifact.json").exists()


def test_chunk_map_matches_faiss_positions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """FAISS vector positions should map to the correct chunk IDs."""

    builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    builder.build(make_test_chunks())

    assert builder.chunk_map[0]["position"] == 0
    assert builder.chunk_map[0]["chunk_id"] == "chunk_001"

    assert builder.chunk_map[1]["position"] == 1
    assert builder.chunk_map[1]["chunk_id"] == "chunk_002"


def test_artifact_records_embedding_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """IndexArtifact should record important embedding configuration."""

    builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    artifact = builder.build(make_test_chunks())

    assert artifact.metadata["embedding_model"] == "fake-embedding-model"
    assert artifact.metadata["dimension"] == "4"
    assert artifact.metadata["device"] == "cpu"
    assert artifact.metadata["normalisation"] == "L2"
    assert artifact.metadata["similarity"] == "inner_product"

    # One test chunk uses embed_text and one uses plain text.
    assert artifact.metadata["embedding_source"] == "mixed"


def test_saved_index_can_be_loaded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A saved index should be loadable by a new builder."""

    original_builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    original_artifact = original_builder.build(
        make_test_chunks()
    )

    new_builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    loaded_artifact = new_builder.load()

    assert loaded_artifact.artifact_id == original_artifact.artifact_id
    assert loaded_artifact.index_type == original_artifact.index_type
    assert loaded_artifact.chunk_count == 2

    assert new_builder.index.ntotal == 2
    assert new_builder.index.d == 4

    assert new_builder.chunk_map[0]["chunk_id"] == "chunk_001"
    assert new_builder.chunk_map[1]["chunk_id"] == "chunk_002"


def test_empty_chunk_list_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The builder should reject an empty corpus."""

    builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="cannot build an index from zero chunks",
    ):
        builder.build([])


def test_load_missing_index_raises_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Loading before an index exists should raise a clear error."""

    builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    with pytest.raises(IndexUnavailableError):
        builder.load()

def test_faiss_builder_implements_index_builder_protocol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """FaissIndexBuilder should satisfy the shared IndexBuilder protocol."""

    builder = make_builder(
        monkeypatch,
        tmp_path,
    )

    assert isinstance(builder, IndexBuilder)
