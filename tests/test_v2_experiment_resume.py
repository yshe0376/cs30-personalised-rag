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


def interrupt_after_three(done, total, record):
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
    original_rows = (output / "saved_answers.jsonl").read_text().splitlines()
    # A power loss may leave either aggregate incomplete. The atomic cells win.
    (output / "saved_answers.jsonl").write_text('{"torn":')
    (output / "generation_records.jsonl").write_text("")
    second = Client()
    runs = run_experiment(prepared, output, second, provider="synthetic", resume=True)
    assert len(second.prompts) == 9 and len(runs) == 12
    assert (output / "saved_answers.jsonl").read_text().splitlines()[:3] == original_rows
    assert len(list((output / "checkpoints").glob("*.json"))) == 12
    assert json.loads((output / "run_manifest.json").read_text())["resume_count"] == 1
    third = Client()
    assert len(run_experiment(prepared, output, third, provider="synthetic", resume=True)) == 12
    assert not third.prompts
    summary = json.loads((output / "generation_summary.json").read_text())
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
    value = json.loads(path.read_text())
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


def test_completed_cli_resume_reuses_existing_scoring_reports(tmp_path, monkeypatch):
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
    assert main(args) == 3
    report = tmp_path / "run/scoring/open_answer_summary.json"
    before = report.read_bytes()
    assert main(args + ["--resume"]) == 3
    assert not clients[-1].prompts and report.read_bytes() == before


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
        == 3
    )
    assert len(list((output / "checkpoints").glob("*.json"))) == 12


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
    assert state["status"] == (
        "interrupted_resume_available" if outage else "completed_pending_scoring"
    )
    if not outage:
        verification = json.loads((job_dir / "verification.json").read_bytes())
        assert verification["status"] == "passed"
        assert verification["saved_answers"] == verification["expected_cells"] == 12
    assert (job_dir / "README.md").exists()
