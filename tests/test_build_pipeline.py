from pathlib import Path

import cs30.pipeline as pipeline
from cs30.contracts import Chunk
from cs30.indexing.fixture import FixtureIndexBuilder
from cs30.retrieval.fixture import FixtureRetriever


def test_fixture_build_pipeline_produces_a_retrievable_index_artifact() -> None:
    deps = pipeline.build_fixture_build_deps()

    artifact = pipeline.run_build_pipeline(Path("unused-openstax-source"), deps)
    result = deps.retriever.retrieve("What is acceleration?", top_k=3)

    assert artifact.index_type == "fixture-lexical"
    assert artifact.chunk_count == 3
    assert result.hits[0].chunk_id == "chunk_ch01_0001"


def test_fixture_dependencies_cannot_be_reported_as_real() -> None:
    deps = pipeline.build_fixture_deps()

    result = pipeline.run_pipeline(
        "What is acceleration?",
        pipeline.StudentLevel.BEGINNER,
        deps,
        pipeline.load_config("development"),
    )

    assert result.mode == "fixture"


def test_fixture_retriever_loads_the_chunks_that_were_actually_indexed() -> None:
    chunk = Chunk(
        chunk_id="custom_chunk",
        document_id="custom_document",
        chapter_id="custom_chapter",
        text="zebraword",
        source="fixture://custom",
        char_start=0,
        char_end=9,
        token_count=1,
    )
    artifact = FixtureIndexBuilder().build([chunk])
    retriever = FixtureRetriever()

    retriever.load_index(artifact)
    result = retriever.retrieve("zebraword", top_k=1)

    assert [hit.chunk_id for hit in result.hits] == ["custom_chunk"]
