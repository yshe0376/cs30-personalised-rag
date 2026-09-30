"""Single-writer, append-only JSONL storage for Concept Check events."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from threading import RLock

from cs30.concept_check.learner_state import EventReplayer
from cs30.v2.contracts import ConceptCheckEvent, ConceptCheckEventType

_LOGGER = logging.getLogger(__name__)


class JsonlEventStore:
    """One process owns this store; the event stream remains the source of truth."""

    def __init__(self, directory: Path, replayer: EventReplayer) -> None:
        self.directory = Path(directory)
        self.replayer = replayer
        self._lock = RLock()

    def _path(self, profile_id: str) -> Path:
        digest = hashlib.sha256(profile_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.jsonl"

    def events(self, profile_id: str) -> tuple[ConceptCheckEvent, ...]:
        """Read typed events; callers decide when to replay learner state."""

        with self._lock:
            events, _ = self._read_events(profile_id)
            return events

    def _read_events(self, profile_id: str) -> tuple[tuple[ConceptCheckEvent, ...], bytes]:
        if profile_id != self.replayer.static_profile.profile_id:
            raise ValueError("event store profile_id mismatch")
        path = self._path(profile_id)
        if not path.exists():
            return (), b""
        payload = path.read_bytes()
        lines = payload.splitlines(keepends=True)
        events: list[ConceptCheckEvent] = []
        valid_end = 0
        for index, line in enumerate(lines):
            if not line.strip():
                valid_end += len(line)
                continue
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                if index == len(lines) - 1 and not line.endswith((b"\n", b"\r")):
                    _LOGGER.warning("Ignoring incomplete final Concept Check record in %s", path)
                    break
                raise
            event = ConceptCheckEvent.model_validate(value)
            if event.profile_id != profile_id:
                raise ValueError("stored event profile_id mismatch")
            events.append(event)
            valid_end += len(line)
        return tuple(events), payload[:valid_end]

    def append(self, event: ConceptCheckEvent) -> ConceptCheckEvent:
        with self._lock:
            existing, valid_payload = self._read_events(event.profile_id)
            for prior in existing:
                same_event = prior.event_id == event.event_id
                same_attempt = (
                    event.event_type
                    in {
                        ConceptCheckEventType.ATTEMPT_SUBMITTED,
                        ConceptCheckEventType.ATTEMPT_SKIPPED,
                    }
                    and prior.attempt_id is not None
                    and prior.attempt_id == event.attempt_id
                )
                if same_event or same_attempt:
                    stable_fields = {"stream_version", "state_version_before", "created_at"}
                    if same_attempt and not same_event:
                        stable_fields |= {"event_id"}
                    left = prior.model_dump(exclude=stable_fields)
                    right = event.model_dump(exclude=stable_fields)
                    if left != right:
                        raise ValueError("Concept Check event or attempt idempotency conflict")
                    return prior
            stored = event.model_copy(
                update={
                    "stream_version": len(existing) + 1,
                    "state_version_before": len(existing),
                }
            )
            self.replayer.replay((*existing, stored))
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self._path(event.profile_id)
            with path.open("r+b" if path.exists() else "w+b") as stream:
                stream.seek(len(valid_payload))
                stream.truncate()  # Remove only an incomplete, unterminated final record.
                if valid_payload and not valid_payload.endswith(b"\n"):
                    stream.write(b"\n")
                stream.write(
                    (json.dumps(stored.model_dump(mode="json"), sort_keys=True) + "\n").encode(
                        "utf-8"
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
            return stored
