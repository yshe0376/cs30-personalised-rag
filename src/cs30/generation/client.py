"""Minimal LLM clients for real Responses API calls and offline smoke tests."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .exceptions import LLMEmptyResponseError, LLMProviderError, LLMTimeoutError


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    usage: TokenUsage
    response_id: str | None
    latency_ms: float
    done_reason: str | None = None
    request_id: str | None = None
    provider: str | None = None
    model_version: str | None = None
    system_fingerprint: str | None = None


class LLMClient(Protocol):
    model: str
    temperature: float | None

    def complete(self, prompt: str, text_format: dict) -> LLMResponse: ...


class OpenAIResponsesClient:
    """Call the OpenAI Responses API without adding a new runtime dependency."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        temperature: float | None = 0.0,
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 800,
    ) -> None:
        self.model = model.strip()
        self.api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        if not self.model:
            raise ValueError("model must not be empty")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        payload = {
            "model": self.model,
            "input": prompt,
            "text": {"format": text_format},
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_id = response.headers.get("x-request-id")
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise LLMProviderError(f"OpenAI API returned HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            raise LLMTimeoutError(
                f"OpenAI API timed out after {self.timeout_seconds:g} seconds"
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise LLMTimeoutError(
                    f"OpenAI API timed out after {self.timeout_seconds:g} seconds"
                ) from exc
            raise LLMProviderError(f"OpenAI API request failed: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMProviderError("OpenAI API returned an unreadable response") from exc

        text = self._extract_output_text(body)
        usage_payload = body.get("usage") or {}
        input_tokens = int(usage_payload.get("input_tokens", 0) or 0)
        output_tokens = int(usage_payload.get("output_tokens", 0) or 0)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=int(usage_payload.get("total_tokens") or input_tokens + output_tokens),
        )
        return LLMResponse(
            text=text,
            model=str(body.get("model") or self.model),
            usage=usage,
            response_id=response_id or body.get("id"),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _extract_output_text(body: dict) -> str:
        direct = body.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        for item in body.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content["text"])
        raise LLMEmptyResponseError("OpenAI response contained no output_text")


class OllamaChatClient:
    """Call a model running locally through Ollama's native chat API."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        temperature: float | None = 0.0,
        timeout_seconds: float = 120.0,
        max_output_tokens: int = 800,
        context_window: int | None = None,
        seed: int = 0,
    ) -> None:
        self.model = model.strip()
        resolved_base_url = (
            base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        )
        self.endpoint = f"{resolved_base_url.rstrip('/')}/api/chat"
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.seed = seed
        self.context_window = context_window
        self.model_digest: str | None = None
        if not self.model:
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if context_window is not None and context_window <= max_output_tokens:
            raise ValueError("context_window must exceed max_output_tokens")

    def pin_model(self) -> None:
        """Record the installed weights identity before starting/resuming a batch."""
        url = self.endpoint.removesuffix("/api/chat") + "/api/tags"
        with urllib.request.urlopen(url, timeout=min(self.timeout_seconds, 15)) as response:
            payload = json.load(response)
        names = {self.model, self.model + ":latest"}
        matches = [m for m in payload.get("models", []) if m.get("name") in names]
        if len(matches) != 1 or not matches[0].get("digest"):
            raise ValueError("requested Ollama model has no unique installed weights identity")
        self.model_digest = matches[0]["digest"]

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        schema = text_format.get("schema", text_format)
        options: dict[str, float | int] = {"num_predict": self.max_output_tokens, "seed": self.seed}
        if self.context_window is not None:
            # UTF-8 bytes bound byte-level token counts conservatively. Reserve
            # room for the response and chat framing; refuse rather than truncate.
            if len(prompt.encode("utf-8")) + self.max_output_tokens + 512 > self.context_window:
                raise LLMProviderError("prompt exceeds the explicitly pinned context budget")
            options["num_ctx"] = self.context_window
        if self.temperature is not None:
            options["temperature"] = self.temperature
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            "options": options,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise LLMProviderError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            raise LLMTimeoutError(
                f"Ollama timed out after {self.timeout_seconds:g} seconds"
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise LLMTimeoutError(
                    f"Ollama timed out after {self.timeout_seconds:g} seconds"
                ) from exc
            raise LLMProviderError(
                f"Ollama request failed at {self.endpoint}: {exc.reason}. "
                "Check that Ollama is installed and running."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Ollama returned an unreadable response") from exc

        message = body.get("message") or {}
        text = message.get("content")
        if (not isinstance(text, str) or not text.strip()) and body.get("done_reason") != "length":
            error = LLMEmptyResponseError("Ollama response contained no message content")
            error.done_reason = body.get("done_reason")
            raise error
        input_tokens = int(body.get("prompt_eval_count", 0) or 0)
        output_tokens = int(body.get("eval_count", 0) or 0)
        return LLMResponse(
            text=text if isinstance(text, str) else "",
            model=str(body.get("model") or self.model),
            done_reason=body.get("done_reason"),
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            response_id=None,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


class MockJsonLLMClient:
    """Deterministic JSON-producing stand-in for development and CI."""

    model = "mock-json-generator"
    temperature = 0.0
    _citation_pattern = re.compile(r"ALLOWED_CITATION_IDS:\s*(\[[^\n]+\])")
    _level_pattern = re.compile(r"STUDENT_LEVEL:\s*(beginner|intermediate|advanced)")

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        del text_format
        started = time.perf_counter()
        citation_match = self._citation_pattern.search(prompt)
        citations = json.loads(citation_match.group(1)) if citation_match else []
        if not citations:
            raise LLMEmptyResponseError("mock prompt did not contain citation ids")
        level_match = self._level_pattern.search(prompt)
        level = level_match.group(1) if level_match else "intermediate"
        is_multiple_choice = "\nA." in prompt
        if is_multiple_choice:
            explanations = {
                "beginner": "In simple terms, the first retrieved passage supports option A.",
                "intermediate": (
                    "The governing physics principle in the first retrieved passage "
                    "supports option A."
                ),
                "advanced": (
                    "Under the assumptions stated in the first retrieved passage, "
                    "option A follows from the governing relation."
                ),
            }
        else:
            explanations = {
                "beginner": "In simple terms, the first retrieved passage answers the question.",
                "intermediate": (
                    "The governing physics principle is stated in the first retrieved passage."
                ),
                "advanced": (
                    "Under the stated assumptions, the first retrieved passage gives the "
                    "governing relation."
                ),
            }
        output = json.dumps(
            {
                "final_choice": "A" if is_multiple_choice else None,
                "explanation": explanations[level],
                "citations": [citations[0]],
            }
        )
        input_tokens = max(1, len(prompt) // 4)
        output_tokens = max(1, len(output) // 4)
        return LLMResponse(
            text=output,
            model=self.model,
            usage=TokenUsage(input_tokens, output_tokens, input_tokens + output_tokens),
            response_id="mock-response",
            latency_ms=(time.perf_counter() - started) * 1000,
        )
