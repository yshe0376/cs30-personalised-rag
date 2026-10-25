"""End-to-end regression tests for the repeated-generation CLI inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.v2_generation_artifacts import (
    build_correctness_score_binding,
    write_correctness_score_binding,
)
from cs30.evaluation.v2_generation_cli import main
from cs30.evaluation.v2_generation_models import (
    ExperimentArm,
    GenerationEvaluationInput,
    GenerationRunStatus,
)

GOLD_SHA256 = "a" * 64
LAMBDA_SHA256 = "b" * 64
BASELINE_SOURCE_RUN = "c" * 64
REPEAT_SOURCE_RUN = "d" * 64
JUDGE_CONFIG_SHA256 = "e" * 64
PROFILE_PACKAGE_SHA256 = "f" * 64


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _inputs(
    question_count: int,
    *,
    label: str,
    source_run_sha256: str,
    nonanswered_status: GenerationRunStatus | None = None,
) -> list[GenerationEvaluationInput]:
    result = []
    for question_index in range(question_count):
        question_id = f"q-{question_index:02d}"
        for level in StudentLevel:
            for condition in ExperimentArm:
                run_id = f"run-{question_id}-{level.value}-{condition.value}"
                answer = f"{label} answer for {run_id}"
                status = (
                    nonanswered_status
                    if question_id == "q-07" and nonanswered_status is not None
                    else GenerationRunStatus.ANSWERED
                )
                if status.is_technical_failure:
                    answer = None
                result.append(
                    GenerationEvaluationInput(
                        evaluation_id=f"{label}-{run_id}",
                        run_id=run_id,
                        question_id=question_id,
                        question=f"Question {question_id}?",
                        answer=answer,
                        target_level=level,
                        condition=condition,
                        lambda_weight=0.2,
                        generation_model_family="gpt-oss",
                        generation_model_revision="20b",
                        source_split="dev",
                        eligibility="full",
                        source_artifact_sha256="1" * 64,
                        source_run_sha256=source_run_sha256,
                        answer_sha256=_sha256_text(answer) if answer is not None else None,
                        source_status=status,
                        abstained=status is GenerationRunStatus.ABSTAINED,
                        technical_failure=status.is_technical_failure,
                        failure_reason="fixture technical failure"
                        if status.is_technical_failure
                        else None,
                    )
                )
    return result


def _write_input_bundle(
    path: Path,
    items: list[GenerationEvaluationInput],
    *,
    source_run_sha256: str,
) -> tuple[Path, Path, str]:
    path.mkdir()
    inputs_path = path / "generation_evaluation_inputs.jsonl"
    _write_jsonl(inputs_path, [item.model_dump(mode="json") for item in items])
    inputs_sha256 = hashlib.sha256(inputs_path.read_bytes()).hexdigest()
    manifest_path = path / "adapter_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_run_sha256": source_run_sha256,
                "gold_sha256": GOLD_SHA256,
                "record_count": len(items),
                "question_count": len({item.question_id for item in items}),
                "matrix_complete": True,
                "input_sha256": {"lambda_selection": LAMBDA_SHA256},
                "output_sha256": {"generation_evaluation_inputs": inputs_sha256},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return inputs_path, manifest_path, inputs_sha256


def _write_scores_and_binding(
    path: Path,
    items: list[GenerationEvaluationInput],
    *,
    inputs_sha256: str,
    changed_rubric_question: str | None = None,
    invalid_failure_rubric: str | None = None,
) -> tuple[Path, Path]:
    score_path = path / "open_answer_scores.jsonl"
    rows = []
    for item in items:
        rubric_source = (
            f"changed-rubric:{item.question_id}"
            if item.question_id == changed_rubric_question
            else f"rubric:{item.question_id}"
        )
        rubric_hash = _sha256_text(rubric_source)
        if item.question_id == "q-07" and invalid_failure_rubric == "missing":
            rubric_hash = None
        elif (
            item.question_id == "q-07"
            and invalid_failure_rubric == "conflicting"
            and item.target_level is StudentLevel.BEGINNER
        ):
            rubric_hash = _sha256_text("conflicting-rubric")
        answered = item.source_status is GenerationRunStatus.ANSWERED
        rows.append(
            {
                "run_id": item.run_id,
                "question_id": item.question_id,
                "condition_id": item.condition.value,
                "student_level": item.target_level.value,
                "generator_model": (
                    f"{item.generation_model_family}:{item.generation_model_revision}"
                ),
                "split": item.source_split,
                "gold_sha256": GOLD_SHA256,
                "rubric_sha256": rubric_hash,
                "rubric_version": "correctness-v1",
                "answer_sha256": item.answer_sha256,
                "run_status": item.source_status.value,
                "score_status": "scored",
                "score": 2 if answered else 0,
                "scoring_source": "judge" if answered else "system",
                "reason": "fixture score",
                "judge_model": "gemini-3.1-flash-lite" if answered else None,
                "judge_config_sha256": JUDGE_CONFIG_SHA256 if answered else None,
            }
        )
    _write_jsonl(score_path, rows)
    binding = build_correctness_score_binding(
        score_path,
        items,
        evaluation_inputs_sha256=inputs_sha256,
        gold_sha256=GOLD_SHA256,
    )
    binding_path = path / "correctness_score_binding.json"
    write_correctness_score_binding(binding, binding_path)
    return score_path, binding_path


def _write_empty_judge_evaluation(
    path: Path,
    *,
    inputs_sha256: str,
    source_run_sha256: str,
) -> Path:
    path.mkdir()
    output_hashes = {}
    for name, filename in {
        "adaptation": "adaptation_results.jsonl",
        "discrimination": "discrimination_results.jsonl",
        "evidence_support": "evidence_support_results.jsonl",
        "unresolved": "judge_unresolved.jsonl",
    }.items():
        output_path = path / filename
        output_path.write_text("", encoding="utf-8")
        output_hashes[name] = hashlib.sha256(output_path.read_bytes()).hexdigest()
    (path / "judge_evaluation_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "expected_request_count": 0,
                "supplied_request_count": 0,
                "provenance": {
                    "evaluation_inputs_sha256": inputs_sha256,
                    "source_run_sha256": source_run_sha256,
                    "judge_configuration_sha256": JUDGE_CONFIG_SHA256,
                    "judge_config_version": "judge-v1",
                    "profile_package_sha256": PROFILE_PACKAGE_SHA256,
                    "reverse_adaptation_criteria": False,
                },
                "output_sha256": output_hashes,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _development_report_args(
    tmp_path: Path,
    *,
    changed_repeat_rubric_question: str | None = None,
    nonanswered_batch: str | None = None,
    nonanswered_status: GenerationRunStatus = GenerationRunStatus.GENERATION_ERROR,
    invalid_failure_rubric: str | None = None,
) -> tuple[list[str], Path]:
    baseline_items = _inputs(
        31,
        label="baseline",
        source_run_sha256=BASELINE_SOURCE_RUN,
        nonanswered_status=nonanswered_status if nonanswered_batch == "baseline" else None,
    )
    repeat_items = _inputs(
        30,
        label="repeat",
        source_run_sha256=REPEAT_SOURCE_RUN,
        nonanswered_status=nonanswered_status if nonanswered_batch == "repeat" else None,
    )
    baseline_dir = tmp_path / "baseline"
    repeat_dir = tmp_path / "repeat"
    baseline_inputs, baseline_manifest, baseline_hash = _write_input_bundle(
        baseline_dir,
        baseline_items,
        source_run_sha256=BASELINE_SOURCE_RUN,
    )
    repeat_inputs, repeat_manifest, repeat_hash = _write_input_bundle(
        repeat_dir,
        repeat_items,
        source_run_sha256=REPEAT_SOURCE_RUN,
    )
    baseline_scores, baseline_binding = _write_scores_and_binding(
        baseline_dir,
        baseline_items,
        inputs_sha256=baseline_hash,
        invalid_failure_rubric=invalid_failure_rubric if nonanswered_batch == "baseline" else None,
    )
    repeat_scores, repeat_binding = _write_scores_and_binding(
        repeat_dir,
        repeat_items,
        inputs_sha256=repeat_hash,
        changed_rubric_question=changed_repeat_rubric_question,
        invalid_failure_rubric=invalid_failure_rubric if nonanswered_batch == "repeat" else None,
    )
    baseline_judge = _write_empty_judge_evaluation(
        baseline_dir / "judge",
        inputs_sha256=baseline_hash,
        source_run_sha256=BASELINE_SOURCE_RUN,
    )
    repeat_judge = _write_empty_judge_evaluation(
        repeat_dir / "judge",
        inputs_sha256=repeat_hash,
        source_run_sha256=REPEAT_SOURCE_RUN,
    )
    output_dir = tmp_path / "report"
    return (
        [
            "development-report",
            "--inputs",
            str(baseline_inputs),
            "--adapter-manifest",
            str(baseline_manifest),
            "--correctness-scores",
            str(baseline_scores),
            "--correctness-score-binding",
            str(baseline_binding),
            "--judge-evaluation-dir",
            str(baseline_judge),
            "--generation-repeat-inputs",
            str(repeat_inputs),
            "--generation-repeat-adapter-manifest",
            str(repeat_manifest),
            "--generation-repeat-correctness-scores",
            str(repeat_scores),
            "--generation-repeat-correctness-score-binding",
            str(repeat_binding),
            "--generation-repeat-judge-evaluation-dir",
            str(repeat_judge),
            "--bootstrap-draws",
            "20",
            "--output-dir",
            str(output_dir),
        ],
        output_dir,
    )


def test_development_report_accepts_a_thirty_question_repeat_subset(
    tmp_path: Path,
) -> None:
    args, output_dir = _development_report_args(tmp_path)

    assert main(args) == 0

    report = json.loads((output_dir / "v2_generation_evaluation.json").read_text(encoding="utf-8"))
    paired = report["diagnostics"]["generation_noise_floor"]["paired_repeat_batch"]
    assert paired["status"] == "complete"
    assert paired["question_count"] == 30
    assert paired["pair_count"] == 360


def test_development_report_rejects_a_changed_repeat_question_rubric(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args, _ = _development_report_args(
        tmp_path,
        changed_repeat_rubric_question="q-07",
    )

    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 2
    assert "different correctness rubrics for question q-07" in capsys.readouterr().err


@pytest.mark.parametrize("batch", ["baseline", "repeat"])
@pytest.mark.parametrize(
    "status", [GenerationRunStatus.ABSTAINED, GenerationRunStatus.GENERATION_ERROR]
)
def test_development_report_preserves_all_twelve_nonanswered_cells(
    tmp_path: Path, batch: str, status: GenerationRunStatus
) -> None:
    args, output_dir = _development_report_args(
        tmp_path, nonanswered_batch=batch, nonanswered_status=status
    )

    assert main(args) == 0

    report = json.loads((output_dir / "v2_generation_evaluation.json").read_text(encoding="utf-8"))
    paired = report["diagnostics"]["generation_noise_floor"]["paired_repeat_batch"]
    assert paired["status"] == "complete"
    assert paired["question_count"] == 30
    assert paired["pair_count"] == 360
    assert paired["overall"]["correctness_pairs"]["evaluated"] == 360
    assert paired["overall"]["correct_flip_count"] == 12
    assert paired["overall"]["adaptation_pairs"]["not_applicable"] == 12
    for row in paired["by_condition"]:
        zero_side = "baseline" if batch == "baseline" else "repeat"
        assert row[f"{zero_side}_strict_correct_rate"] == pytest.approx(29 / 30)


@pytest.mark.parametrize("batch", ["baseline", "repeat"])
def test_development_report_rejects_mismatched_rubric_with_no_answered_cells(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], batch: str
) -> None:
    args, _ = _development_report_args(
        tmp_path, nonanswered_batch=batch, changed_repeat_rubric_question="q-07"
    )

    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 2
    assert "different correctness rubrics for question q-07" in capsys.readouterr().err


@pytest.mark.parametrize("batch", ["baseline", "repeat"])
@pytest.mark.parametrize("invalid_rubric", ["missing", "conflicting"])
def test_development_report_rejects_invalid_rubrics_on_failed_cells(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], batch: str, invalid_rubric: str
) -> None:
    args, _ = _development_report_args(
        tmp_path, nonanswered_batch=batch, invalid_failure_rubric=invalid_rubric
    )

    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 2
    message = capsys.readouterr().err
    assert "q-07" in message
    assert (
        "without a rubric" if invalid_rubric == "missing" else "conflicting correctness rubrics"
    ) in message
