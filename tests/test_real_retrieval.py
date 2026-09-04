from pathlib import Path

import numpy as np
import pytest

import cs30.retrieval.real as real_retrieval
from cs30.contracts import IndexArtifact, RetrievalMode, RetrievalResult
from cs30.errors import ArtifactMismatchError


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
