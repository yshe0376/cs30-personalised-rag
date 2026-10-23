"""File-based command integration, including provenance and human review commands."""

import json
from pathlib import Path

import pytest
from test_open_answer_scoring import (
    JudgeClient,
    assessment,
    case,
    experiment,
    gold,
    rating,
    rubric,
    run,
)

from cs30.evaluation.open_answer_cli import load_gold, main, read_jsonl
from cs30.evaluation.open_answer_models import OpenAnswerScore
from cs30.evaluation.open_answer_scoring import sha256_bytes


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def inputs(tmp_path, answer="deceleration", missing=False):
    gold_path = tmp_path / "gold.jsonl"
    write_jsonl(gold_path, [gold().model_dump(mode="json")])
    gold_hash = sha256_bytes(gold_path.read_bytes())
    rubric_path = tmp_path / "rubrics.jsonl"
    write_jsonl(rubric_path, [rubric(gold_sha256=gold_hash).model_dump(mode="json")])
    runs_path = tmp_path / "runs.jsonl"
    write_jsonl(runs_path, [] if missing else [run(answer=answer).model_dump(mode="json")])
    matrix = experiment(case()).model_copy(
        update={
            "gold_sha256": gold_hash,
            "rubrics_sha256": sha256_bytes(rubric_path.read_bytes()),
        }
    )
    manifest_path = tmp_path / "expected.json"
    manifest_path.write_text(matrix.model_dump_json(), encoding="utf-8")
    output = tmp_path / "output"
    args = [
        "score",
        "--gold",
        str(gold_path),
        "--rubrics",
        str(rubric_path),
        "--runs",
        str(runs_path),
        "--expected-manifest",
        str(manifest_path),
        "--output-dir",
        str(output),
    ]
    return args, output


def test_cli_scores_and_writes_versioned_outputs_without_model_calls(tmp_path):
    args, output = inputs(tmp_path)
    assert main(args) == 0
    report = json.loads((output / "open_answer_summary.json").read_text(encoding="utf-8"))
    assert report["overall"]["open_answer_full_correct_rate_e2e"]["value"] == 1
    assert report["reportable"] is False
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_sha256"]["gold"] == sha256_bytes((tmp_path / "gold.jsonl").read_bytes())
    assert len(list(output.iterdir())) == 6


def test_cli_scores_m7_schema_0_2_and_binds_m8_rubrics_independently(tmp_path):
    args, output = inputs(tmp_path)
    expected_path = tmp_path / "expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    expected["schema_version"] = "0.2"
    expected.pop("rubrics_sha256")
    expected_path.write_text(json.dumps(expected), encoding="utf-8")

    assert main(args) == 0
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["generation_matrix_schema_version"] == "0.2"
    assert manifest["input_sha256"]["rubrics"] == sha256_bytes(
        (tmp_path / "rubrics.jsonl").read_bytes()
    )


@pytest.mark.parametrize("missing", [False, True])
def test_cli_pending_returns_attention_code_and_preserves_denominator(tmp_path, missing):
    args, output = inputs(tmp_path, answer="a synonymous answer", missing=missing)
    assert main(args) == 3
    report = json.loads((output / "open_answer_summary.json").read_text(encoding="utf-8"))
    metric = report["overall"]["open_answer_full_correct_rate_e2e"]
    assert metric["value"] is None and metric["denominator"] == 1
    assert len(read_jsonl(output / "open_answer_review_queue.jsonl")) == 1


def test_cli_live_adapter_passes_strict_judge_schema(tmp_path, monkeypatch):
    args, output = inputs(tmp_path, answer="slowing down")
    client = JudgeClient(assessment())
    monkeypatch.setattr("cs30.evaluation.open_answer_cli.OllamaChatClient", lambda *a, **kw: client)
    assert main(args + ["--provider", "ollama", "--model", "judge-v1"]) == 0
    assert len(client.prompts) == 1
    assert read_jsonl(output / "open_answer_scores.jsonl")[0]["score"] == 2


def test_cli_can_select_gemini_for_open_answer_judging(tmp_path, monkeypatch):
    args, output = inputs(tmp_path, answer="slowing down")
    client = JudgeClient(assessment())
    captured = {}

    def client_factory(*_args, **kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr(
        "cs30.evaluation.open_answer_cli.GeminiJudgeClient", client_factory
    )

    assert main(args + ["--provider", "gemini", "--model", "gemini-test"]) == 0

    assert len(client.prompts) == 1
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "gemini"
    assert captured["temperature"] == 1.0
    assert captured["thinking_level"] == "high"
    assert captured["max_output_tokens"] == 8192


@pytest.mark.parametrize("change", ["gold", "rubrics"])
def test_cli_rejects_changed_input_before_calling_provider(tmp_path, monkeypatch, change):
    args, output = inputs(tmp_path)
    path = tmp_path / f"{change}.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")

    def unexpected(*args, **kwargs):
        raise AssertionError("invalid inputs must not invoke the judge")

    monkeypatch.setattr("cs30.evaluation.open_answer_cli.OllamaChatClient", unexpected)
    assert main(args + ["--provider", "ollama", "--model", "judge-v1"]) == 2
    assert not output.exists()


def test_cli_does_not_overwrite_output_and_rejects_unknown_runs(tmp_path):
    args, output = inputs(tmp_path)
    assert main(args) == 0
    original = (output / "open_answer_scores.jsonl").read_bytes()
    assert main(args) == 2
    assert (output / "open_answer_scores.jsonl").read_bytes() == original
    another = tmp_path / "new-report"
    args[-1] = str(another)
    write_jsonl(tmp_path / "runs.jsonl", [run(2).model_dump(mode="json")])
    assert main(args) == 2
    assert not another.exists()


def test_cli_requires_model_and_supported_gold_schema(tmp_path):
    args, output = inputs(tmp_path)
    assert main(args + ["--provider", "ollama"]) == 2
    assert main(args + ["--model", "judge-v1"]) == 2
    path = tmp_path / "unknown.jsonl"
    write_jsonl(path, [gold().model_dump(mode="json") | {"schema_version": "unknown"}])
    with pytest.raises(ValueError, match="schema_version"):
        load_gold(path)
    assert not output.exists()


def test_human_review_command_creates_new_artifacts_and_preserves_original(tmp_path):
    args, output = inputs(tmp_path, answer="slowing down")
    assert main(args) == 3
    scores = output / "open_answer_scores.jsonl"
    original = scores.read_bytes()
    record = OpenAnswerScore.model_validate(read_jsonl(scores)[0])
    decision = rating(record, "human-1", 2).model_dump() | {"review_record_id": "review-1"}
    decisions = tmp_path / "decisions.jsonl"
    write_jsonl(decisions, [decision])
    reviewed = tmp_path / "reviewed"
    assert (
        main(
            [
                "review",
                "--scores",
                str(scores),
                "--decisions",
                str(decisions),
                "--output-dir",
                str(reviewed),
            ]
        )
        == 0
    )
    result = read_jsonl(reviewed / "open_answer_scores.jsonl")[0]
    assert result["score"] == 2 and result["scoring_source"] == "human"
    assert scores.read_bytes() == original


def test_calibration_command_reads_actual_double_ratings(tmp_path):
    args, output = inputs(tmp_path)
    assert main(args) == 0
    scores = output / "open_answer_scores.jsonl"
    record = OpenAnswerScore.model_validate(read_jsonl(scores)[0])
    ratings = tmp_path / "ratings.jsonl"
    write_jsonl(ratings, [rating(record, rater, 2).model_dump() for rater in ("a", "b")])
    calibrated = tmp_path / "calibrated"
    assert (
        main(
            [
                "calibrate",
                "--scores",
                str(scores),
                "--ratings",
                str(ratings),
                "--output-dir",
                str(calibrated),
            ]
        )
        == 0
    )
    report = json.loads(
        (calibrated / "calibration_summary.json").read_text(encoding="utf-8")
    )
    assert report["sample_count"] == 1 and report["raw_human_agreement"] == 1
    assert report["linear_weighted_cohen_kappa"] is None
    assert report["reportable"] is False


@pytest.mark.parametrize("content", ["[]\n", '{"incomplete":\n'])
def test_jsonl_loader_reports_line_errors(tmp_path, content):
    path = tmp_path / "bad.jsonl"
    path.write_text(content)
    with pytest.raises(ValueError, match=r"bad.jsonl:1"):
        read_jsonl(path)


def test_example_can_load_legacy_gold_without_renaming_choice_metrics():
    fixture = Path(__file__).parent / "fixtures/evaluation/gold_v0_1.jsonl"
    loaded = load_gold(fixture)
    assert loaded and any(item.options for item in loaded.values())


def test_cli_scores_a_consistent_input_snapshot_when_files_change_during_judging(
    tmp_path, monkeypatch
):
    args, output = inputs(tmp_path, answer="slowing down")
    gold_path = tmp_path / "gold.jsonl"
    original_hash = sha256_bytes(gold_path.read_bytes())

    class MutatingClient(JudgeClient):
        def complete(self, prompt, text_format):
            gold_path.write_text("changed while judging")
            return super().complete(prompt, text_format)

    monkeypatch.setattr(
        "cs30.evaluation.open_answer_cli.OllamaChatClient",
        lambda *a, **kw: MutatingClient(assessment()),
    )
    assert main(args + ["--provider", "ollama", "--model", "judge-v1"]) == 0
    saved = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert saved["input_sha256"]["gold"] == original_hash
    assert saved["input_sha256"]["gold"] != sha256_bytes(gold_path.read_bytes())


@pytest.mark.parametrize("argument, value", [("--timeout", "nan"), ("--max-output-tokens", "0")])
def test_cli_rejects_invalid_judge_limits_before_any_call(tmp_path, argument, value):
    args, output = inputs(tmp_path)
    assert main(args + [argument, value]) == 2
    assert not output.exists()
