import json
from pathlib import Path

import numpy as np
import pytest

import cs30.retrieval.real as real_retrieval
from cs30.config import AppConfig, RetrievalConfig
from cs30.contracts import (
    EvidenceProvenance,
    IndexArtifact,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
)
from cs30.errors import ArtifactMismatchError, EmptyQueryError, RetrievalError
from cs30.pipeline import build_real_deps

def _chunks() -> list[dict]:
    return [
        {
            "position": 0,
            "chunk_id": "chunk-1",
            "text": "Acceleration is the rate of change of velocity with time.",
            "chapter_id": "chapter-1",
            "source": "fixture://openstax/chapter-1",
        },
        {
            "position": 1,
            "chunk_id": "chunk-2",
            "text": "The SI unit of acceleration is metres per second squared.",
            "chapter_id": "chapter-1",
            "source": "fixture://openstax/chapter-1",
        },
    ]


def _artifact(*, dense: bool = False) -> IndexArtifact:
    metadata = {
        "corpus_hash": "test-corpus-hash",
        "chunk_config_hash": "test-chunk-config-hash",
        "index_version": "test-index-v1",
    }
    if dense:
        metadata.update({
            "embedding_model": "fake-embedding-model",
            "dimension": "2",
        })

    return IndexArtifact(
        artifact_id="test-artifact",
        index_type="faiss-flat-ip" if dense else "bm25",
        location="unused",
        chunk_count=2,
        metadata=metadata,
    )


def _artifact_at(path: Path, *, dense: bool = False) -> IndexArtifact:
    return IndexArtifact.model_validate(
        {
            **_artifact(dense=dense).model_dump(),
            "location": str(path),
        }
    )


def _write_chunk_map(path: Path, chunks: list[dict]) -> None:
    (path / "chunks.json").write_text(
        json.dumps(chunks),
        encoding="utf-8",
    )


def test_bm25_out_of_scope_question_returns_no_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_retrieval,
        "_load_chunk_map",
        lambda artifact: _chunks(),
    )

    retriever = real_retrieval.BM25Retriever()
    retriever.load_index(_artifact())

    result = retriever.retrieve(
        "What is quantum entanglement?",
        top_k=5,
    )

    assert result.hits == []
    assert result.mode is RetrievalMode.BM25
    assert result.provenance is not None
    assert result.provenance.embedding_model is None

def test_bm25_stopword_only_question_returns_no_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_retrieval,
        "_load_chunk_map",
        lambda artifact: _chunks(),
    )

    retriever = real_retrieval.BM25Retriever()
    retriever.load_index(_artifact())

    result = retriever.retrieve("Is the a of", top_k=5)

    assert result.hits == []


def test_bm25_rejects_unsupported_artifact_type() -> None:
    invalid_artifact = IndexArtifact.model_validate(
        {
            **_artifact().model_dump(),
            "index_type": "unknown-index",
        }
    )
    retriever = real_retrieval.BM25Retriever()

    with pytest.raises(
        ArtifactMismatchError,
        match="bm25 or faiss-flat-ip",
    ):
        retriever.load_index(invalid_artifact)


class _FakeEmbeddingModel:
    def encode(
        self,
        sentences: list[str],
        *,
        convert_to_numpy: bool = True,
    ) -> np.ndarray:
        return np.array([[1.0, 0.0]], dtype=np.float32)


class _FakeIndex:
    ntotal = 2
    d = 2

    def search(
        self,
        vectors: np.ndarray,
        top_k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        scores = np.array([[0.8, 0.2]], dtype=np.float32)
        positions = np.array([[0, 1]], dtype=np.int64)
        return scores[:, :top_k], positions[:, :top_k]


class _FakeIndexWithPadding(_FakeIndex):
    def search(
        self,
        vectors: np.ndarray,
        top_k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        scores = np.array([[0.8, -1.0]], dtype=np.float32)
        positions = np.array([[0, -1]], dtype=np.int64)
        return scores[:, :top_k], positions[:, :top_k]


def test_dense_filters_hits_below_similarity_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_retrieval,
        "_load_chunk_map",
        lambda artifact: _chunks(),
    )
    monkeypatch.setattr(
        real_retrieval,
        "_resolve_artifact_file",
        lambda *args, **kwargs: Path("unused"),
    )

    retriever = real_retrieval.FaissDenseRetriever(
        min_similarity=0.5,
        model_loader=lambda model_name: _FakeEmbeddingModel(),
        index_reader=lambda path: _FakeIndex(),
    )
    retriever.load_index(_artifact(dense=True))

    result = retriever.retrieve("What is acceleration?", top_k=2)

    assert [hit.chunk_id for hit in result.hits] == ["chunk-1"]
    assert result.hits[0].score == pytest.approx(0.8)
    assert result.hits[0].rank == 1


def test_dense_skips_negative_faiss_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_retrieval,
        "_load_chunk_map",
        lambda artifact: _chunks(),
    )
    monkeypatch.setattr(
        real_retrieval,
        "_resolve_artifact_file",
        lambda *args, **kwargs: Path("unused"),
    )

    retriever = real_retrieval.FaissDenseRetriever(
        model_loader=lambda model_name: _FakeEmbeddingModel(),
        index_reader=lambda path: _FakeIndexWithPadding(),
    )
    retriever.load_index(_artifact(dense=True))

    result = retriever.retrieve("What is acceleration?", top_k=2)

    assert [hit.chunk_id for hit in result.hits] == ["chunk-1"]
    assert [hit.rank for hit in result.hits] == [1]
    assert result.hits[0].score == pytest.approx(0.8)
    

def test_dense_rejects_invalid_similarity_threshold() -> None:
    with pytest.raises(
        ValueError,
        match="min_similarity must be between -1 and 1",
    ):
        real_retrieval.FaissDenseRetriever(
            min_similarity=1.1,
        )


def test_dense_rejects_wrong_artifact_type() -> None:
    retriever = real_retrieval.FaissDenseRetriever()

    with pytest.raises(
        ArtifactMismatchError,
        match="faiss-flat-ip",
    ):
        retriever.load_index(_artifact())


def test_dense_rejects_missing_embedding_model() -> None:
    dense_artifact = _artifact(dense=True)
    metadata = dense_artifact.metadata.copy()
    metadata.pop("embedding_model")

    invalid_artifact = IndexArtifact.model_validate(
        {
            **dense_artifact.model_dump(),
            "metadata": metadata,
        }
    )
    retriever = real_retrieval.FaissDenseRetriever()

    with pytest.raises(
        ArtifactMismatchError,
        match="metadata.embedding_model",
    ):
        retriever.load_index(invalid_artifact)


def test_dense_rejects_vector_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_retrieval,
        "_load_chunk_map",
        lambda artifact: _chunks(),
    )
    monkeypatch.setattr(
        real_retrieval,
        "_resolve_artifact_file",
        lambda *args, **kwargs: Path("unused"),
    )

    wrong_count_index = _FakeIndex()
    wrong_count_index.ntotal = 1

    retriever = real_retrieval.FaissDenseRetriever(
        model_loader=lambda model_name: _FakeEmbeddingModel(),
        index_reader=lambda path: wrong_count_index,
    )

    with pytest.raises(
        ArtifactMismatchError,
        match="vector count",
    ):
        retriever.load_index(_artifact(dense=True))


def test_dense_rejects_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_retrieval,
        "_load_chunk_map",
        lambda artifact: _chunks(),
    )
    monkeypatch.setattr(
        real_retrieval,
        "_resolve_artifact_file",
        lambda *args, **kwargs: Path("unused"),
    )

    wrong_dimension_index = _FakeIndex()
    wrong_dimension_index.d = 3

    retriever = real_retrieval.FaissDenseRetriever(
        model_loader=lambda model_name: _FakeEmbeddingModel(),
        index_reader=lambda path: wrong_dimension_index,
    )

    with pytest.raises(
        ArtifactMismatchError,
        match="dimension",
    ):
        retriever.load_index(_artifact(dense=True))


def test_chunk_map_rejects_non_consecutive_positions(
    tmp_path: Path,
) -> None:
    chunks = _chunks()
    chunks[1]["position"] = 3
    _write_chunk_map(tmp_path, chunks)

    with pytest.raises(
        ArtifactMismatchError,
        match="positions",
    ):
        real_retrieval._load_chunk_map(_artifact_at(tmp_path))


def test_chunk_map_rejects_duplicate_chunk_ids(
    tmp_path: Path,
) -> None:
    chunks = _chunks()
    chunks[1]["chunk_id"] = chunks[0]["chunk_id"]
    _write_chunk_map(tmp_path, chunks)

    with pytest.raises(
        ArtifactMismatchError,
        match="duplicate chunk_id",
    ):
        real_retrieval._load_chunk_map(_artifact_at(tmp_path))


def test_chunk_map_rejects_count_mismatch(
    tmp_path: Path,
) -> None:
    _write_chunk_map(tmp_path, _chunks()[:1])

    with pytest.raises(
        ArtifactMismatchError,
        match="count",
    ):
        real_retrieval._load_chunk_map(_artifact_at(tmp_path))


class _SpyRetriever:
    def __init__(
        self,
        result: RetrievalResult | None = None,
    ) -> None:
        self.loaded = False
        self.result = result

    def load_index(self, artifact: IndexArtifact) -> None:
        self.loaded = True

    def retrieve(
        self,
        query: str,
        top_k: int,
    ) -> RetrievalResult:
        if self.result is None:
            raise AssertionError("no fake retrieval result was configured")
        return self.result

def _provenance(mode: RetrievalMode) -> EvidenceProvenance:
    return EvidenceProvenance(
        corpus_hash="test-corpus-hash",
        chunk_config_hash="test-chunk-config-hash",
        embedding_model=(
            "fake-embedding-model"
            if mode is RetrievalMode.DENSE
            else None
        ),
        index_version="test-index-v1",
    )


def _result(
    mode: RetrievalMode,
    chunk_ids: list[str],
) -> RetrievalResult:
    return RetrievalResult(
        query="What is acceleration?",
        mode=mode,
        hits=[
            RetrievedEvidence(
                chunk_id=chunk_id,
                text=f"Evidence for {chunk_id}.",
                chapter_id="chapter-1",
                source="fixture://openstax/chapter-1",
                score=1.0 / rank,
                rank=rank,
                retriever_type=mode,
            )
            for rank, chunk_id in enumerate(
                chunk_ids,
                start=1,
            )
        ],
        provenance=_provenance(mode),
    )


def test_rrf_fuses_rankings_and_labels_contributing_modes() -> None:
    dense = _SpyRetriever(
        result=_result(
            RetrievalMode.DENSE,
            ["dense-only", "shared"],
        )
    )
    bm25 = _SpyRetriever(
        result=_result(
            RetrievalMode.BM25,
            ["shared", "bm25-only"],
        )
    )

    retriever = real_retrieval.RRFRetriever(
        dense=dense,
        bm25=bm25,
    )
    retriever.load_index(_artifact(dense=True))

    result = retriever.retrieve(
        "What is acceleration?",
        top_k=3,
    )

    assert [hit.chunk_id for hit in result.hits] == [
        "shared",
        "dense-only",
        "bm25-only",
    ]
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    assert [hit.retriever_type for hit in result.hits] == [
        RetrievalMode.HYBRID,
        RetrievalMode.DENSE,
        RetrievalMode.BM25,
    ]


def test_rrf_returns_empty_when_both_backends_abstain() -> None:
    dense = _SpyRetriever(
        result=_result(RetrievalMode.DENSE, [])
    )
    bm25 = _SpyRetriever(
        result=_result(RetrievalMode.BM25, [])
    )

    retriever = real_retrieval.RRFRetriever(
        dense=dense,
        bm25=bm25,
    )
    retriever.load_index(_artifact(dense=True))

    result = retriever.retrieve(
        "Unknown topic",
        top_k=3,
    )

    assert result.mode is RetrievalMode.HYBRID
    assert result.hits == []


def test_cache_returns_equal_copies_without_leaking_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_retrieval,
        "_load_chunk_map",
        lambda artifact: _chunks(),
    )

    retriever = real_retrieval.BM25Retriever()
    retriever.load_index(_artifact())

    first = retriever.retrieve(
        "What is acceleration?",
        top_k=2,
    )
    second = retriever.retrieve(
        "What is acceleration?",
        top_k=2,
    )

    assert first == second
    assert first is not second

    second.hits.clear()

    third = retriever.retrieve(
        "What is acceleration?",
        top_k=2,
    )
    assert third.hits


def test_empty_query_raises_typed_error() -> None:
    with pytest.raises(EmptyQueryError):
        real_retrieval.BM25Retriever().retrieve(
            "   ",
            top_k=1,
        )


def test_non_positive_top_k_raises_typed_error() -> None:
    with pytest.raises(
        RetrievalError,
        match="top_k must be positive",
    ):
        real_retrieval.BM25Retriever().retrieve(
            "acceleration",
            top_k=0,
        )


def test_pipeline_uses_shared_real_bm25_fixture() -> None:
    index_dir = Path(__file__).parent / "fixtures" / "index"
    config = AppConfig(
        fixture_mode=False,
        retrieval=RetrievalConfig(
            mode=RetrievalMode.BM25,
            index_dir=str(index_dir),
        ),
    )

    deps = build_real_deps(config)

    assert deps.mode == "real"
    assert isinstance(
        deps.retriever,
        real_retrieval.BM25Retriever,
    )
    result = deps.retriever.retrieve(
        "What is acceleration?",
        top_k=3,
    )
    assert result.hits


def test_pipeline_falls_back_to_fixture_when_index_is_missing(
    tmp_path: Path,
) -> None:
    config = AppConfig(
        fixture_mode=True,
        retrieval=RetrievalConfig(
            index_dir=str(tmp_path / "missing"),
        ),
    )

    deps = build_real_deps(config)

    assert deps.mode == "fixture"


def test_real_service_loads_only_selected_backend() -> None:
    dense = _SpyRetriever()
    bm25 = _SpyRetriever()
    hybrid = _SpyRetriever()

    service = real_retrieval.RealRetrievalService(
        dense=dense,
        bm25=bm25,
        hybrid=hybrid,
    )

    service.load_index(
        _artifact(),
        RetrievalMode.BM25,
    )

    assert bm25.loaded is True
    assert dense.loaded is False
    assert hybrid.loaded is False


def test_real_service_rejects_result_without_provenance() -> None:
    bm25_result = RetrievalResult(
        query="What is acceleration?",
        mode=RetrievalMode.BM25,
        hits=[],
        provenance=None,
    )

    service = real_retrieval.RealRetrievalService(
        dense=_SpyRetriever(),
        bm25=_SpyRetriever(result=bm25_result),
        hybrid=_SpyRetriever(),
    )

    with pytest.raises(
        ArtifactMismatchError,
        match="real retrieval result must include provenance",
    ):
        service.retrieve(
            "What is acceleration?",
            top_k=5,
            mode=RetrievalMode.BM25,
        )
