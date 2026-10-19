from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.v2_generation_cli import main
from cs30.evaluation.v2_generation_models import ExperimentArm


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
        provenance={**shared_provenance, "judge_execution_id": "primary-run"},
    )
    _write_judge_evaluation_dir(
        repeat,
        rows=_rows_for_evaluation_ids(result_rows, repeat_ids),
        provenance={**shared_provenance, "judge_execution_id": "repeat-run"},
    )
    _write_judge_evaluation_dir(
        order,
        rows=_rows_for_evaluation_ids(result_rows, order_ids),
        provenance={
            **shared_provenance,
            "judge_execution_id": "order-run",
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
