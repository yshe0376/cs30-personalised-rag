"""Interruption, recovery, locking and provider-budget regression tests."""

import json
import urllib.request

import pytest
from test_v2_experiment import Client, prepare

from cs30.generation.client import OllamaChatClient
from cs30.generation.exceptions import LLMProviderError
from cs30.v2.experiment import run_experiment
from cs30.v2.experiment_checkpoint import writer_lock
from cs30.v2.experiment_cli import main


def interrupt_after_three(done, total, record, details):
    if done == 3:
        raise KeyboardInterrupt("synthetic process interruption")


def test_resume_uses_committed_cells_and_repairs_torn_aggregate_files(tmp_path):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    first = Client()
    with pytest.raises(KeyboardInterrupt):
        run_experiment(
            prepared, output, first, provider="synthetic", progress=interrupt_after_three
        )
    assert len(first.prompts) == 3
    assert len(list((output / "checkpoints").glob("*.json"))) == 3
    original_rows = (output / "saved_answers.jsonl").read_text(encoding="utf-8").splitlines()
    # A power loss may leave either aggregate incomplete. The atomic cells win.
    (output / "saved_answers.jsonl").write_text('{"torn":')
    (output / "generation_records.jsonl").write_text("")
    second = Client()
    runs = run_experiment(prepared, output, second, provider="synthetic", resume=True)
    assert len(second.prompts) == 9 and len(runs) == 12
    assert (output / "saved_answers.jsonl").read_text(encoding="utf-8").splitlines()[
        :3
    ] == original_rows
    assert len(list((output / "checkpoints").glob("*.json"))) == 12
    assert (
        json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))["resume_count"] == 1
    )
    third = Client()
    assert len(run_experiment(prepared, output, third, provider="synthetic", resume=True)) == 12
    assert not third.prompts
    summary = json.loads((output / "generation_summary.json").read_text(encoding="utf-8"))
    assert sum(g["model_calls"] for g in summary["groups"]) == 12


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("context_window", 32768),
        ("model_digest", "new-weights"),
        ("temperature", 0.5),
        ("max_output_tokens", 999),
    ],
)
def test_changed_runtime_cannot_mix_with_original_cells(tmp_path, attribute, value):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_experiment(
            prepared, output, Client(), provider="synthetic", progress=interrupt_after_three
        )
    original_manifest = (output / "run_manifest.json").read_bytes()
    client = Client()
    setattr(client, attribute, value)
    with pytest.raises(ValueError, match="resume client"):
        run_experiment(prepared, output, client, provider="synthetic", resume=True)
    assert not client.prompts
    assert (output / "run_manifest.json").read_bytes() == original_manifest


def test_corrupt_checkpoint_fails_before_calls_or_aggregate_rewrite(tmp_path):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_experiment(
            prepared, output, Client(), provider="synthetic", progress=interrupt_after_three
        )
    path = next((output / "checkpoints").glob("*.json"))
    value = json.loads(path.read_text(encoding="utf-8"))
    value["record"]["answer"]["explanation"] = "Changed after completion"
    path.write_text(json.dumps(value))
    original_answers = (output / "saved_answers.jsonl").read_bytes()
    client = Client()
    with pytest.raises(ValueError, match="checkpoint content hash"):
        run_experiment(prepared, output, client, provider="synthetic", resume=True)
    assert not client.prompts and (output / "saved_answers.jsonl").read_bytes() == original_answers


def test_concurrent_writer_is_rejected_and_os_lock_can_be_reacquired(tmp_path):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    run_experiment(prepared, output, Client(), provider="synthetic")
    with writer_lock(output):
        with pytest.raises(ValueError, match="already writing"):
            run_experiment(prepared, output, Client(), provider="synthetic", resume=True)
    client = Client()
    run_experiment(prepared, output, client, provider="synthetic", resume=True)
    assert not client.prompts


def test_completed_cli_resume_reuses_cells_without_scoring(tmp_path, monkeypatch):
    prepared = prepare(tmp_path)
    clients = []

    def factory(*args):
        client = Client()
        clients.append(client)
        return client

    monkeypatch.setattr("cs30.v2.experiment_cli._client", factory)
    args = [
        "run",
        "--prepared-dir",
        str(prepared),
        "--output-dir",
        str(tmp_path / "run"),
        "--provider",
        "ollama",
    ]
    assert main(args) == 0
    assert main(args + ["--resume"]) == 0
    assert not clients[-1].prompts
    assert not (tmp_path / "run/scoring").exists()


def test_ollama_context_guard_refuses_before_any_http_call(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("oversized input must not reach provider")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    client = OllamaChatClient("model", max_output_tokens=20, context_window=600)
    with pytest.raises(LLMProviderError, match="context budget"):
        client.complete("x" * 100, {})


def test_ollama_pins_weights_and_sends_explicit_context(monkeypatch):
    import io

    requests = []

    def provider(request, **kwargs):
        if isinstance(request, str):
            return io.BytesIO(
                json.dumps({"models": [{"name": "model:latest", "digest": "weights-v1"}]}).encode()
            )
        requests.append(json.loads(request.data))
        return io.BytesIO(
            json.dumps(
                {
                    "model": "model:latest",
                    "message": {"content": "{}"},
                    "prompt_eval_count": 1,
                    "eval_count": 1,
                }
            ).encode()
        )

    monkeypatch.setattr(urllib.request, "urlopen", provider)
    client = OllamaChatClient("model", max_output_tokens=20, context_window=32768)
    client.pin_model()
    assert client.model_digest == "weights-v1"
    client.complete("test", {})
    assert requests[0]["options"]["num_ctx"] == 32768


def test_cli_outage_guard_stops_after_three_durable_failures(tmp_path, monkeypatch):
    class Unavailable(Client):
        def complete(self, *args):
            raise TimeoutError("synthetic outage")

    prepared = prepare(tmp_path)
    monkeypatch.setattr("cs30.v2.experiment_cli._client", lambda *a: Unavailable())
    output = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--prepared-dir",
                str(prepared),
                "--output-dir",
                str(output),
                "--provider",
                "ollama",
                "--stop-after-errors",
                "3",
            ]
        )
        == 2
    )
    assert len(list((output / "checkpoints").glob("*.json"))) == 3
    assert json.loads((output / "run_manifest.json").read_bytes())["status"] == "interrupted"
    monkeypatch.setattr("cs30.v2.experiment_cli._client", lambda *a: Client())
    assert (
        main(
            [
                "run",
                "--prepared-dir",
                str(prepared),
                "--output-dir",
                str(output),
                "--provider",
                "ollama",
                "--stop-after-errors",
                "3",
                "--resume",
            ]
        )
        == 0
    )
    assert len(list((output / "checkpoints").glob("*.json"))) == 12
    rows = [
        json.loads(line)
        for line in (output / "saved_answers.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(row["status"] == "answered" for row in rows)
    assert len(list((output / "checkpoints/superseded").glob("*.json"))) == 3


@pytest.mark.parametrize("outage", [False, True])
def test_detached_supervisor_verifies_results_or_preserves_interruption(
    tmp_path, monkeypatch, outage
):
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "v2_batch_job_test", root / "scripts/run_v2_batch_job.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prepared = prepare(tmp_path)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "prepared_dir": str(prepared),
                "python": sys.executable,
                "code_dir": str(root),
                "source_commit": "synthetic",
                "timeout": 180,
                "max_output_tokens": 2048,
                "context_window": 32768,
            }
        )
    )

    class Provider(Client):
        def complete(self, *args):
            if outage:
                raise TimeoutError("synthetic outage")
            return super().complete(*args)

    monkeypatch.setattr("cs30.v2.experiment_cli._client", lambda *a: Provider())
    monkeypatch.setattr(module.signal, "signal", lambda *a: None)

    class Child:
        pid = 12345

        def __init__(self, command, **kwargs):
            self.code = main(command[command.index("run") :])

        def poll(self):
            return self.code

        def wait(self):
            return self.code

    monkeypatch.setattr(module.subprocess, "Popen", Child)
    module.worker(job_dir, resume=False)
    state = json.loads((job_dir / "progress.json").read_bytes())
    assert state["completed_cells"] == (3 if outage else 12)
    assert state["status"] == ("interrupted_resume_available" if outage else "completed")
    if not outage:
        verification = json.loads((job_dir / "verification.json").read_bytes())
        assert verification["status"] == "passed"
        assert verification["saved_answers"] == verification["expected_cells"] == 12
    assert (job_dir / "README.md").exists()


def test_citation_failures_never_trip_service_outage_guard(tmp_path, monkeypatch):
    from cs30.generation.client import LLMResponse, TokenUsage

    class BadCitation(Client):
        def complete(self, *args):
            self.prompts.append(args[0])
            return LLMResponse(
                '{"final_choice":null,"explanation":"Answer","citations":["E99"]}',
                self.model,
                TokenUsage(),
                None,
                0,
            )

    prepared = prepare(tmp_path)
    client = BadCitation()
    monkeypatch.setattr("cs30.v2.experiment_cli._client", lambda *a: client)
    output = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--prepared-dir",
                str(prepared),
                "--output-dir",
                str(output),
                "--provider",
                "ollama",
                "--stop-after-errors",
                "3",
            ]
        )
        == 3
    )
    assert len(client.prompts) == 12
    assert json.loads((output / "run_manifest.json").read_bytes())["status"] == "completed"
    # Deterministic citation errors remain finalized on resume.
    assert (
        main(
            [
                "run",
                "--prepared-dir",
                str(prepared),
                "--output-dir",
                str(output),
                "--provider",
                "ollama",
                "--resume",
            ]
        )
        == 3
    )
    assert len(client.prompts) == 12


def test_output_budget_exhaustion_is_distinct_from_service_failure(tmp_path, monkeypatch):
    from cs30.generation.client import LLMResponse, TokenUsage

    class Truncated(Client):
        def complete(self, *args):
            return LLMResponse("", self.model, TokenUsage(1, 20, 21), None, 0, done_reason="length")

    prepared = prepare(tmp_path)
    monkeypatch.setattr("cs30.v2.experiment_cli._client", lambda *a: Truncated())
    output = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--prepared-dir",
                str(prepared),
                "--output-dir",
                str(output),
                "--provider",
                "ollama",
                "--stop-after-errors",
                "3",
            ]
        )
        == 3
    )
    rows = [
        json.loads(line)
        for line in (output / "saved_answers.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 12 and all(r["status"] == "output_truncated" for r in rows)
    details = [
        json.loads(line)
        for line in (output / "generation_records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(r["generation_trace"]["attempts"][-1]["done_reason"] == "length" for r in details)
    manifest = json.loads((output / "run_manifest.json").read_bytes())
    assert manifest["technical_failures"] == 0 and manifest["output_truncated"] == 12


def test_rubric_updates_cannot_change_generation_or_resume_identity(tmp_path):
    prepared = prepare(tmp_path)
    output = tmp_path / "run"
    run_experiment(prepared, output, Client(), provider="synthetic")
    before = (output / "saved_answers.jsonl").read_bytes()
    (prepared / "rubrics.jsonl").write_text("M8 may revise this independently", encoding="utf-8")
    client = Client()
    run_experiment(prepared, output, client, provider="synthetic", resume=True)
    assert not client.prompts and (output / "saved_answers.jsonl").read_bytes() == before
    assert (
        "rubrics.jsonl"
        not in json.loads((prepared / "input_manifest.json").read_bytes())["input_sha256"]
    )


def test_ollama_preserves_empty_truncation_reason_and_seed(monkeypatch):
    import io

    captured = []

    def provider(request, **kwargs):
        captured.append(json.loads(request.data))
        return io.BytesIO(
            json.dumps(
                {"message": {"content": ""}, "done_reason": "length", "eval_count": 20}
            ).encode()
        )

    monkeypatch.setattr(urllib.request, "urlopen", provider)
    client = OllamaChatClient("model", seed=37, max_output_tokens=20)
    response = client.complete("test", {})
    assert response.text == "" and response.done_reason == "length"
    assert response.usage.output_tokens == 20
    assert captured[0]["options"]["seed"] == 37


def test_supervisor_rejects_windows_before_side_effects(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "windows_batch_guard", Path(__file__).resolve().parents[1] / "scripts/run_v2_batch_job.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, "platform", "win32")
    destination = tmp_path / "job"
    assert module.main(["start", "--job-dir", str(destination)]) == 2
    assert not destination.exists()
    assert "macOS/Linux only" in capsys.readouterr().err


def test_resume_preserves_a_mixed_parse_and_provider_failure(tmp_path):
    from test_v2_experiment import inputs

    from cs30.generation.client import LLMResponse, TokenUsage
    from cs30.v2.experiment import ExperimentConfig, prepare_experiment

    corpus, gold, _ = inputs(tmp_path)
    prepared = tmp_path / "prepared"
    prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold,
        output_dir=prepared,
        config=ExperimentConfig(
            generator_model=Client.model, max_retries=1, allow_missing_roles=True
        ),
    )

    class Mixed(Client):
        def complete(self, *args):
            if not self.prompts:
                self.prompts.append(args[0])
                return LLMResponse("not JSON", self.model, TokenUsage(), None, 0)
            if len(self.prompts) == 1:
                self.prompts.append(args[0])
                raise TimeoutError("second attempt had an outage")
            return super().complete(*args)

    output = tmp_path / "run"
    first = run_experiment(prepared, output, Mixed(), provider="synthetic")
    assert first[0].status == "generation_error"
    recovered = Client()
    final = run_experiment(prepared, output, recovered, provider="synthetic", resume=True)
    assert final[0] == first[0] and not recovered.prompts
    assert not (output / "checkpoints/superseded").exists()


def test_nontruncated_empty_ollama_response_retains_done_reason_in_trace(monkeypatch):
    import io

    from test_v2_generation_adapter import _bundle

    from cs30.v2.contracts import StudentProfile
    from cs30.v2.generation import V2AnswerGenerator, V2GenerationFailure

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: io.BytesIO(b'{"message":{"content":""},"done_reason":"stop"}'),
    )
    generator = V2AnswerGenerator(OllamaChatClient("model"), max_retries=0)
    with pytest.raises(V2GenerationFailure) as caught:
        generator.generate(
            "What is motion?", StudentProfile(profile_id="s", level="beginner"), _bundle()
        )
    attempt = caught.value.trace.attempts[0]
    assert attempt.status == "provider_failure" and attempt.done_reason == "stop"
