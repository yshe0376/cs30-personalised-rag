"""Pure replay of a single student's append-only Concept Check event stream."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckEventType,
    LearnerState,
    StudentLevel,
    StudentProfile,
    TopicState,
)

_LEVELS = (StudentLevel.BEGINNER, StudentLevel.INTERMEDIATE, StudentLevel.ADVANCED)


def _topic_state(
    topic_id: str,
    initial_level: StudentLevel,
    history: Sequence[ConceptCheckEvent],
    config: ConceptCheckConfig,
) -> TopicState:
    level = initial_level
    score = 0.5
    total = 0
    epoch_count = 0
    correct_count = 0
    window: list[ConceptCheckEvent] = []
    for event in history:
        if event.event_type is ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN:
            assert event.new_level is not None
            level, score, epoch_count = event.new_level, 0.5, 0
            window.clear()
            continue
        if event.event_type is not ConceptCheckEventType.ATTEMPT_SUBMITTED:
            continue
        assert event.question_difficulty is not None and event.performance is not None
        current_index = _LEVELS.index(level)
        question_index = _LEVELS.index(event.question_difficulty)
        relation = (
            0 if question_index < current_index else 2 if question_index > current_index else 1
        )
        correct = event.performance == 1.0
        weights = config.correct_difficulty_weights if correct else config.wrong_difficulty_weights
        score += 0.2 * weights[relation] * (event.performance - score)
        total += 1
        correct_count += int(correct)
        epoch_count += 1
        window.append(event)
        window = window[-config.level_change_window :]
        if len(window) < config.level_change_window:
            continue
        if current_index < 2 and score >= config.promotion_threshold:
            target = _LEVELS[current_index + 1]
            qualifying = sum(
                item.performance == 1.0
                and _LEVELS.index(item.question_difficulty) >= _LEVELS.index(target)
                for item in window
            )
            if qualifying >= 2:
                level, score, epoch_count = target, 0.5, 0
                window.clear()
        elif current_index > 0 and score <= config.demotion_threshold:
            qualifying = sum(
                item.performance == 0.0 and _LEVELS.index(item.question_difficulty) <= current_index
                for item in window
            )
            if qualifying >= 2:
                level, score, epoch_count = _LEVELS[current_index - 1], 0.5, 0
                window.clear()
    return TopicState(
        topic_id=topic_id,
        mastery_score=score,
        level=level,
        attempt_coverage=min(1.0, epoch_count / config.attempt_coverage_window),
        total_attempts=total,
        attempts_since_level_change=epoch_count,
        correct_attempts=correct_count,
    )


class EventReplayer:
    """Validate stream order and derive state; revocation replays surviving history."""

    def __init__(
        self,
        static_profile: StudentProfile,
        topic_registry_version: str,
        config: ConceptCheckConfig | None = None,
    ) -> None:
        self.static_profile = static_profile
        self.topic_registry_version = topic_registry_version
        self.config = config or ConceptCheckConfig()

    def replay(self, events: Sequence[ConceptCheckEvent]) -> LearnerState:
        ordered = sorted(events, key=lambda item: item.stream_version)
        seen_events: dict[str, ConceptCheckEvent] = {}
        seen_attempts: dict[str, ConceptCheckEvent] = {}
        revoked: set[str] = set()
        histories: dict[str, list[ConceptCheckEvent]] = defaultdict(list)
        for expected_version, event in enumerate(ordered, start=1):
            if event.stream_version != expected_version:
                raise ValueError("Concept Check stream versions must be consecutive")
            if event.state_version_before != expected_version - 1:
                raise ValueError("Concept Check state_version_before mismatch")
            if event.profile_id != self.static_profile.profile_id:
                raise ValueError("Concept Check event profile_id mismatch")
            if event.topic_registry_version != self.topic_registry_version:
                raise ValueError("Concept Check topic registry version mismatch")
            if event.event_id in seen_events:
                raise ValueError("duplicate Concept Check event_id")
            seen_events[event.event_id] = event
            if event.event_type in {
                ConceptCheckEventType.ATTEMPT_SUBMITTED,
                ConceptCheckEventType.ATTEMPT_SKIPPED,
            }:
                assert event.attempt_id is not None
                if event.attempt_id in seen_attempts:
                    raise ValueError("duplicate Concept Check attempt_id")
                seen_attempts[event.attempt_id] = event
                if event.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED:
                    if event.performance not in (0.0, 1.0):
                        raise ValueError("first-version grading requires performance 0 or 1")
                    histories[event.topic_id].append(event)
            elif event.event_type is ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN:
                histories[event.topic_id].append(event)
            elif event.event_type is ConceptCheckEventType.ATTEMPT_REVOKED:
                target_id = event.revoked_attempt_id
                target = seen_attempts.get(target_id or "")
                if (
                    target is None
                    or target.event_type is not ConceptCheckEventType.ATTEMPT_SUBMITTED
                ):
                    raise ValueError("revocation requires an existing submitted attempt")
                if target.topic_id != event.topic_id or target_id in revoked:
                    raise ValueError("revocation topic mismatch or already revoked")
                latest = next(
                    (
                        item
                        for item in reversed(histories[event.topic_id])
                        if item.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED
                        and item.attempt_id not in revoked
                    ),
                    None,
                )
                if latest is None or latest.attempt_id != target_id:
                    raise ValueError("only the most recent valid submission may be revoked")
                revoked.add(target_id)
        topics = {
            topic_id: _topic_state(
                topic_id,
                self.static_profile.topic_levels.get(topic_id, self.static_profile.level),
                [item for item in history if item.attempt_id not in revoked],
                self.config,
            )
            for topic_id, history in histories.items()
        }
        version = len(ordered)
        return LearnerState(
            state_id=f"state:{self.static_profile.profile_id}",
            profile_id=self.static_profile.profile_id,
            topic_registry_version=self.topic_registry_version,
            state_version=version,
            derived_from_event_version=version,
            topics=topics,
        )
