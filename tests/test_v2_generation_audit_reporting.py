from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.evaluation_audit import prepare_calibration_and_audit
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
                items.append(
                    GenerationEvaluationInput(
                        evaluation_id=f"eval-{index}",
                        run_id=f"run-{index}",
                        question_id=question,
                        question="Why does the object accelerate?",
                        answer=f"Answer {index} explains that a force changes velocity.",
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
                    )
                )
    return items


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_audit_packets_are_disjoint_deduplicated_and_hide_condition_fields(
    tmp_path: Path,
) -> None:
    paths = prepare_calibration_and_audit(
        _items(),
        tmp_path,
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
        "unresolved_items": [{"evaluation_id": "eval-1"}],
        "provenance": {"branch": "feat/v2-m8-generation-evaluation"},
    }
    report = build_v2_generation_report(mode=EvaluationMode.DEVELOPMENT, **kwargs)
    assert report["reportable"] is False
    assert report["automatic_full_run"]["correctness"]["strict_correct_rate"] is None
    paths = write_v2_generation_report(report, tmp_path / "report")
    assert all(path.is_file() for path in paths.values())
    assert "Reportable: `false`" in paths["markdown"].read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="reportable evaluation is blocked"):
        build_v2_generation_report(mode=EvaluationMode.REPORTABLE, **kwargs)
