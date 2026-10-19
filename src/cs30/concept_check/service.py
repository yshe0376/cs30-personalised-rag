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
    ConceptCheckSelection,
    LearnerContextSnapshot,
    LearnerState,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    TopicState,
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
        if config.allow_unreviewed_questions:
            raise ValueError("allow_unreviewed_questions is not supported by this runtime")
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
        if static_profile != self.replayer.static_profile:
            raise ValueError("prepare static_profile must match the replayer's static profile")
        state = self.replayer.replay(self.event_store.events(static_profile.profile_id))
        resolution = self.resolver.resolve_retrieval_topic(retrieval)
        if (
            resolution.status is TopicResolutionStatus.RESOLVED
            and resolution.topic_registry_version != self.replayer.topic_registry_version
        ):
            resolution = TopicResolution(
                status=TopicResolutionStatus.TOPIC_MAP_MISMATCH,
                topic_registry_version=resolution.topic_registry_version,
                error_code="TOPIC_REGISTRY_MISMATCH",
            )
        if (
            resolution.status is TopicResolutionStatus.RESOLVED
            and resolution.topic_id not in self.replayer.topic_ids
        ):
            resolution = TopicResolution(
                status=TopicResolutionStatus.NO_TOPIC_AVAILABLE,
                topic_registry_version=resolution.topic_registry_version,
                error_code="UNKNOWN_TOPIC",
            )
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
    ) -> ConceptCheckSelection:
        """Offer a current question or explain refusal according to spec §5.1/§5.3."""

        if not self.config.enabled:
            return ConceptCheckSelection(status="disabled")
        if prepared.retrieval_topic is None:
            return ConceptCheckSelection(
                status="no_topic_available", error_code="NO_RETRIEVAL_TOPIC"
            )
        if prepared.retrieval_topic.status is not TopicResolutionStatus.RESOLVED:
            return ConceptCheckSelection(
                status="no_topic_available",
                error_code=prepared.retrieval_topic.error_code or "NO_TOPIC_AVAILABLE",
            )
        if validated.abstained:
            return ConceptCheckSelection(
                status="no_question_available", error_code="ANSWER_ABSTAINED"
            )
        if validated.citation_status != "passed":
            return ConceptCheckSelection(
                status="no_question_available", error_code="CITATION_VALIDATION_FAILED"
            )
        if not validated.resolved_citations:
            return ConceptCheckSelection(status="no_question_available", error_code="NO_CITATIONS")
        if retrieval.provenance is None:
            return ConceptCheckSelection(
                status="no_topic_available", error_code="TOPIC_MAP_UNAVAILABLE"
            )
        cited_topic = self.resolver.resolve_cited_topic(retrieval, validated)
        if cited_topic.status is not TopicResolutionStatus.RESOLVED:
            return ConceptCheckSelection(
                status="no_topic_available",
                error_code=cited_topic.error_code or "NO_TOPIC_AVAILABLE",
            )
        if cited_topic.topic_registry_version != self.replayer.topic_registry_version:
            return ConceptCheckSelection(
                status="no_topic_available", error_code="TOPIC_REGISTRY_MISMATCH"
            )
        if cited_topic.topic_id not in self.replayer.topic_ids:
            return ConceptCheckSelection(status="no_topic_available", error_code="UNKNOWN_TOPIC")
        topic_id = cited_topic.topic_id
        assert topic_id is not None  # Enforced by the TopicResolution contract.
        events = self.event_store.events(prepared.snapshot.profile.profile_id)
        state = self.replayer.replay(events)
        topic_state = state.topics.get(topic_id) or TopicState(
            topic_id=topic_id,
            level=self.replayer.static_profile.topic_levels.get(
                topic_id, self.replayer.static_profile.level
            ),
        )
        used_ids = list(
            event.question_id
            for event in events
            if event.event_type
            in {
                ConceptCheckEventType.ATTEMPT_SUBMITTED,
                ConceptCheckEventType.ATTEMPT_SKIPPED,
            }
            and event.question_id is not None
        )
        provenance = retrieval.provenance
        while True:
            release = self.provider.select(
                topic_id=topic_id,
                target_levels=target_levels(topic_state, self.config),
                corpus_version=provenance.corpus_version,
                corpus_hash=provenance.corpus_hash,
                cited_chunk_ids=validated.resolved_citations,
                excluded_question_ids=tuple(used_ids),
            )
            if release is None:
                return ConceptCheckSelection(
                    status="no_question_available", error_code="NO_USABLE_QUESTION"
                )
            question = release.question
            if question.question_id in used_ids:
                raise ValueError("question provider returned an excluded question")
            if question.topic_registry_version != self.replayer.topic_registry_version:
                # Exclude stale candidates before accepting the provider's next ranked choice.
                used_ids.append(question.question_id)
                continue
            return ConceptCheckSelection(status="offered", question=release)

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
        self.replayer.validate_topic(question.topic_id)
        grade = self.grader.grade(
            question,
            attempt_id=attempt_id,
            selected_choice=selected_choice,
        )
        event = ConceptCheckEvent(
            event_id=event_id,
            profile_id=self.replayer.static_profile.profile_id,
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
            # The event store assigns authoritative stream versions under its writer lock.
            state_version_before=0,
            stream_version=1,
            created_at=created_at or datetime.now(UTC),
        )
        stored = self.event_store.append(event)
        return grade, self.replayer.replay(self.event_store.events(stored.profile_id))

    def revoke(
        self,
        attempt_id: str,
        *,
        event_id: str,
        created_at: datetime | None = None,
    ) -> LearnerState:
        """Revoke the latest valid submission for its Topic; retries reuse event_id."""

        if not self.config.enabled:
            raise ValueError("Concept Check is disabled")
        profile_id = self.replayer.static_profile.profile_id
        target = next(
            (
                event
                for event in self.event_store.events(profile_id)
                if event.attempt_id == attempt_id
                and event.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED
            ),
            None,
        )
        if target is None:
            raise ValueError("revocation requires an existing submitted attempt")
        event = ConceptCheckEvent(
            event_id=event_id,
            profile_id=profile_id,
            topic_id=target.topic_id,
            topic_registry_version=target.topic_registry_version,
            revoked_attempt_id=attempt_id,
            event_type=ConceptCheckEventType.ATTEMPT_REVOKED,
            actor="student",
            state_version_before=0,
            stream_version=1,
            created_at=created_at or datetime.now(UTC),
        )
        stored = self.event_store.append(event)
        return self.replayer.replay(self.event_store.events(stored.profile_id))

    def override_level(
        self,
        topic_id: str,
        new_level: StudentLevel,
        *,
        reason: str,
        event_id: str,
        created_at: datetime | None = None,
    ) -> LearnerState:
        """Record a student's correction and replay the reset Topic epoch."""

        if not self.config.enabled:
            raise ValueError("Concept Check is disabled")
        self.replayer.validate_topic(topic_id)
        event = ConceptCheckEvent(
            event_id=event_id,
            profile_id=self.replayer.static_profile.profile_id,
            topic_id=topic_id,
            topic_registry_version=self.replayer.topic_registry_version,
            new_level=new_level,
            reason=reason,
            actor="student",
            event_type=ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN,
            state_version_before=0,
            stream_version=1,
            created_at=created_at or datetime.now(UTC),
        )
        stored = self.event_store.append(event)
        return self.replayer.replay(self.event_store.events(stored.profile_id))
