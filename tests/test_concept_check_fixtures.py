"""The shared Concept Check fixture pack is consistent and drives the runtime."""

from __future__ import annotations

import pytest

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.fixtures import (
    FIXTURE_CORPUS_HASH,
    FIXTURE_CORPUS_VERSION,
    FIXTURE_TOPIC_REGISTRY_VERSION,
    fixture_retrieval_result,
    load_fixture_corpus,
    load_fixture_releases,
    load_fixture_topic_registry,
)
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckQuestionStatus,
    ConceptCheckResult,
    GeneratedAnswer,
    QuestionSourceType,
    StudentLevel,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    ValidatedAnswer,
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


def test_retrieval_fixture_carries_the_corpus_identity_of_the_bindings() -> None:
    corpus = load_fixture_corpus()
    retrieval = fixture_retrieval_result(("fixture-cp2e-ch4-p1", "fixture-cp2e-ch2-p2"))

    assert retrieval.provenance is not None
    assert (retrieval.provenance.corpus_version, retrieval.provenance.corpus_hash) == (
        FIXTURE_CORPUS_VERSION,
        FIXTURE_CORPUS_HASH,
    )
    assert [hit.rank for hit in retrieval.hits] == [1, 2]
    assert [hit.chapter_id for hit in retrieval.hits] == ["4", "2"]
    assert all(hit.text == corpus.chunk_text(hit.chunk_id) for hit in retrieval.hits)
    with pytest.raises(ValueError, match="unknown fixture chunk"):
        fixture_retrieval_result(("not-a-fixture-chunk",))


class _ChapterTopicResolver:
    """Stand-in for M7's topics.py: each fixture chapter carries one Topic."""

    _topics = {"2": "acceleration", "4": "newtons-second-law"}

    def _resolve(self, chapter_id: str) -> TopicResolution:
        return TopicResolution(
            status=TopicResolutionStatus.RESOLVED,
            topic_id=self._topics[chapter_id],
            topic_registry_version=FIXTURE_TOPIC_REGISTRY_VERSION,
            support=1.0,
        )

    def resolve_retrieval_topic(self, retrieval):
        return self._resolve(retrieval.hits[0].chapter_id)

    def resolve_cited_topic(self, retrieval, validated):
        cited = {hit.chunk_id: hit for hit in retrieval.hits}
        return self._resolve(cited[validated.resolved_citations[0]].chapter_id)


def test_fixture_pack_drives_select_and_submit(tmp_path) -> None:
    profile = StudentProfile(profile_id="fixture-student", level=StudentLevel.BEGINNER)
    replayer = EventReplayer(profile, FIXTURE_TOPIC_REGISTRY_VERSION)
    service = ConceptCheckService(
        config=ConceptCheckConfig(enabled=True),
        resolver=_ChapterTopicResolver(),
        provider=FixtureQuestionProvider(load_fixture_releases()),
        event_store=JsonlEventStore(tmp_path, replayer),
        replayer=replayer,
    )
    retrieval = fixture_retrieval_result(("fixture-cp2e-ch4-p1", "fixture-cp2e-ch4-p2"))
    validated = ValidatedAnswer(
        answer=GeneratedAnswer(
            explanation="Acceleration is proportional to the net force.",
            citations=("fixture-cp2e-ch4-p1",),
        ),
        citation_status="passed",
        resolved_citations=("fixture-cp2e-ch4-p1",),
    )

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
