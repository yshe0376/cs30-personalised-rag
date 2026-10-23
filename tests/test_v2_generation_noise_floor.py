"""Paired repeated-generation noise-floor tests."""

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.v2_generation_models import ExperimentArm
from cs30.evaluation.v2_generation_reporting import (
    paired_generation_noise_floor,
    write_v2_generation_report,
)


def _rows(*, repeated: bool) -> list[dict[str, object]]:
    rows = []
    for question_index in range(30):
        for level in StudentLevel:
            for condition in ExperimentArm:
                flipped = repeated and question_index == 0 and level is StudentLevel.BEGINNER
                rows.append(
                    {
                        "run_id": f"q{question_index}-{level.value}-{condition.value}",
                        "question_id": f"q{question_index}",
                        "target_level": level.value,
                        "condition": condition.value,
                        "generation_model_family": "gpt-oss",
                        "generation_model_revision": "gpt-oss:20b",
                        "correctness_score": 1 if flipped else 2,
                        "adaptation_criterion_pass_rate": 0.5 if flipped else 1.0,
                        "adaptation_passed": not flipped,
                    }
                )
    return rows


def test_paired_noise_floor_reports_differences_flips_and_twelve_groups() -> None:
    result = paired_generation_noise_floor(
        _rows(repeated=False),
        _rows(repeated=True),
        correctness_delta=0.1,
    )

    assert result["status"] == "complete"
    assert result["question_count"] == 30
    assert result["pair_count"] == 360
    assert len(result["by_condition_and_level"]) == 12
    assert result["overall"]["correct_flip_count"] == 4
    assert result["overall"]["adaptation_pass_flip_count"] == 4
    assert result["overall"]["correctness_score_difference"][
        "mean_absolute_difference"
    ] == pytest.approx(4 / 360)
    floor = result["strict_correct_noise_floor"]
    assert floor["status"] == "complete"
    # Each condition has 90 paired cells and one of them flips from 2 to 1.
    assert floor["value"] == pytest.approx(1 / 90)
    for row in floor["by_condition"]:
        assert row["strict_correct_rate_difference"] == pytest.approx(-1 / 90)
        assert row["correct_flip_rate"] >= row["absolute_strict_correct_rate_difference"]
    assert result["delta_exceeds_strict_correct_noise_floor"] is True
    assert "cannot replace" in result["interpretation"]


def test_delta_below_noise_floor_is_reported_as_not_exceeding() -> None:
    result = paired_generation_noise_floor(
        _rows(repeated=False),
        _rows(repeated=True),
        correctness_delta=0.005,
    )

    assert result["delta_exceeds_strict_correct_noise_floor"] is False


def test_paired_noise_floor_rejects_anything_other_than_thirty_complete_questions() -> None:
    with pytest.raises(ValueError, match="30 questions x 12 cells"):
        paired_generation_noise_floor(_rows(repeated=False), _rows(repeated=True)[:-1])


def test_unresolved_outcomes_stay_in_denominator_and_withhold_the_floor() -> None:
    repeated = _rows(repeated=True)
    repeated[0]["correctness_score"] = None
    repeated[0]["adaptation_passed"] = None

    result = paired_generation_noise_floor(
        _rows(repeated=False), repeated, correctness_delta=0.1
    )

    assert result["status"] == "incomplete"
    assert result["pair_count"] == 360
    assert result["overall"]["unresolved_correctness_pair_count"] == 1
    assert result["overall"]["unresolved_adaptation_pair_count"] == 1
    floor = result["strict_correct_noise_floor"]
    assert floor["status"] == "incomplete"
    assert floor["value"] is None
    affected = next(
        row for row in floor["by_condition"] if row["condition"] == repeated[0]["condition"]
    )
    assert affected["repeat"]["denominator"] == 90
    assert affected["repeat"]["unresolved_count"] == 1
    assert affected["repeat"]["strict_correct_rate"] is None
    lower, upper = affected["repeat"]["strict_correct_rate_bounds"]
    assert upper - lower == pytest.approx(1 / 90)
    assert result["delta_exceeds_strict_correct_noise_floor"] is None


def test_paired_noise_floor_rejects_scores_outside_zero_one_two() -> None:
    repeated = _rows(repeated=True)
    repeated[0]["correctness_score"] = 3
    with pytest.raises(ValueError, match="0, 1, 2, or null"):
        paired_generation_noise_floor(_rows(repeated=False), repeated)


def test_markdown_report_shows_the_noise_floor_and_how_to_use_it(tmp_path) -> None:
    noise = paired_generation_noise_floor(
        _rows(repeated=False), _rows(repeated=True), correctness_delta=0.1
    )
    keys = (
        "registered_analysis",
        "automatic_full_run",
        "judge_validity",
        "human_audit",
        "condition_contrasts",
        "lambda_evaluation",
        "unresolved_items",
        "limitations",
    )
    report = {
        "mode": "development",
        "reportable": False,
        "claim_boundary": "test",
        **{key: None for key in keys},
        "condition_contrasts": [],
        "decision_config": None,
        "provenance": None,
        "diagnostics": {"generation_noise_floor": {"paired_repeat_batch": noise}},
    }

    paths = write_v2_generation_report(report, tmp_path)
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert "## Generation noise floor" in markdown
    assert "δ must exceed" in markdown
    assert '"delta_exceeds_strict_correct_noise_floor": true' in markdown
