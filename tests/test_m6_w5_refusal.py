"""M6 W5 deterministic Dense/Hybrid refusal gates."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cs30.retrieval.real as real_retrieval
from cs30.config import AppConfig, RetrievalConfig
from cs30.contracts import IndexArtifact, RetrievalMode, StudentLevel
from cs30.generation import FixtureAnswerGenerator
from cs30.pipeline import PipelineDeps, run_pipeline
from cs30.profile import FixtureProfileProvider


class _ControlledModel:
    def encode(
        self,
        sentences: list[str],
        *,
        convert_to_numpy: bool = True,
    ) -> np.ndarray:
        del sentences, convert_to_numpy
        return np.array([[1.0, 0.0]], dtype=np.float32)


class _BelowThresholdIndex:
    ntotal = 2
    d = 2

    def search(
        self,
        vectors: np.ndarray,
        top_k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        del vectors
        scores = np.array([[0.49, 0.10]], dtype=np.float32)
        positions = np.array([[0, 1]], dtype=np.int64)
        return scores[:, :top_k], positions[:, :top_k]


def _chunks() -> list[dict[str, object]]:
    return [
        {
            "position": 0,
            "chunk_id": "chunk-1",
            "text": "Acceleration is the rate of change of velocity.",
            "chapter_id": "chapter-1",
            "source": "fixture://openstax/chapter-1",
        },
        {
            "position": 1,
            "chunk_id": "chunk-2",
            "text": "Force equals mass times acceleration.",
            "chapter_id": "chapter-1",
            "source": "fixture://openstax/chapter-1",
        },
    ]


def _artifact() -> IndexArtifact:
    return IndexArtifact(
        artifact_id="controlled-m6-refusal",
        index_type="faiss-flat-ip",
        location="unused",
        chunk_count=2,
        metadata={
            "corpus_hash": "controlled-corpus",
            "chunk_config_hash": "controlled-chunks",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "index_version": "controlled-index-v1",
            "dimension": "2",
        },
    )


def _dense(monkeypatch: pytest.MonkeyPatch) -> real_retrieval.FaissDenseRetriever:
    monkeypatch.setattr(real_retrieval, "_load_chunk_map", lambda artifact: _chunks())
    monkeypatch.setattr(
        real_retrieval,
        "_resolve_artifact_file",
        lambda *args, **kwargs: Path("unused"),
    )
    retriever = real_retrieval.FaissDenseRetriever(
        expected_model_name="sentence-transformers/all-MiniLM-L6-v2",
        min_similarity=0.50,
        model_loader=lambda model_name: _ControlledModel(),
        index_reader=lambda path: _BelowThresholdIndex(),
    )
    retriever.load_index(_artifact())
    return retriever


def _run(retriever: object, mode: RetrievalMode):
    config = AppConfig(
        fixture_mode=False,
        retrieval=RetrievalConfig(mode=mode, top_k=2),
    )
    deps = PipelineDeps(
        mode="real",
        profile_provider=FixtureProfileProvider(),
        retriever=retriever,
        generator=FixtureAnswerGenerator(),
    )
    return run_pipeline(
        "Which unsupported topic should be answered?",
        StudentLevel.INTERMEDIATE,
        deps,
        config,
    )


def _assert_safe_refusal(result: object, mode: RetrievalMode) -> None:
    assert result.retrieval.mode is mode
    assert result.retrieval.hits == []
    assert result.evidence_bundle.evidence_items == []
    assert result.answer.abstained is True
    assert result.answer.citations == []
    assert result.citation_integrity == "skipped"


def test_dense_threshold_empty_result_reaches_generation_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_safe_refusal(_run(_dense(monkeypatch), RetrievalMode.DENSE), RetrievalMode.DENSE)


def test_hybrid_empty_result_reaches_generation_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dense = _dense(monkeypatch)
    bm25 = real_retrieval.BM25Retriever(min_score=1_000_000.0)
    bm25.load_index(_artifact())
    hybrid = real_retrieval.RRFRetriever(dense=dense, bm25=bm25)
    hybrid.load_index(_artifact())

    _assert_safe_refusal(_run(hybrid, RetrievalMode.HYBRID), RetrievalMode.HYBRID)
