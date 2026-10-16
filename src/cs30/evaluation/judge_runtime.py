"""Provider-neutral blinded judge requests, validation, and hash-bound caching."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from .level_profiles import canonical_json_sha256
from .v2_generation_models import (
    EvaluationMode,
    JudgeConfiguration,
    JudgeRequest,
    JudgeResultEnvelope,
    JudgeTask,
)

ValidatedOutput = TypeVar("ValidatedOutput", bound=BaseModel)


class JudgeProvider(Protocol):
    """Minimal seam implemented by an approved local or third-party judge client."""

    def __call__(
        self,
        request: JudgeRequest,
        configuration: JudgeConfiguration,
    ) -> Mapping[str, Any]: ...


def configuration_sha256(configuration: JudgeConfiguration) -> str:
    return canonical_json_sha256(configuration.model_dump(mode="json"))


def make_judge_request(
    *,
    task: JudgeTask,
    payload: Mapping[str, object],
    system_instruction: str,
    configuration: JudgeConfiguration,
    generation_model_family: str,
    mode: EvaluationMode,
) -> JudgeRequest:
    """Create a request after enforcing provider/family/data approval boundaries."""

    configuration.assert_allowed(generation_model_family, mode)
    input_sha256 = canonical_json_sha256(
        {
            "task": task.value,
            "system_instruction": system_instruction,
            "payload": payload,
            "prompt_version": configuration.prompt_version,
            "output_schema_version": configuration.output_schema_version,
        }
    )
    return JudgeRequest(
        task=task,
        request_id=f"{task.value}-{input_sha256[:20]}",
        input_sha256=input_sha256,
        config_sha256=configuration_sha256(configuration),
        system_instruction=system_instruction,
        payload=dict(payload),
    )


def request_cache_key(request: JudgeRequest) -> str:
    return canonical_json_sha256(request.model_dump(mode="json"))


def _load_cache(path: Path) -> dict[str, JudgeResultEnvelope]:
    if not path.exists():
        return {}
    cache: dict[str, JudgeResultEnvelope] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                envelope = JudgeResultEnvelope.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid judge cache: {exc}") from exc
            if envelope.cache_key in cache:
                raise ValueError(f"{path}:{line_number}: duplicate judge cache key")
            cache[envelope.cache_key] = envelope
    return cache


def _write_cache(path: Path, cache: Mapping[str, JudgeResultEnvelope]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for cache_key in sorted(cache):
            stream.write(cache[cache_key].model_dump_json())
            stream.write("\n")
    temporary.replace(path)


class CachedJudgeRunner:
    """Run one approved judge task with deterministic cache and unresolved handling."""

    def __init__(self, cache_path: Path, *, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.cache_path = cache_path
        self.max_attempts = max_attempts

    def run(
        self,
        request: JudgeRequest,
        configuration: JudgeConfiguration,
        provider: JudgeProvider,
        validator: Callable[[Mapping[str, Any]], ValidatedOutput],
    ) -> JudgeResultEnvelope:
        expected_config = configuration_sha256(configuration)
        if request.config_sha256 != expected_config:
            raise ValueError("judge request is bound to a different configuration")
        cache_key = request_cache_key(request)
        cache = _load_cache(self.cache_path)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        errors: list[str] = []
        validated: ValidatedOutput | None = None
        last_raw: dict[str, object] | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = provider(request, configuration)
                if not isinstance(raw, Mapping):
                    raise TypeError("judge provider must return a mapping")
                last_raw = dict(raw)
                validated = validator(raw)
                break
            except Exception as exc:  # Provider failures remain auditable unresolved records.
                errors.append(f"attempt {attempt}: {exc}")

        if validated is None:
            envelope = JudgeResultEnvelope(
                task=request.task,
                request_id=request.request_id,
                cache_key=cache_key,
                judge_config_version=configuration.config_version,
                raw_output=last_raw,
                unresolved=True,
                error="; ".join(errors),
            )
        else:
            envelope = JudgeResultEnvelope(
                task=request.task,
                request_id=request.request_id,
                cache_key=cache_key,
                judge_config_version=configuration.config_version,
                output=validated.model_dump(mode="json"),
            )
        cache[cache_key] = envelope
        _write_cache(self.cache_path, cache)
        return envelope


def write_judge_requests(requests: list[JudgeRequest], path: Path) -> Path:
    """Persist blinded requests for an approved external runner without hidden fields."""

    request_ids = [request.request_id for request in requests]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("judge request IDs must be unique")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(request.model_dump_json() + "\n" for request in requests),
        encoding="utf-8",
    )
    return path
