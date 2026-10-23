"""Deterministic diagnostics and combined reporting for V2 generation evaluation."""

from __future__ import annotations

import csv
import hashlib
import json
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
        "lambda_evaluation": dict(lambda_evaluation) if lambda_evaluation else None,
        "unresolved_items": list(unresolved_items),
        "limitations": [
            "Automatic, validity, and human-audit results are reported separately.",
            "Text and Role statistics are descriptive and are not adaptation outcomes.",
            "Development data used for tuning cannot provide an untouched Test claim.",
            "Generation at temperature zero remains stochastic; see the reported noise floor.",
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
        ("Lambda evaluation", "lambda_evaluation"),
        ("Unresolved items", "unresolved_items"),
        ("Limitations", "limitations"),
    ):
        rendered = json.dumps(report[key], ensure_ascii=False, indent=2)
        lines.extend(["", f"## {heading}", "", "```json", rendered, "```"])
    return "\n".join(lines) + "\n"


def write_v2_generation_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_dir / "v2_generation_evaluation.json",
        "markdown": output_dir / "v2_generation_evaluation.md",
        "contrasts_csv": output_dir / "v2_generation_condition_contrasts.csv",
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
    with paths["contrasts_csv"].open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in contrast_rows:
            interval = row.get("cluster_bootstrap") or {}
            writer.writerow(
                {
                    **{field: row.get(field) for field in fields[:-2]},
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
            for name in ("json", "markdown", "contrasts_csv")
        },
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths
