from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.judge_runtime import configuration_sha256
from cs30.evaluation.v2_generation_cli import (
    _assert_comparable_judge_runs,
    _judge_response_fingerprint,
    main,
)
from cs30.evaluation.v2_generation_models import (
    ExperimentArm,
    JudgeConfiguration,
    JudgeResultEnvelope,
    JudgeTask,
)
from cs30.generation.client import LLMResponse, TokenUsage


def _write_judge_evaluation_dir(
    path: Path,
    *,
    rows: dict[str, list[dict[str, object]]],
    provenance: dict[str, object],
) -> None:
    path.mkdir()
    filenames = {
        "adaptation": "adaptation_results.jsonl",
        "discrimination": "discrimination_results.jsonl",
        "evidence_support": "evidence_support_results.jsonl",
        "unresolved": "judge_unresolved.jsonl",
    }
    hashes = {}
    for name, filename in filenames.items():
        output = path / filename
        output.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows.get(name, [])),
            encoding="utf-8",
        )
        hashes[name] = hashlib.sha256(output.read_bytes()).hexdigest()
    (path / "judge_evaluation_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "expected_request_count": sum(len(value) for value in rows.values()),
                "supplied_request_count": sum(len(value) for value in rows.values()),
                "provenance": provenance,
                "output_sha256": hashes,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _rows_for_evaluation_ids(
    rows: dict[str, list[dict[str, object]]],
    evaluation_ids: set[str],
) -> dict[str, list[dict[str, object]]]:
    return {
        name: [
            row
            for row in values
            if name == "unresolved" or row.get("evaluation_id") in evaluation_ids
        ]
        for name, values in rows.items()
    }


def test_cli_help_keeps_legacy_report_extension_v1_only(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "cs30-evaluate report-" in output
    assert "extension command remains V1-only" in output


def test_validate_inputs_uses_evidence_files_instead_of_declaration_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["validate-inputs", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--leader-calibration-record" in output
    assert "--label-provenance-record" in output
    assert "--calibrated-with-leader" not in output
    assert "--labels-created-without-model-answers" not in output


def test_run_judge_requests_calls_provider_and_records_fresh_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = "discrimination-request-1"
    requests = tmp_path / "requests.jsonl"
    requests.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "task": "discrimination",
                "request_id": request_id,
                "input_sha256": "a" * 64,
                "config_sha256": "b" * 64,
                "system_instruction": "Return the required structured JSON.",
                "payload": {
                    "answer": "A net force causes acceleration.",
                    "required_output": {},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "judge-config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "judge-v1",
                "provider": "ollama",
                "model_family": "judge-family",
                "model_revision": "judge-family:7b",
                "temperature": 0,
                "seed": 5703,
                "prompt_version": "prompt-v1",
                "output_schema_version": "1.0",
                "local_model": True,
                "data_approval": "not_required",
            }
        ),
        encoding="utf-8",
    )
    request_payload = json.loads(requests.read_text(encoding="utf-8"))
    request_payload["config_sha256"] = configuration_sha256(
        JudgeConfiguration.model_validate_json(config.read_text(encoding="utf-8"))
    )
    requests.write_text(json.dumps(request_payload) + "\n", encoding="utf-8")

    class Client:
        def complete(self, _prompt: str, _text_format: dict) -> LLMResponse:
            return LLMResponse(
                text=json.dumps(
                    {
                        "schema_version": "1.0",
                        "request_id": request_id,
                        "predicted_level": "beginner",
                        "exact_quote": "A net force causes acceleration",
                        "reason": "The answer states the core relation directly.",
                    }
                ),
                model="judge-family:7b",
                usage=TokenUsage(input_tokens=10, output_tokens=8, total_tokens=18),
                response_id="provider-response-1",
                latency_ms=1.0,
            )

    monkeypatch.setattr(
        "cs30.evaluation.v2_generation_cli.OllamaChatClient",
        lambda *_args, **_kwargs: Client(),
    )
    cache = tmp_path / "cache.jsonl"
    output = tmp_path / "results.jsonl"
    assert (
        main(
            [
                "run-judge-requests",
                "--requests",
                str(requests),
                "--judge-config",
                str(config),
                "--cache",
                str(cache),
                "--output",
                str(output),
                "--require-fresh-cache",
            ]
        )
        == 0
    )
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["provider_response_id"] == "provider-response-1"
    assert envelope["reported_model"] == "judge-family:7b"
    assert envelope["cache_hit"] is False
    assert len(cache.read_text(encoding="utf-8").splitlines()) == 1


def test_repeat_comparison_rejects_reused_provider_responses() -> None:
    shared = {
        "evaluation_inputs_sha256": "a" * 64,
        "source_run_sha256": "b" * 64,
        "profile_package_sha256": "c" * 64,
        "judge_configuration_sha256": "d" * 64,
        "judge_cache_hit_count": 0,
        "judge_response_fingerprints": ["same-provider-response"],
        "reverse_adaptation_criteria": False,
    }
    primary = {"manifest": {"provenance": {**shared, "judge_execution_id": "first"}}}
    repeat = {"manifest": {"provenance": {**shared, "judge_execution_id": "second"}}}
    with pytest.raises(ValueError, match="reused provider responses"):
        _assert_comparable_judge_runs(primary, repeat, purpose="repeat")


def test_response_fingerprint_detects_reuse_across_request_and_timestamp_changes() -> None:
    first = JudgeResultEnvelope(
        task=JudgeTask.DISCRIMINATION,
        request_id="request-one",
        cache_key="a" * 64,
        judge_config_version="judge-v1",
        output={"decision": "beginner"},
        provider_response_id="provider-response-shared",
        completed_at_utc="2026-10-20T00:00:00+00:00",
    )
    repeated = first.model_copy(
        update={
            "request_id": "request-two",
            "cache_key": "b" * 64,
            "completed_at_utc": "2026-10-20T00:05:00+00:00",
        }
    )
    assert _judge_response_fingerprint(first) == _judge_response_fingerprint(repeated)

    timestamp_only = first.model_copy(update={"provider_response_id": None})
    same_timestamp = repeated.model_copy(
        update={
            "provider_response_id": None,
            "completed_at_utc": timestamp_only.completed_at_utc,
        }
    )
    assert _judge_response_fingerprint(timestamp_only) == _judge_response_fingerprint(
        same_timestamp
    )
    assert _judge_response_fingerprint(timestamp_only) != _judge_response_fingerprint(
        repeated.model_copy(update={"provider_response_id": None})
    )


def test_second_judge_comparison_normalizes_model_size_suffixes() -> None:
    shared = {
        "evaluation_inputs_sha256": "a" * 64,
        "source_run_sha256": "b" * 64,
        "profile_package_sha256": "c" * 64,
    }
    primary = {
        "manifest": {
            "provenance": {
                **shared,
                "judge_execution_id": "first",
                "judge_model_family": "gpt-oss",
            }
        }
    }
    second = {
        "manifest": {
            "provenance": {
                **shared,
                "judge_execution_id": "second",
                "judge_model_family": "gpt-oss-120b",
            }
        }
    }
    with pytest.raises(ValueError, match="different model family"):
        _assert_comparable_judge_runs(primary, second, purpose="second")


def test_condition_stats_cli_writes_all_four_predeclared_contrasts(tmp_path: Path) -> None:
    observations = tmp_path / "observations.jsonl"
    values = {
        ExperimentArm.P0R0_PLAIN: 0.5,
        ExperimentArm.P1R0_PROMPT_ONLY: 0.6,
        ExperimentArm.P0R1_RERANKING_ONLY: 0.55,
        ExperimentArm.P1R1_COMBINED: 0.7,
    }
    rows = [
        {
            "schema_version": "1.0",
            "question_id": question,
            "target_level": level.value,
            "condition": condition.value,
            "metric": "adaptation",
            "value": value,
        }
        for question in ("q-1", "q-2")
        for level in StudentLevel
        for condition, value in values.items()
    ]
    observations.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "stats.json"
    assert (
        main(
            [
                "condition-stats",
                "--observations",
                str(observations),
                "--bootstrap-draws",
                "20",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["contrasts"]) == 4
    assert {row["contrast"] for row in payload["contrasts"]} == {
        "prompt_without_reranking",
        "prompt_with_reranking",
        "reranking_without_prompt",
        "reranking_with_prompt",
    }


def test_cli_rejects_duplicate_metric_cells(tmp_path: Path) -> None:
    observations = tmp_path / "duplicate.jsonl"
    row = {
        "schema_version": "1.0",
        "question_id": "q-1",
        "target_level": "beginner",
        "condition": "P0R0_plain",
        "metric": "adaptation",
        "value": 0.5,
    }
    observations.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    output = tmp_path / "stats.json"
    try:
        main(
            [
                "condition-stats",
                "--observations",
                str(observations),
                "--output",
                str(output),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("duplicate metric cells must terminate the CLI")


def test_validity_report_cli_keeps_missing_required_checks_fail_closed(
    tmp_path: Path,
) -> None:
    observations = tmp_path / "validity.json"
    observations.write_text(
        json.dumps(
            {
                "thresholds": {
                    "schema_version": "1.0",
                    "threshold_version": "thresholds-v1",
                    "p0r0_max_chance_deviation": 0.4,
                    "duplicate_min_consistency": 1.0,
                    "max_abs_length_correlation": 1.0,
                    "max_formula_pass_rate_gap": 1.0,
                    "order_min_consistency": 1.0,
                    "second_judge_min_consistency": 1.0,
                    "perturbation_min_detection_rate": 0.8,
                    "p0r0_min_case_count": 3,
                    "duplicate_min_group_count": 1,
                    "surface_min_rows_per_level": 3,
                    "order_min_case_count": 1,
                    "second_judge_min_case_count": 1,
                    "perturbation_min_case_count": 1,
                    "second_judge_max_evidence_rate_gap": 0.1,
                },
                "p0r0_rows": [
                    ["beginner", "beginner"],
                    ["intermediate", "advanced"],
                    ["advanced", "intermediate"],
                ],
                "duplicate_rows": [],
                "surface_rows": [["beginner", True, 10, False]],
                "order_pairs": [["case-1", "same", "same"]],
                "second_judge_pairs": [["case-1", "same", "same"]],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "validity-report.json"
    assert (
        main(["validity-report", "--observations", str(observations), "--output", str(output)]) == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["formal_use_allowed"] is False
    assert "duplicate_consistency" in report["failed_or_missing_required_checks"]
    assert "source_binding" in report["failed_or_missing_required_checks"]


def test_validity_report_rejects_truthy_strings_in_boolean_fields(tmp_path: Path) -> None:
    observations = tmp_path / "invalid-validity.json"
    observations.write_text(
        json.dumps(
            {
                "thresholds": {
                    "threshold_version": "thresholds-v1",
                    "p0r0_max_chance_deviation": 0.4,
                    "duplicate_min_consistency": 1.0,
                    "max_abs_length_correlation": 1.0,
                    "max_formula_pass_rate_gap": 1.0,
                    "order_min_consistency": 1.0,
                    "second_judge_min_consistency": 1.0,
                    "perturbation_min_detection_rate": 0.8,
                    "p0r0_min_case_count": 3,
                    "duplicate_min_group_count": 1,
                    "surface_min_rows_per_level": 3,
                    "order_min_case_count": 1,
                    "second_judge_min_case_count": 1,
                    "perturbation_min_case_count": 1,
                    "second_judge_max_evidence_rate_gap": 0.1,
                },
                "surface_rows": [["beginner", "false", 10, False]],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "validity-report",
                "--observations",
                str(observations),
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
    assert exc_info.value.code == 2


def test_validity_cli_derives_semantic_repeat_order_and_second_judge_pairs(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs.jsonl"
    input_rows = []
    result_rows = {
        "adaptation": [],
        "discrimination": [],
        "evidence_support": [],
        "unresolved": [],
    }
    for level in StudentLevel:
        for condition in ExperimentArm:
            evaluation_id = f"eval-{level.value}-{condition.value}"
            answer = f"A distinct saved answer for {evaluation_id}."
            answer_sha256 = hashlib.sha256(answer.encode("utf-8")).hexdigest()
            input_rows.append(
                {
                    "schema_version": "1.0",
                    "evaluation_id": evaluation_id,
                    "run_id": f"run-{evaluation_id}",
                    "question_id": "q-shared",
                    "question": "Explain the result.",
                    "answer": answer,
                    "target_level": level.value,
                    "condition": condition.value,
                    "lambda_weight": 0.0 if "R0" in condition.value else 0.2,
                    "generation_model_family": "generator-family",
                    "generation_model_revision": "generator-r1",
                    "eligibility": "full",
                    "source_artifact_sha256": "a" * 64,
                    "source_run_sha256": "b" * 64,
                    "answer_sha256": answer_sha256,
                }
            )
            result_rows["adaptation"].append(
                {
                    "evaluation_id": evaluation_id,
                    "question_id": "q-shared",
                    "target_level": level.value,
                    "evaluated_level": level.value,
                    "condition": condition.value,
                    "is_target_level_evaluation": True,
                    "criterion_pass_rate": 1.0,
                    "criteria": [
                        {
                            "criterion_id": f"{level.value}-criterion",
                            "verdict": "pass",
                            "reason": "wording may change without changing the decision",
                        }
                    ],
                }
            )
            result_rows["discrimination"].append(
                {
                    "evaluation_id": evaluation_id,
                    "question_id": "q-shared",
                    "target_level": level.value,
                    "condition": condition.value,
                    "predicted_level": level.value,
                }
            )
            result_rows["evidence_support"].append(
                {
                    "evaluation_id": evaluation_id,
                    "question_id": "q-shared",
                    "target_level": level.value,
                    "condition": condition.value,
                    "bundle_faithfulness": 1.0,
                    "citation_support": 1.0,
                }
            )
    inputs.write_text(
        "".join(json.dumps(row) + "\n" for row in input_rows),
        encoding="utf-8",
    )
    inputs_sha256 = hashlib.sha256(inputs.read_bytes()).hexdigest()
    shared_provenance = {
        "evaluation_inputs_sha256": inputs_sha256,
        "source_run_sha256": "b" * 64,
        "profile_package_sha256": "c" * 64,
        "judge_configuration_sha256": "d" * 64,
        "judge_model_family": "primary-family",
        "judge_cache_hit_count": 0,
        "reverse_adaptation_criteria": False,
    }
    primary = tmp_path / "primary"
    repeat = tmp_path / "repeat"
    order = tmp_path / "order"
    second = tmp_path / "second"
    repeat_ids = {
        f"eval-{level.value}-{ExperimentArm.P0R0_PLAIN.value}"
        for level in StudentLevel
    }
    order_ids = set(repeat_ids)
    second_ids = {
        f"eval-{StudentLevel.BEGINNER.value}-{condition.value}"
        for condition in ExperimentArm
    } | {
        f"eval-{StudentLevel.INTERMEDIATE.value}-{ExperimentArm.P0R0_PLAIN.value}",
        f"eval-{StudentLevel.ADVANCED.value}-{ExperimentArm.P0R0_PLAIN.value}",
    }
    repeat_ids_path = tmp_path / "repeat-ids.txt"
    order_ids_path = tmp_path / "order-ids.txt"
    second_ids_path = tmp_path / "second-ids.txt"
    repeat_ids_path.write_text("\n".join(sorted(repeat_ids)) + "\n", encoding="utf-8")
    order_ids_path.write_text("\n".join(sorted(order_ids)) + "\n", encoding="utf-8")
    second_ids_path.write_text("\n".join(sorted(second_ids)) + "\n", encoding="utf-8")
    _write_judge_evaluation_dir(
        primary,
        rows=result_rows,
        provenance={
            **shared_provenance,
            "judge_execution_id": "primary-run",
            "judge_response_fingerprints": ["primary-response"],
        },
    )
    _write_judge_evaluation_dir(
        repeat,
        rows=_rows_for_evaluation_ids(result_rows, repeat_ids),
        provenance={
            **shared_provenance,
            "judge_execution_id": "repeat-run",
            "judge_response_fingerprints": ["repeat-response"],
        },
    )
    _write_judge_evaluation_dir(
        order,
        rows=_rows_for_evaluation_ids(result_rows, order_ids),
        provenance={
            **shared_provenance,
            "judge_execution_id": "order-run",
            "judge_response_fingerprints": ["order-response"],
            "reverse_adaptation_criteria": True,
        },
    )
    _write_judge_evaluation_dir(
        second,
        rows=_rows_for_evaluation_ids(result_rows, second_ids),
        provenance={
            **shared_provenance,
            "judge_execution_id": "second-run",
            "judge_configuration_sha256": "e" * 64,
            "judge_model_family": "second-family",
            "judge_response_fingerprints": ["second-response"],
        },
    )
    primary_manifest_sha256 = hashlib.sha256(
        (primary / "judge_evaluation_manifest.json").read_bytes()
    ).hexdigest()
    observations = tmp_path / "observations.json"
    observations.write_text(
        json.dumps(
            {
                "thresholds": {
                    "threshold_version": "candidate-v1",
                    "p0r0_max_chance_deviation": 0.01,
                    "duplicate_min_consistency": 1.0,
                    "max_abs_length_correlation": 1.0,
                    "max_formula_pass_rate_gap": 1.0,
                    "order_min_consistency": 1.0,
                    "second_judge_min_consistency": 1.0,
                    "perturbation_min_detection_rate": 0.8,
                    "p0r0_min_case_count": 3,
                    "duplicate_min_group_count": 1,
                    "surface_min_rows_per_level": 3,
                    "order_min_case_count": 3,
                    "second_judge_min_case_count": 6,
                    "perturbation_min_case_count": 1,
                    "second_judge_max_evidence_rate_gap": 0.1,
                },
                "adaptation_pass_threshold": 0.5,
                "provenance": {
                    "evaluation_inputs_sha256": inputs_sha256,
                    "source_run_sha256": "b" * 64,
                    "judge_evaluation_manifest_sha256": primary_manifest_sha256,
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "validity-report.json"
    assert (
        main(
            [
                "validity-report",
                "--observations",
                str(observations),
                "--inputs",
                str(inputs),
                "--judge-evaluation-dir",
                str(primary),
                "--repeat-judge-evaluation-dir",
                str(repeat),
                "--repeat-comparison-ids",
                str(repeat_ids_path),
                "--order-judge-evaluation-dir",
                str(order),
                "--order-comparison-ids",
                str(order_ids_path),
                "--second-judge-evaluation-dir",
                str(second),
                "--second-comparison-ids",
                str(second_ids_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    checks = {row["check"]: row for row in report["checks"]}
    assert checks["duplicate_consistency"]["status"] == "complete"
    assert checks["position_order_consistency"]["coverage_complete"] is True
    assert checks["second_judge_consistency"]["coverage_complete"] is True
    assert checks["position_order_consistency"]["consistency_rate"] == 1.0
    assert checks["second_judge_consistency"]["consistency_rate"] == 1.0
