"""Standalone post-answer Concept Check flow; no corpus-build pipeline wiring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from cs30.concept_check.grader import DeterministicGrader
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import target_levels
from cs30.concept_check.snapshot import build_learner_context_snapshot
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckEventType,
    ConceptCheckGrade,
    ConceptCheckQuestionRelease,
    ConceptCheckResult,
    LearnerContextSnapshot,
    LearnerState,
    RetrievalResult,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    ValidatedAnswer,
)
from cs30.v2.ports import ConceptCheckEventStore, ConceptCheckQuestionProvider, TopicResolver


@dataclass(frozen=True)
class PreparedRound:
    snapshot: LearnerContextSnapshot
    retrieval_topic: TopicResolution | None


class ConceptCheckService:
    def __init__(
        self,
        *,
        config: ConceptCheckConfig,
        resolver: TopicResolver,
        provider: ConceptCheckQuestionProvider,
        event_store: ConceptCheckEventStore,
        replayer: EventReplayer,
    ) -> None:
        self.config = config
        self.resolver = resolver
        self.provider = provider
        self.event_store = event_store
        self.replayer = replayer
        self.grader = DeterministicGrader()

    def prepare(self, retrieval: RetrievalResult, static_profile: StudentProfile) -> PreparedRound:
        """Call after retrieval; pass this exact snapshot to reranking and generation."""

        if not self.config.enabled:
            return PreparedRound(
                snapshot=build_learner_context_snapshot(static_profile, enabled=False),
                retrieval_topic=None,
            )
        state = self.replayer.replay(self.event_store.events(static_profile.profile_id))
        resolution = self.resolver.resolve_retrieval_topic(retrieval)
        if (
            resolution.status is TopicResolutionStatus.RESOLVED
            and resolution.topic_registry_version != self.replayer.topic_registry_version
        ):
            raise ValueError("retrieval Topic registry version mismatch")
        snapshot = build_learner_context_snapshot(
            static_profile,
            enabled=True,
            learner_state=state,
            topic_resolution=resolution,
        )
        return PreparedRound(snapshot=snapshot, retrieval_topic=resolution)

    def select(
        self,
        prepared: PreparedRound,
        retrieval: RetrievalResult,
        validated: ValidatedAnswer,
    ) -> ConceptCheckQuestionRelease | None:
        """Offer a bound, reviewed question only after a cited valid answer."""

        if not self.config.enabled or prepared.retrieval_topic is None:
            return None
        if prepared.retrieval_topic.status is not TopicResolutionStatus.RESOLVED:
            return None
        if validated.abstained or validated.citation_status != "passed":
            return None
        if not validated.resolved_citations or retrieval.provenance is None:
            return None
        cited_topic = self.resolver.resolve_cited_topic(retrieval, validated)
        if cited_topic.status is not TopicResolutionStatus.RESOLVED:
            return None
        if cited_topic.topic_registry_version != self.replayer.topic_registry_version:
            raise ValueError("cited Topic registry version mismatch")
        if cited_topic.topic_id != prepared.retrieval_topic.topic_id:
            return None
        topic_id = cited_topic.topic_id
        if topic_id is None:
            return None
        state = self.replayer.replay(self.event_store.events(prepared.snapshot.profile.profile_id))
        topic_state = state.topics.get(topic_id) or prepared.snapshot.topic_state
        if topic_state is None:
            return None
        used_ids = tuple(
            event.question_id
            for event in self.event_store.events(state.profile_id)
            if event.event_type
            in {
                ConceptCheckEventType.ATTEMPT_SUBMITTED,
                ConceptCheckEventType.ATTEMPT_SKIPPED,
            }
            and event.question_id is not None
        )
        provenance = retrieval.provenance
        return self.provider.select(
            topic_id=topic_id,
            target_levels=target_levels(topic_state, self.config),
            corpus_version=provenance.corpus_version,
            corpus_hash=provenance.corpus_hash,
            cited_chunk_ids=validated.resolved_citations,
            excluded_question_ids=used_ids,
        )

    def submit(
        self,
        release: ConceptCheckQuestionRelease,
        *,
        attempt_id: str,
        selected_choice: Literal["A", "B", "C", "D"] | None,
        event_id: str,
        corpus_version: str,
        corpus_hash: str,
        created_at: datetime | None = None,
    ) -> tuple[ConceptCheckGrade, LearnerState]:
        if not self.config.enabled:
            raise ValueError("Concept Check is disabled")
        question = release.question
        if (release.binding.corpus_version, release.binding.corpus_hash) != (
            corpus_version,
            corpus_hash,
        ):
            raise ValueError("question binding does not match the current corpus")
        if question.topic_registry_version != self.replayer.topic_registry_version:
            raise ValueError("question topic registry version mismatch")
        grade = self.grader.grade(
            question,
            attempt_id=attempt_id,
            selected_choice=selected_choice,
        )
        before = self.replayer.replay(
            self.event_store.events(self.replayer.static_profile.profile_id)
        )
        event = ConceptCheckEvent(
            event_id=event_id,
            profile_id=before.profile_id,
            attempt_id=attempt_id,
            question_id=question.question_id,
            topic_id=question.topic_id,
            topic_registry_version=question.topic_registry_version,
            question_difficulty=question.difficulty,
            selected_choice=grade.selected_choice,
            performance=grade.performance,
            event_type=(
                ConceptCheckEventType.ATTEMPT_SKIPPED
                if grade.result is ConceptCheckResult.SKIPPED
                else ConceptCheckEventType.ATTEMPT_SUBMITTED
            ),
            state_version_before=before.state_version,
            stream_version=before.state_version + 1,
            created_at=created_at or datetime.now(UTC),
        )
        self.event_store.append(event)
        return grade, self.replayer.replay(self.event_store.events(before.profile_id))
