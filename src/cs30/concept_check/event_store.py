"""Single-writer, append-only JSONL storage for Concept Check events."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from threading import RLock

from cs30.concept_check.learner_state import EventReplayer
from cs30.v2.contracts import ConceptCheckEvent, ConceptCheckEventType


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
        with self._lock:
            if profile_id != self.replayer.static_profile.profile_id:
                raise ValueError("event store profile_id mismatch")
            path = self._path(profile_id)
            if not path.exists():
                return ()
            with path.open("r", encoding="utf-8") as stream:
                events = tuple(
                    ConceptCheckEvent.model_validate_json(line) for line in stream if line.strip()
                )
            self.replayer.replay(events)
            return events

    def append(self, event: ConceptCheckEvent) -> ConceptCheckEvent:
        with self._lock:
            existing = self.events(event.profile_id)
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
                    stable_fields = {"stream_version", "state_version_before"}
                    if same_attempt and not same_event:
                        stable_fields |= {"event_id", "created_at"}
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
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(stored.model_dump(mode="json"), sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return stored
