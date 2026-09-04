import pytest

from cs30.config import load_config
from cs30.contracts import StudentLevel
from cs30.errors import EmptyQueryError
from cs30.pipeline import (
    build_fixture_deps,
    build_parser,
    build_task7_smoke_deps,
    run_pipeline,
)

CONFIG = load_config("development")


def run(question: str, level: StudentLevel = StudentLevel.BEGINNER):
    return run_pipeline(question, level, build_fixture_deps(), CONFIG)


def test_fixture_pipeline_runs_end_to_end() -> None:
    result = run("What is acceleration?")

    assert result.mode == "fixture"
    assert result.trace["index_version"] == "fixture-index-v1"
    assert result.trace["artifact_version"] == "fixture-index-v1"
    assert result.profile.level is StudentLevel.BEGINNER
    assert result.retrieval.hits[0].chunk_id == "chunk_ch01_0001"
    assert result.answer.citations == ["chunk_ch01_0001"]
    assert result.answer.abstained is False
    assert result.citation_integrity == "passed"


def test_pipeline_abstains_when_no_evidence_matches() -> None:
    """An off-topic question must not be answered from unrelated fixtures."""

    result = run("What is quantum entanglement in condensed matter?")

    assert result.retrieval.hits == []
    assert result.answer.abstained is True
    assert result.answer.citations == []
    assert result.answer.final_choice is None


def test_every_citation_comes_from_retrieval() -> None:
    result = run("What is acceleration?")

    assert set(result.validated_answer.resolved_citations) <= {
        item.chunk_id for item in result.evidence_bundle.evidence_items
    }


def test_level_changes_the_explanation() -> None:
    explanations = {
        level: run("What is acceleration?", level).answer.explanation for level in StudentLevel
    }

    assert len(set(explanations.values())) == len(StudentLevel)


def test_empty_question_raises_typed_error() -> None:
    with pytest.raises(EmptyQueryError):
        run("   ")


def test_run_metadata_records_configuration() -> None:
    result = run("What is acceleration?")

    assert result.metadata["environment"] == "development"
    assert result.metadata["top_k"] == str(CONFIG.retrieval.top_k)
    assert "retrieval_ms" in result.metadata


def test_fixture_dependencies_declare_their_run_mode() -> None:
    assert build_fixture_deps().mode == "fixture"


def test_task7_smoke_dependencies_run_in_pipeline_and_record_generation() -> None:
    result = run_pipeline(
        "What is acceleration?",
        StudentLevel.INTERMEDIATE,
        build_task7_smoke_deps(),
        CONFIG,
    )

    assert result.mode == "fixture"
    assert result.citation_integrity == "passed"
    assert result.metadata["generation_model"] == "mock-json-generator"
    assert int(result.metadata["total_tokens"]) > 0
    assert result.metadata["generation_failures"] == "none"


def test_answer_only_and_top_k_are_optional_cli_controls() -> None:
    args = build_parser().parse_args(
        ["--question", "What is acceleration?", "--answer-only"]
    )

    assert args.answer_only is True
    assert args.top_k is None
