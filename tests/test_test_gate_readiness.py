"""No generated Test answers: synthetic rubrics/Gold and public ID/config metadata only."""

import argparse
import json
import socket
from pathlib import Path

import pytest

from cs30.evaluation.level_profiles import load_eligibility_package
from cs30.evaluation.test_gate_analysis import PROFILE_SHA
from cs30.evaluation.test_gate_readiness import FROZEN_JUDGE_FILE_SHA, file_sha, prepare
from cs30.evaluation.v2_generation_cli import main as eval_cli
from cs30.evaluation.v2_generation_models import EligibilityReviewWaiver

REPO = Path(__file__).resolve().parents[1]
LABELS = REPO / "docs/evaluation/eligibility-v1/personalisation_eligibility_v1.jsonl"
PROFILE = REPO / "docs/evaluation/level-profile-v1/profile_checklist.frozen.json"
SPLIT = REPO / "docs/examples/v2-generation-split-dev154-test187.json"
CONFIG = REPO / (
    "docs/results/m8_dev_validity_diagnostics_20261029/perturbation-results/"
    "run/config/judge-config.low.json"
)


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("readiness tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def waiver():
    return EligibilityReviewWaiver(
        decision_record=("https://github.com/yshe0376/cs30-personalised-rag/pull/224"),
        decided_by="yshe0376",
        decision_date="2026-10-29",
        profile_package_sha256=PROFILE_SHA,
        eligibility_sha256="ab585f05c02ec896889bae174475493f954eee1d4bb2dda32fc111fe4ef54c42",
        calibration_waived=True,
        content_review_waived=True,
        labelling_rerun_waived=True,
    )


def save(path, data):
    path.write_bytes((json.dumps(data, sort_keys=True) + "\n").encode())
    return path


def test_waiver_binds_exact_label_bytes_profile_and_does_not_claim_calibration(tmp_path):
    record = load_eligibility_package(
        LABELS,
        package_version="fixture",
        gold_version="fixture",
        gold_sha256="a" * 64,
        review_waiver=waiver(),
        profile_package_sha256=PROFILE_SHA,
        expected_question_ids=["sciq-train-00004"],
        require_resolved=True,
    )
    assert record.calibration_question_count is None
    assert record.leader_calibration_record_sha256 is None
    changed = tmp_path / "changed.jsonl"
    changed.write_bytes(LABELS.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="label bytes"):
        load_eligibility_package(
            changed,
            package_version="fixture",
            gold_version="fixture",
            gold_sha256="a" * 64,
            review_waiver=waiver(),
            profile_package_sha256=PROFILE_SHA,
        )
    with pytest.raises(ValueError, match="different frozen profile"):
        load_eligibility_package(
            LABELS,
            package_version="fixture",
            gold_version="fixture",
            gold_sha256="a" * 64,
            review_waiver=waiver(),
            profile_package_sha256="b" * 64,
        )


def test_legacy_path_still_requires_evidence_and_waiver_cannot_mix_claims():
    with pytest.raises(ValueError, match="calibration evidence"):
        load_eligibility_package(
            LABELS, package_version="x", gold_version="x", gold_sha256="a" * 64
        )
    with pytest.raises(ValueError, match="must not claim"):
        load_eligibility_package(
            LABELS,
            package_version="x",
            gold_version="x",
            gold_sha256="a" * 64,
            review_waiver=waiver(),
            profile_package_sha256=PROFILE_SHA,
            calibration_question_count=15,
        )


@pytest.fixture
def readiness_args(tmp_path):
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    ids = sorted(k for k, v in split.items() if v == "test")
    gold = tmp_path / "synthetic_gold.jsonl"
    gold.write_bytes("".join(json.dumps({"question_id": q}) + "\n" for q in ids).encode())
    gold_sha = file_sha(gold)
    review = save(tmp_path / "waiver.json", waiver().model_dump(mode="json"))
    validation = tmp_path / "validation.json"
    assert (
        eval_cli(
            [
                "validate-inputs",
                "--profiles",
                str(PROFILE),
                "--eligibility",
                str(LABELS),
                "--gold",
                str(gold),
                "--gold-version",
                "synthetic-only",
                "--eligibility-version",
                "v1",
                "--eligibility-review-waiver",
                str(review),
                "--reportable",
                "--output",
                str(validation),
            ]
        )
        == 0
    )
    rubrics = tmp_path / "synthetic_rubrics.jsonl"
    rubrics.write_bytes(
        "".join(
            json.dumps(
                {
                    "question_id": q,
                    "gold_sha256": gold_sha,
                    "rubric_version": "synthetic-only",
                    "criteria": [
                        {
                            "criterion_id": "core",
                            "description": "Synthetic fixture criterion, not a real Test answer",
                            "core": True,
                            "reference_span_ids": ["fixture-span"],
                        }
                    ],
                    "required_paths": [["core"]],
                }
            )
            + "\n"
            for q in ids
        ).encode()
    )
    question_ids = tmp_path / "ids.txt"
    question_ids.write_bytes(("\n".join(ids) + "\n").encode())
    return argparse.Namespace(
        profiles=PROFILE,
        judge_config=CONFIG,
        input_validation=validation,
        gold=gold,
        rubrics=rubrics,
        question_ids=question_ids,
        split_map=SPLIT,
        expected_rubrics_sha256=file_sha(rubrics),
        output=tmp_path / "ready.json",
    )


def test_prepare_records_all_187_rubrics_before_scores_and_never_reads_answers(readiness_args):
    assert file_sha(CONFIG) == FROZEN_JUDGE_FILE_SHA
    result = prepare(readiness_args)
    assert len(result["per_question_rubric_sha256"]) == 187
    assert result["expected_cells_per_generator"] == 2244
    assert result["rubrics_independently_reviewed"] is False
    assert result["eligibility_human_calibrated"] is False
    assert result["paid_execution_authorized"] is False
    assert result["provider_calls"] == 0
    assert len(result["correctness_rubric_set_sha256"]) == 64
    assert b"\r" not in readiness_args.output.read_bytes()


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "wrong_gold",
        "changed_bytes",
        "wrong_ids",
        "changed_judge",
        "changed_validation",
    ],
)
def test_prepare_fails_before_writing_for_changed_inputs(readiness_args, change, tmp_path):
    args = readiness_args
    data = [json.loads(line) for line in args.rubrics.read_text().splitlines()]
    if change == "missing":
        data.pop()
    elif change == "duplicate":
        data.append(data[0])
    elif change == "wrong_gold":
        data[0]["gold_sha256"] = "f" * 64
    elif change == "wrong_ids":
        args.question_ids.write_bytes(b"wrong\n")
    elif change == "changed_judge":
        args.judge_config = save(tmp_path / "judge.json", {"thinking_level": "high"})
    elif change == "changed_validation":
        args.input_validation = save(tmp_path / "bad-validation.json", {"valid": True})
    if change in {"missing", "duplicate", "wrong_gold"}:
        args.rubrics.write_bytes("".join(json.dumps(r) + "\n" for r in data).encode())
        args.expected_rubrics_sha256 = file_sha(args.rubrics)
    elif change == "changed_bytes":
        args.rubrics.write_bytes(args.rubrics.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        prepare(args)
    assert not args.output.exists()


def test_waiver_authority_cannot_be_changed():
    payload = waiver().model_dump(mode="json")
    payload["decided_by"] = "someone-else"
    with pytest.raises(ValueError):
        EligibilityReviewWaiver.model_validate(payload)


def test_synthetic_full_matrix_report_uses_native_bindings_and_rejects_changed_rubric(
    readiness_args,
    tmp_path,
):
    from cs30.contracts import StudentLevel
    from cs30.evaluation.judge_results import write_judge_evaluation_outputs
    from cs30.evaluation.test_gate_readiness import report
    from cs30.evaluation.v2_generation_artifacts import (
        build_correctness_score_binding,
        write_correctness_score_binding,
    )
    from cs30.evaluation.v2_generation_models import ExperimentArm, GenerationEvaluationInput

    ready = prepare(readiness_args)
    items, scores, adaptation = [], [], []
    criteria = {
        "beginner": ["B1", "B2", "B3", "B4"],
        "intermediate": ["I1", "I2", "I3"],
        "advanced": ["A1", "A2", "A3", "A4"],
    }
    for qid in ready["test_question_ids"]:
        for level in StudentLevel:
            for arm in ExperimentArm:
                index = len(items)
                failed, unknown = index == 0, index == 1
                item = GenerationEvaluationInput(
                    evaluation_id=f"fixture-{index}",
                    run_id=f"fixture-run-{index}",
                    question_id=qid,
                    question="Fictional fixture question",
                    answer=None if failed else "Fictional fixture answer",
                    target_level=level,
                    condition=arm,
                    lambda_weight=0.1,
                    generation_model_family="gpt-oss-20b",
                    generation_model_revision="fixture",
                    source_split="test",
                    source_artifact_sha256="a" * 64,
                    source_run_sha256="b" * 64,
                    eligibility="full",
                    source_status="generation_error" if failed else "answered",
                    technical_failure=failed,
                    failure_reason="fictional failure" if failed else None,
                )
                items.append(item)
                scores.append(
                    {
                        "run_id": item.run_id,
                        "question_id": qid,
                        "condition_id": arm.value,
                        "student_level": level.value,
                        "generator_model": "gpt-oss-20b:fixture",
                        "split": "test",
                        "gold_sha256": ready["gold_sha256"],
                        "rubric_sha256": ready["per_question_rubric_sha256"][qid],
                        "rubric_version": "synthetic",
                        "answer_sha256": item.answer_sha256,
                        "run_status": item.source_status.value,
                        "score_status": "needs_review" if unknown else "scored",
                        "score": None if unknown else 0 if failed else 2,
                        "scoring_source": "none" if unknown else "system" if failed else "rule",
                        "reason": "synthetic offline fixture",
                    }
                )
                if not failed:
                    adaptation.append(
                        {
                            "evaluation_id": item.evaluation_id,
                            "question_id": qid,
                            "condition": arm.value,
                            "target_level": level.value,
                            "evaluated_level": level.value,
                            "is_target_level_evaluation": True,
                            "criteria": [
                                {"criterion_id": c, "verdict": "fail" if c == "I3" else "pass"}
                                for c in criteria[level.value]
                            ],
                        }
                    )

    def jsonl(name, rows):
        path = tmp_path / name
        path.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode())
        return path

    inputs = jsonl("fictional-inputs.jsonl", [i.model_dump(mode="json") for i in items])
    score_path = jsonl("fictional-scores.jsonl", scores)
    adapter = save(
        tmp_path / "adapter.json",
        {
            "output_sha256": {"generation_evaluation_inputs": file_sha(inputs)},
            "input_sha256": {"eligibility": ready["eligibility_sha256"]},
            "gold_sha256": ready["gold_sha256"],
            "source_run_sha256": "b" * 64,
        },
    )
    binding = build_correctness_score_binding(
        score_path,
        items,
        evaluation_inputs_sha256=file_sha(inputs),
        gold_sha256=ready["gold_sha256"],
    )
    binding_path = write_correctness_score_binding(binding, tmp_path / "binding.json")
    judge_dir = tmp_path / "judged"
    write_judge_evaluation_outputs(
        {
            "adaptation": adaptation,
            "discrimination": [],
            "evidence_support": [],
            "unresolved": [],
            "expected_request_count": len(adaptation),
            "supplied_request_count": len(adaptation),
        },
        judge_dir,
        provenance={
            "evaluation_inputs_sha256": file_sha(inputs),
            "source_run_sha256": "b" * 64,
            "profile_package_sha256": PROFILE_SHA,
            "judge_configuration_sha256": FROZEN_JUDGE_FILE_SHA,
            "reverse_adaptation_criteria": False,
        },
    )
    args = argparse.Namespace(
        readiness=readiness_args.output,
        inputs=inputs,
        adapter_manifest=adapter,
        correctness_scores=score_path,
        correctness_binding=binding_path,
        judge_evaluation_dir=judge_dir,
        noise_floors=None,
        output=tmp_path / "analysis.json",
    )
    result = report(args)
    coverage = result["coverage_by_condition"]
    assert sum(g["generation_failures"] for g in coverage.values()) == 1
    assert sum(g["answered_unscored"] for g in coverage.values()) == 1
    intermediate = [
        r for r in result["adaptation_by_level_condition"] if r["level"] == "intermediate"
    ]
    assert all(r["mean_main_criterion_pass_rate"] == 1 for r in intermediate)
    assert all(r["i3_reference_pass_count"] == 0 for r in intermediate)
    assert result["reportable"] is False
    assert result["correctness_rubric_set_sha256"] == ready["correctness_rubric_set_sha256"]
    ready["per_question_rubric_sha256"][ready["test_question_ids"][0]] = "f" * 64
    save(readiness_args.output, ready)
    args.output = tmp_path / "rejected.json"
    with pytest.raises(ValueError, match="frozen per-question rubric"):
        report(args)
    assert not args.output.exists()
