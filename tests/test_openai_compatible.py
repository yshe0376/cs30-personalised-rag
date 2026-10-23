"""Wire-level provider, concurrency, paid-call budgets and crash recovery."""

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_v2_experiment import Client, prepare

from cs30.generation.compatible import OpenAICompatibleClient
from cs30.generation.exceptions import (
    LLMOutputValidationError,
    LLMProviderError,
    LLMRequestBudgetExceeded,
)
from cs30.generation.schema import openai_text_format, parse_answer_payload
from cs30.v2.experiment import run_experiment
from cs30.v2.experiment_cli import main

SECRET = "unit-test-secret-never-persist"
ANSWER = {"final_choice": None, "explanation": "Force and motion.", "citations": ["E1"]}


@contextmanager
def server(replies=(), *, delay=0, barrier_size=0):
    state = {"requests": [], "active": 0, "peak": 0}
    lock = threading.Lock()
    barrier = threading.Barrier(barrier_size) if barrier_size else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                number = len(state["requests"])
                state["requests"].append((self.path, payload, self.headers["Authorization"]))
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            if barrier is not None and number < barrier_size:
                barrier.wait(timeout=5)
            if delay:
                time.sleep(delay)
            status, body, headers = (
                replies[number]
                if number < len(replies)
                else (
                    200,
                    {
                        "id": "completion-1",
                        "model": "resolved-model-v1",
                        "system_fingerprint": "fp1",
                        "choices": [
                            {"message": {"content": json.dumps(ANSWER)}, "finish_reason": "stop"}
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    },
                    {"x-request-id": f"wire-{number}"},
                )
            )
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())
            with lock:
                state["active"] -= 1

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/v1", state
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()


def client(url, monkeypatch, **kwargs):
    monkeypatch.setenv("M7_TEST_API_KEY", SECRET)
    return OpenAICompatibleClient(
        Client.model,
        base_url=url,
        provider_name="fake-host",
        model_version="pinned-v1",
        api_key_env="M7_TEST_API_KEY",
        **kwargs,
    )


def test_wire_payload_metadata_and_cache_replay(tmp_path, monkeypatch):
    with server() as (url, state):
        first = client(url, monkeypatch, seed=7).for_cell("cell1", tmp_path)
        response = first.complete("JSON question", openai_text_format())
        path, payload, auth = state["requests"][0]
        assert path == "/v1/chat/completions" and auth == "Bearer " + SECRET
        assert payload["temperature"] == 0 and payload["seed"] == 7
        assert payload["response_format"]["json_schema"]["schema"]["required"]
        assert response.provider == "fake-host" and response.model_version == "pinned-v1"
        assert response.model == "resolved-model-v1" and response.request_id == "wire-0"
        assert response.response_id == "completion-1" and response.system_fingerprint == "fp1"
        assert response.usage.total_tokens == 15
        replay = client(url, monkeypatch, seed=7).for_cell("cell1", tmp_path)
        assert replay.complete("JSON question", openai_text_format()) == response
        assert len(state["requests"]) == 1
        # Identical prompts in distinct cells must be independent draws.
        client(url, monkeypatch).for_cell("cell2", tmp_path).complete("JSON question", {})
        assert len(state["requests"]) == 2
    assert all(SECRET not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_429_and_503_backoff_are_cached(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr("cs30.generation.compatible.time.sleep", waits.append)
    replies = [
        (429, {"error": "rate limit"}, {"Retry-After": "2"}),
        (503, {"error": "temporary outage"}, {}),
    ]
    with server(replies) as (url, state):
        result = client(url, monkeypatch).for_cell("cell", tmp_path).complete("question", {})
        assert result.text and len(state["requests"]) == 3 and waits == [2, 2]
    events = [
        json.loads(p.read_bytes()) for p in tmp_path.rglob("*.json") if p.name != "response.json"
    ]
    assert {e["status"] for e in events} == {429, 503, 200}


def test_explicit_format_unsupported_falls_back_but_auth_does_not(tmp_path, monkeypatch):
    replies = [
        (400, {"error": "response_format json_schema is unsupported"}, {}),
        (422, {"error": "json_object not supported"}, {}),
    ]
    with server(replies) as (url, state):
        client(url, monkeypatch).for_cell("cell", tmp_path).complete("question", {})
        formats = [p.get("response_format", {}).get("type") for _, p, _ in state["requests"]]
        assert formats == ["json_schema", "json_object", None]
    with server([(401, {"error": "invalid key " + SECRET}, {})]) as (url, state):
        with pytest.raises(LLMProviderError, match="HTTP 401"):
            client(url, monkeypatch).for_cell("auth", tmp_path).complete("question", {})
        assert len(state["requests"]) == 1
    assert all(SECRET not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_retry_after_above_wait_budget_does_not_retry_early(monkeypatch):
    with server([(429, {}, {"Retry-After": "3600"})]) as (url, state):
        with pytest.raises(LLMProviderError, match="bounded wait budget"):
            client(url, monkeypatch).complete("q", {})
        assert len(state["requests"]) == 1


def test_fenced_json_fallback_keeps_schema_and_citation_validation():
    raw = "```json\n" + json.dumps(ANSWER) + "\n```"
    assert parse_answer_payload(raw, allow_json_fence=True).citations == ["E1"]
    with pytest.raises(LLMOutputValidationError):
        parse_answer_payload("prose " + raw, allow_json_fence=True)


def test_crash_after_response_before_checkpoint_reuses_paid_response(tmp_path, monkeypatch):
    from cs30.v2 import experiment

    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    save = experiment.save_cell
    with server() as (url, state):

        def crash(*args):
            raise KeyboardInterrupt("response committed, checkpoint not yet committed")

        monkeypatch.setattr(experiment, "save_cell", crash)
        with pytest.raises(KeyboardInterrupt):
            run_experiment(prepared, output, client(url, monkeypatch), provider="openai-compatible")
        assert len(state["requests"]) == 1
        monkeypatch.setattr(experiment, "save_cell", save)
        runs = run_experiment(
            prepared, output, client(url, monkeypatch), provider="openai-compatible", resume=True
        )
        assert len(state["requests"]) == 12 and all(r.status == "answered" for r in runs)
        details = json.loads((output / "generation_records.jsonl").read_text().splitlines()[0])
        assert details["generation_trace"]["attempts"][0]["request_id"] == "wire-0"


def test_concurrency_checkpoints_and_resume_do_not_duplicate_calls(tmp_path, monkeypatch):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    with server(barrier_size=3) as (url, state):

        def interrupt(done, *args):
            if done == 3:
                raise KeyboardInterrupt("interrupt concurrent batch")

        with pytest.raises(KeyboardInterrupt):
            run_experiment(
                prepared,
                output,
                client(url, monkeypatch),
                provider="openai-compatible",
                concurrency=3,
                progress=interrupt,
            )
        saved = len(list((output / "checkpoints").glob("*.json")))
        assert 3 <= saved < 12 and state["peak"] == 3
        runs = run_experiment(
            prepared,
            output,
            client(url, monkeypatch),
            provider="openai-compatible",
            concurrency=3,
            resume=True,
        )
        assert len(state["requests"]) == len(runs) == 12
        again = run_experiment(
            prepared, output, client(url, monkeypatch), provider="openai-compatible", resume=True
        )
        assert runs == again and len(state["requests"]) == 12


def test_cumulative_http_budget_survives_resume_and_explicit_increase(tmp_path, monkeypatch):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    with server() as (url, state):
        for resume in (False, True):
            with pytest.raises(LLMRequestBudgetExceeded):
                run_experiment(
                    prepared,
                    output,
                    client(url, monkeypatch, max_api_requests=3),
                    provider="openai-compatible",
                    resume=resume,
                )
            assert len(state["requests"]) == 3
        runs = run_experiment(
            prepared,
            output,
            client(url, monkeypatch, max_api_requests=12),
            provider="openai-compatible",
            resume=True,
        )
        assert len(runs) == len(state["requests"]) == 12
    manifest = json.loads((output / "run_manifest.json").read_bytes())
    assert manifest["budget_history"] == [{"previous": 3, "new": 12}]


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_version", "v2"),
        ("provider_name", "other"),
        ("structured_output", "text"),
        ("seed", 3),
    ],
)
def test_changed_api_runtime_fails_resume_before_calls(tmp_path, monkeypatch, field, value):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    with server() as (url, state):
        run_experiment(prepared, output, client(url, monkeypatch), provider="openai-compatible")
        changed = client(url, monkeypatch)
        setattr(changed, field, value)
        with pytest.raises(ValueError, match="resume client"):
            run_experiment(prepared, output, changed, provider="openai-compatible", resume=True)
        assert len(state["requests"]) == 12


def test_cli_wires_compatible_provider_budget_and_concurrency(tmp_path, monkeypatch):
    prepared = prepare(tmp_path)
    with server() as (url, state):
        monkeypatch.setenv("M7_TEST_API_KEY", SECRET)
        args = [
            "run",
            "--prepared-dir",
            str(prepared),
            "--output-dir",
            str(tmp_path / "run"),
            "--provider",
            "openai-compatible",
            "--base-url",
            url,
            "--provider-name",
            "fake-host",
            "--model-version",
            "pinned-v1",
            "--api-key-env",
            "M7_TEST_API_KEY",
            "--max-api-requests",
            "12",
            "--concurrency",
            "3",
        ]
        assert main(args) == main(args + ["--resume"]) == 0
        assert len(state["requests"]) == 12


def test_cached_response_tampering_is_rejected_before_network(tmp_path, monkeypatch):
    with server() as (url, state):
        client(url, monkeypatch).for_cell("cell", tmp_path).complete("q", {})
        path = next(tmp_path.rglob("response.json"))
        value = json.loads(path.read_bytes())
        value["body"]["choices"][0]["message"]["content"] = "tampered"
        path.write_text(json.dumps(value))
        with pytest.raises(ValueError, match="cache hash mismatch"):
            client(url, monkeypatch).for_cell("cell", tmp_path).complete("q", {})
        assert len(state["requests"]) == 1


def test_output_truncation_and_missing_content_remain_visible(tmp_path, monkeypatch):
    prepared = prepare(tmp_path)
    replies = [
        (
            200,
            {
                "choices": [{"message": {"content": None}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2048},
            },
            {},
        )
    ]
    with server(replies) as (url, state):
        runs = run_experiment(
            prepared, tmp_path / "run", client(url, monkeypatch), provider="openai-compatible"
        )
        assert runs[0].status == "output_truncated" and len(state["requests"]) == 12
    manifest = json.loads((tmp_path / "run/run_manifest.json").read_bytes())
    assert manifest["api_audit"]["http_attempts"] == 12
    assert manifest["api_audit"]["reported_input_tokens"] == 120
    assert manifest["api_audit"]["reported_output_tokens"] == 2048 + 11 * 5


def test_rate_limit_retry_later_aborts_batch_without_immediate_outer_retry(tmp_path, monkeypatch):
    from cs30.generation.exceptions import LLMRetryLater

    prepared = prepare(tmp_path)
    with server([(429, {}, {"Retry-After": "3600"})]) as (url, state):
        with pytest.raises(LLMRetryLater):
            run_experiment(
                prepared, tmp_path / "run", client(url, monkeypatch), provider="openai-compatible"
            )
        assert len(state["requests"]) == 1
        assert not list((tmp_path / "run/checkpoints").glob("*.json"))


def test_malformed_wire_envelope_can_recover_on_resume(tmp_path, monkeypatch):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    with server([(200, {"choices": []}, {})]) as (url, state):
        runs = run_experiment(
            prepared, output, client(url, monkeypatch), provider="openai-compatible"
        )
        assert runs[0].status == "generation_error"
        recovered = run_experiment(
            prepared, output, client(url, monkeypatch), provider="openai-compatible", resume=True
        )
        assert all(r.status == "answered" for r in recovered)
        assert len(state["requests"]) == 13
