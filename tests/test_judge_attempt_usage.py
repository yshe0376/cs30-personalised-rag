"""Offline provider stand-ins: these tests never construct a paid API client."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from cs30.evaluation.evidence_support import build_evidence_support_request
from cs30.evaluation.gemini_judge_client import GeminiJudgeClient
from cs30.evaluation.judge_runtime import (
    CachedJudgeRunner,
    JudgeProviderResponse,
    StructuredJsonJudgeProvider,
    make_judge_request,
    validate_output_against_request,
)
from cs30.evaluation.v2_generation_cli import main
from cs30.evaluation.v2_generation_models import (
    EvaluationMode,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeTask,
)
from cs30.generation.client import LLMResponse, TokenUsage


def configuration():
    return JudgeConfiguration(
        config_version="usage-test",
        provider="local",
        model_family="independent",
        model_revision="test",
        temperature=0,
        prompt_version="1",
        output_schema_version="1.0",
        local_model=True,
        data_approval="not_required",
    )


def request_and_output():
    request = make_judge_request(
        task=JudgeTask.DISCRIMINATION,
        payload={"answer": "A sample answer."},
        system_instruction="Offline fixture",
        configuration=configuration(),
        generation_model_family="gpt-oss",
        mode=EvaluationMode.DEVELOPMENT,
    )
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "predicted_level": "uncertain",
        "exact_quote": None,
        "reason": "Fixture.",
    }
    return request, raw


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("recovers", [True, False])
def test_every_validation_attempt_retains_usage_and_request_totals(tmp_path, recovers):
    request, valid = request_and_output()
    log = tmp_path / "calls.jsonl"
    prompts = []

    def provider(attempt_request, _config):
        # The previous rejected attempt must already be on disk before retrying.
        if prompts:
            assert len(read_log(log)) == len(prompts)
        prompts.append(attempt_request.system_instruction)
        output = dict(valid)
        if len(prompts) == 1 or not recovers:
            output["request_id"] = "wrong-request"
        return JudgeProviderResponse(
            output=output,
            response_id=f"response-{len(prompts)}",
            completed_at_utc="2026-10-28T00:00:00+00:00",
            reported_model="independent",
            input_tokens=100 if len(prompts) == 1 else 80,
            output_tokens=30 if len(prompts) == 1 else 20,
            thought_tokens=10 if len(prompts) == 1 else 5,
        )

    cache = tmp_path / "cache.jsonl"
    runner = CachedJudgeRunner(cache, judge_execution_id="usage-test", attempt_log_path=log)
    validate = lambda raw: validate_output_against_request(raw, request)  # noqa: E731
    result = runner.run(request, configuration(), provider, validate)
    assert len(prompts) == 2 and "REPAIR_REQUEST" in prompts[1]
    assert result.unresolved is (not recovers)
    assert result.attempt_count == 2 and result.usage_complete is True
    assert (result.input_tokens, result.output_tokens, result.thought_tokens) == (180, 50, 15)
    assert result.provider_response_id == "response-2"
    records = read_log(log)
    assert [row["status"] for row in records] == [
        "invalid_output",
        "accepted" if recovers else "invalid_output",
    ]
    assert [row["input_tokens"] for row in records] == [100, 80]
    assert all(
        row["usage_available"] and row["request_id"] == request.request_id for row in records
    )
    assert len({row["attempt_id"] for row in records}) == 2
    assert sum(row["thought_tokens"] for row in records) == result.thought_tokens
    if recovers:
        assert cache.exists()
        assert runner.run(request, configuration(), provider, validate) == result
        resumed = CachedJudgeRunner(cache, judge_execution_id="resume", attempt_log_path=log)
        assert resumed.run(request, configuration(), provider, validate).cache_hit
        assert len(read_log(log)) == len(prompts) == 2
    else:
        assert not cache.exists() and result.output is None
        assert result.raw_output["request_id"] == "wrong-request"


@pytest.mark.parametrize(
    ("text", "reason"), [("invalid JSON", "stop"), ("[]", "stop"), ("{}", "length")]
)
def test_returned_usage_survives_decode_and_truncation_failures(tmp_path, text, reason):
    request, _ = request_and_output()
    calls = []

    class FakeClient:
        def complete(self, prompt, text_format):
            calls.append(prompt)
            return LLMResponse(
                text=text,
                model="independent",
                done_reason=reason,
                usage=TokenUsage(input_tokens=7, output_tokens=4, total_tokens=11),
                response_id="bad-output",
                latency_ms=0,
            )

    cache = tmp_path / "cache.jsonl"
    runner = CachedJudgeRunner(cache, judge_execution_id="decode-test")
    result = runner.run(
        request,
        configuration(),
        StructuredJsonJudgeProvider(FakeClient()),
        lambda raw: validate_output_against_request(raw, request),
    )
    assert len(calls) == 2 and result.unresolved
    assert result.input_tokens == 14 and result.output_tokens == 8
    assert all(
        row["status"] == "invalid_output" and row["usage_available"]
        for row in read_log(runner.attempt_log_path)
    )


@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("recovers", [False, True])
def test_gemini_empty_response_usage_survives_retries(tmp_path, blocked, recovers):
    request, valid = request_and_output()
    calls = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        succeeds = recovers and len(calls) == 2
        return SimpleNamespace(
            text=json.dumps(valid) if succeeds else None,
            candidates=[
                SimpleNamespace(finish_reason="STOP" if succeeds or not blocked else "SAFETY")
            ],
            prompt_feedback=(
                SimpleNamespace(block_reason="SAFETY", block_reason_message="Fixture block")
                if blocked and not succeeds
                else None
            ),
            usage_metadata=SimpleNamespace(
                prompt_token_count=31 if len(calls) == 1 else 17,
                candidates_token_count=3 if succeeds else 0,
                thoughts_token_count=2 if len(calls) == 1 else 4,
            ),
            model_version="independent",
            response_id=f"gemini-{len(calls)}",
        )

    client = GeminiJudgeClient(
        "independent",
        sdk_client=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)),
    )
    cache = tmp_path / "cache.jsonl"
    runner = CachedJudgeRunner(cache, judge_execution_id="empty-response-test")
    result = runner.run(
        request,
        configuration(),
        StructuredJsonJudgeProvider(client),
        lambda raw: validate_output_against_request(raw, request),
    )

    records = read_log(runner.attempt_log_path)
    assert len(calls) == 2
    assert result.unresolved is (not recovers)
    assert (result.output is not None) is recovers
    assert cache.exists() is recovers
    assert [row["status"] for row in records] == [
        "invalid_output",
        "accepted" if recovers else "invalid_output",
    ]
    assert "contained no text" in records[0]["error"]
    if blocked:
        assert "Fixture block" in records[0]["error"]
    assert all(row["usage_available"] for row in records)
    assert [row["input_tokens"] for row in records] == [31, 17]
    assert [row["output_tokens"] for row in records] == [2, 7 if recovers else 4]
    assert [row["thought_tokens"] for row in records] == [2, 4]
    assert [row["provider_response_id"] for row in records] == ["gemini-1", "gemini-2"]
    assert (result.input_tokens, result.output_tokens, result.thought_tokens) == (
        48,
        9 if recovers else 6,
        6,
    )
    assert result.provider_response_id == "gemini-2"


@pytest.mark.parametrize("content", ["valid", "empty", "malformed", "truncated"])
def test_gemini_response_without_usage_metadata_remains_unknown(tmp_path, content):
    request, valid = request_and_output()
    response = SimpleNamespace(
        text={"valid": json.dumps(valid), "empty": None, "malformed": "[", "truncated": ""}[
            content
        ],
        candidates=[
            SimpleNamespace(finish_reason="MAX_TOKENS" if content == "truncated" else "STOP")
        ],
        model_version="independent",
        response_id="no-usage",
    )
    client = GeminiJudgeClient(
        "independent",
        sdk_client=SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **_kwargs: response)
        ),
    )
    runner = CachedJudgeRunner(tmp_path / "cache.jsonl", judge_execution_id="missing-usage")
    result = runner.run(
        request,
        configuration(),
        StructuredJsonJudgeProvider(client),
        lambda raw: validate_output_against_request(raw, request),
    )
    records = read_log(runner.attempt_log_path)
    assert result.unresolved is (content != "valid")
    assert len(records) == (1 if content == "valid" else 2)
    assert all(not row["usage_available"] for row in records)
    assert all(
        row[field] is None
        for row in records
        for field in ("input_tokens", "output_tokens", "thought_tokens")
    )
    assert (result.input_tokens, result.output_tokens, result.thought_tokens) == (0, 0, 0)


def test_provider_error_has_unknown_usage_not_a_false_zero_measurement(tmp_path):
    request, valid = request_and_output()
    calls = []

    def provider(*_args):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("No response metadata")
        return JudgeProviderResponse(
            valid, "response", "2026-10-28T00:00:00+00:00", input_tokens=9, output_tokens=3
        )

    runner = CachedJudgeRunner(tmp_path / "cache.jsonl", judge_execution_id="unknown-test")
    result = runner.run(
        request,
        configuration(),
        provider,
        lambda raw: validate_output_against_request(raw, request),
    )
    records = read_log(runner.attempt_log_path)
    assert records[0]["status"] == "provider_error"
    assert records[0]["input_tokens"] is None and not records[0]["usage_available"]
    assert result.input_tokens == 9 and not result.unresolved
    assert result.attempt_count == 2 and result.usage_complete is False


def test_legacy_envelope_cache_does_not_invent_accounting_metadata(tmp_path):
    request, valid = request_and_output()
    cache = tmp_path / "cache.jsonl"
    runner = CachedJudgeRunner(cache, judge_execution_id="original")
    original = runner.run(
        request,
        configuration(),
        lambda *_: JudgeProviderResponse(valid, "r1", "2026-10-28T00:00:00+00:00"),
        lambda raw: validate_output_against_request(raw, request),
    )
    assert original.attempt_count == 1 and original.usage_complete is True
    saved = read_log(cache)[0]
    saved.pop("attempt_count")
    saved.pop("usage_complete")
    cache.write_text(json.dumps(saved) + "\n", encoding="utf-8")
    resumed = CachedJudgeRunner(cache, judge_execution_id="resume")

    def unexpected(*_):
        raise AssertionError("cached output must not call the provider")

    result = resumed.run(request, configuration(), unexpected, lambda raw: raw)
    assert result.cache_hit and result.attempt_count is None and result.usage_complete is None
    assert len(read_log(runner.attempt_log_path)) == 1


def test_log_write_failure_stops_before_another_provider_attempt(tmp_path, monkeypatch):
    import cs30.evaluation.judge_runtime as module

    request, _ = request_and_output()
    calls = []

    def provider(*_args):
        calls.append(1)
        return JudgeProviderResponse({}, "response", "2026-10-28T00:00:00+00:00", input_tokens=4)

    def fail_write(*_args):
        raise OSError("ledger disk failure")

    runner = CachedJudgeRunner(tmp_path / "cache.jsonl", judge_execution_id="disk-test")
    monkeypatch.setattr(module, "_append_attempt", fail_write)
    with pytest.raises(OSError, match="ledger disk failure"):
        runner.run(
            request,
            configuration(),
            provider,
            lambda raw: validate_output_against_request(raw, request),
        )
    assert len(calls) == 1


def test_log_path_is_checked_before_any_provider_can_run(tmp_path):
    with pytest.raises(ValueError, match="separate"):
        CachedJudgeRunner(
            tmp_path / "cache", judge_execution_id="paths", attempt_log_path=tmp_path / "cache"
        )
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    with pytest.raises(OSError):
        CachedJudgeRunner(
            tmp_path / "cache", judge_execution_id="paths", attempt_log_path=directory
        )


def evidence_request():
    item = GenerationEvaluationInput(
        evaluation_id="e",
        run_id="r",
        question_id="q",
        question="Question?",
        answer="A sample answer.",
        target_level="beginner",
        condition="P0R0_plain",
        lambda_weight=0.1,
        generation_model_family="gpt-oss",
        generation_model_revision="fixture",
        eligibility="full",
        source_artifact_sha256="a" * 64,
    )
    return build_evidence_support_request(item, configuration())


def test_evidence_prompt_hash_changes_and_requires_quoted_support_ids():
    import cs30.evaluation.evidence_support as module

    request = evidence_request()
    assert "only IDs for which you provide quotations" in request.system_instruction
    assert (
        "at least one evidence_quotes row for every listed supporting ID"
        in request.system_instruction
    )
    assert "citation_ids" in request.system_instruction
    # The real builder hashes system instructions; no old-prompt cache can match.
    old = make_judge_request(
        task=request.task,
        payload=request.payload,
        system_instruction="Old prompt",
        configuration=configuration(),
        generation_model_family="gpt-oss",
        mode=EvaluationMode.DEVELOPMENT,
    )
    assert old.request_id != request.request_id
    assert module.EVIDENCE_SUPPORT_SYSTEM_INSTRUCTION.strip() == request.system_instruction


def test_single_evidence_attempt_is_rejected_before_client_construction(tmp_path, monkeypatch):
    import cs30.evaluation.v2_generation_cli as module

    request = evidence_request()
    config = configuration().model_copy(update={"provider": "gemini"})
    requests = tmp_path / "requests.jsonl"
    requests.write_text(request.model_dump_json() + "\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")

    def forbidden(*_args, **_kwargs):
        pytest.fail("Minimum retries must be checked before constructing a client")

    monkeypatch.setattr(module, "GeminiJudgeClient", forbidden)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "run-judge-requests",
                "--requests",
                str(requests),
                "--judge-config",
                str(config_path),
                "--cache",
                str(tmp_path / "cache"),
                "--output",
                str(tmp_path / "result"),
                "--judge-execution-id",
                "single-test",
                "--max-attempts",
                "1",
            ]
        )
    assert exc.value.code == 2
    runner = CachedJudgeRunner(tmp_path / "cache", judge_execution_id="single-test", max_attempts=1)
    with pytest.raises(ValueError, match="at least two"):
        runner.run(request, configuration(), forbidden, forbidden)


def test_cli_writes_default_attempt_log_without_network(tmp_path, monkeypatch):
    import cs30.evaluation.v2_generation_cli as module

    request, valid = request_and_output()
    # A local stand-in is injected at the existing OpenAI adapter seam, not an API call.
    config = configuration().model_copy(update={"provider": "openai"})
    request = make_judge_request(
        task=request.task,
        payload=request.payload,
        system_instruction=request.system_instruction,
        configuration=config,
        generation_model_family="gpt-oss",
        mode=EvaluationMode.DEVELOPMENT,
    )
    valid["request_id"] = request.request_id

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def complete(self, *_args):
            return LLMResponse(
                text=json.dumps(valid),
                model="independent",
                usage=TokenUsage(input_tokens=10, output_tokens=4, total_tokens=14),
                response_id="fixture",
                latency_ms=0,
            )

    monkeypatch.setattr(module, "OpenAIResponsesClient", FakeClient)
    requests = tmp_path / "requests.jsonl"
    requests.write_text(request.model_dump_json() + "\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    assert (
        main(
            [
                "run-judge-requests",
                "--requests",
                str(requests),
                "--judge-config",
                str(config_path),
                "--cache",
                str(tmp_path / "cache.jsonl"),
                "--output",
                str(tmp_path / "results.jsonl"),
                "--judge-execution-id",
                "cli-test",
            ]
        )
        == 0
    )
    ledger = read_log(tmp_path / "results.attempts.jsonl")
    assert len(ledger) == 1 and ledger[0]["input_tokens"] == 10
