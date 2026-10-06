"""M8 fixture composition for the post-answer v2 Concept Check UI.

The existing Streamlit shell still consumes the v1-compatible ``PipelineRun``.
This module is an explicit development adapter: it converts that saved run to
the M1-owned v2 contracts, then delegates selection, grading, event storage and
state replay to M7's ``ConceptCheckService``.  It must never be presented as an
official v2 experiment or used to invent production corpus identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService
from cs30.contracts import PipelineRun
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckGrade,
    ConceptCheckQuestion,
    ConceptCheckQuestionBinding,
    ConceptCheckQuestionRelease,
    ConceptCheckQuestionStatus,
    EvidenceProvenance,
    EvidenceSpan,
    EvidenceSpanBinding,
    GeneratedAnswer,
    LearnerState,
    QuestionSourceType,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
    SpanResolutionMethod,
    SpanResolutionStatus,
    StudentLevel,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    ValidatedAnswer,
)
from cs30.v2.ids import source_locator

FIXTURE_CORPUS_VERSION = "v2-ui-fixture-1"
FIXTURE_CORPUS_HASH = "sha256:v2-ui-fixture-corpus"
FIXTURE_TOPIC_ID = "motion"
FIXTURE_TOPIC_REGISTRY_VERSION = "topics-ui-fixture-1"
FIXTURE_TEXTBOOK_ID = "fixture-physics"
FIXTURE_DOCUMENT_ID = "fixture-physics-document"
FIXTURE_SOURCE_NAME = "fixture-physics-source"


class FixtureTopicResolver:
    """Resolve the single fixture topic without touching production mappings."""

    def resolve_retrieval_topic(self, retrieval: RetrievalResult) -> TopicResolution:
        return self._resolution(bool(retrieval.hits))

    def resolve_cited_topic(
        self,
        retrieval: RetrievalResult,
        validated: ValidatedAnswer,
    ) -> TopicResolution:
        available = {hit.chunk_id for hit in retrieval.hits}
        return self._resolution(bool(set(validated.resolved_citations) & available))

    @staticmethod
    def _resolution(resolved: bool) -> TopicResolution:
        if resolved:
            return TopicResolution(
                status=TopicResolutionStatus.RESOLVED,
                topic_id=FIXTURE_TOPIC_ID,
                topic_registry_version=FIXTURE_TOPIC_REGISTRY_VERSION,
                support=1.0,
                topic_support={FIXTURE_TOPIC_ID: 1.0},
            )
        return TopicResolution(
            status=TopicResolutionStatus.NO_TOPIC_AVAILABLE,
            support=0.0,
            error_code="fixture_topic_unavailable",
        )


@dataclass(frozen=True)
class ConceptCheckFixtureSession:
    """One UI-ready fixture session backed by M7's real service objects."""

    service: ConceptCheckService
    retrieval: RetrievalResult
    validated: ValidatedAnswer
    profile: StudentProfile
    release: ConceptCheckQuestionRelease | None

    def submit(
        self,
        *,
        selected_choice: Literal["A", "B", "C", "D"] | None,
        attempt_id: str,
        event_id: str,
    ) -> tuple[ConceptCheckGrade, LearnerState]:
        if self.release is None:
            raise ValueError("no Concept Check question is available")
        provenance = self.retrieval.provenance
        if provenance is None:
            raise ValueError("fixture retrieval provenance is required")
        return self.service.submit(
            self.release,
            attempt_id=attempt_id,
            selected_choice=selected_choice,
            event_id=event_id,
            corpus_version=provenance.corpus_version,
            corpus_hash=provenance.corpus_hash,
        )


def build_fixture_session(
    run: PipelineRun,
    *,
    event_directory: Path,
) -> ConceptCheckFixtureSession:
    """Adapt one fixture ``PipelineRun`` and select an eligible micro-check."""

    if run.mode != "fixture":
        raise ValueError("the temporary Concept Check adapter accepts fixture runs only")
    if run.validated_answer is None:
        raise ValueError("PipelineRun must include a validated answer")

    retrieval = _adapt_retrieval(run)
    validated = _adapt_validated_answer(run)
    profile = StudentProfile(
        profile_id=run.profile.profile_id,
        level=StudentLevel(run.profile.level.value),
        topic_levels={
            topic_id: StudentLevel(level.value)
            for topic_id, level in run.profile.topic_levels.items()
        },
        confidence=run.profile.confidence,
    )
    config = ConceptCheckConfig(enabled=True)
    replayer = EventReplayer(profile, FIXTURE_TOPIC_REGISTRY_VERSION, config)
    store = JsonlEventStore(event_directory, replayer)
    release = _fixture_release(retrieval, profile.level)
    provider = (
        FixtureQuestionProvider((release,))
        if release is not None
        else FixtureQuestionProvider(())
    )
    service = ConceptCheckService(
        config=config,
        resolver=FixtureTopicResolver(),
        provider=provider,
        event_store=store,
        replayer=replayer,
    )
    prepared = service.prepare(retrieval, profile)
    selected = service.select(prepared, retrieval, validated)
    return ConceptCheckFixtureSession(
        service=service,
        retrieval=retrieval,
        validated=validated,
        profile=profile,
        release=selected,
    )


def _adapt_retrieval(run: PipelineRun) -> RetrievalResult:
    hits: list[RetrievedEvidence] = []
    offset = 0
    for hit in run.retrieval.hits:
        location = f"chapter-{hit.chapter_id}"
        locator = source_locator(
            source_name=FIXTURE_SOURCE_NAME,
            textbook_id=FIXTURE_TEXTBOOK_ID,
            chapter_id=hit.chapter_id,
            page_or_location=location,
            char_start=offset,
            char_end=offset + len(hit.text),
        )
        hits.append(
            RetrievedEvidence(
                provider="fixture",
                textbook_id=FIXTURE_TEXTBOOK_ID,
                document_id=FIXTURE_DOCUMENT_ID,
                chunk_id=hit.chunk_id,
                chapter_id=hit.chapter_id,
                source_name=FIXTURE_SOURCE_NAME,
                page_or_location=location,
                source_locator=locator,
                text=hit.text,
                score=hit.score,
                rank=hit.rank,
                retriever_type=RetrievalMode(hit.retriever_type.value),
            )
        )
        offset += len(hit.text) + 1
    mode = RetrievalMode(run.retrieval.mode.value)
    return RetrievalResult(
        query=run.retrieval.query,
        mode=mode,
        hits=tuple(hits),
        provenance=EvidenceProvenance(
            corpus_version=FIXTURE_CORPUS_VERSION,
            corpus_hash=FIXTURE_CORPUS_HASH,
            manifest_hash="sha256:v2-ui-fixture-manifest",
            chunk_config_hash="sha256:v2-ui-fixture-chunks",
            index_version="v2-ui-fixture-index-1",
            retrieval_mode=mode,
            retrieval_config_hash="sha256:v2-ui-fixture-retrieval",
        ),
    )


def _adapt_validated_answer(run: PipelineRun) -> ValidatedAnswer:
    source = run.validated_answer
    assert source is not None
    answer = GeneratedAnswer(
        final_choice=run.answer.final_choice,
        explanation=run.answer.explanation,
        citations=tuple(run.answer.citations),
        abstained=run.answer.abstained,
    )
    return ValidatedAnswer(
        answer=answer,
        resolved_citations=tuple(source.resolved_citations),
        citation_status=source.citation_status,
        run_provenance={
            **source.run_provenance,
            "ui_adapter": "v1-pipeline-run-to-v2-concept-check-fixture",
            "source_run_id": run.run_id,
        },
    )


def _fixture_release(
    retrieval: RetrievalResult,
    difficulty: StudentLevel,
) -> ConceptCheckQuestionRelease | None:
    if not retrieval.hits:
        return None
    hit = retrieval.hits[0]
    anchor = EvidenceSpan(
        span_id="cc:ui-fixture-motion:1",
        textbook_id=hit.textbook_id,
        chapter_id=hit.chapter_id,
        chapter_char_start=0,
        chapter_char_end=5,
        verbatim_text="Force",
        origin_corpus_version=FIXTURE_CORPUS_VERSION,
    )
    question = ConceptCheckQuestion(
        question_id=f"ui-fixture-motion-{difficulty.value}",
        question="Which statement best describes how a net force affects an object?",
        options={
            "A": "A net force can change the object's motion.",
            "B": "A net force can only change the object's colour.",
            "C": "A net force always keeps velocity unchanged.",
            "D": "A net force has no relationship to acceleration.",
        },
        correct_answer="A",
        topic_id=FIXTURE_TOPIC_ID,
        topic_registry_version=FIXTURE_TOPIC_REGISTRY_VERSION,
        difficulty=difficulty,
        evidence_anchors=(anchor,),
        source_type=QuestionSourceType.HUMAN_AUTHORED,
        rationale="A non-zero net force produces acceleration and can change motion.",
        review_record_id="ui-fixture-review",
        status=ConceptCheckQuestionStatus.PUBLISHED,
    )
    binding = ConceptCheckQuestionBinding(
        question_id=question.question_id,
        corpus_version=FIXTURE_CORPUS_VERSION,
        corpus_hash=FIXTURE_CORPUS_HASH,
        bindings=(
            EvidenceSpanBinding(
                span_id=anchor.span_id,
                textbook_id=anchor.textbook_id,
                corpus_version=FIXTURE_CORPUS_VERSION,
                corpus_hash=FIXTURE_CORPUS_HASH,
                resolution_status=SpanResolutionStatus.RESOLVED,
                resolution_method=SpanResolutionMethod.VERBATIM_UNIQUE,
                document_id=hit.document_id,
                char_start=0,
                char_end=5,
                chunk_ids=(hit.chunk_id,),
            ),
        ),
    )
    return ConceptCheckQuestionRelease(question=question, binding=binding)


__all__ = [
    "ConceptCheckFixtureSession",
    "FIXTURE_CORPUS_HASH",
    "FIXTURE_CORPUS_VERSION",
    "build_fixture_session",
]
