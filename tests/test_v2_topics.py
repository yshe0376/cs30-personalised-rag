"""Tests for the v2 topic sidecar boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.v2.contracts import Chunk
from cs30.v2.topics import (
    ChunkTopicAssignment,
    ChunkTopicMap,
    canonical_chunk_topic_map,
    load_chunk_topic_map,
    validate_chunk_topic_map,
    write_chunk_topic_map,
)


def test_topic_assignments_are_a_sidecar_not_chunk_fields(tmp_path: Path) -> None:
    topic_map = ChunkTopicMap(
        corpus_version="2.0.0-dev.1",
        corpus_hash="sha256:corpus",
        topic_registry_version="topics-v1",
        assignments=(
            ChunkTopicAssignment(chunk_id="chunk-b", topic_ids=("motion", "force")),
            ChunkTopicAssignment(chunk_id="chunk-a", topic_ids=("energy",)),
        ),
    )
    path = tmp_path / "chunk_topic_map.json"

    write_chunk_topic_map(topic_map, path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [item["chunk_id"] for item in payload["assignments"]] == [
        "chunk-a",
        "chunk-b",
    ]
    assert payload["assignments"][1]["topic_ids"] == ["force", "motion"]
    assert load_chunk_topic_map(path) == canonical_chunk_topic_map(topic_map)
    assert "topic_ids" not in Chunk.model_fields


def test_topic_map_rejects_duplicate_chunk_assignments() -> None:
    with pytest.raises(ValueError, match="only once"):
        ChunkTopicMap(
            corpus_version="2.0.0-dev.1",
            corpus_hash="sha256:corpus",
            topic_registry_version="topics-v1",
            assignments=(
                ChunkTopicAssignment(chunk_id="chunk-a", topic_ids=("force",)),
                ChunkTopicAssignment(chunk_id="chunk-a", topic_ids=("motion",)),
            ),
        )


def test_topic_map_must_match_the_manifest_and_corpus_chunk_ids() -> None:
    from types import SimpleNamespace

    manifest = SimpleNamespace(
        corpus_version="2.0.0-dev.1",
        corpus_hash="sha256:corpus",
    )
    topic_map = ChunkTopicMap(
        corpus_version="2.0.0-dev.1",
        corpus_hash="sha256:corpus",
        topic_registry_version="topics-v1",
        assignments=(ChunkTopicAssignment(chunk_id="chunk-a", topic_ids=("force",)),),
    )

    validate_chunk_topic_map(topic_map, manifest, ("chunk-a", "chunk-b"))

    with pytest.raises(ValueError, match="corpus_hash"):
        validate_chunk_topic_map(
            topic_map.model_copy(update={"corpus_hash": "sha256:other"}),
            manifest,
            ("chunk-a", "chunk-b"),
        )
    with pytest.raises(ValueError, match="absent"):
        validate_chunk_topic_map(
            topic_map.model_copy(
                update={
                    "assignments": (
                        ChunkTopicAssignment(chunk_id="chunk-z", topic_ids=("force",)),
                    )
                }
            ),
            manifest,
            ("chunk-a", "chunk-b"),
        )
