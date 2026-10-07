"""The shared Concept Check fixture pack is consistent and drives the runtime."""

from __future__ import annotations

import pytest

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.fixtures import (
    FIXTURE_CHUNK_CONFIG_HASH,
    FIXTURE_CORPUS_HASH,
    FIXTURE_CORPUS_VERSION,
    FIXTURE_TOPIC_REGISTRY_VERSION,
    fixture_retrieval_result,
    load_fixture_chunk_topic_map,
    load_fixture_corpus,
    load_fixture_manifest,
    load_fixture_releases,
    load_fixture_scenarios,
    load_fixture_topic_registry,
)
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckQuestionStatus,
    ConceptCheckResult,
    QuestionSourceType,
    StudentLevel,
    StudentProfile,
    TopicResolutionStatus,
)
from cs30.v2.topics import (
    canonical_chunk_topic_map,
    resolve_topic_from_citations,
    resolve_topic_from_retrieval,
)


def test_releases_are_published_practice_questions_on_the_fixture_registry() -> None:
    registry = load_fixture_topic_registry()
    releases = load_fixture_releases()

    assert registry.topic_registry_version == FIXTURE_TOPIC_REGISTRY_VERSION
    assert 3 <= len(releases) <= 5
    topic_ids = {topic.topic_id for topic in registry.topics}
    levels: dict[str, set[StudentLevel]] = {}
    for release in releases:
        question = release.question
        assert question.status is ConceptCheckQuestionStatus.PUBLISHED
        assert question.split_guard == "practice_only"
        assert question.source_type is QuestionSourceType.HUMAN_AUTHORED
        assert question.review_record_id == f"fixture-review:{question.question_id}"
        assert question.topic_registry_version == FIXTURE_TOPIC_REGISTRY_VERSION
        assert question.topic_id in topic_ids
        assert len(set(question.options.values())) == 4
        levels.setdefault(question.topic_id, set()).add(question.difficulty)
    # One Topic spans every level, so the upward probe can be exercised.
    assert levels["newtons-second-law"] == set(StudentLevel)
    assert len({release.question.correct_answer for release in releases}) >= 3


def test_corpus_chunks_tile_their_chapters_in_order() -> None:
    corpus = load_fixture_corpus()

    assert (corpus.corpus_version, corpus.corpus_hash) == (
        FIXTURE_CORPUS_VERSION,
        FIXTURE_CORPUS_HASH,
    )
    for chapter in corpus.chapters:
        chunks = [chunk for chunk in corpus.chunks if chunk.chapter_id == chapter.chapter_id]
        assert chunks[0].char_start == chapter.char_start
        assert chunks[-1].char_end == chapter.char_end
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.char_end < current.char_start
        for chunk in chunks:
            text = corpus.chunk_text(chunk.chunk_id)
            assert text and text == text.strip()


def test_anchors_quote_the_corpus_and_bindings_locate_them() -> None:
    corpus = load_fixture_corpus()

    for release in load_fixture_releases():
        assert (release.binding.corpus_version, release.binding.corpus_hash) == (
            FIXTURE_CORPUS_VERSION,
            FIXTURE_CORPUS_HASH,
        )
        bindings = {binding.span_id: binding for binding in release.binding.bindings}
        for anchor in release.question.evidence_anchors:
            chapter = corpus.chapter(anchor.chapter_id)
            start = chapter.char_start + anchor.chapter_char_start
            end = chapter.char_start + anchor.chapter_char_end
            assert anchor.textbook_id == corpus.textbook_id
            assert anchor.origin_corpus_version == FIXTURE_CORPUS_VERSION
            assert end <= chapter.char_end
            assert corpus.text[start:end] == anchor.verbatim_text

            binding = bindings[anchor.span_id]
            assert (binding.document_id, binding.char_start, binding.char_end) == (
                corpus.document_id,
                start,
                end,
            )
            assert binding.chunk_ids == tuple(
                chunk.chunk_id
                for chunk in corpus.chunks
                if chunk.char_start < end and start < chunk.char_end
            )


def test_retrieval_fixture_carries_the_corpus_and_manifest_identity() -> None:
    corpus = load_fixture_corpus()
    manifest = load_fixture_manifest()
    retrieval = fixture_retrieval_result(("fixture-cp2e-ch4-p1", "fixture-cp2e-ch2-p2"))

    assert retrieval.provenance is not None
    assert (retrieval.provenance.corpus_version, retrieval.provenance.corpus_hash) == (
        FIXTURE_CORPUS_VERSION,
        FIXTURE_CORPUS_HASH,
    )
    assert retrieval.provenance.manifest_hash == manifest.manifest_hash
    assert retrieval.provenance.chunk_config_hash == FIXTURE_CHUNK_CONFIG_HASH
    assert [hit.rank for hit in retrieval.hits] == [1, 2]
    assert [hit.chapter_id for hit in retrieval.hits] == ["4", "2"]
    assert all(hit.text == corpus.chunk_text(hit.chunk_id) for hit in retrieval.hits)
    with pytest.raises(ValueError, match="unknown fixture chunk"):
        fixture_retrieval_result(("not-a-fixture-chunk",))


def test_topic_map_validates_against_the_fixture_manifest() -> None:
    corpus = load_fixture_corpus()
    manifest = load_fixture_manifest()
    registry = load_fixture_topic_registry()
    loaded = load_fixture_chunk_topic_map()

    assert loaded.error_code is None and loaded.topic_map is not None
    assert (loaded.corpus_version, loaded.corpus_hash) == (
        FIXTURE_CORPUS_VERSION,
        FIXTURE_CORPUS_HASH,
    )
    assert manifest.mode == "development" and not manifest.reportable
    assert manifest.record_count == len(corpus.chunks)
    topic_map = loaded.topic_map
    assert topic_map.topic_registry_version == registry.topic_registry_version
    assert canonical_chunk_topic_map(topic_map) == topic_map
    assignments = {item.chunk_id: item.topic_ids for item in topic_map.assignments}
    known = {topic.topic_id for topic in registry.topics}
    assert all(set(topic_ids) <= known for topic_ids in assignments.values())
    # Deliberate edge cases: one chunk splits its weight, one has no Topic.
    assert [len(topic_ids) for topic_ids in assignments.values()].count(2) == 1
    assert {chunk.chunk_id for chunk in corpus.chunks} - set(assignments) == {"fixture-cp2e-ch2-p3"}


def test_every_question_is_bound_to_chunks_of_its_own_topic() -> None:
    loaded = load_fixture_chunk_topic_map()
    assert loaded.topic_map is not None
    assignments = {item.chunk_id: item.topic_ids for item in loaded.topic_map.assignments}

    for release in load_fixture_releases():
        for binding in release.binding.bindings:
            for chunk_id in binding.chunk_ids:
                assert release.question.topic_id in assignments[chunk_id]


@pytest.mark.parametrize(
    "scenario", load_fixture_scenarios(), ids=lambda scenario: scenario.scenario_id
)
def test_scenarios_resolve_as_documented_with_the_m1_resolver(scenario) -> None:
    topic_map = load_fixture_chunk_topic_map()
    registry = load_fixture_topic_registry()
    retrieval = scenario.retrieval()

    resolutions = (
        (
            resolve_topic_from_retrieval(retrieval, topic_map, registry),
            scenario.expected_retrieval_topic,
            scenario.expected_retrieval_error,
        ),
        (
            resolve_topic_from_citations(
                retrieval, scenario.validated_answer(), topic_map, registry
            ),
            scenario.expected_cited_topic,
            scenario.expected_cited_error,
        ),
    )
    for resolution, topic_id, error_code in resolutions:
        assert resolution.topic_id == topic_id
        assert resolution.error_code == error_code
        assert (resolution.status is TopicResolutionStatus.RESOLVED) == (topic_id is not None)


def test_scenarios_carry_a_displayable_answer_that_the_validated_answer_uses() -> None:
    scenarios = load_fixture_scenarios()

    assert len({scenario.scenario_id for scenario in scenarios}) == len(scenarios)
    for scenario in scenarios:
        assert scenario.query.strip() and scenario.answer.strip()
        validated = scenario.validated_answer()
        assert validated.answer.explanation == scenario.answer
        assert validated.resolved_citations == scenario.cited_chunk_ids


class _FixtureTopicResolver:
    """Stand-in for M7's topics.py: the M1 resolver functions over the fixture map."""

    def __init__(self) -> None:
        self.topic_map = load_fixture_chunk_topic_map()
        self.registry = load_fixture_topic_registry()

    def resolve_retrieval_topic(self, retrieval):
        return resolve_topic_from_retrieval(retrieval, self.topic_map, self.registry)

    def resolve_cited_topic(self, retrieval, validated):
        return resolve_topic_from_citations(retrieval, validated, self.topic_map, self.registry)


def _service(
    tmp_path, level: StudentLevel = StudentLevel.BEGINNER
) -> tuple[ConceptCheckService, StudentProfile]:
    profile = StudentProfile(profile_id="fixture-student", level=level)
    replayer = EventReplayer(profile, FIXTURE_TOPIC_REGISTRY_VERSION)
    service = ConceptCheckService(
        config=ConceptCheckConfig(enabled=True),
        resolver=_FixtureTopicResolver(),
        provider=FixtureQuestionProvider(load_fixture_releases()),
        event_store=JsonlEventStore(tmp_path, replayer),
        replayer=replayer,
    )
    return service, profile


def _scenario(scenario_id: str):
    return next(item for item in load_fixture_scenarios() if item.scenario_id == scenario_id)


def test_fixture_pack_drives_select_and_submit(tmp_path) -> None:
    service, profile = _service(tmp_path)
    scenario = _scenario("newtons-second-law")
    retrieval, validated = scenario.retrieval(), scenario.validated_answer()

    prepared = service.prepare(retrieval, profile)
    first = service.select(prepared, retrieval, validated)
    assert first is not None and first.question.question_id == "cc-fixture-003"

    grade, state = service.submit(
        first,
        attempt_id="fixture-attempt-1",
        selected_choice=first.question.correct_answer,
        event_id="fixture-event-1",
        corpus_version=FIXTURE_CORPUS_VERSION,
        corpus_hash=FIXTURE_CORPUS_HASH,
    )
    assert grade.result is ConceptCheckResult.CORRECT
    assert state.topics["newtons-second-law"].total_attempts == 1

    # The answered beginner question is excluded; the nearest level comes next.
    second = service.select(prepared, retrieval, validated)
    assert second is not None and second.question.question_id == "cc-fixture-004"


def test_cited_topic_chooses_the_question_and_a_tie_offers_none(tmp_path) -> None:
    service, profile = _service(tmp_path)

    differs = _scenario("cited-topic-differs")
    retrieval = differs.retrieval()
    prepared = service.prepare(retrieval, profile)
    assert prepared.snapshot.topic_id == "newtons-second-law"
    release = service.select(prepared, retrieval, differs.validated_answer())
    assert release is not None and release.question.question_id == "cc-fixture-001"

    tie = _scenario("topic-tie")
    retrieval = tie.retrieval()
    prepared = service.prepare(retrieval, profile)
    assert prepared.snapshot.topic_id is None
    assert service.select(prepared, retrieval, tie.validated_answer()) is None


def test_level_not_scenario_decides_which_newton_question_comes_first(tmp_path) -> None:
    scenario = _scenario("two-block-system")
    retrieval, validated = scenario.retrieval(), scenario.validated_answer()
    expected = {
        StudentLevel.BEGINNER: "cc-fixture-003",
        StudentLevel.ADVANCED: "cc-fixture-005",
    }

    for level, question_id in expected.items():
        service, profile = _service(tmp_path / level.value, level)
        prepared = service.prepare(retrieval, profile)
        release = service.select(prepared, retrieval, validated)
        assert release is not None and release.question.question_id == question_id
