"""Pure construction of the profile snapshot shared by reranking and generation."""

from __future__ import annotations

from cs30.v2.contracts import (
    LearnerContextSnapshot,
    LearnerState,
    ProfileSource,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    TopicState,
)


def build_learner_context_snapshot(
    static_profile: StudentProfile,
    *,
    enabled: bool,
    learner_state: LearnerState | None = None,
    topic_resolution: TopicResolution | None = None,
) -> LearnerContextSnapshot:
    """Build one deterministic snapshot without reading or mutating external state.

    With Concept Check disabled the function deliberately ignores the state and
    resolution inputs.  This is the static-profile path used by the formal
    retrieval/generation experiments.  When enabled, a resolved Topic selects
    the TopicState level; a missing or non-unique Topic safely falls back to the
    global static level while keeping the replayed state version auditable.
    """

    if not enabled:
        return LearnerContextSnapshot(
            profile=static_profile,
            profile_source=ProfileSource.STATIC_PROFILE,
            attempt_coverage=0.0,
            state_version=0,
            topic_resolution=None,
            resolver_called=False,
        )

    if learner_state is None:
        raise ValueError("enabled Concept Check snapshots require replayed learner_state")
    if learner_state.profile_id != static_profile.profile_id:
        raise ValueError("learner_state profile_id must match static_profile profile_id")

    topic_state: TopicState | None = None
    profile = static_profile
    topic_id = None
    attempt_coverage = 0.0

    if (
        topic_resolution is not None
        and topic_resolution.status is TopicResolutionStatus.RESOLVED
        and topic_resolution.topic_id is not None
    ):
        topic_id = topic_resolution.topic_id
        topic_state = learner_state.topics.get(topic_id)
        if topic_state is None:
            topic_state = TopicState(
                topic_id=topic_id,
                level=static_profile.topic_levels.get(topic_id, static_profile.level),
            )
        topic_levels = dict(static_profile.topic_levels)
        topic_levels[topic_id] = topic_state.level
        profile = static_profile.model_copy(
            update={"level": topic_state.level, "topic_levels": topic_levels}
        )
        attempt_coverage = topic_state.attempt_coverage

    return LearnerContextSnapshot(
        profile=profile,
        profile_source=ProfileSource.LEARNER_STATE_REPLAY,
        topic_id=topic_id,
        topic_state=topic_state,
        attempt_coverage=attempt_coverage,
        state_version=learner_state.state_version,
        topic_resolution=topic_resolution,
        resolver_called=(
            topic_resolution is not None and topic_resolution.resolver_called
        ),
    )
