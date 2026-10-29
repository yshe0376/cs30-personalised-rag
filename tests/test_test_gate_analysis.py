"""Synthetic offline tests of the #224 reporting rules, not research findings."""

import copy

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation import test_gate_analysis as analysis
from cs30.evaluation.v2_generation_models import ExperimentArm, GenerationEvaluationInput


def fixtures(questions=4, family="openai/gpt-oss-20b"):
    items, scores, rows = [], {}, []
    names = {
        "beginner": ["B1", "B2", "B3", "B4"],
        "intermediate": ["I1", "I2", "I3"],
        "advanced": ["A1", "A2", "A3", "A4"],
    }
    for q in range(questions):
        for level in StudentLevel:
            for arm in ExperimentArm:
                eid = f"e-{q}-{level.value}-{arm.value}"
                item = GenerationEvaluationInput(
                    evaluation_id=eid,
                    run_id=eid,
                    question_id=f"q-{q}",
                    question="Fixture question",
                    answer="Fixture answer",
                    target_level=level,
                    condition=arm,
                    lambda_weight=0.1,
                    generation_model_family=family,
                    generation_model_revision="fixture",
                    source_split="test",
                    source_artifact_sha256="a" * 64,
                    source_run_sha256="b" * 64,
                    eligibility="endpoint_only",
                )
                items.append(item)
                scores[eid] = 2
                rows.append(
                    {
                        "evaluation_id": eid,
                        "question_id": item.question_id,
                        "condition": arm.value,
                        "target_level": level.value,
                        "evaluated_level": level.value,
                        "is_target_level_evaluation": True,
                        "criteria": [
                            {"criterion_id": c, "verdict": "pass"} for c in names[level.value]
                        ],
                    }
                )
    return items, scores, rows


def test_i3_is_preserved_but_excluded_from_main_and_joint_rule():
    row = {
        "evaluated_level": "intermediate",
        "criteria": [
            {"criterion_id": "I1", "verdict": "pass"},
            {"criterion_id": "I2", "verdict": "pass"},
            {"criterion_id": "I3", "verdict": "fail"},
        ],
    }
    before = copy.deepcopy(row)
    result = analysis.main_adaptation(row)
    assert result["main_criterion_pass_rate"] == 1
    assert result["main_all_applicable_passed"] is True
    assert result["reference_only_i3"] == "fail"
    assert row == before


def test_all_applicable_pass_means_all_not_a_loose_threshold():
    row = {
        "evaluated_level": "beginner",
        "criteria": [
            {"criterion_id": k, "verdict": v}
            for k, v in zip(
                ["B1", "B2", "B3", "B4"], ["pass", "pass", "not_applicable", "fail"], strict=True
            )
        ],
    }
    assert analysis.main_adaptation(row)["main_all_applicable_passed"] is False


def test_required_na_and_duplicate_criteria_are_rejected():
    row = fixtures()[2][0]
    row["criteria"][0]["verdict"] = "not_applicable"
    with pytest.raises(ValueError, match="always-assessed"):
        analysis.main_adaptation(row)
    row["criteria"][0]["verdict"] = "pass"
    row["criteria"].append(row["criteria"][0])
    with pytest.raises(ValueError, match="coverage"):
        analysis.main_adaptation(row)


def test_holm_uses_cumulative_max_and_two_test_family():
    assert analysis.holm_adjust({"beginner": 0.03, "advanced": 0.04}) == {
        "beginner": 0.06,
        "advanced": 0.06,
    }
    assert analysis.holm_adjust({"beginner": 0.01, "advanced": 0.04}) == {
        "beginner": 0.02,
        "advanced": 0.04,
    }
    with pytest.raises(ValueError):
        analysis.holm_adjust({"beginner": float("nan")})


def test_question_clusters_keep_all_levels_together_and_repeat_deterministically():
    result = analysis.cluster_interval({"q1": [1, -1, 0], "q2": [1, -1, 0]}, draws=100)
    assert result["estimate"] == result["ci_lower"] == result["ci_upper"] == 0
    assert result["question_cluster_count"] == 2 and result["paired_cell_count"] == 6
    assert result == analysis.cluster_interval({"q1": [1, -1, 0], "q2": [1, -1, 0]}, draws=100)


def test_system_failures_are_zero_while_judge_unknowns_are_bounded():
    items, scores, rows = fixtures()
    failure = next(i for i in items if i.condition is analysis.TREATMENT)
    index = items.index(failure)
    items[index] = failure.model_copy(
        update={
            "technical_failure": True,
            "answer": None,
            "source_status": "generation_error",
            "failure_reason": "fixture",
        }
    )
    scores[failure.evaluation_id] = 0
    unknown = next(
        i
        for i in items
        if i.condition is analysis.TREATMENT and i.evaluation_id != failure.evaluation_id
    )
    scores[unknown.evaluation_id] = None
    rows = [r for r in rows if r["evaluation_id"] != failure.evaluation_id]
    result = analysis.registered_analysis(items, scores, rows, draws=100)
    ni = result["correctness_noninferiority"]
    assert ni["unresolved_pairs"] == 1
    assert ni["worst_case"]["estimate"] < ni["best_case"]["estimate"]
    assert ni["supported_at_both_bounds"] is False
    coverage = result["coverage_by_condition"][analysis.TREATMENT.value]
    assert coverage["generation_failures"] == coverage["answered_unscored"] == 1
    assert coverage["cells"] == 12 and coverage["answered"] == 11
    assert coverage["answered_only_strict_correct_bounds"] == [10 / 11, 1]


@pytest.mark.parametrize("family", ["google/gemma-3-12b", "openai/gpt-oss-120b"])
def test_comparison_models_remain_exploratory(family):
    result = analysis.registered_analysis(*fixtures(family=family), draws=100)
    assert all(not r["co_primary"] for r in result["adaptation_endpoints"])
    assert result["correctness_noninferiority"]["supported_at_both_bounds"] is False


def test_missing_endpoint_does_not_shrink_holm_family(monkeypatch):
    items, scores, rows = fixtures()
    rows = [r for r in rows if r["target_level"] != "advanced"]
    monkeypatch.setattr(
        analysis,
        "cluster_interval",
        lambda *a, **k: {"estimate": 0.1, "p_value": 0.04, "ci_lower": 0, "ci_upper": 0.2},
    )
    result = analysis.registered_analysis(items, scores, rows)
    b, a = result["adaptation_endpoints"]
    assert b["holm_adjusted_p"] == 0.08 and a["holm_adjusted_p"] is None


def test_noise_floor_is_required_and_blocks_small_differences(monkeypatch):
    monkeypatch.setattr(
        analysis,
        "cluster_interval",
        lambda *a, **k: {"estimate": 0.02, "p_value": 0.001, "ci_lower": 0.01, "ci_upper": 0.03},
    )
    result = analysis.registered_analysis(*fixtures())
    assert all(r["statistically_positive"] for r in result["adaptation_endpoints"])
    assert not any(r["positive_effect_supported"] for r in result["adaptation_endpoints"])
    result = analysis.registered_analysis(
        *fixtures(), adaptation_noise_floors={"beginner": 0.03, "advanced": 0.01}
    )
    assert [r["positive_effect_supported"] for r in result["adaptation_endpoints"]] == [False, True]


def test_changed_metadata_and_duplicate_cells_fail_closed():
    items, scores, rows = fixtures()
    rows[0]["condition"] = "wrong"
    with pytest.raises(ValueError, match="bound input"):
        analysis.registered_analysis(items, scores, rows)
    with pytest.raises(ValueError, match="unique evaluation"):
        analysis.registered_analysis(items + [items[0]], scores, [])
