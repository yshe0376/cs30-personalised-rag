"""Deterministic diagnostics and combined reporting for V2 generation evaluation."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from cs30.contracts import StudentLevel

from .condition_statistics import CONTRASTS, correctness_noninferiority
from .level_profiles import PREFERRED_ROLES
from .v2_generation_models import (
    EvaluationDecisionConfig,
    EvaluationEvidence,
    EvaluationMode,
    ExperimentArm,
)


def _syllable_count(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.casefold())
    count = len(groups)
    if word.casefold().endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def answer_text_diagnostics(
    answer: str,
    *,
    jargon_terms: Iterable[str] = (),
) -> dict[str, Any]:
    """Compute descriptive-only FKGL, jargon, length, and formula diagnostics."""

    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?", answer)
    sentences = [part for part in re.split(r"[.!?]+", answer) if part.strip()]
    word_count = len(words)
    sentence_count = max(1, len(sentences))
    syllables = sum(_syllable_count(word) for word in words if word[0].isalpha())
    fkgl = (
        0.39 * (word_count / sentence_count) + 11.8 * (syllables / max(1, word_count)) - 15.59
        if word_count
        else None
    )
    normalized_jargon = {term.casefold() for term in jargon_terms}
    jargon_count = sum(word.casefold() in normalized_jargon for word in words)
    formula_present = bool(
        re.search(r"(?:[=≈≠≤≥±×÷]|\b(?:sin|cos|tan|log|sqrt)\s*\(|\^\d)", answer)
    )
    return {
        "word_count": word_count,
        "character_count": len(answer),
        "sentence_count": sentence_count,
        "fkgl": fkgl,
        "jargon_count": jargon_count,
        "jargon_ratio": jargon_count / word_count if word_count else None,
        "formula_present": formula_present,
        "interpretation": "descriptive diagnostic only; not an adaptation verdict",
    }


def preferred_role_share(
    evidence: Sequence[EvaluationEvidence],
    level: StudentLevel,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    top = sorted(evidence, key=lambda item: item.rank)[:top_k]
    preferred = PREFERRED_ROLES[level]
    count = sum(item.role in preferred for item in top)
    return {
        "target_level": level.value,
        "top_k": top_k,
        "preferred_roles": sorted(preferred),
        "preferred_role_count": count,
        "evidence_count": len(top),
        "preferred_role_share": count / len(top) if top else None,
        "interpretation": "mechanism diagnostic only; not a lambda-selection target",
    }


def preferred_role_lambda_diagnostic(
    rows: Iterable[tuple[str, StudentLevel, float, float]],
) -> dict[str, Any]:
    """Check expected mechanism direction without using it to choose lambda."""

    grouped: dict[tuple[str, StudentLevel], list[tuple[float, float]]] = defaultdict(list)
    for question_id, level, lambda_weight, share in rows:
        if not 0 <= lambda_weight <= 1 or not 0 <= share <= 1:
            raise ValueError("lambda weights and preferred-role shares must be in [0, 1]")
        grouped[(question_id, level)].append((lambda_weight, share))
    details = []
    monotonic_count = 0
    for (question_id, level), values in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1].value)
    ):
        ordered = sorted(values)
        lambdas = [value[0] for value in ordered]
        if len(lambdas) != len(set(lambdas)):
            raise ValueError(f"duplicate lambda for {question_id}/{level.value}")
        shares = [value[1] for value in ordered]
        monotonic = all(right >= left for left, right in zip(shares, shares[1:], strict=False))
        monotonic_count += int(monotonic)
        details.append(
            {
                "question_id": question_id,
                "target_level": level.value,
                "values": [
                    {"lambda": lambda_weight, "preferred_role_share": share}
                    for lambda_weight, share in ordered
                ],
                "nondecreasing": monotonic,
            }
        )
    return {
        "group_count": len(details),
        "nondecreasing_group_count": monotonic_count,
        "nondecreasing_rate": monotonic_count / len(details) if details else None,
        "records": details,
        "interpretation": (
            "diagnoses whether reranking changes evidence roles; never selects lambda or "
            "substitutes for answer-quality evaluation"
        ),
    }


def generation_stochasticity_summary(
    rows: Iterable[tuple[str, str]],
) -> dict[str, Any]:
    """Estimate repeated-identical-prompt answer mismatch from saved outputs."""

    grouped: dict[str, list[str]] = defaultdict(list)
    for prompt_sha256, answer in rows:
        grouped[prompt_sha256].append(hashlib.sha256(answer.encode("utf-8")).hexdigest())
    repeated = {key: values for key, values in grouped.items() if len(values) > 1}
    inconsistent_groups = sum(len(set(values)) > 1 for values in repeated.values())
    unequal_pairs = 0
    total_pairs = 0
    for values in repeated.values():
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                total_pairs += 1
                unequal_pairs += int(left != right)
    return {
        "repeated_prompt_group_count": len(repeated),
        "inconsistent_group_count": inconsistent_groups,
        "inconsistent_group_rate": (inconsistent_groups / len(repeated) if repeated else None),
        "pair_count": total_pairs,
        "unequal_pair_count": unequal_pairs,
        "pairwise_mismatch_rate": unequal_pairs / total_pairs if total_pairs else None,
        "interpretation": "generation noise diagnostic; not removed by paired bootstrap",
    }


def generation_noise_floor(
    items: Sequence[Any],
) -> dict[str, Any]:
    """Measure answer mismatch only where the recorded prompt bytes are identical.

    R0/R1 comparisons are paired within question and level.  The P0 cross-level
    check follows the frozen plan's two comparisons per question: beginner versus
    intermediate and beginner versus advanced.
    """

    indexed: dict[tuple[str, str, str], Any] = {}
    for item in items:
        if item.answer is None:
            continue
        key = (item.question_id, item.target_level.value, item.condition.value)
        if key in indexed:
            raise ValueError(f"duplicate generation-noise cell: {key}")
        indexed[key] = item

    def compare(pairs: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
        candidate_pairs = 0
        missing_pairs = 0
        nonidentical_prompts = 0
        eligible = 0
        mismatched = 0
        for left, right in pairs:
            candidate_pairs += 1
            if (
                left is None
                or right is None
                or left.prompt_sha256 is None
                or right.prompt_sha256 is None
            ):
                missing_pairs += 1
                continue
            if left.prompt_sha256 != right.prompt_sha256:
                nonidentical_prompts += 1
                continue
            eligible += 1
            mismatched += int(left.answer != right.answer)
        return {
            "candidate_pair_count": candidate_pairs,
            "missing_pair_count": missing_pairs,
            "nonidentical_prompt_pair_count": nonidentical_prompts,
            "identical_prompt_pair_count": eligible,
            "answer_mismatch_count": mismatched,
            "answer_mismatch_rate": mismatched / eligible if eligible else None,
        }

    questions = sorted({item.question_id for item in items})
    levels = [level.value for level in StudentLevel]
    p0r0_r0r1 = compare(
        (
            indexed.get((question, level, "P0R0_plain")),
            indexed.get((question, level, "P0R1_reranking_only")),
        )
        for question in questions
        for level in levels
    )
    p1r0_r0r1 = compare(
        (
            indexed.get((question, level, "P1R0_prompt_only")),
            indexed.get((question, level, "P1R1_combined")),
        )
        for question in questions
        for level in levels
    )
    p0_cross_level = compare(
        (
            indexed.get((question, StudentLevel.BEGINNER.value, "P0R0_plain")),
            indexed.get((question, other.value, "P0R0_plain")),
        )
        for question in questions
        for other in (StudentLevel.INTERMEDIATE, StudentLevel.ADVANCED)
    )
    return {
        "method": "exact saved-answer mismatch among byte-identical generation prompts",
        "P0R0_vs_P0R1": p0r0_r0r1,
        "P1R0_vs_P1R1": p1r0_r0r1,
        "P0R0_cross_level": p0_cross_level,
        "interpretation": (
            "generation noise floor; condition effects must be interpreted against this "
            "residual stochasticity"
        ),
    }


def _difference_distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "pair_count": 0,
            "mean_difference": None,
            "mean_absolute_difference": None,
            "quantiles": None,
            "absolute_difference_quantiles": None,
        }
    ordered = sorted(values)
    absolute = sorted(abs(value) for value in values)

    def quantile(data: Sequence[float], probability: float) -> float:
        position = (len(data) - 1) * probability
        lower = int(position)
        upper = min(lower + 1, len(data) - 1)
        fraction = position - lower
        return data[lower] * (1 - fraction) + data[upper] * fraction

    return {
        "pair_count": len(values),
        "mean_difference": sum(values) / len(values),
        "mean_absolute_difference": sum(abs(value) for value in values) / len(values),
        "quantiles": {
            "q05": quantile(ordered, 0.05),
            "q25": quantile(ordered, 0.25),
            "q50": quantile(ordered, 0.50),
            "q75": quantile(ordered, 0.75),
            "q95": quantile(ordered, 0.95),
        },
        "absolute_difference_quantiles": {
            "q05": quantile(absolute, 0.05),
            "q25": quantile(absolute, 0.25),
            "q50": quantile(absolute, 0.50),
            "q75": quantile(absolute, 0.75),
            "q95": quantile(absolute, 0.95),
        },
    }


def paired_generation_noise_floor(
    baseline_rows: Sequence[Mapping[str, Any]],
    repeat_rows: Sequence[Mapping[str, Any]],
    *,
    correctness_delta: float | None = None,
    main_comparison: Mapping[str, Any] | None = None,
    adaptation_threshold_frozen: bool = False,
) -> dict[str, Any]:
    """Compare a 30-question repeat generation batch with its Dev baseline by run ID.

    The correctness noise floor is the standard deviation that generation noise adds
    to the main strict-correct comparison: ``sqrt(flip_rate / n)``. ``flip_rate`` is
    the share of paired cells whose strict-correct outcome (score 2) changes between
    the two runs, averaged over the two conditions of the main contrast, and ``n`` is
    that comparison's paired cell count. Flips in opposite directions therefore do not
    cancel. Unresolved correctness stays in the denominator as a bounded unknown, as in
    ``strict_correctness_summary``: the floor is reported as bounds and compared with
    delta only once every pair is scored.

    Adaptation outcomes are summarised separately. Pairs where an answer was abstained
    or failed technically, or where the pass threshold is not frozen, are counted as
    not applicable rather than as unevaluated, so they never hold the correctness
    status open.
    """

    def index(rows: Sequence[Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
        indexed: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            run_id = str(row.get("run_id") or "")
            if not run_id or run_id in indexed:
                raise ValueError(f"{label} rows require unique nonempty run_id values")
            indexed[run_id] = row
        return indexed

    def optional_score(row: Mapping[str, Any], run_id: str) -> int | None:
        value = row.get("correctness_score")
        if value is None:
            return None
        if type(value) is not int or value not in {0, 1, 2}:
            raise ValueError(f"{run_id}: correctness_score must be 0, 1, 2, or null")
        return value

    def optional_float(row: Mapping[str, Any], field: str) -> float | None:
        value = row.get(field)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be numeric or null")
        numeric = float(value)
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise ValueError(f"{field} must be finite and between zero and one")
        return numeric

    def optional_bool(row: Mapping[str, Any], field: str) -> bool | None:
        value = row.get(field)
        if value is None:
            return None
        if type(value) is not bool:
            raise ValueError(f"{field} must be a boolean or null")
        return value

    def classify(applicable: bool, left: object, right: object) -> str:
        if not applicable:
            return "not_applicable"
        if left is None or right is None:
            return "not_evaluated"
        return "evaluated"

    baseline = index(baseline_rows, "baseline")
    repeated = index(repeat_rows, "repeat")
    repeat_questions = {str(row.get("question_id") or "") for row in repeat_rows}
    if len(repeat_rows) != 360 or len(repeat_questions) != 30 or "" in repeat_questions:
        raise ValueError("generation repeat batch must contain 30 questions x 12 cells (360 rows)")
    expected_cells = {
        (level.value, condition.value) for level in StudentLevel for condition in ExperimentArm
    }
    for question_id in repeat_questions:
        observed = {
            (str(row.get("target_level")), str(row.get("condition")))
            for row in repeat_rows
            if row.get("question_id") == question_id
        }
        if observed != expected_cells:
            raise ValueError(f"repeat question {question_id} does not contain all 12 cells")
    if not set(repeated) <= set(baseline):
        raise ValueError("repeat run IDs must be a subset of the baseline Dev run IDs")

    paired: list[dict[str, Any]] = []
    for run_id, repeat in repeated.items():
        base = baseline[run_id]
        for field in (
            "question_id",
            "target_level",
            "condition",
            "generation_model_family",
            "generation_model_revision",
        ):
            if base.get(field) != repeat.get(field):
                raise ValueError(f"{run_id}: repeat {field} differs from the Dev baseline")
        baseline_correctness = optional_score(base, run_id)
        repeat_correctness = optional_score(repeat, run_id)
        base_applicable = base.get("adaptation_applicable", True)
        repeat_applicable = repeat.get("adaptation_applicable", True)
        if type(base_applicable) is not bool or type(repeat_applicable) is not bool:
            raise ValueError("adaptation_applicable must be a boolean")
        adaptation_applicable = base_applicable and repeat_applicable
        baseline_adaptation = optional_float(base, "adaptation_criterion_pass_rate")
        repeat_adaptation = optional_float(repeat, "adaptation_criterion_pass_rate")
        baseline_passed = optional_bool(base, "adaptation_passed")
        repeat_passed = optional_bool(repeat, "adaptation_passed")
        correctness_state = classify(True, baseline_correctness, repeat_correctness)
        adaptation_state = classify(
            adaptation_applicable, baseline_adaptation, repeat_adaptation
        )
        pass_state = classify(
            adaptation_applicable and adaptation_threshold_frozen,
            baseline_passed,
            repeat_passed,
        )
        paired.append(
            {
                "run_id": run_id,
                "question_id": repeat["question_id"],
                "target_level": repeat["target_level"],
                "condition": repeat["condition"],
                "baseline_correctness": baseline_correctness,
                "repeat_correctness": repeat_correctness,
                "correctness_state": correctness_state,
                "adaptation_state": adaptation_state,
                "adaptation_pass_state": pass_state,
                "correctness_difference": (
                    repeat_correctness - baseline_correctness
                    if correctness_state == "evaluated"
                    else None
                ),
                "adaptation_difference": (
                    repeat_adaptation - baseline_adaptation
                    if adaptation_state == "evaluated"
                    else None
                ),
                "correct_flip": (
                    (repeat_correctness == 2) != (baseline_correctness == 2)
                    if correctness_state == "evaluated"
                    else None
                ),
                "adaptation_pass_flip": (
                    repeat_passed != baseline_passed if pass_state == "evaluated" else None
                ),
            }
        )

    def state_counts(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
        return {
            state: sum(row[field] == state for row in rows)
            for state in ("evaluated", "not_evaluated", "not_applicable")
        }

    def correct_flip_rate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Bounded flip rate: unresolved pairs count as unknown, never dropped."""

        denominator = len(rows)
        flips = sum(row["correct_flip"] is True for row in rows)
        unresolved = sum(row["correctness_state"] != "evaluated" for row in rows)
        lower = flips / denominator if denominator else None
        upper = (flips + unresolved) / denominator if denominator else None
        return {
            "denominator": denominator,
            "flip_count": flips,
            "unresolved_count": unresolved,
            "rate": lower if unresolved == 0 else None,
            "rate_bounds": [lower, upper],
        }

    def rate_over_evaluated(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
        values = [row[field] for row in rows if row[field] is not None]
        return sum(bool(value) for value in values) / len(values) if values else None

    def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "pair_count": len(rows),
            "correctness_score_difference": _difference_distribution(
                [
                    float(row["correctness_difference"])
                    for row in rows
                    if row["correctness_difference"] is not None
                ]
            ),
            "adaptation_score_difference": _difference_distribution(
                [
                    float(row["adaptation_difference"])
                    for row in rows
                    if row["adaptation_difference"] is not None
                ]
            ),
            "correct_flip_count": sum(row["correct_flip"] is True for row in rows),
            "correct_flip_rate": correct_flip_rate(rows)["rate"],
            "correct_flip_rate_bounds": correct_flip_rate(rows)["rate_bounds"],
            "adaptation_pass_flip_count": sum(
                row["adaptation_pass_flip"] is True for row in rows
            ),
            "adaptation_pass_flip_rate": rate_over_evaluated(rows, "adaptation_pass_flip"),
            "correctness_pairs": state_counts(rows, "correctness_state"),
            "adaptation_pairs": state_counts(rows, "adaptation_state"),
            "adaptation_pass_pairs": state_counts(rows, "adaptation_pass_state"),
        }

    grouped = []
    for condition in ExperimentArm:
        for level in StudentLevel:
            rows = [
                row
                for row in paired
                if row["condition"] == condition.value
                and row["target_level"] == level.value
            ]
            grouped.append(
                {"condition": condition.value, "target_level": level.value, **summary(rows)}
            )

    by_condition: dict[str, dict[str, Any]] = {}
    for condition in ExperimentArm:
        rows = [row for row in paired if row["condition"] == condition.value]
        evaluated = [row for row in rows if row["correctness_state"] == "evaluated"]
        complete = len(evaluated) == len(rows) and bool(rows)
        baseline_rate = (
            sum(row["baseline_correctness"] == 2 for row in rows) / len(rows)
            if complete
            else None
        )
        repeat_rate = (
            sum(row["repeat_correctness"] == 2 for row in rows) / len(rows)
            if complete
            else None
        )
        by_condition[condition.value] = {
            "condition": condition.value,
            "correct_flip_rate": correct_flip_rate(rows),
            "baseline_strict_correct_rate": baseline_rate,
            "repeat_strict_correct_rate": repeat_rate,
            "strict_correct_rate_difference": (
                repeat_rate - baseline_rate if complete else None
            ),
        }

    comparison = dict(main_comparison) if main_comparison is not None else None
    if correctness_delta is not None and (
        not math.isfinite(correctness_delta) or not 0.0 <= correctness_delta <= 1.0
    ):
        raise ValueError("correctness_delta must be finite and between zero and one")
    comparison_conditions = [
        str(value) for value in (comparison or {}).get("conditions") or []
    ]
    unknown = [value for value in comparison_conditions if value not in by_condition]
    if unknown:
        raise ValueError(f"main comparison names unknown conditions: {unknown}")
    if comparison_conditions and (
        len(comparison_conditions) != 2 or len(set(comparison_conditions)) != 2
    ):
        raise ValueError("main comparison must contain two distinct conditions")
    flip_rows = (
        [row for row in paired if row["condition"] in comparison_conditions]
        if comparison_conditions
        else paired
    )
    # Every condition has the same 90 paired cells, so pooling the two arms' cells gives
    # the mean of their flip rates.
    flip = correct_flip_rate(flip_rows)
    flip_source = (
        f"pooled over main contrast conditions {comparison_conditions}"
        if comparison_conditions
        else "pooled over all four conditions (no registered main contrast)"
    )
    raw_cell_count = (comparison or {}).get("paired_cell_count")
    if raw_cell_count is not None and (
        type(raw_cell_count) is not int or raw_cell_count <= 0
    ):
        raise ValueError("main comparison paired_cell_count must be a positive integer")
    cell_count = raw_cell_count
    if cell_count is None:
        floor_status = "awaiting_main_comparison"
        floor_value = None
        floor_bounds = [None, None]
    else:
        lower_rate, upper_rate = flip["rate_bounds"]
        floor_bounds = [
            math.sqrt(lower_rate / cell_count) if lower_rate is not None else None,
            math.sqrt(upper_rate / cell_count) if upper_rate is not None else None,
        ]
        floor_value = (
            math.sqrt(flip["rate"] / cell_count) if flip["rate"] is not None else None
        )
        floor_status = "complete" if floor_value is not None else "incomplete"

    adaptation_counts = state_counts(paired, "adaptation_state")
    pass_counts = state_counts(paired, "adaptation_pass_state")
    if adaptation_counts["not_evaluated"] or (
        adaptation_threshold_frozen and pass_counts["not_evaluated"]
    ):
        adaptation_status = "incomplete"
    elif not adaptation_threshold_frozen:
        adaptation_status = "threshold_not_frozen"
    else:
        adaptation_status = "complete"

    return {
        "status": floor_status,
        "method": "paired_by_run_id_on_30_question_dev_repeat_batch",
        "question_count": len(repeat_questions),
        "pair_count": len(paired),
        "overall": summary(paired),
        "by_condition_and_level": grouped,
        "by_condition": list(by_condition.values()),
        "strict_correct_noise_floor": {
            "statistic": "sqrt(strict-correct flip rate / main comparison paired cells)",
            "status": floor_status,
            "value": floor_value,
            "bounds": floor_bounds,
            "flip_rate": flip,
            "flip_rate_source": flip_source,
            "main_comparison": comparison,
        },
        "adaptation": {
            "status": adaptation_status,
            "threshold_frozen": adaptation_threshold_frozen,
            "criterion_rate_pairs": adaptation_counts,
            "pass_pairs": pass_counts,
        },
        "correctness_noninferiority_delta": correctness_delta,
        "delta_exceeds_strict_correct_noise_floor": (
            correctness_delta > floor_value
            if correctness_delta is not None and floor_value is not None
            else None
        ),
        "interpretation": (
            "The correctness non-inferiority margin delta must exceed this paired "
            "generation noise floor. The floor is sqrt(flip rate / n): the standard "
            "deviation generation noise adds to the main strict-correct comparison, where "
            "the flip rate counts every cell whose strict-correct outcome changes between "
            "runs, so changes in opposite directions do not cancel, and n is the main "
            "comparison's paired cell count. Using the Dev cell count is conservative for "
            "a larger Test set. Unresolved correctness stays in the denominator; the floor "
            "is then reported only as bounds and not compared with delta. Not-applicable "
            "adaptation pairs (abstained or failed answers, or no frozen threshold) are "
            "counted separately from unevaluated ones. Judge repeat agreement measures "
            "judge variability and cannot replace this comparison."
        ),
    }


def strict_correctness_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Score technical failures as zero and unresolved judge rows as bounded unknowns."""

    records = list(rows)
    correct = 0
    unresolved = 0
    technical_failures = 0
    abstentions = 0
    score_sum = 0.0
    scored_count = 0
    for row in records:
        if bool(row.get("technical_failure")):
            technical_failures += 1
            scored_count += 1
            continue
        if bool(row.get("abstained")):
            abstentions += 1
        score = row.get("correctness_score")
        if score is None:
            unresolved += 1
            continue
        numeric = int(score)
        if numeric not in {0, 1, 2}:
            raise ValueError("correctness_score must be 0, 1, 2, or null")
        scored_count += 1
        score_sum += numeric
        correct += int(numeric == 2)
    denominator = len(records)
    lower = correct / denominator if denominator else None
    upper = (correct + unresolved) / denominator if denominator else None
    point = lower if unresolved == 0 else None
    return {
        "denominator": denominator,
        "strict_correct_count": correct,
        "unresolved_count": unresolved,
        "technical_failure_count": technical_failures,
        "abstention_count": abstentions,
        "strict_correct_rate": point,
        "strict_correct_rate_bounds": [lower, upper],
        "mean_score_over_two": (score_sum / (2 * scored_count) if scored_count else None),
        "mean_score_label": "mean score/2; not accuracy",
    }


def joint_correct_and_adapted_summary(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    records = list(rows)
    successes = 0
    unresolved = 0
    for row in records:
        if bool(row.get("end_to_end_zero")) or bool(row.get("technical_failure")):
            continue
        correctness = row.get("correctness_score")
        adapted = row.get("adaptation_passed")
        if correctness is None or adapted is None:
            unresolved += 1
            continue
        successes += int(int(correctness) == 2 and bool(adapted))
    denominator = len(records)
    return {
        "denominator": denominator,
        "fully_correct_and_adapted_count": successes,
        "unresolved_count": unresolved,
        "rate": successes / denominator if denominator and not unresolved else None,
        "rate_bounds": [
            successes / denominator if denominator else None,
            (successes + unresolved) / denominator if denominator else None,
        ],
    }


def build_v2_generation_report(
    *,
    mode: EvaluationMode,
    decision_config: EvaluationDecisionConfig,
    correctness: Mapping[str, Any],
    adaptation: Sequence[Mapping[str, Any]],
    discrimination: Mapping[str, Any],
    evidence_support: Sequence[Mapping[str, Any]],
    mechanism_diagnostics: Sequence[Mapping[str, Any]],
    text_diagnostics: Sequence[Mapping[str, Any]],
    validity: Mapping[str, Any],
    human_audit: Mapping[str, Any] | None,
    condition_contrasts: Sequence[Mapping[str, Any]],
    lambda_evaluation: Mapping[str, Any] | None,
    generation_noise: Mapping[str, Any],
    applicability_summary: Sequence[Mapping[str, Any]],
    joint_correct_and_adapted: Mapping[str, Any],
    unresolved_items: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    eligibility_condition_contrasts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a report with separate dimensions and fail-closed formal gates."""

    missing_decisions = decision_config.missing_reportable_decisions()
    blockers: list[str] = []
    if not bool(validity.get("formal_use_allowed")):
        blockers.append("judge validity checks did not all pass")
    if human_audit is None or not human_audit.get("rating_count"):
        blockers.append("completed independent human audit is missing")
    elif not human_audit.get("binding_verified"):
        blockers.append("human audit is not bound to its prepared packet and source run")
    elif human_audit.get("rating_count") != human_audit.get("expected_rating_count"):
        blockers.append("human audit does not cover the prepared packet exactly")
    elif int(human_audit.get("rating_count", 0)) < 20:
        blockers.append("human audit is smaller than the registered 20-answer audit")
    elif (
        set(human_audit.get("audit_level_coverage", [])) != {level.value for level in StudentLevel}
        or set(human_audit.get("audit_condition_coverage", []))
        != {condition.value for condition in ExperimentArm}
    ):
        blockers.append("human audit does not cover all levels and conditions")
    if unresolved_items:
        blockers.append("unresolved evaluation items remain")
    denominator = int(correctness.get("denominator", 0) or 0)
    if denominator < 1:
        blockers.append("correctness denominator is empty")
    if int(correctness.get("unresolved_count", 0) or 0):
        blockers.append("correctness scores remain unresolved")
    adapter_record_count = (
        provenance.get("adapter_manifest", {}).get("record_count")
        if isinstance(provenance.get("adapter_manifest"), Mapping)
        else None
    )
    if adapter_record_count is None:
        blockers.append("adapter record count is missing from provenance")
    elif denominator != int(adapter_record_count):
        blockers.append("correctness denominator differs from the adapted run size")
    adapter_manifest = provenance.get("adapter_manifest")
    if not isinstance(adapter_manifest, Mapping) or not adapter_manifest.get("matrix_complete"):
        blockers.append("generation matrix is incomplete")
    input_validation = provenance.get("input_validation")
    if not isinstance(input_validation, Mapping) or not input_validation.get(
        "reportable_input_validation"
    ):
        blockers.append("reportable profile and eligibility input validation is missing")
    observed_rubric_set = provenance.get("correctness_rubric_set_sha256")
    if observed_rubric_set is None:
        blockers.append("correctness rubric set binding is missing")
    elif (
        decision_config.correctness_rubric_set_sha256 is not None
        and observed_rubric_set != decision_config.correctness_rubric_set_sha256
    ):
        blockers.append("correctness rubric set differs from the frozen decision")

    by_metric_contrast: dict[tuple[str, str], Mapping[str, Any]] = {}
    duplicate_contrasts: set[tuple[str, str]] = set()
    for row in condition_contrasts:
        key = (str(row.get("metric")), str(row.get("contrast")))
        if key in by_metric_contrast:
            duplicate_contrasts.add(key)
        by_metric_contrast[key] = row
    if duplicate_contrasts:
        blockers.append("condition contrasts contain duplicate metric/contrast rows")
    primary_row = None
    if decision_config.primary_metric is not None and decision_config.primary_contrast is not None:
        primary_row = by_metric_contrast.get(
            (decision_config.primary_metric, decision_config.primary_contrast)
        )
        if primary_row is None:
            blockers.append("registered primary metric/contrast is missing")
        elif int(primary_row.get("missing_pair_count", 0) or 0):
            blockers.append("registered primary contrast has missing pairs")
        elif not primary_row.get("cluster_bootstrap"):
            blockers.append("registered primary contrast has no clustered interval")

    correctness_noninferiority_result: dict[str, Any] | None = None
    if (
        decision_config.primary_contrast is not None
        and decision_config.correctness_noninferiority_delta is not None
    ):
        correctness_row = by_metric_contrast.get(
            ("strict_correct", decision_config.primary_contrast)
        )
        if correctness_row is None:
            blockers.append("correctness non-inferiority contrast is missing")
        elif int(correctness_row.get("missing_pair_count", 0) or 0):
            blockers.append("correctness non-inferiority contrast has missing pairs")
        else:
            correctness_noninferiority_result = correctness_noninferiority(
                correctness_row,
                delta=decision_config.correctness_noninferiority_delta,
            )
            if correctness_noninferiority_result["status"] != "complete":
                blockers.append("correctness non-inferiority interval is unavailable")

    required_contrasts = set(CONTRASTS)
    for metric in {
        value
        for value in (decision_config.primary_metric, "strict_correct")
        if value is not None
    }:
        present = {
            contrast
            for observed_metric, contrast in by_metric_contrast
            if observed_metric == metric
        }
        if condition_contrasts and present != required_contrasts:
            blockers.append(f"{metric} does not contain all four registered contrasts")
        for contrast in present:
            row = by_metric_contrast[(metric, contrast)]
            if int(row.get("missing_pair_count", 0) or 0):
                blockers.append(f"{metric}/{contrast} has missing pairs")
            if int(row.get("paired_question_level_count", 0) or 0) < 1:
                blockers.append(f"{metric}/{contrast} has no paired observations")
            if not row.get("cluster_bootstrap"):
                blockers.append(f"{metric}/{contrast} has no clustered interval")

    if lambda_evaluation is None:
        blockers.append("lambda verification is missing")
    elif (
        decision_config.selected_lambda is not None
        and lambda_evaluation.get("selected_lambda") != decision_config.selected_lambda
    ):
        blockers.append("lambda verification differs from the frozen selected lambda")
    blockers.extend(f"missing decision: {decision}" for decision in missing_decisions)
    reportable = mode is EvaluationMode.REPORTABLE and not blockers
    if mode is EvaluationMode.REPORTABLE and blockers:
        raise ValueError("reportable evaluation is blocked: " + "; ".join(blockers))
    return {
        "schema_version": "1.0",
        "mode": mode.value,
        "reportable": reportable,
        "claim_boundary": (
            "Independent LLM-judge evaluation under frozen learner profiles and rubrics; "
            "not verified with real learners unless a separate learner study is supplied."
        ),
        "development_blockers": blockers,
        "decision_config": decision_config.model_dump(mode="json"),
        "registered_analysis": {
            "primary_metric": decision_config.primary_metric,
            "primary_contrast": decision_config.primary_contrast,
            "multiplicity_policy": decision_config.multiplicity_policy,
            "primary_result": dict(primary_row) if primary_row is not None else None,
            "correctness_noninferiority": correctness_noninferiority_result,
        },
        "provenance": dict(provenance),
        "automatic_full_run": {
            "correctness": dict(correctness),
            "adaptation": list(adaptation),
            "discrimination": dict(discrimination),
            "evidence_support": list(evidence_support),
            "joint_correct_and_adapted": dict(joint_correct_and_adapted),
            "applicability_subsets": list(applicability_summary),
        },
        "diagnostics": {
            "mechanism": list(mechanism_diagnostics),
            "text": list(text_diagnostics),
            "generation_noise_floor": dict(generation_noise),
        },
        "judge_validity": dict(validity),
        "human_audit": dict(human_audit) if human_audit is not None else None,
        "condition_contrasts": list(condition_contrasts),
        "eligibility_condition_contrasts": list(eligibility_condition_contrasts),
        "lambda_evaluation": dict(lambda_evaluation) if lambda_evaluation else None,
        "unresolved_items": list(unresolved_items),
        "limitations": [
            "Automatic, validity, and human-audit results are reported separately.",
            "Text and Role statistics are descriptive and are not adaptation outcomes.",
            "Development data used for tuning cannot provide an untouched Test claim.",
            "Generation remains stochastic; the correctness non-inferiority margin delta "
            "must exceed the paired repeated-generation noise floor when that batch is "
            "supplied.",
            "Judge repeat agreement measures judge variability and cannot substitute for the "
            "paired repeated-generation comparison.",
            "Main adaptation uses full + endpoint_only questions at all three levels. "
            "All-question and none-subset adaptation results are separate diagnostics; "
            "correctness retains all questions, abstentions and technical failures.",
        ],
    }


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# V2 Generation Evaluation Report",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Reportable: `{str(report['reportable']).lower()}`",
        f"- Claim boundary: {report['claim_boundary']}",
        "",
        "## Development blockers",
        "",
    ]
    blockers = list(report.get("development_blockers", []))
    lines.extend(f"- {blocker}" for blocker in blockers)
    if not blockers:
        lines.append("- None")
    for heading, key in (
        ("Registered analysis", "registered_analysis"),
        ("Automatic full-run results", "automatic_full_run"),
        ("Judge validity", "judge_validity"),
        ("Human audit", "human_audit"),
        ("Condition contrasts", "condition_contrasts"),
        ("Eligibility condition contrasts", "eligibility_condition_contrasts"),
        ("Lambda evaluation", "lambda_evaluation"),
        ("Unresolved items", "unresolved_items"),
        ("Limitations", "limitations"),
    ):
        rendered = json.dumps(report.get(key, []), ensure_ascii=False, indent=2)
        lines.extend(["", f"## {heading}", "", "```json", rendered, "```"])
    noise = (report.get("diagnostics") or {}).get("generation_noise_floor")
    if noise is not None:
        lines.extend(
            [
                "",
                "## Generation noise floor",
                "",
                "The correctness non-inferiority margin delta must exceed the paired "
                "repeated-generation noise floor below. Judge repeat agreement measures "
                "only judge variability and cannot replace it.",
                "",
                "```json",
                json.dumps(noise, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def write_v2_generation_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_dir / "v2_generation_evaluation.json",
        "markdown": output_dir / "v2_generation_evaluation.md",
        "contrasts_csv": output_dir / "v2_generation_condition_contrasts.csv",
        "eligibility_contrasts_csv": output_dir / "v2_generation_eligibility_contrasts.csv",
        "manifest": output_dir / "v2_generation_evaluation_manifest.json",
    }
    paths["json"].write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(_markdown(report), encoding="utf-8")
    contrast_rows = list(report.get("condition_contrasts", []))
    fields = [
        "metric",
        "contrast",
        "treatment",
        "control",
        "estimate",
        "paired_question_level_count",
        "question_cluster_count",
        "missing_pair_count",
        "ci_lower",
        "ci_upper",
    ]
    for output, rows, columns in (
        ("contrasts_csv", contrast_rows, fields),
        (
            "eligibility_contrasts_csv",
            list(report.get("eligibility_condition_contrasts", [])),
            ["eligibility_subset", *fields],
        ),
    ):
        with paths[output].open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                interval = row.get("cluster_bootstrap") or {}
                writer.writerow(
                    {
                        **{field: row.get(field) for field in columns[:-2]},
                        "ci_lower": interval.get("lower"),
                        "ci_upper": interval.get("upper"),
                    }
                )
    manifest = {
        "schema_version": "1.0",
        "reportable": report["reportable"],
        "decision_config": report["decision_config"],
        "provenance": report["provenance"],
        "output_sha256": {
            name: hashlib.sha256(paths[name].read_bytes()).hexdigest()
            for name in ("json", "markdown", "contrasts_csv", "eligibility_contrasts_csv")
        },
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths
