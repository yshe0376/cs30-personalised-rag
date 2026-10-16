from __future__ import annotations

from cs30.contracts import StudentLevel
from cs30.evaluation.condition_statistics import (
    MetricObservation,
    correctness_noninferiority,
    evaluate_lambda_candidates,
    paired_condition_contrasts,
)
from cs30.evaluation.judge_validity import (
    ValidityThresholds,
    build_validity_report,
    duplicate_consistency_check,
    p0r0_level_bias_check,
)
from cs30.evaluation.v2_generation_models import ExperimentArm, LevelGuess


def test_p0r0_bias_reports_uncertain_separately_from_decided_chance_rates() -> None:
    guesses = [
        LevelGuess.BEGINNER,
        LevelGuess.INTERMEDIATE,
        LevelGuess.ADVANCED,
        LevelGuess.UNCERTAIN,
    ]
    result = p0r0_level_bias_check(guesses, max_chance_deviation=0.01)
    assert result["passed"] is True
    assert result["uncertain_rate"] == 0.25
    assert result["decided_guess_rates"] == {
        "beginner": 1 / 3,
        "intermediate": 1 / 3,
        "advanced": 1 / 3,
    }


def test_duplicate_consistency_detects_conflicting_outputs() -> None:
    result = duplicate_consistency_check(
        [
            ("q-1", "answer-a", "output-1"),
            ("q-1", "answer-a", "output-2"),
            ("q-2", "answer-b", "output-3"),
            ("q-2", "answer-b", "output-3"),
        ],
        min_consistency=1.0,
    )
    assert result["passed"] is False
    assert result["consistency_rate"] == 0.5


def test_validity_report_fails_closed_when_a_required_check_is_missing() -> None:
    thresholds = ValidityThresholds(
        threshold_version="thresholds-v1",
        p0r0_max_chance_deviation=0.4,
        duplicate_min_consistency=1.0,
        max_abs_length_correlation=1.0,
        max_formula_pass_rate_gap=1.0,
        order_min_consistency=1.0,
        second_judge_min_consistency=1.0,
        perturbation_min_detection_rate=0.8,
    )
    report = build_validity_report(
        thresholds,
        p0r0_guesses=[
            LevelGuess.BEGINNER,
            LevelGuess.INTERMEDIATE,
            LevelGuess.ADVANCED,
        ],
        duplicate_rows=[],
        surface_rows=[
            (StudentLevel.BEGINNER, True, 10, False),
            (StudentLevel.BEGINNER, False, 20, True),
            (StudentLevel.BEGINNER, True, 30, False),
        ],
        order_pairs=[("case-1", "same", "same")],
        second_judge_pairs=[("case-1", "same", "same")],
    )
    assert report["formal_use_allowed"] is False
    assert "duplicate_consistency" in report["failed_or_missing_required_checks"]


def _observations() -> list[MetricObservation]:
    values = {
        ExperimentArm.P0R0_PLAIN: 0.50,
        ExperimentArm.P1R0_PROMPT_ONLY: 0.60,
        ExperimentArm.P0R1_RERANKING_ONLY: 0.55,
        ExperimentArm.P1R1_COMBINED: 0.70,
    }
    return [
        MetricObservation(
            question_id=question,
            target_level=level,
            condition=condition,
            metric="adaptation",
            value=value,
        )
        for question in ("q-1", "q-2", "q-3")
        for level in StudentLevel
        for condition, value in values.items()
    ]


def test_condition_statistics_pair_by_level_and_bootstrap_question_clusters() -> None:
    results = paired_condition_contrasts(
        _observations(),
        bootstrap_draws=100,
        bootstrap_seed=7,
    )
    prompt = next(row for row in results if row["contrast"] == "prompt_without_reranking")
    assert round(prompt["estimate"], 8) == 0.1
    assert prompt["paired_question_level_count"] == 9
    assert prompt["question_cluster_count"] == 3
    assert prompt["missing_pair_count"] == 0
    noninferiority = correctness_noninferiority(prompt, delta=0.05)
    assert noninferiority["passed"] is True


def test_lambda_evidence_uses_relevance_and_correctness_gates_and_smaller_tie() -> None:
    result = evaluate_lambda_candidates(
        complete_hit_rates={0.0: 0.827, 0.1: 0.823, 0.2: 0.821},
        adaptation_improvements={0.1: 0.05, 0.2: 0.05},
        correctness_lower_bounds={0.1: -0.01, 0.2: -0.02},
        predeclared_positive_lambdas=[0.1, 0.2],
        epsilon=0.02,
        delta=0.03,
        sensitivity_lambda=0.2,
    )
    assert result["recommended_lambda"] == 0.1
    assert result["successful_reranking_improvement"] is True


def test_lambda_evidence_reports_no_success_instead_of_forcing_a_choice() -> None:
    result = evaluate_lambda_candidates(
        complete_hit_rates={0.0: 0.827, 0.1: 0.70, 0.2: 0.69},
        adaptation_improvements={0.1: 0.1, 0.2: 0.2},
        correctness_lower_bounds={0.1: -0.01, 0.2: -0.01},
        predeclared_positive_lambdas=[0.1, 0.2],
        epsilon=0.02,
        delta=0.03,
        sensitivity_lambda=0.1,
    )
    assert result["recommended_lambda"] is None
    assert result["successful_reranking_improvement"] is False
