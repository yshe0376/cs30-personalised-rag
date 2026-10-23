"""Paired repeated-generation noise-floor tests."""

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.v2_generation_models import ExperimentArm
from cs30.evaluation.v2_generation_reporting import paired_generation_noise_floor


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
    assert result["delta_exceeds_mean_absolute_correctness_difference"] is True
    assert "cannot replace" in result["interpretation"]


def test_paired_noise_floor_rejects_anything_other_than_thirty_complete_questions() -> None:
    with pytest.raises(ValueError, match="30 questions x 12 cells"):
        paired_generation_noise_floor(_rows(repeated=False), _rows(repeated=True)[:-1])


def test_paired_noise_floor_rejects_unresolved_outcomes() -> None:
    repeated = _rows(repeated=True)
    repeated[0]["correctness_score"] = None
    with pytest.raises(ValueError, match="must be resolved"):
        paired_generation_noise_floor(_rows(repeated=False), repeated)
