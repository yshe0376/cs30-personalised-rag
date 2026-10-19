from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.evaluation_audit import (
    load_bound_human_audit,
    prepare_calibration_and_audit,
)
from cs30.evaluation.models import PersonalisationEligibility
from cs30.evaluation.v2_generation_cli import _applicability_summary
from cs30.evaluation.v2_generation_models import (
    EvaluationDecisionConfig,
    EvaluationEvidence,
    EvaluationMode,
    ExperimentArm,
    GenerationEvaluationInput,
)
from cs30.evaluation.v2_generation_reporting import (
    answer_text_diagnostics,
    build_v2_generation_report,
    generation_noise_floor,
    generation_stochasticity_summary,
    joint_correct_and_adapted_summary,
    preferred_role_lambda_diagnostic,
    preferred_role_share,
    strict_correctness_summary,
    write_v2_generation_report,
)


def _items() -> list[GenerationEvaluationInput]:
    items: list[GenerationEvaluationInput] = []
    index = 0
    for question in ("q-1", "q-2", "q-3"):
        for level in StudentLevel:
            for condition in ExperimentArm:
                index += 1
                answer = f"Answer {index} explains that a force changes velocity."
                items.append(
                    GenerationEvaluationInput(
                        evaluation_id=f"eval-{index}",
                        run_id=f"run-{index}",
                        question_id=question,
                        question="Why does the object accelerate?",
                        answer=answer,
                        target_level=level,
                        condition=condition,
                        lambda_weight=(
                            0.2
                            if condition
                            in {
                                ExperimentArm.P0R1_RERANKING_ONLY,
                                ExperimentArm.P1R1_COMBINED,
                            }
                            else 0.0
                        ),
                        generation_model_family="gpt-oss",
                        generation_model_revision="20b",
                        eligibility="full",
                        evidence=[
                            EvaluationEvidence(
                                evidence_id="E1",
                                text="A net force changes velocity.",
                                rank=1,
                                role="definition",
                            )
                        ],
                        citation_ids=["E1"],
                        source_artifact_sha256="a" * 64,
                        source_run_sha256="b" * 64,
                        answer_sha256=hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                    )
                )
    return items


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_audit_packets_are_disjoint_deduplicated_and_hide_condition_fields(
    tmp_path: Path,
) -> None:
    paths = prepare_calibration_and_audit(
        _items(),
        tmp_path,
        evaluation_inputs_sha256="c" * 64,
        calibration_size=8,
        audit_size=12,
        seed=7,
    )
    calibration = _jsonl(paths["calibration"])
    audit = _jsonl(paths["audit"])
    private = _jsonl(paths["private_key"])
    assert len(calibration) == 8
    assert len(audit) == 12
    assert {row["blinded_answer_id"] for row in calibration}.isdisjoint(
        {row["blinded_answer_id"] for row in audit}
    )
    assert all("condition" not in row and "lambda_weight" not in row for row in calibration)
    assert all("generation_model_family" not in row for row in audit)
    assert {row["packet"] for row in private} == {"calibration", "audit"}
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["packets_overlap"] is False


def test_audit_deduplicates_same_answer_text_across_different_questions(tmp_path: Path) -> None:
    items = _items()[:3]
    items[1].question_id = "different-question"
    items[1].answer = items[0].answer
    items[1].answer_sha256 = hashlib.sha256(items[1].answer.encode("utf-8")).hexdigest()
    paths = prepare_calibration_and_audit(
        items,
        tmp_path,
        evaluation_inputs_sha256="c" * 64,
        calibration_size=1,
        audit_size=1,
        seed=11,
    )
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["unique_answer_count"] == 2
    assert manifest["deduplication"].startswith("normalized answer text sha256")


def test_bound_human_audit_rejects_unknown_blinded_id(tmp_path: Path) -> None:
    paths = prepare_calibration_and_audit(
        _items(),
        tmp_path,
        evaluation_inputs_sha256="c" * 64,
        calibration_size=8,
        audit_size=12,
        seed=7,
    )
    ratings = [
        {
            "blinded_answer_id": row["blinded_answer_id"],
            "rater_id": "rater-1",
            "adaptation_obvious_error": False,
            "discrimination_obvious_error": False,
            "evidence_support_obvious_error": False,
            "profile_package_sha256": "d" * 64,
            "rubric_sha256": "e" * 64,
        }
        for row in _jsonl(paths["audit"])
    ]
    ratings_path = tmp_path / "ratings.jsonl"
    _write_jsonl(ratings_path, ratings)
    summary = load_bound_human_audit(
        ratings_path=ratings_path,
        audit_packet_path=paths["audit"],
        manifest_path=paths["manifest"],
        private_key_path=paths["private_key"],
        expected_evaluation_inputs_sha256="c" * 64,
        expected_source_run_sha256="b" * 64,
        expected_inputs=_items(),
        expected_profile_package_sha256="d" * 64,
        expected_rubric_sha256="e" * 64,
    )
    assert summary["binding_verified"] is True
    ratings[0]["blinded_answer_id"] = "unknown-audit-id"
    _write_jsonl(ratings_path, ratings)
    with pytest.raises(ValueError, match="cover the independent audit packet exactly once"):
        load_bound_human_audit(
            ratings_path=ratings_path,
            audit_packet_path=paths["audit"],
            manifest_path=paths["manifest"],
            private_key_path=paths["private_key"],
            expected_evaluation_inputs_sha256="c" * 64,
            expected_source_run_sha256="b" * 64,
            expected_inputs=_items(),
        )


def test_audit_preparation_rejects_invalid_inputs_digest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="evaluation_inputs_sha256"):
        prepare_calibration_and_audit(
            _items(),
            tmp_path,
            evaluation_inputs_sha256="not-a-digest",
            calibration_size=8,
            audit_size=12,
        )


def test_correctness_and_joint_results_keep_failures_and_unresolved_bounds() -> None:
    correctness = strict_correctness_summary(
        [
            {"correctness_score": 2, "technical_failure": False},
            {"correctness_score": 1, "technical_failure": False},
            {"correctness_score": None, "technical_failure": False},
            {"correctness_score": None, "technical_failure": True},
        ]
    )
    assert correctness["denominator"] == 4
    assert correctness["technical_failure_count"] == 1
    assert correctness["strict_correct_rate"] is None
    assert correctness["strict_correct_rate_bounds"] == [0.25, 0.5]
    joint = joint_correct_and_adapted_summary(
        [
            {"correctness_score": 2, "adaptation_passed": True},
            {"correctness_score": 2, "adaptation_passed": False},
            {"correctness_score": None, "adaptation_passed": True},
        ]
    )
    assert joint["rate"] is None
    assert joint["rate_bounds"] == [1 / 3, 2 / 3]


def test_abstention_is_an_explicit_end_to_end_zero_not_an_unresolved_item() -> None:
    correctness = strict_correctness_summary(
        [{"correctness_score": 0, "abstained": True, "technical_failure": False}]
    )
    assert correctness["abstention_count"] == 1
    assert correctness["unresolved_count"] == 0
    assert correctness["strict_correct_rate"] == 0.0
    joint = joint_correct_and_adapted_summary(
        [
            {
                "correctness_score": 0,
                "adaptation_passed": None,
                "end_to_end_zero": True,
            }
        ]
    )
    assert joint["unresolved_count"] == 0
    assert joint["rate"] == 0.0


def test_text_and_role_statistics_are_explicitly_diagnostic() -> None:
    text = answer_text_diagnostics(
        "Force equals mass times acceleration. F = m a.",
        jargon_terms=["acceleration"],
    )
    assert text["formula_present"] is True
    assert text["jargon_count"] == 1
    assert "not an adaptation verdict" in text["interpretation"]
    role = preferred_role_share(
        [
            EvaluationEvidence(evidence_id="E1", text="x", rank=1, role="definition"),
            EvaluationEvidence(evidence_id="E2", text="y", rank=2, role="boundary"),
        ],
        StudentLevel.BEGINNER,
    )
    assert role["preferred_role_share"] == 0.5
    assert "not a lambda-selection target" in role["interpretation"]
    lambda_diagnostic = preferred_role_lambda_diagnostic(
        [
            ("q-1", StudentLevel.BEGINNER, 0.0, 0.2),
            ("q-1", StudentLevel.BEGINNER, 0.2, 0.6),
        ]
    )
    assert lambda_diagnostic["nondecreasing_rate"] == 1.0
    stochasticity = generation_stochasticity_summary(
        [("prompt-a", "same"), ("prompt-a", "different"), ("prompt-b", "only")]
    )
    assert stochasticity["pairwise_mismatch_rate"] == 1.0


def test_noise_floor_uses_only_byte_identical_prompt_pairs() -> None:
    items = _items()
    for item in items:
        item.prompt_sha256 = (
            "a" * 64
            if item.condition in {ExperimentArm.P0R0_PLAIN, ExperimentArm.P0R1_RERANKING_ONLY}
            else "b" * 64
        )
    result = generation_noise_floor(items)
    assert result["P0R0_vs_P0R1"]["identical_prompt_pair_count"] == 9
    assert result["P0R0_vs_P0R1"]["answer_mismatch_rate"] == 1.0


def test_applicability_summary_keeps_unresolved_scores_in_the_denominator() -> None:
    all_items = _items()
    items = [all_items[0], all_items[4]]
    summary = _applicability_summary(
        items,
        {items[0].evaluation_id: 2, items[1].evaluation_id: None},
        {items[0].evaluation_id: 0.75},
    )[0]
    assert summary["answer_count"] == 2
    assert summary["correctness_unresolved_count"] == 1
    assert summary["strict_correct_rate"] is None
    assert summary["strict_correct_rate_bounds"] == [0.5, 1.0]
    assert summary["adaptation_expected_count"] == 2
    assert summary["adaptation_unresolved_count"] == 1

    ineligible = items[0].model_copy(
        update={"eligibility": PersonalisationEligibility.NONE}
    )
    ineligible_summary = _applicability_summary(
        [ineligible],
        {ineligible.evaluation_id: 2},
        {},
    )[0]
    assert ineligible_summary["adaptation_expected_count"] == 0
    assert ineligible_summary["adaptation_unresolved_count"] == 0


def test_development_report_separates_sections_and_reportable_mode_fails_closed(
    tmp_path: Path,
) -> None:
    decisions = EvaluationDecisionConfig(decision_version="decisions-pending")
    kwargs = {
        "decision_config": decisions,
        "correctness": {"strict_correct_rate": None},
        "adaptation": [],
        "discrimination": {},
        "evidence_support": [],
        "mechanism_diagnostics": [],
        "text_diagnostics": [],
        "validity": {"formal_use_allowed": False},
        "human_audit": None,
        "condition_contrasts": [],
        "lambda_evaluation": None,
        "generation_noise": {},
        "applicability_summary": [],
        "joint_correct_and_adapted": {},
        "unresolved_items": [{"evaluation_id": "eval-1"}],
        "provenance": {"branch": "feat/v2-m8-generation-evaluation"},
    }
    report = build_v2_generation_report(mode=EvaluationMode.DEVELOPMENT, **kwargs)
    assert report["reportable"] is False
    assert report["automatic_full_run"]["correctness"]["strict_correct_rate"] is None
    paths = write_v2_generation_report(report, tmp_path / "report")
    assert all(path.is_file() for path in paths.values())
    assert "Reportable: `false`" in paths["markdown"].read_text(encoding="utf-8")
    output_hashes = json.loads(paths["manifest"].read_text(encoding="utf-8"))["output_sha256"]
    for name in ("json", "markdown", "contrasts_csv"):
        assert output_hashes[name] == hashlib.sha256(paths[name].read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="reportable evaluation is blocked"):
        build_v2_generation_report(mode=EvaluationMode.REPORTABLE, **kwargs)


def test_report_gate_rejects_unbound_audit_zero_denominator_and_missing_pairs() -> None:
    decisions = EvaluationDecisionConfig(
        decision_version="registered-but-incomplete",
        primary_metric="adaptation_pass",
        primary_contrast="prompt_without_reranking",
        correctness_noninferiority_delta=0.01,
    )
    kwargs = {
        "decision_config": decisions,
        "correctness": {"denominator": 0, "unresolved_count": 0},
        "adaptation": [],
        "discrimination": {},
        "evidence_support": [],
        "mechanism_diagnostics": [],
        "text_diagnostics": [],
        "validity": {"formal_use_allowed": True},
        "human_audit": {
            "rating_count": 1,
            "expected_rating_count": 1,
            "binding_verified": False,
        },
        "condition_contrasts": [
            {
                "metric": "adaptation_pass",
                "contrast": "prompt_without_reranking",
                "missing_pair_count": 999,
                "paired_question_level_count": 1,
                "cluster_bootstrap": {"lower": 0.0, "upper": 0.1},
            },
            {
                "metric": "strict_correct",
                "contrast": "prompt_without_reranking",
                "missing_pair_count": 999,
                "paired_question_level_count": 1,
                "cluster_bootstrap": {"lower": 0.0, "upper": 0.1},
            },
        ],
        "lambda_evaluation": {"selected_lambda": 0.2},
        "generation_noise": {},
        "applicability_summary": [],
        "joint_correct_and_adapted": {},
        "unresolved_items": [],
        "provenance": {"adapter_manifest": {"record_count": 12}},
    }
    report = build_v2_generation_report(mode=EvaluationMode.DEVELOPMENT, **kwargs)
    blockers = set(report["development_blockers"])
    assert "human audit is not bound to its prepared packet and source run" in blockers
    assert "correctness denominator is empty" in blockers
    assert "correctness denominator differs from the adapted run size" in blockers
    assert "registered primary contrast has missing pairs" in blockers
    assert "correctness non-inferiority contrast has missing pairs" in blockers
    kwargs["human_audit"] = {
        "rating_count": 1,
        "expected_rating_count": 1,
        "binding_verified": True,
    }
    report = build_v2_generation_report(mode=EvaluationMode.DEVELOPMENT, **kwargs)
    assert (
        "human audit is smaller than the registered 20-answer audit"
        in report["development_blockers"]
    )
