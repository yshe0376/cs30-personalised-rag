"""Contract and seam tests for the v2 Concept Check boundary."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cs30.concept_check.snapshot import build_learner_context_snapshot
from cs30.evaluation.models import GoldOption, GoldSource, PersonalisationEligibility, SourceSplit
from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS, get_textbook_spec
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckEventType,
    ConceptCheckGrade,
    ConceptCheckQuestion,
    ConceptCheckQuestionBinding,
    ConceptCheckQuestionRelease,
    ConceptCheckQuestionStatus,
    ConceptCheckResult,
    EvidenceBundle,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSpan,
    EvidenceSpanBinding,
    GoldQuestion,
    LearnerState,
    ProfileSource,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
    SpanResolutionMethod,
    SpanResolutionStatus,
    StudentLevel,
    StudentProfile,
    Topic,
    TopicRegistry,
    TopicResolution,
    TopicResolutionStatus,
    TopicState,
)
from cs30.v2.ids import sha256_text, source_locator
from cs30.v2.topics import ChunkTopicAssignment, ChunkTopicMap, resolve_topic_from_retrieval

TEXTBOOK_ID = REQUIRED_TEXTBOOK_IDS[0]
CORPUS_VERSION = "2.0.0-dev.1"
CORPUS_HASH = "sha256:corpus"


def _anchor(span_id: str = "cc:fixture:1", text: str = "Force changes motion.") -> EvidenceSpan:
    return EvidenceSpan(
        span_id=span_id,
        textbook_id=TEXTBOOK_ID,
        chapter_id="1",
        chapter_char_start=10,
        chapter_char_end=10 + len(text),
        verbatim_text=text,
        origin_corpus_version=CORPUS_VERSION,
    )


def _question(
    *,
    status: ConceptCheckQuestionStatus = ConceptCheckQuestionStatus.PUBLISHED,
    source_type: str = "human_authored",
) -> ConceptCheckQuestion:
    return ConceptCheckQuestion(
        question_id="cc:fixture:1",
        question="What changes an object's motion?",
        options={
            "A": "A force",
            "B": "A label",
            "C": "A page number",
            "D": "Nothing ever",
        },
        correct_answer="A",
        topic_id="mechanics",
        topic_registry_version="topics-0.1",
        difficulty=StudentLevel.BEGINNER,
        evidence_anchors=(_anchor(),),
        source_type=source_type,
        rationale="A net force changes an object's motion.",
        review_record_id="m3-review-1" if status in {
            ConceptCheckQuestionStatus.REVIEWED,
            ConceptCheckQuestionStatus.PUBLISHED,
        } else None,
        status=status,
    )


def _binding(
    *,
    span_id: str = "cc:fixture:1",
    status: SpanResolutionStatus = SpanResolutionStatus.RESOLVED,
) -> EvidenceSpanBinding:
    return EvidenceSpanBinding(
        span_id=span_id,
        textbook_id=TEXTBOOK_ID,
        corpus_version=CORPUS_VERSION,
        corpus_hash=CORPUS_HASH,
        resolution_status=status,
        resolution_method=(
            SpanResolutionMethod.VERBATIM_UNIQUE
            if status is SpanResolutionStatus.RESOLVED
            else None
        ),
        document_id="doc-1" if status is SpanResolutionStatus.RESOLVED else None,
        char_start=100 if status is SpanResolutionStatus.RESOLVED else None,
        char_end=(
            100 + len(_anchor(span_id=span_id).verbatim_text)
            if status is SpanResolutionStatus.RESOLVED
            else None
        ),
        chunk_ids=("chunk-1",) if status is SpanResolutionStatus.RESOLVED else (),
    )


def _retrieved(chunk_id: str, rank: int) -> RetrievedEvidence:
    return RetrievedEvidence(
        provider="openstax",
        textbook_id=TEXTBOOK_ID,
        document_id="doc-1",
        chunk_id=chunk_id,
        chapter_id="1",
        source_name=get_textbook_spec(TEXTBOOK_ID).source_name,
        page_or_location="chapter-1",
        source_locator=source_locator(
            source_name=TEXTBOOK_ID,
            textbook_id=TEXTBOOK_ID,
            chapter_id="1",
            page_or_location="chapter-1",
            char_start=rank * 10,
            char_end=rank * 10 + 5,
        ),
        text=f"evidence {rank}",
        score=1.0 / rank,
        rank=rank,
        retriever_type=RetrievalMode.FIXTURE,
    )


def _retrieval(*hits: RetrievedEvidence) -> RetrievalResult:
    return RetrievalResult(query="How does motion change?", mode=RetrievalMode.FIXTURE, hits=hits)


def test_published_question_requires_four_options_review_and_stable_anchor() -> None:
    question = _question()

    assert question.status is ConceptCheckQuestionStatus.PUBLISHED
    assert question.evidence_anchors[0].text_hash == sha256_text("Force changes motion.")
    assert question.split_guard == "practice_only"


@pytest.mark.parametrize(
    "update, message",
    [
        ({"options": {"A": "only one"}}, "exactly A, B, C, and D"),
        ({"correct_answer": "E"}, "correct_answer"),
        ({"status": "published", "review_record_id": None}, "review_record_id"),
    ],
)
def test_question_contract_rejects_invalid_publication_shape(
    update: dict[str, object], message: str,
) -> None:
    payload = _question().model_dump()
    payload.update(update)
    with pytest.raises(ValueError, match=message):
        ConceptCheckQuestion.model_validate(payload)


def test_sciq_practice_questions_cannot_use_test_split() -> None:
    payload = _question(status=ConceptCheckQuestionStatus.REVIEWED).model_dump()
    payload.update(
        {
            "source_type": "sciq_aligned",
            "source": GoldSource(
                dataset="SciQ",
                source_question_id="sciq-train-1",
                support="Force changes motion.",
            ).model_dump(),
            "source_split": SourceSplit.TEST,
        }
    )
    with pytest.raises(ValueError, match="train/validation"):
        ConceptCheckQuestion.model_validate(payload)


def test_published_release_requires_every_anchor_to_resolve_current_corpus() -> None:
    question = _question()
    binding = ConceptCheckQuestionBinding(
        question_id=question.question_id,
        corpus_version=CORPUS_VERSION,
        corpus_hash=CORPUS_HASH,
        bindings=(_binding(),),
    )
    release = ConceptCheckQuestionRelease(question=question, binding=binding)
    assert release.binding.bindings[0].chunk_ids == ("chunk-1",)

    stale_binding = binding.model_copy(
        update={"bindings": (_binding(status=SpanResolutionStatus.STALE),)}
    )
    with pytest.raises(ValueError, match="resolved bindings"):
        ConceptCheckQuestionRelease(
            question=question,
            binding=stale_binding,
        )


def test_v2_gold_question_uses_the_same_evidence_span_type() -> None:
    gold = GoldQuestion(
        question_id="gold:fixture:1",
        question="What changes motion?",
        options={
            label: GoldOption(text=text, source_field="fixture")
            for label, text in {
                "A": "A force",
                "B": "A label",
                "C": "A page number",
                "D": "Nothing",
            }.items()
        },
        gold_answer="A",
        answerable=True,
        gold_core_evidence_sets=((
            {
                "span": _anchor("gold:fixture:1"),
                "sufficiency": "core_sufficient",
            },
        ),),
        question_difficulty="beginner",
        question_type="causal",
        concept_group="mechanics",
        personalisation_eligibility=PersonalisationEligibility.FULL,
        eligibility_reason="fixture",
        split="dev",
        corpus_version=CORPUS_VERSION,
        parser_version="fixture-parser-2.0",
        gold_annotation_version="gold-2.0",
        annotation_status="reviewed",
        review_record_id="m3-review-gold-1",
    )

    assert gold.gold_core_evidence_sets[0][0].span.span_id == "gold:fixture:1"


def test_topic_resolution_splits_multi_topic_chunk_weight_and_records_ties() -> None:
    registry = TopicRegistry(
        topic_registry_version="topics-0.1",
        topics=(
            Topic(topic_id="mechanics", title="Mechanics"),
            Topic(topic_id="energy", title="Energy"),
        ),
    )
    topic_map = ChunkTopicMap(
        corpus_version=CORPUS_VERSION,
        corpus_hash=CORPUS_HASH,
        topic_registry_version="topics-0.1",
        assignments=(
            ChunkTopicAssignment(chunk_id="c1", topic_ids=("mechanics", "energy")),
        ),
    )
    resolved = resolve_topic_from_retrieval(_retrieval(_retrieved("c1", 1)), topic_map, registry)
    assert resolved.status is TopicResolutionStatus.NO_TOPIC_AVAILABLE
    assert resolved.error_code == "TOPIC_TIE"

    topic_map = topic_map.model_copy(
        update={
            "assignments": (
                ChunkTopicAssignment(chunk_id="c1", topic_ids=("mechanics",)),
                ChunkTopicAssignment(chunk_id="c2", topic_ids=("energy",)),
            )
        }
    )
    resolved = resolve_topic_from_retrieval(
        _retrieval(_retrieved("c1", 1), _retrieved("c2", 2)),
        topic_map,
        registry,
    )
    assert resolved.status is TopicResolutionStatus.RESOLVED
    assert resolved.topic_id == "mechanics"
    assert resolved.topic_support["mechanics"] == pytest.approx(2 / 3)


def test_topic_map_mismatch_is_not_silently_treated_as_no_topic() -> None:
    registry = TopicRegistry(
        topic_registry_version="topics-0.1",
        topics=(Topic(topic_id="mechanics", title="Mechanics"),),
    )
    topic_map = ChunkTopicMap(
        corpus_version="other-corpus",
        corpus_hash=CORPUS_HASH,
        topic_registry_version="topics-0.1",
        assignments=(ChunkTopicAssignment(chunk_id="c1", topic_ids=("mechanics",)),),
    )
    provenance = EvidenceProvenance(
        corpus_version=CORPUS_VERSION,
        corpus_hash=CORPUS_HASH,
        manifest_hash="sha256:manifest",
        chunk_config_hash="sha256:chunks",
        index_version="index-1",
        retrieval_mode=RetrievalMode.FIXTURE,
        retrieval_config_hash="sha256:retrieval",
    )
    result = RetrievalResult(
        query="q",
        mode=RetrievalMode.FIXTURE,
        hits=(_retrieved("c1", 1),),
        provenance=provenance,
    )
    resolved = resolve_topic_from_retrieval(result, topic_map, registry)
    assert resolved.status is TopicResolutionStatus.TOPIC_MAP_MISMATCH
    assert resolved.error_code == "TOPIC_MAP_MISMATCH"


def test_snapshot_disabled_bypasses_state_and_preserves_static_profile() -> None:
    profile = StudentProfile(
        profile_id="student-1",
        level=StudentLevel.BEGINNER,
        confidence=0.8,
    )
    state = LearnerState(
        state_id="state-1",
        profile_id="student-1",
        topic_registry_version="topics-0.1",
        state_version=9,
    )
    snapshot = build_learner_context_snapshot(
        profile,
        enabled=False,
        learner_state=state,
        topic_resolution=TopicResolution(
            status=TopicResolutionStatus.TOPIC_MAP_UNAVAILABLE,
            error_code="TOPIC_MAP_UNAVAILABLE",
        ),
    )
    assert snapshot.profile_source is ProfileSource.STATIC_PROFILE
    assert snapshot.profile == profile
    assert snapshot.state_version == 0
    assert snapshot.resolver_called is False


def test_enabled_snapshot_uses_topic_level_but_not_coverage_as_confidence() -> None:
    profile = StudentProfile(
        profile_id="student-1",
        level=StudentLevel.BEGINNER,
        confidence=0.8,
    )
    state = LearnerState(
        state_id="state-1",
        profile_id="student-1",
        topic_registry_version="topics-0.1",
        state_version=9,
        derived_from_event_version=9,
        topics={
            "mechanics": TopicState(
                topic_id="mechanics",
                level=StudentLevel.INTERMEDIATE,
                attempt_coverage=0.4,
                total_attempts=2,
                attempts_since_level_change=2,
                correct_attempts=2,
            )
        },
    )
    resolution = TopicResolution(
        status=TopicResolutionStatus.RESOLVED,
        topic_id="mechanics",
        topic_registry_version="topics-0.1",
        support=0.8,
    )
    snapshot = build_learner_context_snapshot(
        profile,
        enabled=True,
        learner_state=state,
        topic_resolution=resolution,
    )
    assert snapshot.profile_source is ProfileSource.LEARNER_STATE_REPLAY
    assert snapshot.profile.level is StudentLevel.INTERMEDIATE
    assert snapshot.profile.confidence == 0.8
    assert snapshot.attempt_coverage == 0.4
    assert snapshot.topic_state is not None


def test_grade_and_event_contracts_keep_submission_deterministic() -> None:
    grade = ConceptCheckGrade(
        attempt_id="attempt-1",
        question_id="cc:fixture:1",
        selected_choice="A",
        correct_answer="A",
        result=ConceptCheckResult.CORRECT,
        performance=1.0,
    )
    event = ConceptCheckEvent(
        event_id="event-1",
        profile_id="student-1",
        attempt_id=grade.attempt_id,
        question_id=grade.question_id,
        topic_id="mechanics",
        question_difficulty=StudentLevel.BEGINNER,
        selected_choice=grade.selected_choice,
        performance=grade.performance,
        event_type=ConceptCheckEventType.ATTEMPT_SUBMITTED,
        state_version_before=0,
        stream_version=1,
        created_at=datetime.now(UTC),
    )
    assert event.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED

    with pytest.raises(ValueError, match="performance 1.0"):
        ConceptCheckGrade.model_validate({**grade.model_dump(), "performance": 0.5})


def test_evidence_bundle_requires_exact_citation_map() -> None:
    item = EvidenceItem(
        evidence_id="E1",
        provider="openstax",
        textbook_id=TEXTBOOK_ID,
        document_id="doc-1",
        chunk_id="chunk-1",
        chapter_id="1",
        source_name=TEXTBOOK_ID,
        page_or_location="chapter-1",
        source_locator=source_locator(
            source_name=TEXTBOOK_ID,
            textbook_id=TEXTBOOK_ID,
            chapter_id="1",
            page_or_location="chapter-1",
            char_start=0,
            char_end=5,
        ),
        text="abcde",
        rank=1,
        score=1.0,
        token_count=1,
    )
    bundle = EvidenceBundle(
        query="q",
        retrieval_mode=RetrievalMode.FIXTURE,
        evidence_items=(item,),
        citation_map={"E1": "chunk-1"},
        token_count=1,
    )
    assert bundle.citation_map == {"E1": "chunk-1"}
