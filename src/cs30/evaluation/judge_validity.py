"""Automatic validity checks required before full-run judge results are usable."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from pydantic import Field

from cs30.contracts import StudentLevel
from cs30.contracts.models import ContractModel, Identifier

from .v2_generation_models import LevelGuess


class ValidityThresholds(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    threshold_version: Identifier
    p0r0_max_chance_deviation: float = Field(ge=0.0, le=1.0)
    duplicate_min_consistency: float = Field(ge=0.0, le=1.0)
    max_abs_length_correlation: float = Field(ge=0.0, le=1.0)
    max_formula_pass_rate_gap: float = Field(ge=0.0, le=1.0)
    order_min_consistency: float = Field(ge=0.0, le=1.0)
    second_judge_min_consistency: float = Field(ge=0.0, le=1.0)
    perturbation_min_detection_rate: float = Field(ge=0.0, le=1.0)


def _result(name: str, *, status: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"check": name, "status": status, "passed": passed, **details}


def p0r0_level_bias_check(
    guesses: Sequence[LevelGuess],
    *,
    max_chance_deviation: float,
) -> dict[str, Any]:
    if not guesses:
        return _result("p0r0_level_bias", status="not_run", passed=False, total=0)
    counts = Counter(guess.value for guess in guesses)
    decided = sum(counts[level.value] for level in StudentLevel)
    uncertain = counts[LevelGuess.UNCERTAIN.value]
    rates = {
        level.value: counts[level.value] / decided if decided else None
        for level in StudentLevel
    }
    deviations = [abs(rate - 1 / 3) for rate in rates.values() if rate is not None]
    max_deviation = max(deviations) if deviations else None
    passed = max_deviation is not None and max_deviation <= max_chance_deviation
    return _result(
        "p0r0_level_bias",
        status="complete",
        passed=passed,
        total=len(guesses),
        decided_count=decided,
        uncertain_count=uncertain,
        uncertain_rate=uncertain / len(guesses),
        decided_guess_rates=rates,
        expected_decided_rate=1 / 3,
        max_chance_deviation=max_deviation,
        threshold=max_chance_deviation,
    )


def duplicate_consistency_check(
    rows: Iterable[tuple[str, str, str]],
    *,
    min_consistency: float,
) -> dict[str, Any]:
    """Rows are `(question_id, exact_answer_sha256, output_sha256)`."""

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for question_id, answer_sha256, output_sha256 in rows:
        grouped[(question_id, answer_sha256)].append(output_sha256)
    duplicate_groups = [outputs for outputs in grouped.values() if len(outputs) > 1]
    if not duplicate_groups:
        return _result(
            "duplicate_consistency",
            status="not_run",
            passed=False,
            duplicate_group_count=0,
        )
    consistent = sum(len(set(outputs)) == 1 for outputs in duplicate_groups)
    rate = consistent / len(duplicate_groups)
    return _result(
        "duplicate_consistency",
        status="complete",
        passed=rate >= min_consistency,
        duplicate_group_count=len(duplicate_groups),
        consistent_group_count=consistent,
        consistency_rate=rate,
        threshold=min_consistency,
    )


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denominator_x == 0 or denominator_y == 0:
        return None
    return numerator / (denominator_x * denominator_y)


def surface_bias_check(
    rows: Iterable[tuple[StudentLevel, bool, int, bool]],
    *,
    max_abs_length_correlation: float,
    max_formula_pass_rate_gap: float,
) -> dict[str, Any]:
    """Check pass association with length and formula within each target level."""

    grouped: dict[StudentLevel, list[tuple[bool, int, bool]]] = defaultdict(list)
    for level, passed, answer_length, has_formula in rows:
        grouped[level].append((passed, answer_length, has_formula))
    details: dict[str, Any] = {}
    evaluable = 0
    failed = False
    for level in StudentLevel:
        level_rows = grouped[level]
        lengths = [float(row[1]) for row in level_rows]
        outcomes = [float(row[0]) for row in level_rows]
        correlation = _pearson(lengths, outcomes)
        with_formula = [row[0] for row in level_rows if row[2]]
        without_formula = [row[0] for row in level_rows if not row[2]]
        formula_gap = None
        if with_formula and without_formula:
            formula_gap = abs(
                sum(with_formula) / len(with_formula)
                - sum(without_formula) / len(without_formula)
            )
        if correlation is not None or formula_gap is not None:
            evaluable += 1
        if correlation is not None and abs(correlation) > max_abs_length_correlation:
            failed = True
        if formula_gap is not None and formula_gap > max_formula_pass_rate_gap:
            failed = True
        details[level.value] = {
            "sample_size": len(level_rows),
            "length_pass_correlation": correlation,
            "formula_pass_rate_gap": formula_gap,
            "with_formula_count": len(with_formula),
            "without_formula_count": len(without_formula),
        }
    return _result(
        "surface_feature_bias",
        status="complete" if evaluable else "not_run",
        passed=evaluable > 0 and not failed,
        levels_evaluable=evaluable,
        max_abs_length_correlation=max_abs_length_correlation,
        max_formula_pass_rate_gap=max_formula_pass_rate_gap,
        levels=details,
    )


def paired_consistency_check(
    name: str,
    pairs: Iterable[tuple[str, str, str]],
    *,
    min_consistency: float,
) -> dict[str, Any]:
    """Rows are `(case_id, first_output_sha256, second_output_sha256)`."""

    rows = list(pairs)
    if not rows:
        return _result(name, status="not_run", passed=False, pair_count=0)
    case_ids = [case_id for case_id, _, _ in rows]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError(f"{name} contains duplicate case_id values")
    consistent = sum(first == second for _, first, second in rows)
    rate = consistent / len(rows)
    return _result(
        name,
        status="complete",
        passed=rate >= min_consistency,
        pair_count=len(rows),
        consistent_pair_count=consistent,
        consistency_rate=rate,
        threshold=min_consistency,
    )


def perturbation_check(
    detections: Sequence[bool],
    *,
    min_detection_rate: float,
) -> dict[str, Any]:
    if not detections:
        return _result(
            "controlled_perturbation",
            status="not_run",
            passed=False,
            case_count=0,
        )
    detected = sum(detections)
    rate = detected / len(detections)
    return _result(
        "controlled_perturbation",
        status="complete",
        passed=rate >= min_detection_rate,
        case_count=len(detections),
        detected_count=detected,
        detection_rate=rate,
        threshold=min_detection_rate,
    )


def build_validity_report(
    thresholds: ValidityThresholds,
    *,
    p0r0_guesses: Sequence[LevelGuess],
    duplicate_rows: Iterable[tuple[str, str, str]],
    surface_rows: Iterable[tuple[StudentLevel, bool, int, bool]],
    order_pairs: Iterable[tuple[str, str, str]],
    second_judge_pairs: Iterable[tuple[str, str, str]],
    perturbation_detections: Sequence[bool] = (),
    require_perturbation: bool = False,
) -> dict[str, Any]:
    checks = [
        p0r0_level_bias_check(
            p0r0_guesses,
            max_chance_deviation=thresholds.p0r0_max_chance_deviation,
        ),
        duplicate_consistency_check(
            duplicate_rows,
            min_consistency=thresholds.duplicate_min_consistency,
        ),
        surface_bias_check(
            surface_rows,
            max_abs_length_correlation=thresholds.max_abs_length_correlation,
            max_formula_pass_rate_gap=thresholds.max_formula_pass_rate_gap,
        ),
        paired_consistency_check(
            "position_order_consistency",
            order_pairs,
            min_consistency=thresholds.order_min_consistency,
        ),
        paired_consistency_check(
            "second_judge_consistency",
            second_judge_pairs,
            min_consistency=thresholds.second_judge_min_consistency,
        ),
    ]
    perturbation = perturbation_check(
        perturbation_detections,
        min_detection_rate=thresholds.perturbation_min_detection_rate,
    )
    checks.append(perturbation)
    required = checks if require_perturbation else checks[:-1]
    passed = all(check["status"] == "complete" and check["passed"] for check in required)
    return {
        "schema_version": "1.0",
        "threshold_version": thresholds.threshold_version,
        "formal_use_allowed": passed,
        "failed_or_missing_required_checks": [
            check["check"]
            for check in required
            if check["status"] != "complete" or not check["passed"]
        ],
        "checks": checks,
    }
