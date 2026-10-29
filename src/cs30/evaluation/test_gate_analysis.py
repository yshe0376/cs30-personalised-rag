"""Offline reporting policy registered in PR #224; raw judge decisions stay intact."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any

from cs30.contracts import StudentLevel

from .condition_statistics import _percentile
from .level_profiles import eligible_levels
from .v2_generation_models import ExperimentArm, GenerationEvaluationInput

POLICY_VERSION = "test-gates-20261029-v1"
DECISION_RECORD = "https://github.com/yshe0376/cs30-personalised-rag/pull/224"
PROFILE_SHA = "1888c3b7fb6f2f0fd52dbe06455c40cef88ff8839ab47383a76d7c29a1088238"
DELTA = 0.03
ALPHA = 0.05
CONTROL = ExperimentArm.P0R0_PLAIN
TREATMENT = ExperimentArm.P1R0_PROMPT_ONLY


def main_adaptation(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a separate main-rate view; I3 remains in the original record."""
    level = str(record["evaluated_level"])
    expected = {
        "beginner": {"B1", "B2", "B3", "B4"},
        "intermediate": {"I1", "I2", "I3"},
        "advanced": {"A1", "A2", "A3", "A4"},
    }[level]
    rows = record["criteria"]
    verdicts = {r["criterion_id"]: r["verdict"] for r in rows}
    if set(verdicts) != expected or len(rows) != len(expected):
        raise ValueError("adaptation reporting requires exact criterion coverage")
    if any(v not in {"pass", "fail", "not_applicable"} for v in verdicts.values()):
        raise ValueError("invalid criterion verdict")
    if any(v == "not_applicable" and k not in {"B3", "A2", "A3"} for k, v in verdicts.items()):
        raise ValueError("always-assessed criterion cannot be not_applicable")
    included = {k: v for k, v in verdicts.items() if k != "I3" and v != "not_applicable"}
    rate = sum(v == "pass" for v in included.values()) / len(included) if included else None
    return {
        "reporting_policy": POLICY_VERSION,
        "main_criterion_pass_rate": rate,
        "main_all_applicable_passed": all(v == "pass" for v in included.values())
        if included
        else None,
        "reference_only_i3": verdicts.get("I3"),
        "main_evaluable_criterion_count": len(included),
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in p_values.values()):
        raise ValueError("p-values must be finite probabilities")
    adjusted, previous = {}, 0.0
    ordered = sorted(p_values, key=lambda name: (p_values[name], name))
    for index, name in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered) - index) * p_values[name]))
        adjusted[name] = previous
    return adjusted


def cluster_interval(differences, *, draws=2000, seed=5703, test_zero=False):
    """Resample whole question clusters; use a centred, two-sided bootstrap test."""
    if draws < 100:
        raise ValueError("at least 100 bootstrap draws are required")
    keys = sorted(differences)
    if len(keys) < 2 or any(not differences[k] for k in keys):
        raise ValueError("at least two nonempty question clusters are required")
    values = [v for k in keys for v in differences[k]]
    if any(not math.isfinite(v) for v in values):
        raise ValueError("bootstrap values must be finite")
    estimate = mean(values)
    rng = random.Random(seed)
    boot = []
    for _ in range(draws):
        selected = [rng.choice(keys) for _ in keys]
        boot.append(mean(v for k in selected for v in differences[k]))
    return {
        "estimate": estimate,
        "ci_lower": _percentile(boot, 0.025),
        "ci_upper": _percentile(boot, 0.975),
        "question_cluster_count": len(keys),
        "paired_cell_count": len(values),
        "bootstrap_draws": draws,
        "seed": seed,
        "p_value": (
            (1 + sum(abs(v - estimate) >= abs(estimate) for v in boot)) / (draws + 1)
            if test_zero
            else None
        ),
        "interval_kind": "unadjusted question-cluster percentile 95%",
    }


def registered_analysis(
    items: Sequence[GenerationEvaluationInput],
    correctness: Mapping[str, Any],
    adaptation: Sequence[Mapping[str, Any]],
    *,
    draws=2000,
    seed=5703,
    adaptation_noise_floors: Mapping[str, float] | None = None,
):
    """Compute registered endpoints; missing correctness is bounded, never erased.

    `correctness` maps evaluation_id to 0/1/2/None. Non-answers have fixed system
    zeros. This pure function supports offline fixtures and Dev diagnostic replay;
    the file-level Test command separately checks full matrix/source bindings.
    """
    if not items or len({i.evaluation_id for i in items}) != len(items):
        raise ValueError("inputs must contain unique evaluation IDs")
    if len({(i.generation_model_family, i.generation_model_revision) for i in items}) != 1:
        raise ValueError("analyse one generator batch at a time")
    by_cell = {(i.question_id, i.target_level, i.condition): i for i in items}
    if len(by_cell) != len(items):
        raise ValueError("duplicate question/level/condition cell")
    by_id = {i.evaluation_id: i for i in items}
    target = {}
    for row in adaptation:
        if not row.get("is_target_level_evaluation"):
            continue
        eid = row["evaluation_id"]
        if eid not in by_id or eid in target:
            raise ValueError("duplicate or unbound adaptation result")
        item = by_id[eid]
        if (
            str(row["evaluated_level"]) != item.target_level.value
            or row.get("question_id") != item.question_id
            or row.get("condition") != item.condition.value
            or row.get("target_level") != item.target_level.value
        ):
            raise ValueError("adaptation level differs from bound input")
        target[eid] = main_adaptation(row)
    family = items[0].generation_model_family.casefold().rsplit("/", 1)[-1]
    primary_model = family in {"gpt-oss", "gpt-oss-20b", "gpt-oss:20b"}
    if adaptation_noise_floors is not None and (
        set(adaptation_noise_floors) != {"beginner", "advanced"}
        or any(not math.isfinite(v) or not 0 <= v <= 1 for v in adaptation_noise_floors.values())
    ):
        raise ValueError("noise floors must cover the two endpoints with finite rates")
    endpoints = []
    for level in (StudentLevel.BEGINNER, StudentLevel.ADVANCED):
        differences = {}
        expected_pairs, excluded, missing = 0, 0, 0
        for qid in sorted({i.question_id for i in items}):
            t, c = (by_cell.get((qid, level, arm)) for arm in (TREATMENT, CONTROL))
            if t is None or c is None:
                missing += 1
                continue
            if t.eligibility != c.eligibility:
                raise ValueError("eligibility must not vary between conditions")
            if level not in eligible_levels(t.eligibility):
                continue
            expected_pairs += 1
            if any(i.technical_failure or i.abstained for i in (t, c)):
                excluded += 1
                continue
            tv, cv = (
                target.get(i.evaluation_id, {}).get("main_criterion_pass_rate") for i in (t, c)
            )
            if tv is None or cv is None:
                missing += 1
                continue
            differences[qid] = [tv - cv]
        result = {
            "level": level.value,
            "expected_eligible_pairs": expected_pairs,
            "non_answer_excluded_pairs": excluded,
            "answered_unscored_pairs": missing,
            "estimate": None,
            "p_value": None,
        }
        if len(differences) >= 2:
            result.update(cluster_interval(differences, draws=draws, seed=seed, test_zero=True))
        endpoints.append(result)
    # Always retain the full two-test family, even when one endpoint is unavailable.
    adjusted = holm_adjust(
        {r["level"]: r["p_value"] if r["p_value"] is not None else 1.0 for r in endpoints}
    )
    for result in endpoints:
        result["holm_adjusted_p"] = (
            adjusted[result["level"]] if result["p_value"] is not None else None
        )
        result["co_primary"] = primary_model
        result["statistically_positive"] = bool(
            primary_model
            and result["p_value"] is not None
            and adjusted[result["level"]] <= ALPHA
            and result["estimate"] > 0
        )
        result["statistically_negative"] = bool(
            primary_model
            and result["p_value"] is not None
            and adjusted[result["level"]] <= ALPHA
            and result["estimate"] < 0
        )
        floor = adaptation_noise_floors.get(result["level"]) if adaptation_noise_floors else None
        result["generation_repeat_noise_floor"] = floor
        result["positive_effect_supported"] = bool(
            result["statistically_positive"] and floor is not None and result["estimate"] > floor
        )
        result["negative_effect_supported"] = bool(
            result["statistically_negative"] and floor is not None and -result["estimate"] > floor
        )
        result["decision_rule"] = "Holm-adjusted two-sided p <= 0.05; direction from estimate"
        result["interval_role"] = "descriptive, unadjusted 95% interval"
        result["missingness_policy"] = "complete pairs; unscored counts reported alongside estimate"

    lower, upper = defaultdict(list), defaultdict(list)
    unresolved = 0
    coverage = defaultdict(
        lambda: {
            "cells": 0,
            "generation_failures": 0,
            "abstentions": 0,
            "answered": 0,
            "answered_unscored": 0,
            "strict_correct": 0,
            "joint_lower_count": 0,
            "joint_upper_count": 0,
            "main_eligible_cells": 0,
            "main_joint_lower_count": 0,
            "main_joint_upper_count": 0,
        }
    )

    def strict(item):
        value = correctness.get(item.evaluation_id)
        if item.technical_failure or item.abstained:
            if value not in (None, 0):
                raise ValueError("non-answers must have a fixed correctness zero")
            return 0
        if value not in (None, 0, 1, 2):
            raise ValueError("correctness must be 0/1/2 or unknown")
        return None if value is None else int(value == 2)

    for item in items:
        group = coverage[item.condition.value]
        group["cells"] += 1
        group["generation_failures"] += int(item.technical_failure)
        group["abstentions"] += int(item.abstained)
        value = strict(item)
        if not item.technical_failure and not item.abstained:
            group["answered"] += 1
            group["answered_unscored"] += int(value is None)
        group["strict_correct"] += int(value == 1)
        adapted = target.get(item.evaluation_id, {}).get("main_all_applicable_passed")
        lower_joint = int(value == 1 and adapted is True)
        upper_joint = int(value in (None, 1) and adapted is not False)
        if item.technical_failure or item.abstained:
            lower_joint = upper_joint = 0
        group["joint_lower_count"] += lower_joint
        group["joint_upper_count"] += upper_joint
        if item.target_level in eligible_levels(item.eligibility):
            group["main_eligible_cells"] += 1
            group["main_joint_lower_count"] += lower_joint
            group["main_joint_upper_count"] += upper_joint
    for group in coverage.values():
        n, answered = group["cells"], group["answered"]
        correct, missing = group["strict_correct"], group["answered_unscored"]
        group["strict_correct_rate_bounds"] = [correct / n, (correct + missing) / n]
        group["answered_only_strict_correct_bounds"] = (
            [correct / answered, (correct + missing) / answered] if answered else None
        )
        group["joint_correct_and_adapted_bounds"] = [
            group["joint_lower_count"] / n,
            group["joint_upper_count"] / n,
        ]
        eligible = group["main_eligible_cells"]
        group["main_eligible_joint_bounds"] = (
            [group["main_joint_lower_count"] / eligible, group["main_joint_upper_count"] / eligible]
            if eligible
            else None
        )
    adaptation_summary = []
    for level in StudentLevel:
        for arm in ExperimentArm:
            selected = [
                i
                for i in items
                if i.target_level == level
                and i.condition == arm
                and level in eligible_levels(i.eligibility)
            ]
            answered = [i for i in selected if not i.technical_failure and not i.abstained]
            resolved = [target[i.evaluation_id] for i in answered if i.evaluation_id in target]
            adaptation_summary.append(
                {
                    "level": level.value,
                    "condition": arm.value,
                    "eligible_cells": len(selected),
                    "answered_cells": len(answered),
                    "resolved_answers": len(resolved),
                    "answered_unscored": len(answered) - len(resolved),
                    "mean_main_criterion_pass_rate": (
                        mean(r["main_criterion_pass_rate"] for r in resolved) if resolved else None
                    ),
                    "all_applicable_passed_count": sum(
                        r["main_all_applicable_passed"] is True for r in resolved
                    ),
                    "i3_reference_pass_count": sum(
                        r["reference_only_i3"] == "pass" for r in resolved
                    ),
                    "i3_reference_denominator": len(resolved)
                    if level is StudentLevel.INTERMEDIATE
                    else 0,
                }
            )
    for qid in sorted({i.question_id for i in items}):
        for level in StudentLevel:
            t, c = (by_cell.get((qid, level, arm)) for arm in (TREATMENT, CONTROL))
            if t is None or c is None:
                raise ValueError("correctness primary contrast requires every question/level pair")
            tv, cv = strict(t), strict(c)
            unresolved += int(tv is None or cv is None)
            lower[qid].append((0 if tv is None else tv) - (1 if cv is None else cv))
            upper[qid].append((1 if tv is None else tv) - (0 if cv is None else cv))
    ni = {"delta": DELTA, "unresolved_pairs": unresolved, "co_primary_model": primary_model}
    if len(lower) >= 2:
        ni["worst_case"] = cluster_interval(lower, draws=draws, seed=seed)
        ni["best_case"] = cluster_interval(upper, draws=draws, seed=seed)
        ni["supported_at_both_bounds"] = bool(
            primary_model
            and all(ni[name]["ci_lower"] > -DELTA for name in ("worst_case", "best_case"))
        )
    else:
        ni["supported_at_both_bounds"] = False
    return {
        "policy": POLICY_VERSION,
        "decision_record": DECISION_RECORD,
        "primary_contrast": "P1R0 - P0R0",
        "alpha": ALPHA,
        "multiplicity": "Holm over beginner and advanced, two-sided centred bootstrap p",
        "adaptation_endpoints": endpoints,
        "correctness_noninferiority": ni,
        "coverage_by_condition": dict(coverage),
        "adaptation_by_level_condition": adaptation_summary,
        "reference_only": ["I3", "discrimination", "citation_support"],
        "reportable": False,
        "limits": "Report evidence limits and compare effects to the Dev noise floor separately.",
    }
