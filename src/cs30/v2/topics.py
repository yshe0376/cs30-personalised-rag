"""Versioned chunk-to-topic assignments kept outside the retrieval corpus."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from cs30.v2.contracts.models import Identifier, V2Model
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


__all__ = [
    "ChunkTopicAssignment",
    "ChunkTopicMap",
    "canonical_chunk_topic_map",
    "load_chunk_topic_map",
    "validate_chunk_topic_map",
    "write_chunk_topic_map",
]
