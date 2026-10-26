"""Not-applicable versus missing pairs in quality contrasts (Leader decision, 2026-10-26)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_v2_generation_cli import _write_judge_evaluation_dir
from test_v2_generation_eligibility_reporting import _labelled_items, _value
from test_v2_generation_repeat_cli import (
    BASELINE_SOURCE_RUN,
    LAMBDA_SHA256,
    _write_input_bundle,
    _write_scores_and_binding,
)

from cs30.contracts import StudentLevel
from cs30.evaluation.condition_statistics import MetricObservation, paired_condition_contrasts
from cs30.evaluation.v2_generation_cli import (
    _noise_floor_adaptation_applicable,
    _quality_not_applicable_cells,
    main,
)
from cs30.evaluation.v2_generation_models import ExperimentArm, GenerationRunStatus
from cs30.evaluation.v2_generation_reporting import _not_applicable_disclosure

ADAPTATION = "adaptation_criterion_pass_rate"
TREATMENT = ExperimentArm.P1R0_PROMPT_ONLY
CONTROL = ExperimentArm.P0R0_PLAIN
MISSING_BLOCKER = "registered primary contrast has missing pairs"

Cell = tuple[str, StudentLevel, ExperimentArm]


def _with_status(item, status: GenerationRunStatus):
    failed = status.is_technical_failure
    return item.model_copy(
        update={
            "source_status": status,
            "abstained": status is GenerationRunStatus.ABSTAINED,
            "technical_failure": failed,
            "answer": None if failed else item.answer,
            "answer_sha256": None if failed else item.answer_sha256,
            "failure_reason": "fixture failure" if failed else None,
        }
    )


def _report(
    tmp_path: Path,
    *,
    abstained: set[Cell] = frozenset(),
    failed: set[Cell] = frozenset(),
    unscored: set[Cell] = frozenset(),
    evidence_unresolved: bool = False,
    include_judge_output: bool = True,
    primary_metric: str = ADAPTATION,
) -> dict:
    items = []
    for item in _labelled_items():
        cell = (item.question_id, item.target_level, item.condition)
        if cell in abstained:
            item = _with_status(item, GenerationRunStatus.ABSTAINED)
        elif cell in failed:
            item = _with_status(item, GenerationRunStatus.GENERATION_ERROR)
        items.append(item)
    inputs, adapter, inputs_hash = _write_input_bundle(
        tmp_path / "baseline", items, source_run_sha256=BASELINE_SOURCE_RUN
    )
    correctness_args = []
    if any(item.source_status is GenerationRunStatus.ANSWERED for item in items):
        scores, binding = _write_scores_and_binding(
            tmp_path / "baseline", items, inputs_sha256=inputs_hash
        )
        correctness_args = [
            "--correctness-scores", str(scores),
            "--correctness-score-binding", str(binding),
        ]
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
        if item.source_status is GenerationRunStatus.ANSWERED
        and (item.question_id, item.target_level, item.condition) not in unscored
    ]
    judge_dir = tmp_path / "judge"
    _write_judge_evaluation_dir(
        judge_dir,
        rows={
            "adaptation": adaptation,
            "unresolved": [
                {
                    "evaluation_id": item.evaluation_id,
                    "dimension": "evidence_support",
                    "reason": "judge result unresolved",
                }
                for item in items
                if evidence_unresolved and item.source_status is GenerationRunStatus.ANSWERED
            ],
        },
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
                "primary_metric": primary_metric,
                "primary_contrast": "prompt_without_reranking",
                "lambda_selection_artifact_sha256": LAMBDA_SHA256,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report"
    assert (
        main(
            [
                "development-report",
                "--inputs", str(inputs),
                "--adapter-manifest", str(adapter),
                *correctness_args,
                *(["--judge-evaluation-dir", str(judge_dir)] if include_judge_output else []),
                "--decision-config", str(decisions),
                "--bootstrap-draws", "20",
                "--output-dir", str(output),
            ]
        )
        == 0
    )
    return json.loads((output / "v2_generation_evaluation.json").read_text(encoding="utf-8"))


def test_one_arm_abstaining_is_not_applicable_and_not_counted_missing(tmp_path: Path) -> None:
    report = _report(tmp_path, abstained={("q-00", StudentLevel.BEGINNER, TREATMENT)})

    primary = report["registered_analysis"]["primary_result"]
    assert primary["missing_pair_count"] == 0
    assert primary["not_applicable_pair_count"] == 1
    assert primary["paired_question_level_count"] == 5
    assert MISSING_BLOCKER not in report["development_blockers"]
    # Non-answers are excluded, never scored zero; correctness keeps its system zero.
    assert report["automatic_full_run"]["correctness"]["denominator"] == 36


def test_answered_but_unscored_pair_is_missing_and_the_gate_blocks(tmp_path: Path) -> None:
    report = _report(tmp_path, unscored={("q-00", StudentLevel.BEGINNER, TREATMENT)})

    primary = report["registered_analysis"]["primary_result"]
    assert primary["missing_pair_count"] == 1
    assert primary["not_applicable_pair_count"] == 0
    assert MISSING_BLOCKER in report["development_blockers"]


def test_every_arm_failing_for_a_question_level_is_not_applicable(tmp_path: Path) -> None:
    failed = {("q-01", StudentLevel.ADVANCED, condition) for condition in ExperimentArm}
    report = _report(tmp_path, failed=failed)

    primary = report["registered_analysis"]["primary_result"]
    assert primary["missing_pair_count"] == 0
    assert primary["not_applicable_pair_count"] == 1
    assert primary["treatment_not_applicable"] == 1
    assert primary["control_not_applicable"] == 1
    assert MISSING_BLOCKER not in report["development_blockers"]


def test_per_condition_not_applicable_counts_are_disclosed(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        abstained={
            ("q-00", StudentLevel.BEGINNER, TREATMENT),
            ("q-00", StudentLevel.ADVANCED, TREATMENT),
        },
        failed={("q-01", StudentLevel.INTERMEDIATE, CONTROL)},
    )

    disclosure = report["registered_analysis"]["primary_not_applicable"]
    assert disclosure["question_level_count"] == 6
    assert disclosure["not_applicable_pair_count"] == 3
    assert disclosure["treatment"] == TREATMENT.value
    assert disclosure["treatment_not_applicable"] == 2
    assert disclosure["treatment_not_applicable_rate"] == pytest.approx(2 / 6)
    assert disclosure["control"] == CONTROL.value
    assert disclosure["control_not_applicable"] == 1
    assert disclosure["control_not_applicable_rate"] == pytest.approx(1 / 6)
    assert disclosure["rate_difference"] == pytest.approx(1 / 6)
    assert disclosure["warning_threshold"] is None
    assert MISSING_BLOCKER not in report["development_blockers"]


def test_pairing_drops_not_applicable_cells_without_counting_them_missing() -> None:
    observations = [
        MetricObservation(
            question_id="q1",
            target_level=StudentLevel.BEGINNER,
            condition=CONTROL,
            metric=ADAPTATION,
            value=1.0,
        )
    ]
    expected = {ADAPTATION: {("q1", StudentLevel.BEGINNER), ("q2", StudentLevel.BEGINNER)}}
    row = next(
        row
        for row in paired_condition_contrasts(
            observations,
            bootstrap_draws=10,
            expected_question_levels=expected,
            not_applicable_cells={ADAPTATION: {("q1", StudentLevel.BEGINNER, TREATMENT)}},
        )
        if row["contrast"] == "prompt_without_reranking"
    )
    # q1 has a not-applicable treatment arm; q2 was expected but never scored.
    assert row["not_applicable_pair_count"] == 1
    assert row["treatment_not_applicable"] == 1
    assert row["control_not_applicable"] == 0
    assert row["missing_pair_count"] == 1
    assert row["missing_pairs"] == [{"question_id": "q2", "target_level": "beginner"}]


def test_evidence_metrics_use_the_same_rule_and_correctness_is_untouched() -> None:
    items = _labelled_items()
    failed = _with_status(items[0], GenerationRunStatus.GENERATION_ERROR)
    nothing_evaluable = items[1]
    items = [failed, nothing_evaluable, *items[2:]]
    cells = _quality_not_applicable_cells(
        items,
        adaptation_not_applicable_ids=frozenset({items[2].evaluation_id}),
        evidence_rows=[
            {
                "evaluation_id": nothing_evaluable.evaluation_id,
                "bundle_faithfulness": None,
                "evaluable_bundle_claim_count": 0,
                "citation_support": 0.5,
                "evaluable_citation_claim_count": 2,
            }
        ],
    )

    def cell(item):
        return (item.question_id, item.target_level, item.condition)

    assert set(cells) == {ADAPTATION, "bundle_faithfulness", "citation_support"}
    for metric in cells:
        assert cell(failed) in cells[metric]
    assert cell(nothing_evaluable) in cells["bundle_faithfulness"]
    assert cell(nothing_evaluable) not in cells["citation_support"]
    assert cell(items[2]) in cells[ADAPTATION]
    assert cell(items[2]) not in cells["bundle_faithfulness"]


def test_noise_floor_adaptation_scope_matches_the_main_result() -> None:
    items = {item.question_id: item for item in _labelled_items()}
    scored = {"criterion_pass_rate": 0.5, "evaluable_criterion_count": 2}

    assert _noise_floor_adaptation_applicable(items["q-00"], scored) is True
    assert _noise_floor_adaptation_applicable(items["q-01"], scored) is True
    assert _noise_floor_adaptation_applicable(items["q-02"], scored) is False  # none
    assert (
        _noise_floor_adaptation_applicable(
            items["q-00"], {"criterion_pass_rate": None, "evaluable_criterion_count": 0}
        )
        is False
    )
    abstained = _with_status(items["q-00"], GenerationRunStatus.ABSTAINED)
    assert _noise_floor_adaptation_applicable(abstained, scored) is False


def test_disclosure_is_absent_without_a_primary_row() -> None:
    assert _not_applicable_disclosure(None) is None


def test_metric_with_only_not_applicable_cells_is_still_reported() -> None:
    from cs30.evaluation.v2_generation_cli import _eligibility_condition_contrasts

    items = _labelled_items()
    every_cell = {(item.question_id, item.target_level, item.condition) for item in items}
    _, rows = _eligibility_condition_contrasts(
        items,
        [],
        bootstrap_draws=10,
        bootstrap_seed=1,
        not_applicable_cells={"bundle_faithfulness": every_cell, ADAPTATION: set()},
    )

    bundle = [row for row in rows if row["metric"] == "bundle_faithfulness"]
    assert bundle, "an all-not-applicable metric must not disappear"
    overall = next(
        row
        for row in bundle
        if row["eligibility_subset"] == "all" and row["contrast"] == "prompt_without_reranking"
    )
    assert overall["not_applicable_pair_count"] == 9
    assert overall["missing_pair_count"] == 0
    assert overall["paired_question_level_count"] == 0


def test_not_applicable_cells_are_restricted_to_each_subset() -> None:
    from cs30.evaluation.v2_generation_cli import _eligibility_condition_contrasts

    items = _labelled_items()
    none_cells = {
        (item.question_id, item.target_level, item.condition)
        for item in items
        if item.eligibility.value == "none"
    }
    _, rows = _eligibility_condition_contrasts(
        items,
        [],
        bootstrap_draws=10,
        bootstrap_seed=1,
        not_applicable_cells={"citation_support": none_cells},
    )

    def row(subset: str):
        return next(
            (
                item
                for item in rows
                if item["metric"] == "citation_support"
                and item["eligibility_subset"] == subset
                and item["contrast"] == "prompt_without_reranking"
            ),
            None,
        )

    assert row("none")["not_applicable_pair_count"] == 3
    assert row("all")["not_applicable_pair_count"] == 3
    # The full subset has no not-applicable cells of its own, so nothing leaks in.
    assert row("full")["not_applicable_pair_count"] == 0
    assert row("full")["missing_pair_count"] == 3
    assert row("full_and_endpoint_only")["not_applicable_pair_count"] == 0
    assert row("full_and_endpoint_only")["missing_pair_count"] == 6


def test_evidence_metrics_are_absent_when_evidence_evaluation_was_not_supplied() -> None:
    items = _labelled_items()
    failed = _with_status(items[0], GenerationRunStatus.GENERATION_ERROR)
    cells = _quality_not_applicable_cells(
        [failed, *items[1:]],
        adaptation_not_applicable_ids=frozenset(),
        evidence_rows=[],
    )

    assert set(cells) == {ADAPTATION}


def test_pairing_reports_a_metric_known_only_from_not_applicable_cells() -> None:
    row = next(
        row
        for row in paired_condition_contrasts(
            [],
            bootstrap_draws=10,
            not_applicable_cells={
                "citation_support": {
                    ("q1", StudentLevel.BEGINNER, TREATMENT),
                    ("q1", StudentLevel.BEGINNER, CONTROL),
                }
            },
        )
        if row["contrast"] == "prompt_without_reranking"
    )

    assert row["metric"] == "citation_support"
    assert row["not_applicable_pair_count"] == 1
    assert row["treatment_not_applicable"] == 1
    assert row["control_not_applicable"] == 1
    assert row["missing_pair_count"] == 0


def test_all_evidence_judge_errors_remain_missing_in_the_cli_report(tmp_path: Path) -> None:
    report = _report(
        tmp_path, evidence_unresolved=True, primary_metric="bundle_faithfulness"
    )

    for metric in ("bundle_faithfulness", "citation_support"):
        row = next(
            row for row in report["condition_contrasts"]
            if row["metric"] == metric and row["contrast"] == "prompt_without_reranking"
        )
        assert row["missing_pair_count"] == 9
        assert row["not_applicable_pair_count"] == 0
        assert row["paired_question_level_count"] == 0
    assert len(report["unresolved_items"]) == 36
    assert MISSING_BLOCKER in report["development_blockers"]
    assert "unresolved evaluation items remain" in report["development_blockers"]


@pytest.mark.parametrize("status", ["failed", "abstained"])
def test_all_non_answers_keep_evidence_exclusions_in_the_cli_report(
    tmp_path: Path, status: str
) -> None:
    cells = {(item.question_id, item.target_level, item.condition) for item in _labelled_items()}
    report = _report(
        tmp_path, **{status: cells}, primary_metric="bundle_faithfulness"
    )

    for metric in ("bundle_faithfulness", "citation_support"):
        row = next(
            row for row in report["condition_contrasts"]
            if row["metric"] == metric and row["contrast"] == "prompt_without_reranking"
        )
        assert row["not_applicable_pair_count"] == 9
        assert row["treatment_not_applicable"] == 9
        assert row["control_not_applicable"] == 9
        assert row["missing_pair_count"] == 0
        assert row["paired_question_level_count"] == 0
    assert MISSING_BLOCKER not in report["development_blockers"]
    assert "registered primary contrast has no clustered interval" in report["development_blockers"]
    correctness = report["automatic_full_run"]["correctness"]
    assert correctness["denominator"] == 36
    assert correctness["strict_correct_rate"] == 0


def test_no_judge_directory_does_not_declare_evidence_contrasts(tmp_path: Path) -> None:
    report = _report(tmp_path, include_judge_output=False)

    assert not any(
        row["metric"] in {"bundle_faithfulness", "citation_support"}
        for row in report["condition_contrasts"]
    )
