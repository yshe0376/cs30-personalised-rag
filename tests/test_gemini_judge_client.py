"""Gemini adapter tests without paid or network calls."""

from types import SimpleNamespace

import pytest

from cs30.evaluation.gemini_judge_client import GeminiJudgeClient
from cs30.generation.exceptions import (
    LLMEmptyResponseError,
    LLMProviderError,
    LLMTimeoutError,
)


class RecordingModels:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def sdk(models: RecordingModels) -> SimpleNamespace:
    return SimpleNamespace(models=models)


def response(
    *,
    text: str | None = '{"decision":"pass"}',
    finish_reason: str = "STOP",
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value=finish_reason))],
        usage_metadata=SimpleNamespace(
            prompt_token_count=31,
            candidates_token_count=7,
            thoughts_token_count=2,
            total_token_count=40,
        ),
        model_version="gemini-3.1-flash-lite",
        response_id="gemini-response-1",
        prompt_feedback=None,
    )


def test_complete_uses_gemini_json_schema_and_preserves_metadata() -> None:
    models = RecordingModels(response())
    client = GeminiJudgeClient(
        "gemini-3.1-flash-lite",
        temperature=0.0,
        timeout_seconds=90,
        max_output_tokens=512,
        seed=5703,
        thinking_level="high",
        sdk_client=sdk(models),
    )
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string"}},
        "required": ["decision"],
        "additionalProperties": False,
    }

    result = client.complete(
        "Judge this answer.",
        {"type": "json_schema", "name": "judge", "strict": True, "schema": schema},
    )

    assert models.calls == [
        {
            "model": "gemini-3.1-flash-lite",
            "contents": "Judge this answer.",
            "config": {
                "temperature": 0.0,
                "max_output_tokens": 512,
                "seed": 5703,
                "thinking_config": {"thinking_level": "high"},
                "response_mime_type": "application/json",
                "response_json_schema": schema,
            },
        }
    ]
    assert result.text == '{"decision":"pass"}'
    assert result.model == "gemini-3.1-flash-lite"
    assert result.response_id == "gemini-response-1"
    assert result.done_reason == "stop"
    assert result.usage.input_tokens == 31
    assert result.usage.output_tokens == 9
    assert result.usage.total_tokens == 40
    assert result.thought_tokens == 2


def test_max_tokens_is_exposed_as_shared_truncation_reason() -> None:
    client = GeminiJudgeClient(
        "gemini-test",
        sdk_client=sdk(RecordingModels(response(text=None, finish_reason="MAX_TOKENS"))),
    )

    result = client.complete("prompt", {"type": "object", "properties": {}})

    assert result.text == ""
    assert result.done_reason == "length"


def test_empty_or_blocked_response_fails_closed() -> None:
    blocked = response(text=None, finish_reason="SAFETY")
    blocked.prompt_feedback = SimpleNamespace(
        block_reason="SAFETY",
        block_reason_message="prompt was blocked",
    )
    client = GeminiJudgeClient("gemini-test", sdk_client=sdk(RecordingModels(blocked)))

    with pytest.raises(LLMEmptyResponseError, match="prompt was blocked"):
        client.complete("prompt", {"type": "object", "properties": {}})


def test_sdk_timeout_and_provider_errors_use_shared_error_categories() -> None:
    class ReadTimeout(Exception):
        pass

    timeout_client = GeminiJudgeClient(
        "gemini-test",
        sdk_client=sdk(RecordingModels(error=ReadTimeout("late"))),
    )
    with pytest.raises(LLMTimeoutError, match="timed out"):
        timeout_client.complete("prompt", {"type": "object", "properties": {}})

    failed_client = GeminiJudgeClient(
        "gemini-test",
        sdk_client=sdk(RecordingModels(error=RuntimeError("service unavailable"))),
    )
    with pytest.raises(LLMProviderError, match="service unavailable"):
        failed_client.complete("prompt", {"type": "object", "properties": {}})


def test_constructor_and_schema_validation_fail_before_network(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiJudgeClient("gemini-test")

    models = RecordingModels(response())
    client = GeminiJudgeClient("gemini-test", sdk_client=sdk(models))
    with pytest.raises(ValueError, match="object JSON schema"):
        client.complete("prompt", {"type": "json_schema", "schema": {"type": "array"}})
    assert models.calls == []


def test_constructor_configures_sdk_retry_policy(monkeypatch) -> None:
    from google import genai

    captured = {}

    def client_factory(**kwargs):
        captured.update(kwargs)
        return sdk(RecordingModels(response()))

    monkeypatch.setattr(genai, "Client", client_factory)
    GeminiJudgeClient("gemini-test", api_key="not-a-real-key")

    options = captured["http_options"]
    assert options.timeout == 120000
    assert options.retry_options.attempts == 5
    assert {408, 429, 500, 599} <= set(options.retry_options.http_status_codes)


def test_defaults_follow_frozen_gemini_judge_policy() -> None:
    client = GeminiJudgeClient("gemini-test", sdk_client=sdk(RecordingModels(response())))

    assert client.temperature == 1.0
    assert client.max_output_tokens == 8192
    assert client.thinking_level == "high"
