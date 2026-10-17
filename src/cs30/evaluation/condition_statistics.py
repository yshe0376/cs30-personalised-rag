"""Question-paired condition effects, clustered uncertainty, and lambda evidence tables."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import Field

from cs30.contracts import StudentLevel
from cs30.contracts.models import ContractModel, Identifier

from .v2_generation_models import ExperimentArm

CONTRASTS: dict[str, tuple[ExperimentArm, ExperimentArm]] = {
    "prompt_without_reranking": (
        ExperimentArm.P1R0_PROMPT_ONLY,
        ExperimentArm.P0R0_PLAIN,
    ),
    "prompt_with_reranking": (
        ExperimentArm.P1R1_COMBINED,
        ExperimentArm.P0R1_RERANKING_ONLY,
    ),
    "reranking_without_prompt": (
        ExperimentArm.P0R1_RERANKING_ONLY,
        ExperimentArm.P0R0_PLAIN,
    ),
    "reranking_with_prompt": (
        ExperimentArm.P1R1_COMBINED,
        ExperimentArm.P1R0_PROMPT_ONLY,
    ),
}


class MetricObservation(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    question_id: Identifier
    target_level: StudentLevel
    condition: ExperimentArm
    metric: Identifier
    value: float = Field(allow_inf_nan=False)


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile of an empty sequence")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _cluster_bootstrap(
    differences: Mapping[str, Sequence[float]],
    *,
    draws: int,
    seed: int,
    confidence: float,
) -> dict[str, float | int]:
    if draws < 1:
        raise ValueError("bootstrap draws must be positive")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    clusters = sorted(differences)
    if not clusters:
        raise ValueError("cluster bootstrap requires at least one question")
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(draws):
        sampled = [rng.choice(clusters) for _ in clusters]
        values = [value for question_id in sampled for value in differences[question_id]]
        estimates.append(sum(values) / len(values))
    alpha = (1 - confidence) / 2
    return {
        "draws": draws,
        "seed": seed,
        "confidence": confidence,
        "lower": _percentile(estimates, alpha),
        "upper": _percentile(estimates, 1 - alpha),
    }


def paired_condition_contrasts(
    observations: Iterable[MetricObservation],
    *,
    bootstrap_draws: int = 2000,
    bootstrap_seed: int = 5703,
    confidence: float = 0.95,
) -> list[dict[str, Any]]:
    """Pair by question and level, then resample complete question clusters."""

    by_metric: dict[str, dict[tuple[str, StudentLevel, ExperimentArm], float]] = defaultdict(dict)
    for observation in observations:
        key = (observation.question_id, observation.target_level, observation.condition)
        if key in by_metric[observation.metric]:
            raise ValueError(
                "duplicate metric observation for question/level/condition: "
                f"{observation.metric}/{key}"
            )
        by_metric[observation.metric][key] = observation.value

    results: list[dict[str, Any]] = []
    for metric in sorted(by_metric):
        values = by_metric[metric]
        for contrast_name, (treatment, control) in CONTRASTS.items():
            differences: dict[str, list[float]] = defaultdict(list)
            all_question_levels = sorted(
                {(question_id, level) for question_id, level, _ in values},
                key=lambda item: (item[0], item[1].value),
            )
            missing: list[dict[str, str]] = []
            for question_id, level in all_question_levels:
                treatment_key = (question_id, level, treatment)
                control_key = (question_id, level, control)
                if treatment_key not in values or control_key not in values:
                    missing.append({"question_id": question_id, "target_level": level.value})
                    continue
                differences[question_id].append(values[treatment_key] - values[control_key])
            flattened = [value for rows in differences.values() for value in rows]
            estimate = sum(flattened) / len(flattened) if flattened else None
            interval = (
                _cluster_bootstrap(
                    differences,
                    draws=bootstrap_draws,
                    seed=bootstrap_seed,
                    confidence=confidence,
                )
                if flattened
                else None
            )
            results.append(
                {
                    "metric": metric,
                    "contrast": contrast_name,
                    "treatment": treatment.value,
                    "control": control.value,
                    "estimate": estimate,
                    "paired_question_level_count": len(flattened),
                    "question_cluster_count": len(differences),
                    "missing_pair_count": len(missing),
                    "missing_pairs": missing,
                    "cluster_bootstrap": interval,
                }
            )
    return results


def correctness_noninferiority(
    contrast: Mapping[str, Any],
    *,
    delta: float,
) -> dict[str, Any]:
    """Pass only when the clustered lower bound is strictly above `-delta`."""

    if not 0 <= delta <= 1:
        raise ValueError("delta must be between zero and one")
    interval = contrast.get("cluster_bootstrap")
    if not isinstance(interval, Mapping) or interval.get("lower") is None:
        return {
            "status": "unresolved",
            "delta": delta,
            "margin": -delta,
            "passed": False,
            "reason": "clustered lower bound is unavailable",
        }
    lower = float(interval["lower"])
    return {
        "status": "complete",
        "delta": delta,
        "margin": -delta,
        "lower_bound": lower,
        "passed": lower > -delta,
    }


def evaluate_lambda_candidates(
    *,
    complete_hit_rates: Mapping[float, float],
    adaptation_improvements: Mapping[float, float],
    correctness_lower_bounds: Mapping[float, float],
    predeclared_positive_lambdas: Sequence[float],
    epsilon: float,
    delta: float,
    sensitivity_lambda: float | None = None,
) -> dict[str, Any]:
    """Retain the legacy draft-plan helper for API compatibility only."""

    if 0.0 not in complete_hit_rates:
        raise ValueError("lambda stage one requires a lambda=0 relevance baseline")
    if not 2 <= len(predeclared_positive_lambdas) <= 3:
        raise ValueError("stage two requires two or three predeclared positive lambdas")
    if len(set(predeclared_positive_lambdas)) != len(predeclared_positive_lambdas):
        raise ValueError("predeclared lambda candidates must be unique")
    if any(value <= 0 for value in predeclared_positive_lambdas):
        raise ValueError("stage-two candidates must be positive; lambda=0 is control only")
    baseline = complete_hit_rates[0.0]
    rows: list[dict[str, Any]] = []
    selectable: list[float] = []
    for candidate in predeclared_positive_lambdas:
        missing = [
            name
            for name, source in (
                ("complete_hit_rate", complete_hit_rates),
                ("adaptation_improvement", adaptation_improvements),
                ("correctness_lower_bound", correctness_lower_bounds),
            )
            if candidate not in source
        ]
        if missing:
            raise ValueError(f"lambda {candidate} is missing: {missing}")
        relevance_passed = baseline - complete_hit_rates[candidate] <= epsilon
        correctness_passed = correctness_lower_bounds[candidate] > -delta
        adaptation_improved = adaptation_improvements[candidate] > 0
        eligible = relevance_passed and correctness_passed and adaptation_improved
        if eligible:
            selectable.append(candidate)
        rows.append(
            {
                "lambda": candidate,
                "complete_hit_rate": complete_hit_rates[candidate],
                "loss_vs_lambda_zero": baseline - complete_hit_rates[candidate],
                "relevance_gate_passed": relevance_passed,
                "adaptation_improvement": adaptation_improvements[candidate],
                "correctness_lower_bound": correctness_lower_bounds[candidate],
                "correctness_noninferiority_passed": correctness_passed,
                "adaptation_improved": adaptation_improved,
                "selectable": eligible,
            }
        )
    recommended = (
        min(
            selectable,
            key=lambda candidate: (-adaptation_improvements[candidate], candidate),
        )
        if selectable
        else None
    )
    if sensitivity_lambda is not None and sensitivity_lambda not in predeclared_positive_lambdas:
        raise ValueError("sensitivity lambda must be one of the predeclared candidates")
    return {
        "lambda_zero_complete_hit_rate": baseline,
        "epsilon": epsilon,
        "delta": delta,
        "candidates": rows,
        "recommended_lambda": recommended,
        "successful_reranking_improvement": recommended is not None,
        "sensitivity_lambda": sensitivity_lambda,
        "interpretation": (
            "recommend the eligible lambda with the largest adaptation improvement; "
            "ties use the smaller lambda"
            if recommended is not None
            else "no positive lambda improved adaptation while passing both gates"
        ),
    }


def verify_dev_lambda_selection(
    *,
    complete_hit_rates: Mapping[float, float],
    selected_lambda: float,
    margin: float = 0.01,
) -> dict[str, Any]:
    """Verify, but never make, the generation owner's frozen Dev lambda choice.

    The team rule fixed on 2026-10-18 selects the largest positive lambda whose
    pooled complete-evidence hit rate is no more than one absolute percentage
    point below the lambda-zero baseline.  Correctness, adaptation and every
    judge score are deliberately absent from this function.
    """

    if 0.0 not in complete_hit_rates:
        raise ValueError("lambda verification requires a lambda=0 relevance baseline")
    if selected_lambda <= 0:
        raise ValueError("selected lambda must be positive; lambda=0 is control only")
    if not 0 <= margin <= 1:
        raise ValueError("lambda relevance margin must be between zero and one")
    if any(not 0 <= value <= 1 for value in complete_hit_rates.values()):
        raise ValueError("complete-evidence hit rates must be between zero and one")

    baseline = complete_hit_rates[0.0]
    positive = sorted(candidate for candidate in complete_hit_rates if candidate > 0)
    if not positive:
        raise ValueError("lambda verification requires at least one positive candidate")
    eligible = [
        candidate for candidate in positive if baseline - complete_hit_rates[candidate] <= margin
    ]
    if not eligible:
        raise ValueError("no positive lambda passes the frozen retrieval-hit-rate rule")
    expected = max(eligible)
    if selected_lambda not in complete_hit_rates:
        raise ValueError("selected lambda is absent from the supplied Dev grid")
    if selected_lambda != expected:
        raise ValueError(
            f"selected lambda {selected_lambda} violates the frozen rule; expected {expected}"
        )

    rows = [
        {
            "lambda": candidate,
            "complete_hit_rate": complete_hit_rates[candidate],
            "loss_vs_lambda_zero": baseline - complete_hit_rates[candidate],
            "passes_retrieval_rule": (
                candidate > 0 and baseline - complete_hit_rates[candidate] <= margin
            ),
            "role": "control" if candidate == 0 else "candidate",
            "selected": candidate == selected_lambda,
        }
        for candidate in sorted(complete_hit_rates)
    ]
    return {
        "rule_version": "largest-positive-within-one-percentage-point-2026-10-18",
        "selection_owner": "generation",
        "verification_owner": "evaluation",
        "lambda_zero_complete_hit_rate": baseline,
        "absolute_margin": margin,
        "selected_lambda": selected_lambda,
        "candidates": rows,
        "judge_scores_used_for_selection": False,
        "interpretation": (
            "verified the generation owner's largest eligible positive lambda; "
            "lambda=0 remains the non-reranked control"
        ),
    }
