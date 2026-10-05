"""Published practice-question fixture selection with deterministic ordering."""

from __future__ import annotations

from collections.abc import Sequence

from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckQuestionRelease,
    StudentLevel,
    TopicState,
)

_LEVELS = (StudentLevel.BEGINNER, StudentLevel.INTERMEDIATE, StudentLevel.ADVANCED)


def target_levels(topic_state: TopicState, config: ConceptCheckConfig) -> tuple[StudentLevel, ...]:
    """Prefer an upward probe only when the latest state has earned one."""

    current = _LEVELS.index(topic_state.level)
    ordinary = tuple(
        sorted(
            _LEVELS, key=lambda level: (abs(_LEVELS.index(level) - current), _LEVELS.index(level))
        )
    )
    if topic_state.mastery_score >= config.promotion_threshold and current < 2:
        return (
            _LEVELS[current + 1],
            *[level for level in ordinary if level != _LEVELS[current + 1]],
        )
    return ordinary


class FixtureQuestionProvider:
    def __init__(self, releases: Sequence[ConceptCheckQuestionRelease]) -> None:
        self.releases = tuple(releases)
        ids = [release.question.question_id for release in self.releases]
        if len(ids) != len(set(ids)):
            raise ValueError("fixture question IDs must be unique")

    def select(
        self,
        *,
        topic_id: str,
        target_levels: Sequence[StudentLevel],
        corpus_version: str,
        corpus_hash: str,
        cited_chunk_ids: Sequence[str],
        excluded_question_ids: Sequence[str] = (),
    ) -> ConceptCheckQuestionRelease | None:
        priority = {level: index for index, level in enumerate(target_levels)}
        cited = set(cited_chunk_ids)
        excluded = set(excluded_question_ids)
        candidates = [
            release
            for release in self.releases
            if release.question.topic_id == topic_id
            and release.question.difficulty in priority
            and release.question.question_id not in excluded
            and release.binding.corpus_version == corpus_version
            and release.binding.corpus_hash == corpus_hash
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda release: (
                priority[release.question.difficulty],
                -int(
                    any(
                        cited.intersection(binding.chunk_ids)
                        for binding in release.binding.bindings
                    )
                ),
                release.question.question_id,
            ),
        )
