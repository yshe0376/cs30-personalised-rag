from __future__ import annotations

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.condition_statistics import (
    MetricObservation,
    correctness_noninferiority,
    paired_condition_contrasts,
    verify_dev_lambda_selection,
)
from cs30.evaluation.judge_validity import (
    ValidityThresholds,
    build_validity_report,
    duplicate_consistency_check,
    p0r0_level_bias_check,
    semantic_judge_agreement,
    semantic_judge_signature,
)
from cs30.evaluation.v2_generation_models import ExperimentArm, LevelGuess


def test_p0r0_bias_reports_uncertain_separately_from_decided_chance_rates() -> None:
    rows = [
        (StudentLevel.BEGINNER, LevelGuess.BEGINNER),
        (StudentLevel.BEGINNER, LevelGuess.UNCERTAIN),
        (StudentLevel.INTERMEDIATE, LevelGuess.ADVANCED),
        (StudentLevel.INTERMEDIATE, LevelGuess.INTERMEDIATE),
        (StudentLevel.ADVANCED, LevelGuess.INTERMEDIATE),
        (StudentLevel.ADVANCED, LevelGuess.UNCERTAIN),
    ]
    result = p0r0_level_bias_check(
        rows,
        max_chance_deviation=0.1,
        min_case_count=3,
    )
    assert result["accuracy"] == 1 / 3
    assert result["passed"] is True
    assert result["uncertain_rate"] == 1 / 3
    assert result["decided_guess_rates"] == {
        "beginner": 0.25,
        "intermediate": 0.5,
        "advanced": 0.25,
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
        min_group_count=2,
    )
    assert result["passed"] is False
    assert result["consistency_rate"] == 0.5


def test_semantic_judge_comparison_ignores_reason_wording_and_criterion_order() -> None:
    first = {
        "criteria": [
            {"criterion_id": "B1", "verdict": "pass", "reason": "first wording"},
            {"criterion_id": "B2", "verdict": "fail", "reason": "first wording"},
        ]
    }
    second = {
        "criteria": [
            {"criterion_id": "B2", "verdict": "fail", "reason": "different wording"},
            {"criterion_id": "B1", "verdict": "pass", "reason": "different wording"},
        ]
    }
    assert semantic_judge_signature("adaptation", first) == semantic_judge_signature(
        "adaptation", second
    )
    assert semantic_judge_agreement(
        "adaptation", first, second, evidence_rate_tolerance=0.0
    )


def test_second_judge_evidence_comparison_uses_registered_rate_tolerance() -> None:
    first = {"bundle_faithfulness": 0.8, "citation_support": 0.7}
    close = {"bundle_faithfulness": 0.75, "citation_support": 0.65}
    far = {"bundle_faithfulness": 0.5, "citation_support": 0.7}
    assert semantic_judge_agreement(
        "evidence_support", first, close, evidence_rate_tolerance=0.1
    )
    assert not semantic_judge_agreement(
        "evidence_support", first, far, evidence_rate_tolerance=0.1
    )


def test_validity_checks_reject_tiny_samples_even_when_every_pair_agrees() -> None:
    thresholds = ValidityThresholds(
        threshold_version="thresholds-v1",
        p0r0_max_chance_deviation=0.4,
        duplicate_min_consistency=1.0,
        max_abs_length_correlation=1.0,
        max_formula_pass_rate_gap=1.0,
        order_min_consistency=1.0,
        second_judge_min_consistency=1.0,
        perturbation_min_detection_rate=0.8,
        p0r0_min_case_count=6,
        duplicate_min_group_count=2,
        surface_min_rows_per_level=3,
        order_min_case_count=2,
        second_judge_min_case_count=2,
        perturbation_min_case_count=2,
        second_judge_max_evidence_rate_gap=0.1,
    )
    report = build_validity_report(
        thresholds,
        p0r0_rows=[
            (StudentLevel.BEGINNER, LevelGuess.BEGINNER),
            (StudentLevel.INTERMEDIATE, LevelGuess.ADVANCED),
            (StudentLevel.ADVANCED, LevelGuess.INTERMEDIATE),
        ],
        duplicate_rows=[("q-1", "answer", "same"), ("q-1", "answer", "same")],
        surface_rows=[],
        order_pairs=[("case-1", "same", "same")],
        second_judge_pairs=[("case-1", "same", "same")],
        order_coverage_complete=True,
        second_judge_coverage_complete=True,
        order_case_count=1,
        second_judge_case_count=1,
    )
    assert report["formal_use_allowed"] is False
    checks = {row["check"]: row for row in report["checks"]}
    assert checks["p0r0_level_bias"]["status"] == "insufficient_data"
    assert checks["duplicate_consistency"]["status"] == "insufficient_data"
    assert checks["position_order_consistency"]["status"] == "insufficient_data"
    assert checks["second_judge_consistency"]["status"] == "insufficient_data"


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
        p0r0_min_case_count=3,
        duplicate_min_group_count=1,
        surface_min_rows_per_level=3,
        order_min_case_count=1,
        second_judge_min_case_count=1,
        perturbation_min_case_count=1,
        second_judge_max_evidence_rate_gap=0.1,
    )
    report = build_validity_report(
        thresholds,
        p0r0_rows=[
            (StudentLevel.BEGINNER, LevelGuess.BEGINNER),
            (StudentLevel.INTERMEDIATE, LevelGuess.ADVANCED),
            (StudentLevel.ADVANCED, LevelGuess.INTERMEDIATE),
        ],
        duplicate_rows=[],
        surface_rows=[
            (StudentLevel.BEGINNER, True, 10, False),
            (StudentLevel.BEGINNER, False, 20, True),
            (StudentLevel.BEGINNER, True, 30, False),
        ],
        order_pairs=[("case-1", "same", "same")],
        second_judge_pairs=[("case-1", "same", "same")],
        order_coverage_complete=True,
        second_judge_coverage_complete=True,
        order_case_count=1,
        second_judge_case_count=1,
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


def test_lambda_verification_uses_only_the_frozen_retrieval_rule() -> None:
    result = verify_dev_lambda_selection(
        complete_hit_rates={0.0: 0.827, 0.1: 0.823, 0.2: 0.821, 0.25: 0.815},
        selected_lambda=0.2,
    )
    assert result["selected_lambda"] == 0.2
    assert result["judge_scores_used_for_selection"] is False
    assert (
        next(row for row in result["candidates"] if row["lambda"] == 0.25)["passes_retrieval_rule"]
        is False
    )


def test_lambda_verification_rejects_no_eligible_positive_candidate() -> None:
    with pytest.raises(ValueError, match="no positive lambda"):
        verify_dev_lambda_selection(
            complete_hit_rates={0.0: 0.827, 0.1: 0.70, 0.2: 0.69},
            selected_lambda=0.1,
        )
