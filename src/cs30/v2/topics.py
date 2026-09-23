"""Versioned chunk-to-topic assignments kept outside the retrieval corpus."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from cs30.v2.contracts.models import (
    Identifier,
    RetrievalResult,
    TopicRegistry,
    TopicResolution,
    TopicResolutionStatus,
    V2Model,
)
from cs30.v2.ids import canonical_json_bytes

if TYPE_CHECKING:
    from cs30.v2.corpus.manifest import CorpusManifest


class ChunkTopicAssignment(V2Model):
    """The topics assigned to one chunk in a specific topic registry."""

    chunk_id: Identifier
    topic_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_topic_ids(self) -> ChunkTopicAssignment:
        if len(set(self.topic_ids)) != len(self.topic_ids):
            raise ValueError("topic_ids must be unique per chunk")
        return self


class ChunkTopicMap(V2Model):
    """Sidecar mapping that does not change corpus or index identity."""

    schema_version: Literal["2.0"] = "2.0"
    corpus_version: Identifier
    corpus_hash: Identifier
    topic_registry_version: Identifier
    assignments: tuple[ChunkTopicAssignment, ...] = ()

    @model_validator(mode="after")
    def validate_chunk_ids(self) -> ChunkTopicMap:
        chunk_ids = [assignment.chunk_id for assignment in self.assignments]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("each chunk may occur only once in chunk_topic_map")
        return self


def canonical_chunk_topic_map(topic_map: ChunkTopicMap) -> ChunkTopicMap:
    """Return deterministic assignment and topic ordering for persistence."""

    assignments = tuple(
        assignment.model_copy(update={"topic_ids": tuple(sorted(assignment.topic_ids))})
        for assignment in sorted(topic_map.assignments, key=lambda item: item.chunk_id)
    )
    return topic_map.model_copy(update={"assignments": assignments})


def validate_chunk_topic_map(
    topic_map: ChunkTopicMap,
    manifest: CorpusManifest,
    chunk_ids: Sequence[str],
) -> None:
    """Verify that a topic sidecar belongs to the supplied corpus."""

    if topic_map.corpus_version != manifest.corpus_version:
        raise ValueError("topic map corpus_version does not match the manifest")
    if topic_map.corpus_hash != manifest.corpus_hash:
        raise ValueError("topic map corpus_hash does not match the manifest")

    corpus_chunk_ids = tuple(chunk_ids)
    if len(corpus_chunk_ids) != len(set(corpus_chunk_ids)):
        raise ValueError("the supplied corpus chunk_ids must be unique")
    unknown_chunk_ids = sorted(
        {assignment.chunk_id for assignment in topic_map.assignments}
        - set(corpus_chunk_ids)
    )
    if unknown_chunk_ids:
        raise ValueError(
            "topic map references chunk_ids absent from the corpus: "
            f"{unknown_chunk_ids}"
        )


def write_chunk_topic_map(topic_map: ChunkTopicMap, path: Path) -> None:
    """Write a stable sidecar tied to one corpus hash and topic registry."""

    canonical = canonical_chunk_topic_map(topic_map)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(canonical.model_dump(mode="json")))


def load_chunk_topic_map(path: Path) -> ChunkTopicMap:
    """Load and validate a chunk-topic sidecar."""

    return ChunkTopicMap.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_topic_from_retrieval(
    retrieval: RetrievalResult,
    topic_map: ChunkTopicMap | None,
    registry: TopicRegistry | None,
    *,
    min_topic_support: float = 0.5,
) -> TopicResolution:
    """Resolve one unique Topic using rank-weighted chunk assignments.

    Each hit contributes ``1 / rank``. If a chunk maps to multiple Topics its
    contribution is split evenly, then normalized across all supported Topics.
    Missing assignments are not errors; a missing sidecar or a sidecar bound to
    another corpus is an explicit configuration failure.
    """

    if not 0.0 <= min_topic_support <= 1.0:
        raise ValueError("min_topic_support must be between 0 and 1")
    if topic_map is None:
        return TopicResolution(
            status=TopicResolutionStatus.TOPIC_MAP_UNAVAILABLE,
            error_code="TOPIC_MAP_UNAVAILABLE",
        )
    if registry is None:
        return TopicResolution(
            status=TopicResolutionStatus.TOPIC_MAP_UNAVAILABLE,
            error_code="TOPIC_REGISTRY_UNAVAILABLE",
        )
    if retrieval.provenance is not None and (
        topic_map.corpus_version != retrieval.provenance.corpus_version
        or topic_map.corpus_hash != retrieval.provenance.corpus_hash
    ):
        return TopicResolution(
            status=TopicResolutionStatus.TOPIC_MAP_MISMATCH,
            error_code="TOPIC_MAP_MISMATCH",
        )
    if topic_map.topic_registry_version != registry.topic_registry_version:
        return TopicResolution(
            status=TopicResolutionStatus.TOPIC_MAP_MISMATCH,
            error_code="TOPIC_REGISTRY_MISMATCH",
        )
    if not retrieval.hits:
        return TopicResolution(
            status=TopicResolutionStatus.NO_TOPIC_AVAILABLE,
            error_code="NO_RETRIEVAL_HITS",
        )

    known_topics = {topic.topic_id for topic in registry.topics}
    if any(
        topic_id not in known_topics
        for assignment in topic_map.assignments
        for topic_id in assignment.topic_ids
    ):
        return TopicResolution(
            status=TopicResolutionStatus.TOPIC_MAP_MISMATCH,
            topic_registry_version=registry.topic_registry_version,
            error_code="TOPIC_REGISTRY_MISMATCH",
        )
    assignments = {
        assignment.chunk_id: assignment.topic_ids for assignment in topic_map.assignments
    }
    weights: dict[str, float] = {}
    for hit in retrieval.hits:
        topic_ids = tuple(
            topic_id
            for topic_id in assignments.get(hit.chunk_id, ())
            if topic_id in known_topics
        )
        if not topic_ids:
            continue
        contribution = 1.0 / (hit.rank * len(topic_ids))
        for topic_id in topic_ids:
            weights[topic_id] = weights.get(topic_id, 0.0) + contribution

    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        return TopicResolution(
            status=TopicResolutionStatus.NO_TOPIC_AVAILABLE,
            topic_registry_version=registry.topic_registry_version,
            error_code="NO_TOPIC_AVAILABLE",
        )
    support = {topic_id: weight / total_weight for topic_id, weight in weights.items()}
    top_support = max(support.values())
    winners = [
        topic_id
        for topic_id, value in support.items()
        if math.isclose(value, top_support, rel_tol=1e-12, abs_tol=1e-12)
    ]
    if len(winners) != 1:
        return TopicResolution(
            status=TopicResolutionStatus.NO_TOPIC_AVAILABLE,
            topic_registry_version=registry.topic_registry_version,
            support=top_support,
            topic_support=support,
            error_code="TOPIC_TIE",
        )
    if top_support < min_topic_support:
        return TopicResolution(
            status=TopicResolutionStatus.NO_TOPIC_AVAILABLE,
            topic_registry_version=registry.topic_registry_version,
            support=top_support,
            topic_support=support,
            error_code="TOPIC_SUPPORT_BELOW_THRESHOLD",
        )
    return TopicResolution(
        status=TopicResolutionStatus.RESOLVED,
        topic_id=winners[0],
        topic_registry_version=registry.topic_registry_version,
        support=top_support,
        topic_support=support,
    )


__all__ = [
    "ChunkTopicAssignment",
    "ChunkTopicMap",
    "canonical_chunk_topic_map",
    "load_chunk_topic_map",
    "validate_chunk_topic_map",
    "write_chunk_topic_map",
    "resolve_topic_from_retrieval",
]
