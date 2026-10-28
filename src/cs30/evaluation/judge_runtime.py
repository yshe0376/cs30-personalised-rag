"""Provider-neutral blinded judge requests, validation, and hash-bound caching."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from cs30.generation.client import LLMClient

from .adaptation_applicability import validate_adaptation_applicability
from .evidence_quotes import quote_is_grounded
from .gemini_judge_client import GeminiJudgeEmptyResponseError
from .level_profiles import canonical_json_sha256
from .v2_generation_models import (
    AdaptationJudgeOutput,
    DiscriminationJudgeOutput,
    EvaluationMode,
    EvidenceSupportJudgeOutput,
    JudgeConfiguration,
    JudgeRequest,
    JudgeResultEnvelope,
    JudgeTask,
    SupportVerdict,
    canonical_model_family,
)

ValidatedOutput = TypeVar("ValidatedOutput", bound=BaseModel)


class JudgeProvider(Protocol):
    """Minimal seam implemented by an approved local or third-party judge client."""

    def __call__(
        self,
        request: JudgeRequest,
        configuration: JudgeConfiguration,
    ) -> Mapping[str, Any] | JudgeProviderResponse: ...


@dataclass(frozen=True)
class JudgeProviderResponse:
    output: Mapping[str, Any]
    response_id: str | None
    completed_at_utc: str
    reported_model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    usage_available: bool = True


class JudgeProviderOutputError(ValueError):
    """Preserve returned usage when structured-output decoding fails locally."""

    def __init__(self, message: str, response: JudgeProviderResponse) -> None:
        super().__init__(message)
        self.response = response


def _append_attempt(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


_OUTPUT_MODELS: dict[JudgeTask, type[BaseModel]] = {
    JudgeTask.ADAPTATION: AdaptationJudgeOutput,
    JudgeTask.DISCRIMINATION: DiscriminationJudgeOutput,
    JudgeTask.EVIDENCE_SUPPORT: EvidenceSupportJudgeOutput,
}


def _strict_object(properties: dict[str, object]) -> dict[str, object]:
    """Build the object shape accepted by strict structured-output providers."""

    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_NULLABLE_STRING: dict[str, object] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_ONLINE_OUTPUT_SCHEMAS: dict[JudgeTask, dict[str, object]] = {
    JudgeTask.ADAPTATION: _strict_object(
        {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "request_id": {"type": "string"},
            "criteria": {
                "type": "array",
                "items": _strict_object(
                    {
                        "criterion_id": {"type": "string"},
                        "verdict": {
                            "type": "string",
                            "enum": ["pass", "fail", "not_applicable"],
                        },
                        "exact_quote": _NULLABLE_STRING,
                        "reason": {"type": "string"},
                    }
                ),
            },
        }
    ),
    JudgeTask.DISCRIMINATION: _strict_object(
        {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "request_id": {"type": "string"},
            "predicted_level": {
                "type": "string",
                "enum": ["beginner", "intermediate", "advanced", "uncertain"],
            },
            "exact_quote": _NULLABLE_STRING,
            "reason": {"type": "string"},
        }
    ),
    JudgeTask.EVIDENCE_SUPPORT: _strict_object(
        {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "request_id": {"type": "string"},
            "claims": {
                "type": "array",
                "items": _strict_object(
                    {
                        "claim_id": {"type": "string"},
                        "claim_text": {"type": "string"},
                        "bundle_support": {
                            "type": "string",
                            "enum": ["supported", "unsupported", "not_applicable"],
                        },
                        "citation_support": {
                            "type": "string",
                            "enum": ["supported", "unsupported", "not_applicable"],
                        },
                        "supporting_evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "evidence_quotes": {
                            "type": "array",
                            "items": _strict_object(
                                {
                                    "evidence_id": {"type": "string"},
                                    "quote": {"type": "string"},
                                }
                            ),
                        },
                        "reason": {"type": "string"},
                    }
                ),
            },
        }
    ),
}
_REPAIR_MARKER = "\n\nREPAIR_REQUEST:\n"


def _render_judge_prompt(request: JudgeRequest) -> str:
    """Place validation feedback after the original request payload."""

    instruction, marker, repair = request.system_instruction.partition(_REPAIR_MARKER)
    prompt = (
        f"{instruction.rstrip()}\n\n"
        f"REQUEST_ID: {request.request_id}\n"
        "REQUEST_PAYLOAD_JSON:\n"
        + json.dumps(request.payload, ensure_ascii=False, sort_keys=True)
    )
    if marker:
        prompt += _REPAIR_MARKER + repair
    return prompt


class StructuredJsonJudgeProvider:
    """Call an existing structured-output LLM client for one blinded judge request."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def __call__(
        self,
        request: JudgeRequest,
        configuration: JudgeConfiguration,
    ) -> JudgeProviderResponse:
        prompt = _render_judge_prompt(request)
        empty_error = None
        try:
            response = self.client.complete(
                prompt,
                {
                    "type": "json_schema",
                    "name": f"{request.task.value}_judge_output",
                    "strict": True,
                    "schema": _ONLINE_OUTPUT_SCHEMAS[request.task],
                },
            )
        except GeminiJudgeEmptyResponseError as exc:
            response = exc.response
            empty_error = exc
        metadata = JudgeProviderResponse(
            output={},
            response_id=response.response_id,
            completed_at_utc=datetime.now(UTC).isoformat(),
            reported_model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            thought_tokens=int(getattr(response, "thought_tokens", 0)),
            usage_available=bool(getattr(response, "usage_available", True)),
        )
        if empty_error is not None:
            raise JudgeProviderOutputError(str(empty_error), metadata) from empty_error
        if response.done_reason == "length":
            raise JudgeProviderOutputError("judge provider output was truncated", metadata)
        try:
            raw = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise JudgeProviderOutputError(
                "judge provider did not return valid JSON", metadata
            ) from exc
        if not isinstance(raw, Mapping):
            raise JudgeProviderOutputError("judge provider JSON must be an object", metadata)
        return replace(metadata, output=raw)


def configuration_sha256(configuration: JudgeConfiguration) -> str:
    payload = configuration.model_dump(mode="json")
    # thinking_level only exists for Gemini. Leaving an unset value out keeps every
    # earlier non-Gemini configuration hash, and the requests and caches bound to it, valid.
    if payload.get("thinking_level") is None:
        payload.pop("thinking_level", None)
    return canonical_json_sha256(payload)


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


def validate_output_against_request(
    raw: Mapping[str, Any],
    request: JudgeRequest,
) -> BaseModel:
    """Validate provider JSON against the blinded request before it can be cached."""

    output_model = _OUTPUT_MODELS[request.task]
    output = output_model.model_validate(raw)
    if getattr(output, "request_id", None) != request.request_id:
        raise ValueError("judge output request_id does not match request")
    answer = request.payload.get("answer")
    if not isinstance(answer, str):
        raise ValueError("judge request is missing answer text")

    if isinstance(output, AdaptationJudgeOutput):
        checklist = request.payload.get("checklist")
        if not isinstance(checklist, list):
            raise ValueError("adaptation request is missing its checklist")
        expected_ids = {
            str(item.get("criterion_id"))
            for item in checklist
            if isinstance(item, Mapping) and item.get("criterion_id")
        }
        actual_ids = [item.criterion_id for item in output.criteria]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
            raise ValueError("adaptation output criterion coverage does not match request")
        for judgement in output.criteria:
            if judgement.exact_quote is not None and judgement.exact_quote not in answer:
                raise ValueError(
                    f"criterion {judgement.criterion_id} quote is not an exact answer substring"
                )
        validate_adaptation_applicability(request, output)
        return output

    if isinstance(output, DiscriminationJudgeOutput):
        if output.exact_quote is not None and output.exact_quote not in answer:
            raise ValueError("discrimination quote is not an exact answer substring")
        return output

    if not isinstance(output, EvidenceSupportJudgeOutput):
        raise AssertionError(f"unsupported judge output model: {type(output)!r}")
    evidence_rows = request.payload.get("evidence")
    if not isinstance(evidence_rows, list):
        raise ValueError("evidence-support request is missing evidence")
    evidence = {
        str(item["evidence_id"]): str(item["text"])
        for item in evidence_rows
        if isinstance(item, Mapping) and "evidence_id" in item and "text" in item
    }
    citations = {str(value) for value in request.payload.get("citation_ids") or []}
    claim_ids = [claim.claim_id for claim in output.claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("evidence-support output contains duplicate claim IDs")
    for claim in output.claims:
        if claim.claim_text not in answer:
            raise ValueError(f"claim {claim.claim_id} is not an exact answer substring")
        supporting = set(claim.supporting_evidence_ids)
        if len(supporting) != len(claim.supporting_evidence_ids):
            raise ValueError(f"claim {claim.claim_id} repeats supporting evidence IDs")
        if not supporting <= evidence.keys():
            raise ValueError(f"claim {claim.claim_id} references unknown evidence")
        if set(claim.evidence_quotes) != supporting:
            raise ValueError(f"claim {claim.claim_id} requires one quote per supporting ID")
        if any(
            not quote_is_grounded(quote, evidence[evidence_id])
            for evidence_id, quote in claim.evidence_quotes.items()
        ):
            raise ValueError(f"claim {claim.claim_id} has a quote outside the supplied evidence")
        if claim.bundle_support is SupportVerdict.SUPPORTED and not supporting:
            raise ValueError(f"supported claim {claim.claim_id} requires supporting evidence")
        if claim.citation_support is SupportVerdict.SUPPORTED and (
            claim.bundle_support is not SupportVerdict.SUPPORTED
            or not supporting.intersection(citations)
        ):
            raise ValueError(f"claim {claim.claim_id} lacks support among the cited evidence")
    return output


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
            if envelope.unresolved:
                continue
            if envelope.cache_key in cache:
                raise ValueError(f"{path}:{line_number}: duplicate judge cache key")
            cache[envelope.cache_key] = envelope
    return cache


def _append_cache(path: Path, envelope: JudgeResultEnvelope) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(envelope.model_dump_json())
        stream.write("\n")


def _repair_judge_request(
    request: JudgeRequest,
    invalid_output: Mapping[str, Any],
    error: Exception,
) -> JudgeRequest:
    """Append one bounded local-validation correction request for the next attempt."""

    previous_output = json.dumps(
        invalid_output,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )[:2000]
    repair_instruction = f"""{request.system_instruction.rstrip()}{_REPAIR_MARKER}
The previous response was rejected by local validation.
ERROR_TYPE: {type(error).__name__}
ERROR: {str(error)[:2000]}
PREVIOUS_OUTPUT: {previous_output}

Return one corrected JSON object only.
"""
    return request.model_copy(update={"system_instruction": repair_instruction})


class CachedJudgeRunner:
    """Run one approved judge task with deterministic cache and unresolved handling."""

    def __init__(
        self,
        cache_path: Path,
        *,
        judge_execution_id: str,
        model_digest: str | None = None,
        context_window: int | None = None,
        max_attempts: int = 2,
        require_current_execution_cache: bool = False,
        attempt_log_path: Path | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        judge_execution_id = judge_execution_id.strip()
        if not judge_execution_id:
            raise ValueError("judge_execution_id must not be empty")
        if context_window is not None and context_window <= 0:
            raise ValueError("context_window must be positive")
        self.cache_path = cache_path
        self.attempt_log_path = attempt_log_path or cache_path.with_suffix(".attempts.jsonl")
        if self.attempt_log_path.resolve() == cache_path.resolve():
            raise ValueError("judge attempt log must be separate from the success cache")
        self.judge_execution_id = judge_execution_id
        self.model_digest = model_digest
        self.context_window = context_window
        self.max_attempts = max_attempts
        self._cache = _load_cache(cache_path)
        if require_current_execution_cache and any(
            envelope.judge_execution_id != self.judge_execution_id
            for envelope in self._cache.values()
        ):
            raise ValueError(
                "fresh judge execution cache contains results from another or unaudited execution"
            )
        self.attempt_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.attempt_log_path.open("a", encoding="utf-8"):
            pass

    def run(
        self,
        request: JudgeRequest,
        configuration: JudgeConfiguration,
        provider: JudgeProvider,
        validator: Callable[[Mapping[str, Any]], ValidatedOutput],
    ) -> JudgeResultEnvelope:
        if request.task is JudgeTask.EVIDENCE_SUPPORT and self.max_attempts < 2:
            raise ValueError("evidence support requires at least two application attempts")
        expected_config = configuration_sha256(configuration)
        if request.config_sha256 != expected_config:
            raise ValueError("judge request is bound to a different configuration")
        cache_key = request_cache_key(request)
        cached = self._cache.get(cache_key)
        if cached is not None:
            reused_from_other_execution = cached.judge_execution_id != self.judge_execution_id
            if not reused_from_other_execution and (
                cached.model_digest != self.model_digest
                or cached.context_window != self.context_window
            ):
                raise ValueError("judge resume runtime differs from the original execution")
            return cached.model_copy(update={"cache_hit": reused_from_other_execution})

        errors: list[str] = []
        validated: ValidatedOutput | None = None
        last_raw: dict[str, object] | None = None
        last_response: JudgeProviderResponse | None = None
        attempt_request = request
        totals = {"input_tokens": 0, "output_tokens": 0, "thought_tokens": 0}
        for attempt in range(1, self.max_attempts + 1):
            attempt_raw: dict[str, object] | None = None
            response: JudgeProviderResponse | None = None
            started_at = datetime.now(UTC).isoformat()
            status = "provider_error"
            attempt_error: str | None = None
            attempt_failure: Exception | None = None
            try:
                provider_result = provider(attempt_request, configuration)
                if isinstance(provider_result, JudgeProviderResponse):
                    response = provider_result
                    raw = response.output
                else:
                    raw = provider_result
                    response = JudgeProviderResponse(
                        output=raw,
                        response_id=None,
                        completed_at_utc=datetime.now(UTC).isoformat(),
                        usage_available=False,
                    )
                last_response = response
                status = "invalid_output"
                if response.reported_model is not None and canonical_model_family(
                    response.reported_model
                ) != canonical_model_family(configuration.model_family):
                    raise ValueError(
                        "judge provider reported a model outside the configured model family"
                    )
                if not isinstance(raw, Mapping):
                    raise TypeError("judge provider must return a mapping")
                attempt_raw = dict(raw)
                last_raw = attempt_raw
                validated = validator(raw)
                status = "accepted"
            except Exception as exc:  # Provider failures remain auditable unresolved records.
                if isinstance(exc, JudgeProviderOutputError):
                    response = last_response = exc.response
                    status = "invalid_output"
                attempt_error = str(exc)
                attempt_failure = exc
                errors.append(f"attempt {attempt}: {exc}")
            usage_available = response is not None and response.usage_available
            usage = {
                field: getattr(response, field) if usage_available else None for field in totals
            }
            for field, value in usage.items():
                totals[field] += value or 0
            # A ledger write failure propagates: never spend on another retry without logging.
            _append_attempt(
                self.attempt_log_path,
                {
                    "schema_version": "1.0",
                    "attempt_id": uuid4().hex,
                    "judge_execution_id": self.judge_execution_id,
                    "task": request.task.value,
                    "request_id": request.request_id,
                    "cache_key": cache_key,
                    "config_sha256": request.config_sha256,
                    "provider": configuration.provider,
                    "model_revision": configuration.model_revision,
                    "attempt": attempt,
                    "started_at_utc": started_at,
                    "completed_at_utc": response.completed_at_utc
                    if response
                    else datetime.now(UTC).isoformat(),
                    "provider_response_id": response.response_id if response else None,
                    "reported_model": response.reported_model if response else None,
                    "status": status,
                    "error": attempt_error,
                    "usage_available": usage_available,
                    **usage,
                },
            )
            if validated is not None:
                break
            if (
                attempt < self.max_attempts
                and attempt_raw is not None
                and attempt_failure is not None
            ):
                attempt_request = _repair_judge_request(request, attempt_raw, attempt_failure)
            else:
                attempt_request = request

        if validated is None:
            envelope = JudgeResultEnvelope(
                task=request.task,
                request_id=request.request_id,
                cache_key=cache_key,
                judge_config_version=configuration.config_version,
                judge_execution_id=self.judge_execution_id,
                model_digest=self.model_digest,
                context_window=self.context_window,
                raw_output=last_raw,
                unresolved=True,
                error="; ".join(errors),
                completed_at_utc=(
                    last_response.completed_at_utc if last_response is not None else None
                ),
                provider_response_id=last_response.response_id if last_response else None,
                reported_model=last_response.reported_model if last_response else None,
                **totals,
            )
        else:
            if last_response is None:
                raise AssertionError("validated judge output is missing provider metadata")
            envelope = JudgeResultEnvelope(
                task=request.task,
                request_id=request.request_id,
                cache_key=cache_key,
                judge_config_version=configuration.config_version,
                judge_execution_id=self.judge_execution_id,
                model_digest=self.model_digest,
                context_window=self.context_window,
                output=validated.model_dump(mode="json"),
                provider_response_id=last_response.response_id,
                completed_at_utc=last_response.completed_at_utc,
                reported_model=last_response.reported_model,
                **totals,
            )
        if not envelope.unresolved:
            _append_cache(self.cache_path, envelope)
            self._cache[cache_key] = envelope
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
