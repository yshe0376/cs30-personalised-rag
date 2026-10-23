"""Audited, resumable Chat Completions client for hosted open-weight models.

Wire requests are cached before sending; responses are committed before parsing.
No credential headers are persisted. A provider may still charge for a request
whose response was lost before the local commit (no exactly-once API guarantee).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from .client import LLMResponse, TokenUsage
from .exceptions import (
    LLMCacheIntegrityError,
    LLMProviderError,
    LLMRequestBudgetExceeded,
    LLMRetryLater,
    LLMTimeoutError,
)


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAICompatibleClient:
    """Configurable Chat Completions API; local answer validation stays strict."""

    temperature = 0.0
    allow_json_fence = True

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        provider_name: str,
        model_version: str,
        api_key_env: str = "LLM_API_KEY",
        timeout_seconds: float = 120,
        max_output_tokens: int = 2048,
        seed: int | None = None,
        structured_output: str = "auto",
        transport_retries: int = 3,
        max_retry_delay: float = 60,
        max_api_requests: int | None = None,
    ):
        parsed = urllib.parse.urlsplit(base_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise ValueError(
                "base_url requires HTTPS (HTTP only for loopback), without credentials"
            )
        if not all(value.strip() for value in (model, provider_name, model_version, api_key_env)):
            raise ValueError(
                "model, provider name, model version and API key environment are required"
            )
        if (
            not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
            or max_output_tokens < 1
            or transport_retries < 0
            or not math.isfinite(max_retry_delay)
            or max_retry_delay <= 0
        ):
            raise ValueError("invalid API timeout, token limit or retry budget")
        if structured_output not in {"auto", "json_schema", "json_object", "text"}:
            raise ValueError("unknown structured output mode")
        self.api_key = os.environ.get(api_key_env, "").strip()
        if not self.api_key:
            raise ValueError(f"API key environment variable {api_key_env} is empty")
        self.model = model.strip()
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.provider_name = provider_name.strip()
        self.model_version = model_version.strip()
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.seed = seed
        self.structured_output = structured_output
        self.transport_retries = transport_retries
        self.max_retry_delay = max_retry_delay
        if max_api_requests is not None and max_api_requests < 1:
            raise ValueError("max_api_requests must be positive")
        self.max_api_requests = max_api_requests
        self._budget_lock = threading.Lock()
        self._budget_state = {"used": 0}
        self.cache_dir: Path | None = None
        self.cache_scope: str | None = None
        self._call_number = 0

    def configure_run(self, output_dir: Path):
        # Pending attempts count too: after a crash their upstream charge is unknown.
        root = output_dir / "api_cache"
        self._budget_state["used"] = sum(
            path.name != "response.json" for path in root.glob("*/*.json")
        )

    def audit_summary(self, output_dir: Path) -> dict:
        events = [
            json.loads(path.read_bytes())
            for path in (output_dir / "api_cache").glob("*/*.json")
            if path.name != "response.json"
        ]
        input_tokens, output_tokens = 0, 0
        for event in events:
            try:
                usage = json.loads(event.get("response_text", "")).get("usage") or {}
                input_tokens += int(usage.get("prompt_tokens") or 0)
                output_tokens += int(usage.get("completion_tokens") or 0)
            except (ValueError, TypeError, AttributeError):
                continue
        return {
            "http_attempts": len(events),
            "pending_attempts_charge_unknown": sum(e.get("status") == "pending" for e in events),
            "reported_input_tokens": input_tokens,
            "reported_output_tokens": output_tokens,
            "policy": "All wire attempts, including superseded failures; absent provider "
            "usage is unknown and must be reconciled with provider billing.",
        }

    def for_cell(self, run_id: str, cache_dir: Path):
        """Separate logically repeated prompts, cells and noise-floor repetitions."""
        client = copy.copy(self)
        client.cache_scope = run_id
        client.cache_dir = cache_dir
        client._call_number = 0
        return client

    def runtime_identity(self) -> dict:
        return {
            "provider_name": self.provider_name,
            "model_version": self.model_version,
            "api_key_env": self.api_key_env,
            "structured_output": self.structured_output,
            "transport_retries": self.transport_retries,
            "max_retry_delay": self.max_retry_delay,
            "seed_reproducibility": "best effort only; API output is not reproducible verbatim",
        }

    def _delay(self, retry_after: str | None, attempt: int) -> float:
        delay = min(2**attempt, self.max_retry_delay)
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    pass
        if not math.isfinite(delay) or delay > self.max_retry_delay:
            raise LLMRetryLater("Retry-After exceeds bounded wait budget; resume later")
        return max(0, delay)

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        self._call_number += 1
        identity = {
            **self.runtime_identity(),
            "model": self.model,
            "endpoint": self.endpoint,
            "temperature": self.temperature,
            "seed": self.seed,
            "max_output_tokens": self.max_output_tokens,
            "scope": self.cache_scope,
            "call": self._call_number,
            "prompt": prompt,
            "text_format": text_format,
        }
        cache = self.cache_dir / _hash(identity) if self.cache_dir else None
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
            saved = cache / "response.json"
            if saved.exists():
                try:
                    value = json.loads(saved.read_bytes())
                    if value.get("identity_sha256") != _hash(identity) or value.get(
                        "body_sha256"
                    ) != _hash(value["body"]):
                        raise ValueError("hash differs")
                    return self._decode(value["body"], value.get("request_id"), value["latency_ms"])
                except (ValueError, KeyError, TypeError, LLMProviderError) as exc:
                    raise LLMCacheIntegrityError(
                        "API response cache hash mismatch or invalid envelope"
                    ) from exc
        modes = (
            ["json_schema", "json_object", "text"]
            if self.structured_output == "auto"
            else [self.structured_output]
        )
        for mode in modes:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": self.max_output_tokens,
                "stream": False,
            }
            if self.seed is not None:
                payload["seed"] = self.seed
            if mode == "json_schema":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": text_format.get("name", "generated_answer"),
                        "strict": True,
                        "schema": text_format.get("schema", text_format),
                    },
                }
            elif mode == "json_object":
                payload["response_format"] = {"type": "json_object"}
            for attempt in range(self.transport_retries + 1):
                event = cache / (uuid.uuid4().hex + ".json") if cache else None
                audit = {
                    "identity_sha256": _hash(identity),
                    "provider": self.provider_name,
                    "model_version": self.model_version,
                    "endpoint": self.endpoint,
                    "request": payload,
                    "status": "pending",
                    "attempt": attempt,
                    "requested_at_utc": datetime.now(UTC).isoformat(),
                    "format_mode": mode,
                }
                with self._budget_lock:
                    if (
                        self.max_api_requests is not None
                        and self._budget_state["used"] >= self.max_api_requests
                    ):
                        raise LLMRequestBudgetExceeded(
                            "API request budget exhausted; inspect cached attempts"
                        )
                    if event:
                        _atomic(event, audit)
                    self._budget_state["used"] += 1
                request = urllib.request.Request(
                    self.endpoint,
                    data=json.dumps(payload).encode(),
                    method="POST",
                    headers={
                        "Authorization": "Bearer " + self.api_key,
                        "Content-Type": "application/json",
                    },
                )
                started = time.perf_counter()
                status, body_text, request_id, retry_after = None, "", None, None
                try:
                    opener = urllib.request.build_opener(_NoRedirect())
                    with opener.open(request, timeout=self.timeout_seconds) as response:
                        status = response.status
                        request_id = response.headers.get("x-request-id")
                        body_text = response.read().decode("utf-8")
                except urllib.error.HTTPError as exc:
                    status = exc.code
                    request_id = exc.headers.get("x-request-id")
                    retry_after = exc.headers.get("Retry-After")
                    body_text = exc.read().decode("utf-8", errors="replace")
                except (OSError, TimeoutError) as exc:
                    audit["error"] = f"{type(exc).__name__}: {exc}".replace(
                        self.api_key, "[REDACTED]"
                    )
                elapsed = (time.perf_counter() - started) * 1000
                body_text = body_text.replace(self.api_key, "[REDACTED]")
                audit.update(
                    status=status,
                    response_text=body_text,
                    request_id=request_id,
                    latency_ms=elapsed,
                    retry_after=retry_after,
                )
                if event:
                    _atomic(event, audit)
                if status is not None and 200 <= status < 300:
                    try:
                        body = json.loads(body_text)
                    except (ValueError, TypeError) as exc:
                        raise LLMProviderError(
                            "API returned unreadable JSON; see cached response"
                        ) from exc
                    # The raw wire result is already durable in its audit event.
                    # Cache only decodable envelopes, so malformed ones can recover on resume.
                    decoded = self._decode(body, request_id, elapsed)
                    if cache:
                        _atomic(
                            cache / "response.json",
                            {
                                "identity_sha256": _hash(identity),
                                "body": body,
                                "body_sha256": _hash(body),
                                "request_id": request_id,
                                "latency_ms": elapsed,
                            },
                        )
                    return decoded
                unsupported = (
                    status in {400, 422}
                    and mode != "text"
                    and self.structured_output == "auto"
                    and any(
                        word in body_text.lower()
                        for word in ("response_format", "json_schema", "json_object")
                    )
                    and any(
                        word in body_text.lower()
                        for word in ("unsupported", "not support", "not available", "unknown")
                    )
                )
                if unsupported:
                    break
                if status is None or status in {429, 500, 502, 503, 504}:
                    if attempt < self.transport_retries:
                        time.sleep(self._delay(retry_after, attempt))
                        continue
                if status == 429:
                    raise LLMRetryLater(
                        "HTTP 429 retry budget exhausted; resume after the limit resets"
                    )
                if status is None:
                    raise LLMTimeoutError(
                        "API connection failed after bounded retries; see cached attempts"
                    )
                raise LLMProviderError(f"{self.provider_name} HTTP {status}; see cached response")
        raise LLMProviderError("no supported API output format")

    def _decode(self, body, request_id, latency_ms):
        try:
            choice = body["choices"][0]
            text = choice["message"].get("content")
            if not isinstance(text, str):
                if choice.get("finish_reason") == "length":
                    text = ""
                else:
                    raise ValueError("missing answer content")
            usage = body.get("usage") or {}
            inputs = int(usage.get("prompt_tokens") or 0)
            outputs = int(usage.get("completion_tokens") or 0)
            return LLMResponse(
                text=text,
                model=str(body.get("model") or self.model),
                usage=TokenUsage(
                    inputs, outputs, int(usage.get("total_tokens") or inputs + outputs)
                ),
                response_id=body.get("id"),
                request_id=request_id,
                latency_ms=latency_ms,
                done_reason=choice.get("finish_reason"),
                provider=self.provider_name,
                model_version=self.model_version,
                system_fingerprint=body.get("system_fingerprint"),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMProviderError(
                "API returned malformed completion; see cached response"
            ) from exc
