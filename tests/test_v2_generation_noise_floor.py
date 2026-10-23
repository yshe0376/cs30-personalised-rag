"""Paired repeated-generation noise-floor tests."""

import math

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.v2_generation_models import ExperimentArm
from cs30.evaluation.v2_generation_reporting import (
    paired_generation_noise_floor,
    write_v2_generation_report,
)

MAIN = {
    "contrast": "prompt_without_reranking",
    "conditions": [ExperimentArm.P1R0_PROMPT_ONLY.value, ExperimentArm.P0R0_PLAIN.value],
    "paired_cell_count": 462,
}


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
                        "adaptation_applicable": True,
                    }
                )
    return rows


def test_floor_is_sqrt_of_flip_rate_over_main_comparison_cells() -> None:
    result = paired_generation_noise_floor(
        _rows(repeated=False),
        _rows(repeated=True),
        correctness_delta=0.1,
        main_comparison=MAIN,
        adaptation_threshold_frozen=True,
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
    # One flip in each of the two main-contrast conditions: 2 of their 180 cells.
    assert floor["flip_rate"]["rate"] == pytest.approx(2 / 180)
    assert floor["value"] == pytest.approx(math.sqrt((2 / 180) / 462))
    assert floor["bounds"][0] == floor["bounds"][1] == pytest.approx(floor["value"])
    assert result["delta_exceeds_strict_correct_noise_floor"] is True
    assert result["adaptation"]["status"] == "complete"
    assert "cannot replace" in result["interpretation"]


def test_opposite_flips_do_not_cancel() -> None:
    """The Leader's counter-example: 20% of cells flip, half up and half down."""

    baseline = _rows(repeated=False)
    repeated = _rows(repeated=False)
    for rows in (baseline, repeated):
        for row in rows:
            row["correctness_score"] = 2
    for condition in ExperimentArm:
        cells = [row for row in repeated if row["condition"] == condition.value]
        base_cells = [row for row in baseline if row["condition"] == condition.value]
        for index in range(18):  # 18 of 90 cells = 20%
            if index % 2:
                cells[index]["correctness_score"] = 0  # right -> wrong
            else:
                base_cells[index]["correctness_score"] = 0  # wrong -> right

    result = paired_generation_noise_floor(
        baseline, repeated, correctness_delta=0.01, main_comparison=MAIN
    )

    for row in result["by_condition"]:
        assert row["strict_correct_rate_difference"] == pytest.approx(0)
    floor = result["strict_correct_noise_floor"]
    assert floor["flip_rate"]["rate"] == pytest.approx(0.2)
    assert floor["value"] == pytest.approx(math.sqrt(0.2 / 462))
    assert floor["value"] > 0.02
    assert result["delta_exceeds_strict_correct_noise_floor"] is False


def test_unresolved_correctness_reports_bounds_and_withholds_comparison() -> None:
    repeated = _rows(repeated=True)
    target = next(row for row in repeated if row["condition"] == MAIN["conditions"][0])
    target["correctness_score"] = None

    result = paired_generation_noise_floor(
        _rows(repeated=False), repeated, correctness_delta=0.1, main_comparison=MAIN
    )

    assert result["status"] == "incomplete"
    assert result["pair_count"] == 360
    floor = result["strict_correct_noise_floor"]
    assert floor["value"] is None
    assert floor["flip_rate"]["unresolved_count"] == 1
    assert floor["flip_rate"]["denominator"] == 180
    lower, upper = floor["bounds"]
    assert lower < upper
    assert result["overall"]["correctness_pairs"]["not_evaluated"] == 1
    assert result["delta_exceeds_strict_correct_noise_floor"] is None


def test_not_applicable_adaptation_does_not_hold_correctness_open() -> None:
    baseline = _rows(repeated=False)
    repeated = _rows(repeated=True)
    for rows in (baseline, repeated):
        rows[5]["adaptation_applicable"] = False  # abstained or technical failure
        rows[5]["adaptation_criterion_pass_rate"] = None
        rows[5]["adaptation_passed"] = None

    result = paired_generation_noise_floor(
        baseline,
        repeated,
        correctness_delta=0.1,
        main_comparison=MAIN,
        adaptation_threshold_frozen=True,
    )

    assert result["status"] == "complete"
    assert result["adaptation"]["status"] == "complete"
    assert result["adaptation"]["criterion_rate_pairs"]["not_applicable"] == 1
    assert result["adaptation"]["criterion_rate_pairs"]["not_evaluated"] == 0


def test_unscored_adaptation_is_counted_as_not_evaluated() -> None:
    repeated = _rows(repeated=True)
    repeated[5]["adaptation_criterion_pass_rate"] = None

    result = paired_generation_noise_floor(
        _rows(repeated=False),
        repeated,
        main_comparison=MAIN,
        adaptation_threshold_frozen=True,
    )

    assert result["status"] == "complete"
    assert result["adaptation"]["status"] == "incomplete"
    assert result["adaptation"]["criterion_rate_pairs"]["not_evaluated"] == 1


def test_unfrozen_threshold_marks_pass_flips_not_applicable() -> None:
    baseline = _rows(repeated=False)
    repeated = _rows(repeated=True)
    for rows in (baseline, repeated):
        for row in rows:
            row["adaptation_passed"] = None

    result = paired_generation_noise_floor(baseline, repeated, main_comparison=MAIN)

    assert result["status"] == "complete"
    assert result["adaptation"]["status"] == "threshold_not_frozen"
    assert result["adaptation"]["pass_pairs"]["not_applicable"] == 360
    assert result["overall"]["adaptation_pass_flip_rate"] is None


def test_floor_waits_for_the_main_comparison_size() -> None:
    result = paired_generation_noise_floor(
        _rows(repeated=False), _rows(repeated=True), correctness_delta=0.1
    )

    assert result["status"] == "awaiting_main_comparison"
    assert result["strict_correct_noise_floor"]["value"] is None
    assert result["delta_exceeds_strict_correct_noise_floor"] is None


def test_unknown_main_comparison_condition_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown conditions"):
        paired_generation_noise_floor(
            _rows(repeated=False),
            _rows(repeated=True),
            main_comparison={**MAIN, "conditions": ["P9R9"]},
        )


def test_main_comparison_requires_two_conditions_and_positive_cell_count() -> None:
    with pytest.raises(ValueError, match="two distinct conditions"):
        paired_generation_noise_floor(
            _rows(repeated=False),
            _rows(repeated=True),
            main_comparison={**MAIN, "conditions": [MAIN["conditions"][0]]},
        )
    with pytest.raises(ValueError, match="positive integer"):
        paired_generation_noise_floor(
            _rows(repeated=False),
            _rows(repeated=True),
            main_comparison={**MAIN, "paired_cell_count": 0},
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("correctness_score", True, "0, 1, 2, or null"),
        ("adaptation_criterion_pass_rate", "0.5", "numeric or null"),
        ("adaptation_passed", "false", "boolean or null"),
        ("adaptation_applicable", "false", "must be a boolean"),
    ],
)
def test_noise_floor_rejects_coerced_outcome_types(
    field: str, value: object, message: str
) -> None:
    repeated = _rows(repeated=True)
    repeated[0][field] = value
    with pytest.raises(ValueError, match=message):
        paired_generation_noise_floor(_rows(repeated=False), repeated, main_comparison=MAIN)


def test_paired_noise_floor_rejects_anything_other_than_thirty_complete_questions() -> None:
    with pytest.raises(ValueError, match="30 questions x 12 cells"):
        paired_generation_noise_floor(_rows(repeated=False), _rows(repeated=True)[:-1])


def test_paired_noise_floor_rejects_scores_outside_zero_one_two() -> None:
    repeated = _rows(repeated=True)
    repeated[0]["correctness_score"] = 3
    with pytest.raises(ValueError, match="0, 1, 2, or null"):
        paired_generation_noise_floor(_rows(repeated=False), repeated)


def test_markdown_report_shows_the_noise_floor_and_how_to_use_it(tmp_path) -> None:
    noise = paired_generation_noise_floor(
        _rows(repeated=False),
        _rows(repeated=True),
        correctness_delta=0.1,
        main_comparison=MAIN,
    )
    keys = (
        "registered_analysis",
        "automatic_full_run",
        "judge_validity",
        "human_audit",
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
    assert "delta must exceed" in markdown
    assert '"delta_exceeds_strict_correct_noise_floor": true' in markdown
