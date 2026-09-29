"""Runtime checks for M7's independent Concept Check fixture path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.generator import OfflineDraftGenerator
from cs30.concept_check.grader import DeterministicGrader
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider, target_levels
from cs30.concept_check.service import ConceptCheckService
from cs30.concept_check.validator import PublicationValidator
from cs30.evaluation.models import GoldOption, PersonalisationEligibility
from cs30.generation.client import LLMResponse, TokenUsage
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckEventType,
    ConceptCheckQuestion,
    ConceptCheckQuestionBinding,
    ConceptCheckQuestionRelease,
    ConceptCheckQuestionStatus,
    ConceptCheckResult,
    EvidenceProvenance,
    EvidenceSpan,
    EvidenceSpanBinding,
    GeneratedAnswer,
    GoldQuestion,
    ProfileSource,
    RetrievalMode,
    RetrievalResult,
    SpanResolutionMethod,
    SpanResolutionStatus,
    StudentLevel,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    TopicState,
    ValidatedAnswer,
)

_TIME = datetime(2026, 9, 29, tzinfo=UTC)
_PROFILE = StudentProfile(profile_id="student-1", level=StudentLevel.BEGINNER, confidence=0.8)


def _event(
    version: int,
    *,
    performance: float = 1.0,
    difficulty: StudentLevel = StudentLevel.BEGINNER,
    kind: ConceptCheckEventType = ConceptCheckEventType.ATTEMPT_SUBMITTED,
    revoked_attempt_id: str | None = None,
) -> ConceptCheckEvent:
    return ConceptCheckEvent(
        event_id=f"event-{version}",
        profile_id=_PROFILE.profile_id,
        attempt_id=None if kind is ConceptCheckEventType.ATTEMPT_REVOKED else f"attempt-{version}",
        revoked_attempt_id=revoked_attempt_id,
        question_id=None if kind is ConceptCheckEventType.ATTEMPT_REVOKED else f"q-{version}",
        topic_id="motion",
        topic_registry_version="topics-1",
        question_difficulty=None if kind is ConceptCheckEventType.ATTEMPT_REVOKED else difficulty,
        selected_choice=None if kind is ConceptCheckEventType.ATTEMPT_REVOKED else "A",
        performance=None if kind is ConceptCheckEventType.ATTEMPT_REVOKED else performance,
        event_type=kind,
        state_version_before=version - 1,
        stream_version=version,
        created_at=_TIME + timedelta(seconds=version),
    )


def _release(question_id: str, difficulty: StudentLevel = StudentLevel.BEGINNER):
    anchor = EvidenceSpan(
        span_id=f"cc:{question_id}:1",
        textbook_id="book-1",
        chapter_id="chapter-1",
        chapter_char_start=0,
        chapter_char_end=5,
        verbatim_text="Force",
        origin_corpus_version="v2-dev",
    )
    question = ConceptCheckQuestion(
        question_id=question_id,
        question="What changes motion?",
        options={"A": "Force", "B": "Colour", "C": "Name", "D": "Nothing"},
        correct_answer="A",
        topic_id="motion",
        topic_registry_version="topics-1",
        difficulty=difficulty,
        evidence_anchors=(anchor,),
        source_type="human_authored",
        rationale="A force changes motion.",
        review_record_id="synthetic-review",
        status=ConceptCheckQuestionStatus.PUBLISHED,
    )
    binding = ConceptCheckQuestionBinding(
        question_id=question_id,
        corpus_version="v2-dev",
        corpus_hash="sha256:fixture",
        bindings=(
            EvidenceSpanBinding(
                span_id=anchor.span_id,
                textbook_id=anchor.textbook_id,
                corpus_version="v2-dev",
                corpus_hash="sha256:fixture",
                resolution_status=SpanResolutionStatus.RESOLVED,
                resolution_method=SpanResolutionMethod.VERBATIM_UNIQUE,
                document_id="doc-1",
                char_start=0,
                char_end=5,
                chunk_ids=("chunk-1",),
            ),
        ),
    )
    return ConceptCheckQuestionRelease(question=question, binding=binding)


def test_grader_and_promotion_replay_are_deterministic() -> None:
    question = _release("fixture-q").question
    grader = DeterministicGrader()
    assert (
        grader.grade(question, attempt_id="a", selected_choice="A").result
        is ConceptCheckResult.CORRECT
    )
    assert grader.grade(question, attempt_id="b", selected_choice="B").performance == 0.0
    assert (
        grader.grade(question, attempt_id="c", selected_choice=None).result
        is ConceptCheckResult.SKIPPED
    )

    replayer = EventReplayer(_PROFILE, "topics-1")
    events = tuple(
        _event(i, difficulty=StudentLevel.INTERMEDIATE if i > 4 else StudentLevel.BEGINNER)
        for i in range(1, 7)
    )
    state = replayer.replay(events)
    assert replayer.replay(events) == state
    assert state.topics["motion"].level is StudentLevel.INTERMEDIATE
    assert state.topics["motion"].total_attempts == 6
    assert state.topics["motion"].attempt_coverage == 0.0


def test_revocation_is_latest_only_and_recomputes_state() -> None:
    replayer = EventReplayer(_PROFILE, "topics-1")
    first, second = _event(1), _event(2, performance=0.0)
    with pytest.raises(ValueError, match="most recent"):
        replayer.replay(
            (
                first,
                second,
                _event(
                    3, kind=ConceptCheckEventType.ATTEMPT_REVOKED, revoked_attempt_id="attempt-1"
                ),
            )
        )
    revoked = _event(3, kind=ConceptCheckEventType.ATTEMPT_REVOKED, revoked_attempt_id="attempt-2")
    state = replayer.replay((first, second, revoked))
    assert state.topics["motion"].mastery_score == pytest.approx(0.6)
    assert state.topics["motion"].total_attempts == 1
    with pytest.raises(ValueError, match="already revoked"):
        replayer.replay(
            (
                first,
                second,
                revoked,
                _event(
                    4, kind=ConceptCheckEventType.ATTEMPT_REVOKED, revoked_attempt_id="attempt-2"
                ),
            )
        )


def test_jsonl_store_is_append_only_and_attempt_idempotent(tmp_path) -> None:
    replayer = EventReplayer(_PROFILE, "topics-1")
    store = JsonlEventStore(tmp_path, replayer)
    first = store.append(_event(1))
    retry = _event(2).model_copy(update={"attempt_id": "attempt-1", "question_id": "q-1"})
    assert store.append(retry) == first
    assert len(store.events(_PROFILE.profile_id)) == 1
    with pytest.raises(ValueError, match="idempotency conflict"):
        store.append(retry.model_copy(update={"performance": 0.0}))
    assert store.append(_event(2)).stream_version == 2
    assert replayer.replay(store.events(_PROFILE.profile_id)).state_version == 2


def test_provider_uses_level_priority_overlap_and_current_corpus() -> None:
    provider = FixtureQuestionProvider((_release("b"), _release("a")))
    chosen = provider.select(
        topic_id="motion",
        target_levels=(StudentLevel.BEGINNER,),
        corpus_version="v2-dev",
        corpus_hash="sha256:fixture",
        cited_chunk_ids=("chunk-1",),
    )
    assert chosen is not None and chosen.question.question_id == "a"
    assert (
        provider.select(
            topic_id="motion",
            target_levels=(StudentLevel.BEGINNER,),
            corpus_version="v2-dev",
            corpus_hash="sha256:wrong",
            cited_chunk_ids=(),
        )
        is None
    )
    upward = TopicState(topic_id="motion", level=StudentLevel.BEGINNER, mastery_score=0.8)
    assert target_levels(upward, ConceptCheckConfig())[0] is StudentLevel.INTERMEDIATE


def test_disabled_service_never_calls_resolver_or_store() -> None:
    class Forbidden:
        def __getattr__(self, name):
            raise AssertionError(f"disabled Concept Check accessed {name}")

    service = ConceptCheckService(
        config=ConceptCheckConfig(enabled=False),
        resolver=Forbidden(),
        provider=Forbidden(),
        event_store=Forbidden(),
        replayer=EventReplayer(_PROFILE, "topics-1"),
    )
    retrieval = RetrievalResult(query="What is force?", mode=RetrievalMode.FIXTURE)
    prepared = service.prepare(retrieval, _PROFILE)
    assert prepared.snapshot.profile_source is ProfileSource.STATIC_PROFILE
    assert prepared.snapshot.profile.confidence == 0.8
    validated = ValidatedAnswer(
        answer=GeneratedAnswer(explanation="No evidence.", abstained=True),
        citation_status="skipped",
    )
    assert service.select(prepared, retrieval, validated) is None


def test_enabled_service_selects_once_then_replays_submission(tmp_path) -> None:
    class Resolver:
        calls = 0

        def resolve_retrieval_topic(self, retrieval):
            self.calls += 1
            return TopicResolution(
                status=TopicResolutionStatus.RESOLVED,
                topic_id="motion",
                topic_registry_version="topics-1",
                support=1.0,
            )

        def resolve_cited_topic(self, retrieval, validated):
            self.calls += 1
            return TopicResolution(
                status=TopicResolutionStatus.RESOLVED,
                topic_id="motion",
                topic_registry_version="topics-1",
                support=1.0,
            )

    resolver = Resolver()
    replayer = EventReplayer(_PROFILE, "topics-1")
    store = JsonlEventStore(tmp_path, replayer)
    service = ConceptCheckService(
        config=ConceptCheckConfig(enabled=True),
        resolver=resolver,
        provider=FixtureQuestionProvider((_release("q-1"),)),
        event_store=store,
        replayer=replayer,
    )
    retrieval = RetrievalResult(
        query="What is motion?",
        mode=RetrievalMode.FIXTURE,
        provenance=EvidenceProvenance(
            corpus_version="v2-dev",
            corpus_hash="sha256:fixture",
            manifest_hash="sha256:manifest",
            chunk_config_hash="sha256:chunks",
            index_version="index-1",
            retrieval_mode=RetrievalMode.FIXTURE,
            retrieval_config_hash="sha256:retrieval",
        ),
    )
    prepared = service.prepare(retrieval, _PROFILE)
    assert prepared.snapshot.profile_source is ProfileSource.LEARNER_STATE_REPLAY
    assert prepared.snapshot.profile.confidence == 0.8
    validated = ValidatedAnswer(
        answer=GeneratedAnswer(final_choice="A", explanation="Force.", citations=("chunk-1",)),
        citation_status="passed",
        resolved_citations=("chunk-1",),
    )
    release = service.select(prepared, retrieval, validated)
    assert release is not None and release.question.question_id == "q-1"
    grade, state = service.submit(
        release,
        attempt_id="attempt-1",
        selected_choice="A",
        event_id="event-1",
        corpus_version="v2-dev",
        corpus_hash="sha256:fixture",
        created_at=_TIME,
    )
    assert grade.result is ConceptCheckResult.CORRECT
    assert state.topics["motion"].mastery_score == pytest.approx(0.6)
    assert service.select(prepared, retrieval, validated) is None
    assert resolver.calls == 3
    with pytest.raises(ValueError, match="current corpus"):
        service.submit(
            release,
            attempt_id="attempt-2",
            selected_choice="A",
            event_id="event-2",
            corpus_version="stale",
            corpus_hash="sha256:fixture",
        )


def test_publication_validator_requires_gold_binding_and_rejects_overlap() -> None:
    gold_span = EvidenceSpan(
        span_id="gold:g:1",
        textbook_id="book-1",
        chapter_id="chapter-1",
        chapter_char_start=100,
        chapter_char_end=105,
        verbatim_text="Speed",
        origin_corpus_version="v2-dev",
    )
    gold = GoldQuestion(
        question_id="gold-1",
        question="What is speed?",
        options={
            label: GoldOption(text=text, source_field="fixture")
            for label, text in {"A": "Movement", "B": "Force", "C": "Colour", "D": "Name"}.items()
        },
        gold_answer="A",
        answerable=True,
        gold_core_evidence_sets=(({"span": gold_span, "sufficiency": "core_sufficient"},),),
        question_difficulty="beginner",
        question_type="definition",
        concept_group="motion",
        personalisation_eligibility=PersonalisationEligibility.FULL,
        eligibility_reason="fixture",
        split="dev",
        corpus_version="v2-dev",
        parser_version="fixture-parser",
        gold_annotation_version="fixture-gold",
        annotation_status="reviewed",
        review_record_id="m3-review-gold",
    )
    gold_binding = EvidenceSpanBinding(
        span_id=gold_span.span_id,
        textbook_id="book-1",
        corpus_version="v2-dev",
        corpus_hash="sha256:fixture",
        resolution_status=SpanResolutionStatus.RESOLVED,
        resolution_method=SpanResolutionMethod.VERBATIM_UNIQUE,
        document_id="doc-1",
        char_start=100,
        char_end=105,
        chunk_ids=("gold-chunk",),
    )
    with pytest.raises(ValueError, match="resolved M4 binding"):
        PublicationValidator(
            corpus_version="v2-dev",
            corpus_hash="sha256:fixture",
            gold_questions=(gold,),
            gold_bindings={},
            existing_practice_ids=(),
            checker_version="fixture-checker",
            similarity_threshold=0.9,
            similarity_matches=lambda *_: (),
            cross_book_overlap=lambda *_: False,
        )
    validator = PublicationValidator(
        corpus_version="v2-dev",
        corpus_hash="sha256:fixture",
        gold_questions=(gold,),
        gold_bindings={gold_span.span_id: gold_binding},
        existing_practice_ids=(),
        checker_version="fixture-checker",
        similarity_threshold=0.9,
        similarity_matches=lambda *_: (),
        cross_book_overlap=lambda *_: False,
    )
    assert validator.check(_release("q-1").question, _release("q-1").binding).matched_gold_ids == ()
    overlap_span = EvidenceSpan(
        span_id="gold:overlap:1",
        textbook_id="book-1",
        chapter_id="chapter-1",
        chapter_char_start=0,
        chapter_char_end=5,
        verbatim_text="Force",
        origin_corpus_version="v2-dev",
    )
    overlapping = gold.model_copy(
        update={
            "gold_core_evidence_sets": (
                (gold.gold_core_evidence_sets[0][0].model_copy(update={"span": overlap_span}),),
            )
        }
    )
    overlap_validator = PublicationValidator(
        corpus_version="v2-dev",
        corpus_hash="sha256:fixture",
        gold_questions=(overlapping,),
        gold_bindings={
            overlap_span.span_id: gold_binding.model_copy(
                update={"span_id": overlap_span.span_id, "char_start": 0, "char_end": 5}
            )
        },
        existing_practice_ids=(),
        checker_version="fixture-checker",
        similarity_threshold=0.9,
        similarity_matches=lambda *_: (),
        cross_book_overlap=lambda *_: False,
    )
    with pytest.raises(ValueError, match="overlaps Gold"):
        overlap_validator.check(_release("q-1").question, _release("q-1").binding)


def test_offline_generator_outputs_drafts_and_isolates_provider_failure() -> None:
    class Client:
        model = "fixture-model"
        temperature = 0.0

        def __init__(self):
            self.calls = 0

        def complete(self, prompt, text_format):
            self.calls += 1
            assert text_format["strict"] is True
            if self.calls == 2:
                raise RuntimeError("fixture provider failure")
            return LLMResponse(
                '{"question":"What changes motion?","options":{"A":"Force",'
                '"B":"Colour","C":"Name","D":"Nothing"},'
                '"correct_answer":"A","rationale":"Force changes motion."}',
                self.model,
                TokenUsage(),
                None,
                0.0,
            )

    with pytest.raises(ValueError, match="development-only"):
        OfflineDraftGenerator(
            Client(), config=ConceptCheckConfig(allow_llm_generation=True), environment="production"
        )
    generator = OfflineDraftGenerator(
        Client(), config=ConceptCheckConfig(allow_llm_generation=True)
    )
    anchor = _release("seed").question.evidence_anchors[0]
    results = generator.generate_batch(
        (
            ("draft-1", "motion", "topics-1", StudentLevel.BEGINNER, (anchor,)),
            ("draft-2", "motion", "topics-1", StudentLevel.BEGINNER, (anchor,)),
        )
    )
    assert results[0].question is not None
    assert results[0].question.status is ConceptCheckQuestionStatus.DRAFT
    assert results[0].question.review_record_id is None
    assert results[1].question is None
    assert results[1].error.startswith("provider_failure:")
