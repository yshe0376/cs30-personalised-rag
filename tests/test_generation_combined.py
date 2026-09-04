"""Behaviour tests for Task 7's portable combined-evidence retriever."""

from cs30.config import load_config
from cs30.contracts import RetrievalHit, RetrievalMode, StudentLevel
from cs30.generation import CombinedEvidenceRetriever
from cs30.pipeline import build_real_deps, run_pipeline


def evidence() -> list[RetrievalHit]:
    return [
        RetrievalHit(
            chunk_id="acceleration",
            text="Acceleration is the rate at which velocity changes with time.",
            chapter_id="motion",
            source="fixture://motion",
            score=1.0,
            rank=1,
            retriever_type=RetrievalMode.FIXTURE,
        ),
        RetrievalHit(
            chunk_id="corrosion",
            text="A painted coating can protect iron from corrosion.",
            chapter_id="chemistry",
            source="fixture://chemistry",
            score=1.0,
            rank=1,
            retriever_type=RetrievalMode.FIXTURE,
        ),
    ]


def test_combined_retriever_returns_relevant_ranked_evidence() -> None:
    result = CombinedEvidenceRetriever(evidence()).retrieve(
        "What is the difference between velocity and acceleration?",
        top_k=3,
    )

    assert [hit.chunk_id for hit in result.hits] == ["acceleration"]
    assert [hit.rank for hit in result.hits] == [1]
    assert result.mode is RetrievalMode.FIXTURE
    assert all(hit.retriever_type is RetrievalMode.FIXTURE for hit in result.hits)


def test_combined_retriever_rejects_single_word_accidental_overlap() -> None:
    result = CombinedEvidenceRetriever(evidence()).retrieve(
        "Who painted the Mona Lisa?",
        top_k=3,
    )

    assert result.mode is RetrievalMode.FIXTURE
    assert result.hits == []


def test_configured_pipeline_uses_fixture_corpus_and_abstains_without_evidence() -> None:
    config = load_config("development")
    result = run_pipeline(
        "Who painted the Mona Lisa?",
        StudentLevel.BEGINNER,
        build_real_deps(config),
        config,
    )

    assert result.mode == "fixture"
    assert result.retrieval.mode is RetrievalMode.FIXTURE
    assert result.retrieval.hits == []
    assert result.answer.abstained is True
    assert int(result.metadata["corpus_evidence_count"]) >= 44


def test_configured_pipeline_returns_only_retrieved_citations() -> None:
    config = load_config("development")
    result = run_pipeline(
        "What is the difference between velocity and acceleration?",
        StudentLevel.INTERMEDIATE,
        build_real_deps(config),
        config,
    )

    retrieved_ids = {hit.chunk_id for hit in result.retrieval.hits}
    assert result.mode == "fixture"
    assert result.retrieval.mode is RetrievalMode.FIXTURE
    assert all(
        hit.retriever_type is RetrievalMode.FIXTURE
        for hit in result.retrieval.hits
    )
    assert result.answer.abstained is False
    assert set(result.answer.citations) <= retrieved_ids
    assert result.metadata["index_type"] == "weighted-term-coverage"
