"""Gemini structured-output adapter owned by the evaluation pipeline."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cs30.generation.client import LLMResponse, TokenUsage
from cs30.generation.exceptions import (
    LLMEmptyResponseError,
    LLMProviderError,
    LLMTimeoutError,
)


@dataclass(frozen=True)
class GeminiJudgeResponse(LLMResponse):
    """Shared response plus Gemini thinking tokens and usage-metadata availability."""

    thought_tokens: int = 0
    usage_available: bool = True


class GeminiJudgeEmptyResponseError(LLMEmptyResponseError):
    """Reject empty content while retaining the returned Gemini response metadata."""

    def __init__(self, message: str, response: GeminiJudgeResponse) -> None:
        super().__init__(message)
        self.response = response


class GeminiJudgeClient:
    """Adapt the Google Gen AI SDK to the shared, provider-neutral LLM seam."""

    endpoint = "https://generativelanguage.googleapis.com"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        temperature: float | None = 1.0,
        timeout_seconds: float = 120.0,
        max_output_tokens: int = 8192,
        seed: int | None = None,
        thinking_level: str = "high",
        sdk_client: Any | None = None,
    ) -> None:
        self.model = model.strip()
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.seed = seed
        self.thinking_level = thinking_level.strip().casefold()
        if not self.model:
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.thinking_level not in {"minimal", "low", "medium", "high"}:
            raise ValueError("thinking_level must be minimal, low, medium, or high")

        if sdk_client is not None:
            self._client = sdk_client
            return

        resolved_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        ).strip()
        if not resolved_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required for Gemini")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Gemini support requires the topic-llm optional dependency: "
                "python -m pip install -e '.[topic-llm]'"
            ) from exc
        self._client = genai.Client(
            api_key=resolved_key,
            http_options=types.HttpOptions(
                timeout=round(timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=5,
                    http_status_codes=[408, 429, *range(500, 600)],
                ),
            ),
        )

    def complete(self, prompt: str, text_format: dict) -> GeminiJudgeResponse:
        """Request one schema-constrained JSON response and preserve provider metadata."""

        schema = text_format.get("schema", text_format)
        if not isinstance(schema, Mapping) or schema.get("type") != "object":
            raise ValueError("Gemini judge requires an object JSON schema")
        config: dict[str, object] = {
            "max_output_tokens": self.max_output_tokens,
            "response_mime_type": "application/json",
            "response_json_schema": dict(schema),
            "thinking_config": {"thinking_level": self.thinking_level},
        }
        if self.temperature is not None:
            config["temperature"] = self.temperature
        if self.seed is not None:
            config["seed"] = self.seed

        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            if self._is_timeout(exc):
                raise LLMTimeoutError(
                    f"Gemini API timed out after {self.timeout_seconds:g} seconds"
                ) from exc
            raise LLMProviderError(f"Gemini API request failed: {self._safe_error(exc)}") from exc

        done_reason = self._finish_reason(response)
        text = getattr(response, "text", None)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = self._integer_field(usage, "prompt_token_count")
        output_tokens = self._integer_field(usage, "candidates_token_count")
        thought_tokens = self._integer_field(usage, "thoughts_token_count")
        billed_output_tokens = output_tokens + thought_tokens
        total_tokens = self._integer_field(usage, "total_token_count")
        if total_tokens == 0:
            total_tokens = input_tokens + billed_output_tokens
        reported_model = getattr(response, "model_version", None)
        response_id = getattr(response, "response_id", None)
        result = GeminiJudgeResponse(
            text=text if isinstance(text, str) and text.strip() else "",
            model=str(reported_model or self.model),
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=billed_output_tokens,
                total_tokens=total_tokens,
            ),
            response_id=str(response_id) if response_id else None,
            latency_ms=(time.perf_counter() - started) * 1000,
            done_reason=done_reason,
            thought_tokens=thought_tokens,
            usage_available=usage is not None,
        )
        if not result.text.strip() and done_reason != "length":
            detail = self._blocked_detail(response)
            raise GeminiJudgeEmptyResponseError(
                "Gemini response contained no text" + (f": {detail}" if detail else ""),
                result,
            )
        return result

    @staticmethod
    def _integer_field(value: object, name: str) -> int:
        raw = getattr(value, name, None) if value is not None else None
        return int(raw or 0)

    @staticmethod
    def _finish_reason(response: object) -> str | None:
        candidates = getattr(response, "candidates", None) or []
        reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        if reason is None:
            return None
        value = getattr(reason, "value", reason)
        normalized = str(value).rsplit(".", 1)[-1].upper()
        if normalized in {"MAX_TOKENS", "LENGTH"}:
            return "length"
        return normalized.casefold()

    @staticmethod
    def _blocked_detail(response: object) -> str | None:
        feedback = getattr(response, "prompt_feedback", None)
        reason = getattr(feedback, "block_reason", None) if feedback is not None else None
        message = (
            getattr(feedback, "block_reason_message", None)
            if feedback is not None
            else None
        )
        values = [str(value) for value in (reason, message) if value]
        return ": ".join(values) or None

    @staticmethod
    def _is_timeout(error: Exception) -> bool:
        return isinstance(error, TimeoutError) or type(error).__name__ in {
            "ConnectTimeout",
            "ReadTimeout",
            "TimeoutException",
        }

    @staticmethod
    def _safe_error(error: Exception) -> str:
        message = str(error).replace("\n", " ")
        for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            secret = os.environ.get(variable)
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return message[:1000] or type(error).__name__
