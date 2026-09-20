"""Atomic publish and v2 configuration boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cs30.v2.corpus.publish import atomic_publish_directory
from cs30.v2.errors import LockError, PublishConflictError


def test_atomic_publish_renames_only_a_completed_sibling(tmp_path: Path) -> None:
    staging = tmp_path / ".staging-123"
    output = tmp_path / "2.0.0-dev.1"
    staging.mkdir()
    (staging / "records.jsonl").write_text("records\n", encoding="utf-8")

    atomic_publish_directory(staging, output)

    assert not staging.exists()
    assert (output / "records.jsonl").read_text(encoding="utf-8") == "records\n"
    assert not (tmp_path / ".2.0.0-dev.1.lock").exists()


def test_atomic_publish_refuses_overwrite_and_cleans_no_existing_target(tmp_path: Path) -> None:
    staging = tmp_path / ".staging-123"
    output = tmp_path / "2.0.0-dev.1"
    staging.mkdir()
    output.mkdir()
    (output / "existing").write_text("keep", encoding="utf-8")

    with pytest.raises(PublishConflictError, match="already exists"):
        atomic_publish_directory(staging, output)

    assert (output / "existing").read_text(encoding="utf-8") == "keep"
    assert staging.exists()


def test_atomic_publish_honours_an_existing_lock(tmp_path: Path) -> None:
    staging = tmp_path / ".staging-123"
    output = tmp_path / "2.0.0-dev.1"
    staging.mkdir()
    (tmp_path / ".2.0.0-dev.1.lock").write_text("other\n", encoding="utf-8")

    with pytest.raises(LockError, match="locked"):
        atomic_publish_directory(staging, output)

    assert staging.exists()


def test_atomic_publish_does_not_accept_different_parent(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    output = tmp_path / "nested" / "output"
    staging.mkdir()

    with pytest.raises(ValueError, match="share a parent"):
        atomic_publish_directory(staging, output)
