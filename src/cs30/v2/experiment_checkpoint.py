"""Crash-safe per-cell checkpoints and one-writer locks for V2 experiments."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from cs30.evaluation.open_answer_models import ExpectedAnswer
from cs30.v2.contracts import EvidenceBundle
from cs30.v2.experiment_models import GenerationRun
from cs30.v2.io import canonical_hash


@contextmanager
def writer_lock(directory: Path):
    """The OS releases the lock even after SIGKILL or a process crash."""
    with (directory / ".writer.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("another process is already writing this experiment") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def atomic_json(path: Path, value: dict) -> None:
    """Publish only a fully flushed file; an interrupted temp file is not a cell."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write((json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def checkpoint_name(run_id: str) -> str:
    return canonical_hash(run_id) + ".json"


def save_cell(directory: Path, record: GenerationRun, details: dict) -> None:
    path = directory / checkpoint_name(record.run_id)
    if path.exists():
        raise ValueError("refusing to replace a completed experiment cell")
    payload = {"record": record.model_dump(mode="json"), "details": details}
    atomic_json(
        path, {"schema_version": "0.1", "payload_sha256": canonical_hash(payload), **payload}
    )


def load_cells(
    directory: Path, expected: list[ExpectedAnswer]
) -> dict[str, tuple[GenerationRun, dict]]:
    if not directory.is_dir():
        raise ValueError("this older run has no resumable per-cell checkpoints")
    by_name = {checkpoint_name(cell.run_id): cell for cell in expected}
    result = {}
    for path in directory.glob("*.json"):
        if path.name not in by_name:
            raise ValueError("checkpoint contains an unexpected experiment cell")
        value = json.loads(path.read_bytes())
        payload = {"record": value["record"], "details": value["details"]}
        if value.get("schema_version") != "0.1" or canonical_hash(payload) != value.get(
            "payload_sha256"
        ):
            raise ValueError("checkpoint content hash mismatch")
        record = GenerationRun.model_validate(value["record"])
        details = value["details"]
        expected_cell = by_name[path.name]
        for field in ExpectedAnswer.model_fields:
            wanted = getattr(expected_cell, field)
            if getattr(record, field) != wanted or details.get(field) != wanted:
                raise ValueError("checkpoint identity differs from the frozen matrix")
        if details.get("answer") != (
            record.answer.model_dump(mode="json") if record.answer else None
        ):
            raise ValueError("checkpoint answer differs from its complete trace")
        if details.get("error") != record.error:
            raise ValueError("checkpoint technical error differs from its trace")
        bundle = EvidenceBundle.model_validate(details["evidence"])
        if record.answer and not set(record.answer.citations) <= set(bundle.citation_map.values()):
            raise ValueError("checkpoint citations differ from saved evidence")
        result[record.run_id] = (record, details)
    return result


def supersede_cell(directory: Path, run_id: str) -> None:
    """Atomically retain the failed attempt before making the cell runnable again."""
    import uuid

    source = directory / checkpoint_name(run_id)
    archive = directory / "superseded"
    archive.mkdir(exist_ok=True)
    os.replace(source, archive / (source.stem + "-" + uuid.uuid4().hex + ".json"))
    if os.name != "nt":
        for parent in (directory, archive):
            descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
