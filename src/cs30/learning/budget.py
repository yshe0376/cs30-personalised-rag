"""Persistent request budget shared by the three API roles."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cs30.generation.exceptions import LLMRequestBudgetExceeded


@dataclass
class RequestScope:
    turn_id: str
    operation_id: str
    max_requests: int
    turn_limit: int
    used: int = 0


_CURRENT_SCOPE: ContextVar[RequestScope | None] = ContextVar(
    "cs30_learning_request_scope", default=None
)
_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


class _CrossProcessFileLock:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.stream = None
        key = str(self.path).casefold() if os.name == "nt" else str(self.path)
        with _PROCESS_LOCKS_GUARD:
            self.local_lock = _PROCESS_LOCKS.setdefault(key, threading.RLock())

    def __enter__(self):
        self.local_lock.acquire()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.stream = self.path.open("a+b")
            self.stream.seek(0)
            if not self.stream.read(1):
                self.stream.seek(0)
                self.stream.write(b"\0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX)
            return self
        except Exception:
            if self.stream is not None:
                self.stream.close()
            self.local_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        assert self.stream is not None
        try:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
            self.local_lock.release()


class PersistentRequestBudget:
    """Reserve an attempt before sending it, so failures still use the budget."""

    def __init__(self, counter_path: Path, *, total_cap: int, turn_limit: int = 14) -> None:
        if total_cap < 1:
            raise ValueError("a positive process-level request cap is required for live calls")
        if turn_limit < 1:
            raise ValueError("turn_limit must be positive")
        self.counter_path = Path(counter_path)
        self.lock_path = self.counter_path.with_suffix(self.counter_path.suffix + ".lock")
        self.total_cap = total_cap
        self.turn_limit = turn_limit
        self._thread_lock = threading.RLock()
        self._turn_counts: dict[str, int] = {}

    @contextmanager
    def operation(
        self,
        *,
        turn_id: str,
        operation_id: str,
        max_requests: int,
    ) -> Iterator[RequestScope]:
        if not turn_id.strip() or not operation_id.strip() or max_requests < 1:
            raise ValueError("operation IDs and a positive request cap are required")
        if _CURRENT_SCOPE.get() is not None:
            raise RuntimeError("nested API budget operations are not supported")
        scope = RequestScope(turn_id, operation_id, max_requests, self.turn_limit)
        token = _CURRENT_SCOPE.set(scope)
        try:
            yield scope
        finally:
            _CURRENT_SCOPE.reset(token)

    def reserve(self) -> int:
        scope = _CURRENT_SCOPE.get()
        if scope is None:
            raise RuntimeError("an API call must run inside a budgeted operation")
        with self._thread_lock:
            if scope.used >= scope.max_requests:
                raise LLMRequestBudgetExceeded(
                    f"{scope.operation_id} reached its {scope.max_requests}-request limit"
                )
            used_this_turn = self._turn_counts.get(scope.turn_id, 0)
            if used_this_turn >= scope.turn_limit:
                raise LLMRequestBudgetExceeded(f"turn reached its {scope.turn_limit}-request limit")
            new_total = self._reserve_global()
            scope.used += 1
            self._turn_counts[scope.turn_id] = used_this_turn + 1
            return new_total

    def _reserve_global(self) -> int:
        self.counter_path.parent.mkdir(parents=True, exist_ok=True)
        with _CrossProcessFileLock(self.lock_path):
            state = self._read_state()
            used = int(state.get("used", 0))
            if used >= self.total_cap:
                raise LLMRequestBudgetExceeded(
                    f"process-level API request cap reached ({used}/{self.total_cap})"
                )
            used += 1
            self._write_state(used)
            return used

    def _read_state(self) -> dict[str, object]:
        if not self.counter_path.exists():
            return {"schema_version": "1", "used": 0}
        try:
            value = json.loads(self.counter_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMRequestBudgetExceeded(
                "request counter is unreadable; refusing to send another API request"
            ) from exc
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != "1"
            or not isinstance(value.get("used"), int)
        ):
            raise LLMRequestBudgetExceeded(
                "request counter has an unsupported shape; refusing to reset it"
            )
        return value

    def _write_state(self, used: int) -> None:
        payload = {
            "schema_version": "1",
            "used": used,
            "configured_cap": self.total_cap,
            "updated_at_utc": datetime.now(UTC).isoformat(),
        }
        self.counter_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=self.counter_path.name + ".", suffix=".tmp", dir=self.counter_path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.counter_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def snapshot(self) -> dict[str, int]:
        self.counter_path.parent.mkdir(parents=True, exist_ok=True)
        with _CrossProcessFileLock(self.lock_path):
            state = self._read_state()
            return {
                "used": int(state.get("used", 0)),
                "cap": self.total_cap,
                "remaining": max(0, self.total_cap - int(state.get("used", 0))),
            }

    def turn_usage(self, turn_id: str) -> int:
        with self._thread_lock:
            return self._turn_counts.get(turn_id, 0)


class BudgetedClient:
    """Wrap the existing compatible client without changing its wire contract."""

    def __init__(self, client, budget: PersistentRequestBudget) -> None:
        self.client = client
        self.budget = budget
        self.model = client.model

    def __getattr__(self, name: str):
        return getattr(self.client, name)

    def complete(self, prompt: str, text_format: dict):
        self.budget.reserve()
        return self.client.complete(prompt, text_format)
