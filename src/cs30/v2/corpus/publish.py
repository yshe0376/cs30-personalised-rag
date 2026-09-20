"""Small atomic publish boundary for v2 output directories."""

from __future__ import annotations

import os
from pathlib import Path

from cs30.v2.errors import LockError, PublishConflictError


def atomic_publish_directory(staging_dir: Path, output_dir: Path) -> None:
    """Rename a completed sibling directory into a previously unused target."""

    staging_dir = staging_dir.resolve()
    output_dir = output_dir.resolve()
    if staging_dir.parent != output_dir.parent:
        raise ValueError("staging and output directories must share a parent")
    if not staging_dir.is_dir():
        raise ValueError(f"staging directory does not exist: {staging_dir}")
    if output_dir.exists():
        raise PublishConflictError(f"output directory already exists: {output_dir}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir.parent / f".{output_dir.name}.lock"
    try:
        try:
            with lock_path.open("x", encoding="utf-8") as lock:
                lock.write("v2-publish-lock\n")
        except FileExistsError as exc:
            raise LockError(f"publish is already locked: {lock_path}") from exc
        if output_dir.exists():
            raise PublishConflictError(f"output directory already exists: {output_dir}")
        try:
            os.rename(staging_dir, output_dir)
        except FileExistsError as exc:
            raise PublishConflictError(f"output directory already exists: {output_dir}") from exc
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
