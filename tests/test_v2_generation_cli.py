from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.v2_generation_cli import main
from cs30.evaluation.v2_generation_models import ExperimentArm


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
                },
                "p0r0_guesses": ["beginner", "intermediate", "advanced"],
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
