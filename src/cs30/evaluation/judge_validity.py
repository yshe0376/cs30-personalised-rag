"""Automatic validity checks required before full-run judge results are usable."""

from __future__ import annotations

import hashlib
import json
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
    p0r0_min_case_count: int = Field(ge=3)
    duplicate_min_group_count: int = Field(ge=1)
    surface_min_rows_per_level: int = Field(ge=3)
    order_min_case_count: int = Field(ge=1)
    second_judge_min_case_count: int = Field(ge=1)
    perturbation_min_case_count: int = Field(ge=1)
    second_judge_max_evidence_rate_gap: float = Field(ge=0.0, le=1.0)


def _semantic_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def semantic_judge_signature(dimension: str, row: dict[str, Any]) -> str:
    """Hash only the scored decision, never free-form reasons or JSON ordering."""

    if dimension == "adaptation":
        criteria = row.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError("adaptation result is missing criteria")
        decisions: list[tuple[str, str]] = []
        for criterion in criteria:
            if not isinstance(criterion, dict):
                raise ValueError("adaptation criterion must be an object")
            criterion_id = criterion.get("criterion_id")
            verdict = criterion.get("verdict")
            if not isinstance(criterion_id, str) or not isinstance(verdict, str):
                raise ValueError("adaptation criterion is missing its ID or verdict")
            decisions.append((criterion_id, verdict))
        if len(decisions) != len({criterion_id for criterion_id, _ in decisions}):
            raise ValueError("adaptation result contains duplicate criterion IDs")
        return _semantic_hash(sorted(decisions))
    if dimension == "discrimination":
        predicted = row.get("predicted_level")
        if not isinstance(predicted, str):
            raise ValueError("discrimination result is missing predicted_level")
        return _semantic_hash({"predicted_level": predicted})
    if dimension == "evidence_support":
        values = {
            name: row.get(name)
            for name in ("bundle_faithfulness", "citation_support")
        }
        if any(
            value is not None and not isinstance(value, (int, float))
            for value in values.values()
        ):
            raise ValueError("evidence-support rates must be numeric or null")
        return _semantic_hash(values)
    raise ValueError(f"unknown judge-result dimension: {dimension}")


def semantic_judge_agreement(
    dimension: str,
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    evidence_rate_tolerance: float,
) -> bool:
    """Compare normalized decisions rather than complete model wording."""

    if dimension != "evidence_support":
        return semantic_judge_signature(dimension, first) == semantic_judge_signature(
            dimension, second
        )
    for name in ("bundle_faithfulness", "citation_support"):
        left = first.get(name)
        right = second.get(name)
        if left is None or right is None:
            if left is not None or right is not None:
                return False
            continue
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ValueError("evidence-support rates must be numeric or null")
        if abs(float(left) - float(right)) > evidence_rate_tolerance:
            return False
    return True


def _result(name: str, *, status: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"check": name, "status": status, "passed": passed, **details}


def p0r0_level_bias_check(
    rows: Sequence[tuple[StudentLevel, LevelGuess]],
    *,
    max_chance_deviation: float,
    min_case_count: int,
) -> dict[str, Any]:
    if not rows:
        return _result("p0r0_level_bias", status="not_run", passed=False, total=0)
    guesses = [guess for _, guess in rows]
    counts = Counter(guess.value for guess in guesses)
    target_counts = Counter(target.value for target, _ in rows)
    decided = sum(counts[level.value] for level in StudentLevel)
    uncertain = counts[LevelGuess.UNCERTAIN.value]
    rates = {
        level.value: counts[level.value] / decided if decided else None
        for level in StudentLevel
    }
    correct = sum(target.value == guess.value for target, guess in rows)
    accuracy = correct / len(rows)
    chance_deviation = abs(accuracy - 1 / 3)
    enough_data = len(rows) >= min_case_count
    target_coverage_complete = set(target_counts) == {
        level.value for level in StudentLevel
    }
    target_balance_complete = (
        target_coverage_complete and len(set(target_counts.values())) == 1
    )
    passed = (
        enough_data
        and target_balance_complete
        and chance_deviation <= max_chance_deviation
    )
    return _result(
        "p0r0_level_bias",
        status=(
            "complete"
            if enough_data and target_balance_complete
            else "insufficient_data"
        ),
        passed=passed,
        total=len(rows),
        correct_count=correct,
        accuracy=accuracy,
        chance_accuracy=1 / 3,
        chance_deviation=chance_deviation,
        decided_count=decided,
        uncertain_count=uncertain,
        uncertain_rate=uncertain / len(guesses),
        decided_guess_rates=rates,
        expected_decided_guess_rate=1 / 3,
        target_level_counts=dict(sorted(target_counts.items())),
        target_coverage_complete=target_coverage_complete,
        target_balance_complete=target_balance_complete,
        threshold=max_chance_deviation,
        minimum_case_count=min_case_count,
    )


def duplicate_consistency_check(
    rows: Iterable[tuple[str, str, str]],
    *,
    min_consistency: float,
    min_group_count: int,
    required_dimensions: Sequence[str] = (),
) -> dict[str, Any]:
    """Rows are `(case_id, exact_answer_sha256, semantic_output_sha256)`."""

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for question_id, answer_sha256, output_sha256 in rows:
        grouped[(question_id, answer_sha256)].append(output_sha256)
    duplicate_groups = [
        (key, outputs) for key, outputs in grouped.items() if len(outputs) > 1
    ]
    by_dimension_values: dict[str, list[bool]] = defaultdict(list)
    for (case_id, _), outputs in duplicate_groups:
        dimension = case_id.split(":", 1)[0] if ":" in case_id else "unspecified"
        by_dimension_values[dimension].append(len(set(outputs)) == 1)
    dimension_coverage_complete = set(required_dimensions) <= set(by_dimension_values)
    dimensions_have_minimum_groups = all(
        len(by_dimension_values[dimension]) >= min_group_count
        for dimension in required_dimensions
    )
    enough_data = (
        len(duplicate_groups) >= min_group_count
        and dimension_coverage_complete
        and dimensions_have_minimum_groups
    )
    if not enough_data:
        return _result(
            "duplicate_consistency",
            status="not_run" if not duplicate_groups else "insufficient_data",
            passed=False,
            duplicate_group_count=len(duplicate_groups),
            minimum_group_count=min_group_count,
            required_dimensions=list(required_dimensions),
            observed_dimensions=sorted(by_dimension_values),
            dimension_coverage_complete=dimension_coverage_complete,
        )
    consistent = sum(len(set(outputs)) == 1 for _, outputs in duplicate_groups)
    rate = consistent / len(duplicate_groups)
    by_dimension = {
        dimension: {
            "group_count": len(values),
            "consistency_rate": sum(values) / len(values),
        }
        for dimension, values in sorted(by_dimension_values.items())
    }
    every_dimension_passed = all(
        row["consistency_rate"] >= min_consistency for row in by_dimension.values()
    )
    return _result(
        "duplicate_consistency",
        status="complete",
        passed=rate >= min_consistency and every_dimension_passed,
        duplicate_group_count=len(duplicate_groups),
        consistent_group_count=consistent,
        consistency_rate=rate,
        threshold=min_consistency,
        minimum_group_count=min_group_count,
        required_dimensions=list(required_dimensions),
        observed_dimensions=sorted(by_dimension_values),
        dimension_coverage_complete=dimension_coverage_complete,
        by_dimension=by_dimension,
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
    min_rows_per_level: int,
) -> dict[str, Any]:
    """Check pass association with length and formula within each target level."""

    grouped: dict[StudentLevel, list[tuple[bool, int, bool]]] = defaultdict(list)
    row_count = 0
    for level, passed, answer_length, has_formula in rows:
        grouped[level].append((passed, answer_length, has_formula))
        row_count += 1
    details: dict[str, Any] = {}
    evaluable = 0
    failed = False
    levels_with_enough_rows = 0
    for level in StudentLevel:
        level_rows = grouped[level]
        if len(level_rows) >= min_rows_per_level:
            levels_with_enough_rows += 1
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
    coverage_complete = levels_with_enough_rows == len(StudentLevel)
    every_level_evaluable = evaluable == len(StudentLevel)
    return _result(
        "surface_feature_bias",
        status=(
            "complete"
            if coverage_complete and every_level_evaluable
            else "not_run" if row_count == 0 else "insufficient_data"
        ),
        passed=coverage_complete and every_level_evaluable and not failed,
        levels_evaluable=evaluable,
        levels_with_minimum_rows=levels_with_enough_rows,
        minimum_rows_per_level=min_rows_per_level,
        max_abs_length_correlation=max_abs_length_correlation,
        max_formula_pass_rate_gap=max_formula_pass_rate_gap,
        levels=details,
    )


def paired_consistency_check(
    name: str,
    pairs: Iterable[tuple[str, str, str]],
    *,
    min_consistency: float,
    min_case_count: int,
    case_count: int,
    coverage_complete: bool,
    required_dimensions: Sequence[str] = (),
) -> dict[str, Any]:
    """Rows are `(case_id, first_output_sha256, second_output_sha256)`."""

    rows = list(pairs)
    observed_dimensions = {
        case_id.split(":", 1)[0] if ":" in case_id else "unspecified"
        for case_id, _, _ in rows
    }
    dimension_coverage_complete = set(required_dimensions) <= observed_dimensions
    if (
        not rows
        or case_count < min_case_count
        or not coverage_complete
        or not dimension_coverage_complete
    ):
        return _result(
            name,
            status="not_run" if not rows else "insufficient_data",
            passed=False,
            pair_count=len(rows),
            case_count=case_count,
            minimum_case_count=min_case_count,
            coverage_complete=coverage_complete,
            required_dimensions=list(required_dimensions),
            observed_dimensions=sorted(observed_dimensions),
            dimension_coverage_complete=dimension_coverage_complete,
        )
    case_ids = [case_id for case_id, _, _ in rows]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError(f"{name} contains duplicate case_id values")
    consistent = sum(first == second for _, first, second in rows)
    rate = consistent / len(rows)
    by_dimension_values: dict[str, list[bool]] = defaultdict(list)
    for case_id, first, second in rows:
        dimension = case_id.split(":", 1)[0] if ":" in case_id else "unspecified"
        by_dimension_values[dimension].append(first == second)
    by_dimension = {
        dimension: {
            "pair_count": len(values),
            "consistency_rate": sum(values) / len(values),
        }
        for dimension, values in sorted(by_dimension_values.items())
    }
    every_dimension_passed = all(
        row["consistency_rate"] >= min_consistency for row in by_dimension.values()
    )
    return _result(
        name,
        status="complete",
        passed=rate >= min_consistency and every_dimension_passed,
        pair_count=len(rows),
        consistent_pair_count=consistent,
        consistency_rate=rate,
        threshold=min_consistency,
        case_count=case_count,
        minimum_case_count=min_case_count,
        coverage_complete=coverage_complete,
        required_dimensions=list(required_dimensions),
        observed_dimensions=sorted(observed_dimensions),
        dimension_coverage_complete=dimension_coverage_complete,
        by_dimension=by_dimension,
    )


def perturbation_check(
    detections: Sequence[bool],
    *,
    min_detection_rate: float,
    min_case_count: int,
) -> dict[str, Any]:
    if len(detections) < min_case_count:
        return _result(
            "controlled_perturbation",
            status="not_run" if not detections else "insufficient_data",
            passed=False,
            case_count=len(detections),
            minimum_case_count=min_case_count,
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
        minimum_case_count=min_case_count,
    )


def build_validity_report(
    thresholds: ValidityThresholds,
    *,
    p0r0_rows: Sequence[tuple[StudentLevel, LevelGuess]],
    duplicate_rows: Iterable[tuple[str, str, str]],
    surface_rows: Iterable[tuple[StudentLevel, bool, int, bool]],
    order_pairs: Iterable[tuple[str, str, str]],
    second_judge_pairs: Iterable[tuple[str, str, str]],
    perturbation_detections: Sequence[bool] = (),
    require_perturbation: bool = False,
    order_coverage_complete: bool = False,
    second_judge_coverage_complete: bool = False,
    order_case_count: int = 0,
    second_judge_case_count: int = 0,
) -> dict[str, Any]:
    checks = [
        p0r0_level_bias_check(
            p0r0_rows,
            max_chance_deviation=thresholds.p0r0_max_chance_deviation,
            min_case_count=thresholds.p0r0_min_case_count,
        ),
        duplicate_consistency_check(
            duplicate_rows,
            min_consistency=thresholds.duplicate_min_consistency,
            min_group_count=thresholds.duplicate_min_group_count,
            required_dimensions=("adaptation", "discrimination", "evidence_support"),
        ),
        surface_bias_check(
            surface_rows,
            max_abs_length_correlation=thresholds.max_abs_length_correlation,
            max_formula_pass_rate_gap=thresholds.max_formula_pass_rate_gap,
            min_rows_per_level=thresholds.surface_min_rows_per_level,
        ),
        paired_consistency_check(
            "position_order_consistency",
            order_pairs,
            min_consistency=thresholds.order_min_consistency,
            min_case_count=thresholds.order_min_case_count,
            case_count=order_case_count,
            coverage_complete=order_coverage_complete,
            required_dimensions=("adaptation",),
        ),
        paired_consistency_check(
            "second_judge_consistency",
            second_judge_pairs,
            min_consistency=thresholds.second_judge_min_consistency,
            min_case_count=thresholds.second_judge_min_case_count,
            case_count=second_judge_case_count,
            coverage_complete=second_judge_coverage_complete,
            required_dimensions=("adaptation", "discrimination", "evidence_support"),
        ),
    ]
    perturbation = perturbation_check(
        perturbation_detections,
        min_detection_rate=thresholds.perturbation_min_detection_rate,
        min_case_count=thresholds.perturbation_min_case_count,
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
