"""Real correctness adapter/scorer flow with local SDK stand-ins only."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_open_answer_cli import inputs
from test_open_answer_scoring import JudgeClient, assessment, run, score

from cs30.evaluation.gemini_judge_client import GeminiJudgeClient
from cs30.evaluation.open_answer_cli import main
from cs30.evaluation.open_answer_models import JudgeAttempt, OpenAnswerScore
from cs30.evaluation.open_answer_scoring import OpenAnswerScorer


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("failure", ["empty", "blocked", "malformed", "transport"])
@pytest.mark.parametrize("recovers", [True, False])
def test_correctness_retains_every_attempt_through_retry(tmp_path, failure, recovers):
    log = tmp_path / "calls.jsonl"
    calls = []

    def generate_content(**kwargs):
        if calls:
            assert len(rows(log)) == len(calls)
        calls.append(kwargs)
        succeeds = recovers and len(calls) == 2
        if failure == "transport" and not succeeds:
            raise TimeoutError("Offline transport fixture")
        return SimpleNamespace(
            text=assessment().model_dump_json()
            if succeeds
            else "{"
            if failure == "malformed"
            else None,
            candidates=[
                SimpleNamespace(
                    finish_reason="SAFETY" if failure == "blocked" and not succeeds else "STOP"
                )
            ],
            usage_metadata=SimpleNamespace(
                prompt_token_count=31 if len(calls) == 1 else 17,
                candidates_token_count=3 if succeeds else 0,
                thoughts_token_count=2 if len(calls) == 1 else 4,
            ),
            model_version="judge-v1",
            response_id=f"response-{len(calls)}",
        )

    client = GeminiJudgeClient(
        "judge-v1",
        thinking_level="low",
        sdk_client=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)),
    )
    scorer = OpenAnswerScorer(client, attempt_log_path=log)
    result = score(scorer, [run(answer="slowing down")])[0]
    assert len(calls) == result.attempt_count == result.judge_calls_this_run == 2
    assert result.score == (2 if recovers else None)
    assert result.score_status == ("scored" if recovers else "judge_error")
    assert result.usage_complete is (failure != "transport")
    history = result.judge_attempts
    assert history[0].error and (history[1].error is None) is recovers
    assert len({item.attempt_id for item in history}) == 2
    assert sum(item.input_tokens or 0 for item in history) == (
        17 if failure == "transport" and recovers else 0 if failure == "transport" else 48
    )
    for record, attempt in zip(rows(log), history, strict=True):
        assert record["attempt_id"] == attempt.attempt_id
        assert record["usage_available"] == attempt.usage_available
        assert record["input_tokens"] == attempt.input_tokens
        assert record["output_tokens"] == attempt.output_tokens
        assert record["thought_tokens"] == attempt.thought_tokens
        assert "raw_output" not in record
    if failure == "transport":
        assert history[0].input_tokens is None and history[0].usage_available is False
    else:
        assert history[0].input_tokens == 31 and history[0].output_tokens == 2
        assert history[0].provider_response_id == "response-1"
    assert OpenAnswerScore.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("metadata_present", [True, False])
def test_correctness_distinguishes_measured_zero_from_missing_metadata(tmp_path, metadata_present):
    response = SimpleNamespace(
        text=assessment().model_dump_json(),
        model_version="judge-v1",
        response_id="zero",
        usage_metadata=SimpleNamespace(
            prompt_token_count=0, candidates_token_count=0, thoughts_token_count=0
        )
        if metadata_present
        else None,
    )
    client = GeminiJudgeClient(
        "judge-v1",
        sdk_client=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: response)),
    )
    record = score(OpenAnswerScorer(client), [run(answer="slowing down")])[0]
    assert record.score == 2 and record.attempt_count == 1
    assert record.usage_complete is metadata_present
    assert record.judge_attempts[0].input_tokens == (0 if metadata_present else None)


def test_correctness_cache_reuse_and_legacy_history_remain_honest(tmp_path):
    log = tmp_path / "calls.jsonl"
    cache = tmp_path / "cache"
    scorer = OpenAnswerScorer(
        JudgeClient(assessment()), cache_directory=cache, attempt_log_path=log
    )
    first = score(scorer, [run(answer="slowing down")])[0]
    again = score(scorer, [run(answer="slowing down")])[0]
    assert again.cache_hit and again.judge_calls_this_run == 0
    assert again.attempt_count == first.attempt_count == 1 and again.usage_complete
    assert len(rows(log)) == 1
    path = next(cache.glob("*.json"))
    legacy = json.loads(path.read_text(encoding="utf-8"))
    for attempt in legacy["attempts"]:
        for field in ("usage_available", "attempt_id", "provider_response_id"):
            attempt.pop(field)
    path.write_text(json.dumps(legacy), encoding="utf-8")
    old = score(scorer, [run(answer="slowing down")])[0]
    assert old.cache_hit and old.score == 2 and old.usage_complete is False
    assert old.judge_attempts[0].usage_available is None
    assert len(rows(log)) == 1


def test_correctness_log_write_failure_does_not_trigger_more_calls(tmp_path, monkeypatch):
    client = JudgeClient("bad json", assessment())
    scorer = OpenAnswerScorer(client, attempt_log_path=tmp_path / "calls")

    def fail_write(*_):
        raise OSError("fixture disk failure")

    monkeypatch.setattr("cs30.evaluation.open_answer_scoring._append_attempt", fail_write)
    with pytest.raises(OSError, match="disk failure"):
        score(scorer, [run(answer="slowing down")])
    assert len(client.prompts) == 1


def test_correctness_cli_persists_ledger_beside_immutable_report(tmp_path, monkeypatch):
    args, output = inputs(tmp_path, answer="slowing down")
    monkeypatch.setattr(
        "cs30.evaluation.open_answer_cli.GeminiJudgeClient",
        lambda *_a, **_k: JudgeClient(assessment()),
    )
    assert (
        main(args + ["--provider", "gemini", "--model", "judge-v1", "--thinking-level", "low"]) == 0
    )
    log = output.with_name(output.name + ".attempts.jsonl")
    assert len(rows(log)) == 1
    result = rows(output / "open_answer_scores.jsonl")[0]
    assert result["attempt_count"] == 1 and result["usage_complete"] is True
    assert rows(log)[0]["attempt_id"] == result["judge_attempts"][0]["attempt_id"]
    assert len(list(output.iterdir())) == 6


@pytest.mark.parametrize("destination", ["input", "report", "directory"])
def test_correctness_cli_bad_log_path_prevents_generation(tmp_path, monkeypatch, destination):
    args, output = inputs(tmp_path, answer="slowing down")
    client = JudgeClient(assessment())
    monkeypatch.setattr(
        "cs30.evaluation.open_answer_cli.GeminiJudgeClient", lambda *_a, **_k: client
    )
    target = (
        tmp_path / "gold.jsonl"
        if destination == "input"
        else output / "calls"
        if destination == "report"
        else tmp_path
    )
    assert (
        main(args + ["--provider", "gemini", "--model", "judge-v1", "--attempt-log", str(target)])
        == 2
    )
    assert not client.prompts and not output.exists()


def test_usage_metadata_does_not_change_rule_based_scores():
    record = score()[0]
    assert record.score == 2 and record.scoring_source == "rule"
    assert record.attempt_count == 0 and record.usage_complete is True


@pytest.mark.parametrize(
    "payload",
    [
        dict(usage_available=False, input_tokens=0),
        dict(usage_available=True, input_tokens=2),
    ],
)
def test_inconsistent_correctness_usage_is_rejected(payload):
    with pytest.raises(ValidationError):
        JudgeAttempt(raw_output=None, error="fixture", **payload)
