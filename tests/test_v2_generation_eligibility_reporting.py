"""Eligibility subsets must not change the main correctness denominator."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
from test_v2_generation_cli import _write_judge_evaluation_dir
from test_v2_generation_repeat_cli import (
    BASELINE_SOURCE_RUN,
    LAMBDA_SHA256,
    _inputs,
    _write_input_bundle,
    _write_scores_and_binding,
)

from cs30.contracts import StudentLevel
from cs30.evaluation.condition_statistics import MetricObservation, paired_condition_contrasts
from cs30.evaluation.models import PersonalisationEligibility
from cs30.evaluation.v2_generation_cli import (
    _applicability_summary,
    _eligibility_condition_contrasts,
    main,
)
from cs30.evaluation.v2_generation_models import ExperimentArm, GenerationRunStatus

ADAPTATION = "adaptation_criterion_pass_rate"


def _labelled_items():
    items = _inputs(3, label="baseline", source_run_sha256=BASELINE_SOURCE_RUN)
    labels = {"q-00": "full", "q-01": "endpoint_only", "q-02": "none"}
    return [
        item.model_copy(
            update={"eligibility": PersonalisationEligibility(labels[item.question_id])}
        )
        for item in items
    ]


def _value(question: str, condition: ExperimentArm) -> float:
    prompted = condition in {ExperimentArm.P1R0_PROMPT_ONLY, ExperimentArm.P1R1_COMBINED}
    return {
        "q-00": float(prompted),
        "q-01": 0.5 * prompted,
        "q-02": float(not prompted),
    }[question]


def test_stratified_contrasts_keep_none_diagnostics_out_of_the_main_effect() -> None:
    items = _labelled_items()
    observations = [
        MetricObservation(
            question_id=item.question_id,
            target_level=item.target_level,
            condition=item.condition,
            metric=metric,
            value=_value(item.question_id, item.condition) if metric == ADAPTATION else 1.0,
        )
        for item in items
        for metric in (ADAPTATION, "strict_correct")
    ]
    primary, subsets = _eligibility_condition_contrasts(
        items, observations, bootstrap_draws=40, bootstrap_seed=7
    )
    indexed = {(row["metric"], row["contrast"]): row for row in primary}
    assert len(indexed) == len(primary) == 8
    adaptation = indexed[ADAPTATION, "prompt_without_reranking"]
    assert adaptation["estimate"] == 0.75
    assert adaptation["paired_question_level_count"] == 6
    assert adaptation["question_cluster_count"] == 2
    assert adaptation["cluster_bootstrap"]["draws"] == 40
    assert indexed["strict_correct", "prompt_without_reranking"][
        "paired_question_level_count"
    ] == 9
    by_subset = {
        row["eligibility_subset"]: row
        for row in subsets
        if row["metric"] == ADAPTATION and row["contrast"] == "prompt_without_reranking"
    }
    assert by_subset["all"]["estimate"] == pytest.approx(1 / 6)
    assert by_subset["full"]["estimate"] == 1
    assert by_subset["endpoint_only"]["estimate"] == 0.5
    assert by_subset["none"]["estimate"] == -1


def test_empty_main_subset_does_not_fall_back_to_none_scores() -> None:
    items = [item for item in _labelled_items() if item.eligibility.value == "none"]
    observations = [
        MetricObservation(
            question_id=item.question_id,
            target_level=item.target_level,
            condition=item.condition,
            metric=ADAPTATION,
            value=1.0,
        )
        for item in items
    ]
    primary, _ = _eligibility_condition_contrasts(
        items, observations, bootstrap_draws=20, bootstrap_seed=7
    )
    for row in primary:
        if row["metric"] == ADAPTATION:
            assert row["paired_question_level_count"] == 0
            assert row["estimate"] is None
            assert row["cluster_bootstrap"] is None


def test_statistics_keep_a_wholly_unscored_question_in_expected_pairs() -> None:
    result = paired_condition_contrasts(
        [],
        expected_question_levels={ADAPTATION: {("missing", StudentLevel.INTERMEDIATE)}},
    )
    assert len(result) == 4
    for row in result:
        assert row["missing_pair_count"] == 1
        assert row["paired_question_level_count"] == 0
        assert row["estimate"] is None


def test_subsets_reject_inconsistent_question_labels() -> None:
    items = _labelled_items()
    items[0] = items[0].model_copy(update={"eligibility": PersonalisationEligibility.NONE})
    with pytest.raises(ValueError, match="q-00: inconsistent eligibility"):
        _eligibility_condition_contrasts(items, [], bootstrap_draws=20, bootstrap_seed=7)


def test_none_summary_keeps_scores_and_separates_missing_na_and_failed_answers() -> None:
    source = [item for item in _labelled_items() if item.eligibility.value == "none"]
    items = [source[i] for i in (0, 4, 8)]
    summary = _applicability_summary(
        items,
        {item.evaluation_id: 2 for item in items},
        {items[0].evaluation_id: 0.75, items[1].evaluation_id: None},
        adaptation_not_applicable_ids=frozenset({items[1].evaluation_id}),
    )
    none = next(row for row in summary if row["eligibility"] == "none")
    assert none["mean_adaptation_criterion_pass_rate"] == 0.75
    assert none["adaptation_expected_count"] == 3
    assert none["adaptation_evaluable_count"] == 1
    assert none["adaptation_not_applicable_count"] == 1
    assert none["adaptation_unresolved_count"] == 1
    assert none["main_adaptation_answer_count"] == 0
    aggregate = next(row for row in summary if row["subset"] == "all")
    assert aggregate["eligibility"] is None
    assert all(row["eligibility"] == row["subset"] for row in summary if row["subset"] == "none")
    failed = items[2].model_copy(update={"technical_failure": True})
    failed_summary = _applicability_summary(
        [failed], {failed.evaluation_id: 0}, {failed.evaluation_id: 1.0}
    )
    assert failed_summary[0]["adaptation_expected_count"] == 0
    assert failed_summary[0]["adaptation_evaluable_count"] == 0
    assert failed_summary[0]["adaptation_unresolved_count"] == 0


@pytest.mark.parametrize("omit_endpoint_question", [False, True])
@pytest.mark.parametrize(
    "none_status", [None, GenerationRunStatus.ABSTAINED, GenerationRunStatus.GENERATION_ERROR]
)
def test_development_report_exports_eligibility_effects_and_preserves_correctness(
    tmp_path: Path, omit_endpoint_question: bool, none_status: GenerationRunStatus | None
) -> None:
    items = _labelled_items()
    if none_status is not None:
        items = [
            item.model_copy(
                update={
                    "source_status": none_status,
                    "abstained": none_status is GenerationRunStatus.ABSTAINED,
                    "technical_failure": none_status.is_technical_failure,
                    "answer": None if none_status.is_technical_failure else item.answer,
                    "answer_sha256": None
                    if none_status.is_technical_failure else item.answer_sha256,
                    "failure_reason": (
                        "fixture failure" if none_status.is_technical_failure else None
                    ),
                }
            ) if item.eligibility.value == "none" else item
            for item in items
        ]
    inputs, adapter, inputs_hash = _write_input_bundle(
        tmp_path / "baseline", items, source_run_sha256=BASELINE_SOURCE_RUN
    )
    scores, binding = _write_scores_and_binding(
        tmp_path / "baseline", items, inputs_sha256=inputs_hash
    )
    adaptation = [
        {
            "evaluation_id": item.evaluation_id,
            "question_id": item.question_id,
            "target_level": item.target_level.value,
            "evaluated_level": item.target_level.value,
            "condition": item.condition.value,
            "eligibility": item.eligibility.value,
            "is_target_level_evaluation": True,
            "enters_main_adaptation_result": item.eligibility.value != "none",
            "criterion_pass_rate": _value(item.question_id, item.condition),
            "evaluable_criterion_count": 2,
        }
        for item in items
        if not (omit_endpoint_question and item.question_id == "q-01")
        and item.source_status is GenerationRunStatus.ANSWERED
    ]
    # A non-target checklist result must not replace the target-level diagnostic.
    adaptation.append(
        {
            **adaptation[-1],
            "is_target_level_evaluation": False,
            "enters_main_adaptation_result": False,
            "criterion_pass_rate": 0.99,
        }
    )
    judge_dir = tmp_path / "judge"
    _write_judge_evaluation_dir(
        judge_dir,
        rows={"adaptation": adaptation},
        provenance={
            "evaluation_inputs_sha256": inputs_hash,
            "source_run_sha256": BASELINE_SOURCE_RUN,
        },
    )
    decisions = tmp_path / "decisions.json"
    decisions.write_text(
        json.dumps(
            {
                "decision_version": "pending",
                "primary_metric": ADAPTATION,
                "primary_contrast": "prompt_without_reranking",
                "lambda_selection_artifact_sha256": LAMBDA_SHA256,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report"
    assert main(
        [
            "development-report",
            "--inputs", str(inputs),
            "--adapter-manifest", str(adapter),
            "--correctness-scores", str(scores),
            "--correctness-score-binding", str(binding),
            "--judge-evaluation-dir", str(judge_dir),
            "--decision-config", str(decisions),
            "--bootstrap-draws", "20",
            "--output-dir", str(output),
        ]
    ) == 0
    report = json.loads((output / "v2_generation_evaluation.json").read_text(encoding="utf-8"))
    assert report["automatic_full_run"]["correctness"]["denominator"] == 36
    assert report["automatic_full_run"]["correctness"]["strict_correct_rate"] == (
        1.0 if none_status is None else 2 / 3
    )
    primary = report["registered_analysis"]["primary_result"]
    assert primary["eligibility_subset"] == "full_and_endpoint_only"
    assert primary["paired_question_level_count"] == (3 if omit_endpoint_question else 6)
    assert primary["missing_pair_count"] == (3 if omit_endpoint_question else 0)
    assert primary["estimate"] == (1.0 if omit_endpoint_question else 0.75)
    assert report["automatic_full_run"]["joint_correct_and_adapted"]["denominator"] == 24
    subsets = report["automatic_full_run"]["applicability_subsets"]
    none_plain = next(
        row for row in subsets
        if row["eligibility"] == "none" and row["condition"] == "P0R0_plain"
    )
    assert none_plain["mean_adaptation_criterion_pass_rate"] == (
        1.0 if none_status is None else None
    )
    assert none_plain["adaptation_unresolved_count"] == 0
    assert none_plain["main_adaptation_answer_count"] == 0
    assert "duplicate metric/contrast" not in " ".join(report["development_blockers"])
    if omit_endpoint_question:
        assert "registered primary contrast has missing pairs" in report["development_blockers"]
    with (output / "v2_generation_eligibility_contrasts.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        csv_rows = list(csv.DictReader(stream))
    assert {row["eligibility_subset"] for row in csv_rows} == {
        "all", "full", "endpoint_only", "none", "full_and_endpoint_only"
    }
    assert "Eligibility condition contrasts" in (
        output / "v2_generation_evaluation.md"
    ).read_text(encoding="utf-8")
    manifest = json.loads(
        (output / "v2_generation_evaluation_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["output_sha256"]["eligibility_contrasts_csv"] == hashlib.sha256(
        (output / "v2_generation_eligibility_contrasts.csv").read_bytes()
    ).hexdigest()
