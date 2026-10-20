import hashlib
import json
from pathlib import Path

import pytest

from cs30.evaluation.v2_generation_artifacts import (
    adapt_m7_generation_artifacts,
    build_correctness_score_binding,
    load_open_answer_scores,
    write_adapter_outputs,
    write_correctness_score_binding,
)
from cs30.evaluation.v2_generation_cli import main


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = {
        name: tmp_path / filename
        for name, filename in {
            "expected": "expected_experiment.json",
            "records": "generation_records.jsonl",
            "answers": "saved_answers.jsonl",
            "manifest": "run_manifest.json",
            "gold": "gold.jsonl",
            "eligibility": "eligibility.jsonl",
            "lambda": "lambda_selection.json",
        }.items()
    }
    _write_jsonl(paths["gold"], [{"question_id": "q1", "question": "Why?"}])
    _write_jsonl(paths["eligibility"], [{"question_id": "q1", "eligibility": "full"}])
    def selection_cases(hits: tuple[bool, bool, bool]) -> list[dict[str, object]]:
        return [
            {
                "question_id": "lambda-dev-q1",
                "level": level,
                "complete_hit": hit,
                "span_coverage": float(hit),
            }
            for level, hit in zip(
                ("beginner", "intermediate", "advanced"), hits, strict=True
            )
        ]
    _write_json(
        paths["lambda"],
        {
            "schema_version": "0.2",
            "selected_on_split": "dev",
            "lambda_weight": 0.2,
            "objective": "largest_positive_lambda_within_1pt_of_baseline",
            "noninferiority_margin": 0.01,
            "gold_sha256": _sha(paths["gold"]),
            "candidate_lambdas": [0.0, 0.1, 0.2, 0.35, 0.5],
            "metrics": [
                {
                    "lambda_weight": 0.0,
                    "complete_hit_rate": 1.0,
                    "mean_span_coverage": 1.0,
                    "case_count": 3,
                    "cases": selection_cases((True, True, True)),
                },
                {
                    "lambda_weight": 0.1,
                    "complete_hit_rate": 1.0,
                    "mean_span_coverage": 1.0,
                    "case_count": 3,
                    "cases": selection_cases((True, True, True)),
                },
                {
                    "lambda_weight": 0.2,
                    "complete_hit_rate": 1.0,
                    "mean_span_coverage": 1.0,
                    "case_count": 3,
                    "cases": selection_cases((True, True, True)),
                },
                {
                    "lambda_weight": 0.35,
                    "complete_hit_rate": 2 / 3,
                    "mean_span_coverage": 2 / 3,
                    "case_count": 3,
                    "cases": selection_cases((True, True, False)),
                },
                {
                    "lambda_weight": 0.5,
                    "complete_hit_rate": 1 / 3,
                    "mean_span_coverage": 1 / 3,
                    "case_count": 3,
                    "cases": selection_cases((True, False, False)),
                },
            ],
        },
    )
    cases = [
        {
            "run_id": "run-plain",
            "question_id": "q1",
            "condition_id": "P0R0_plain",
            "student_level": "beginner",
            "generator_model": "gpt-oss:20b",
        },
        {
            "run_id": "run-combined",
            "question_id": "q1",
            "condition_id": "P1R1_combined",
            "student_level": "beginner",
            "generator_model": "gpt-oss:20b",
        },
    ]
    _write_json(
        paths["expected"],
        {
            "schema_version": "0.2",
            "matrix_version": "fixture-matrix",
            "gold_sha256": _sha(paths["gold"]),
            "cases": cases,
        },
    )
    evidence = {
        "evidence_items": [
            {"chunk_id": "chunk-1", "text": "Evidence.", "rank": 1, "source_locator": "p1"}
        ]
    }
    answered = {
        **cases[0],
        "status": "answered",
        "answer": {"explanation": "Because.", "citations": ["chunk-1"]},
        "error": None,
    }
    failed = {**cases[1], "status": "output_truncated", "answer": None, "error": "limit"}
    _write_jsonl(paths["answers"], [answered, failed])
    _write_jsonl(
        paths["records"],
        [
            {
                **answered,
                "evidence": evidence,
                "rerank_trace": None,
                "generation_trace": {
                    "prompt_personalised": False,
                    "effective_level": None,
                    "prompt_sha256": "a" * 64,
                },
            },
            {
                **failed,
                "evidence": evidence,
                "rerank_trace": {
                    "enabled": True,
                    "effective_lambda": 0.2,
                    "candidates": [{"chunk_id": "chunk-1", "role": "definition"}],
                },
                "generation_trace": {
                    "prompt_personalised": True,
                    "effective_level": "beginner",
                    "prompt_sha256": "b" * 64,
                },
            },
        ],
    )
    _write_json(
        paths["manifest"],
        {
            "prepared_inputs": {
                "input_sha256": {
                    "gold.jsonl": _sha(paths["gold"]),
                    "lambda_selection.json": _sha(paths["lambda"]),
                }
            },
            "output_sha256": {
                "expected_experiment.json": _sha(paths["expected"]),
                "generation_records.jsonl": _sha(paths["records"]),
                "saved_answers.jsonl": _sha(paths["answers"]),
            },
            "client": {"seed": 5703},
        },
    )
    return paths


def test_adapter_preserves_statuses_hashes_and_chunk_citations(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    items, manifest = adapt_m7_generation_artifacts(
        expected_path=paths["expected"],
        records_path=paths["records"],
        answers_path=paths["answers"],
        run_manifest_path=paths["manifest"],
        gold_path=paths["gold"],
        eligibility_path=paths["eligibility"],
        lambda_selection_path=paths["lambda"],
    )
    assert [item.source_status.value for item in items] == ["answered", "output_truncated"]
    assert items[0].citation_ids == ["chunk-1"]
    assert items[0].evidence[0].role == "definition"
    assert items[0].generation_model_family == "gpt-oss"
    assert items[0].generation_model_revision == "20b"
    assert items[1].technical_failure is True
    assert manifest["status_counts"] == {"answered": 1, "output_truncated": 1}
    assert manifest["matrix_complete"] is False
    written = write_adapter_outputs(items, manifest, tmp_path / "out")
    assert written["inputs"].is_file()
    assert written["manifest"].is_file()
    written_manifest = json.loads(written["manifest"].read_text(encoding="utf-8"))
    assert (
        written_manifest["output_sha256"]["generation_evaluation_inputs"]
        == hashlib.sha256(written["inputs"].read_bytes()).hexdigest()
    )


def test_lambda_case_count_uses_experiment_questions_not_all_gold_rows(
    tmp_path: Path,
) -> None:
    paths = _bundle(tmp_path)
    _write_jsonl(
        paths["gold"],
        [
            {"question_id": "q1", "question": "Why?"},
            {"question_id": "unused-test-question", "question": "What?"},
        ],
    )
    selection = json.loads(paths["lambda"].read_text(encoding="utf-8"))
    selection["gold_sha256"] = _sha(paths["gold"])
    _write_json(paths["lambda"], selection)
    expected = json.loads(paths["expected"].read_text(encoding="utf-8"))
    expected["gold_sha256"] = _sha(paths["gold"])
    _write_json(paths["expected"], expected)
    source_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    source_manifest["prepared_inputs"]["input_sha256"].update(
        {
            "gold.jsonl": _sha(paths["gold"]),
            "lambda_selection.json": _sha(paths["lambda"]),
        }
    )
    source_manifest["output_sha256"]["expected_experiment.json"] = _sha(paths["expected"])
    _write_json(paths["manifest"], source_manifest)

    _, manifest = adapt_m7_generation_artifacts(
        expected_path=paths["expected"],
        records_path=paths["records"],
        answers_path=paths["answers"],
        run_manifest_path=paths["manifest"],
        gold_path=paths["gold"],
        eligibility_path=paths["eligibility"],
        lambda_selection_path=paths["lambda"],
    )
    assert {
        row["case_count"] for row in manifest["lambda_selection"]["candidates"]
    } == {3}
    assert manifest["question_count"] == 1


def test_test_run_accepts_dev_lambda_evidence_with_its_own_gold_hash(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    selection = json.loads(paths["lambda"].read_text(encoding="utf-8"))
    selection["gold_sha256"] = "c" * 64
    _write_json(paths["lambda"], selection)
    source_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    source_manifest["prepared_inputs"]["input_sha256"]["lambda_selection.json"] = _sha(
        paths["lambda"]
    )
    _write_json(paths["manifest"], source_manifest)

    _, manifest = adapt_m7_generation_artifacts(
        expected_path=paths["expected"],
        records_path=paths["records"],
        answers_path=paths["answers"],
        run_manifest_path=paths["manifest"],
        gold_path=paths["gold"],
        eligibility_path=paths["eligibility"],
        lambda_selection_path=paths["lambda"],
    )
    assert manifest["gold_sha256"] == _sha(paths["gold"])
    assert manifest["lambda_selection_gold_sha256"] == "c" * 64


def test_lambda_selection_recomputes_aggregate_metrics_from_cases(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    selection = json.loads(paths["lambda"].read_text(encoding="utf-8"))
    selection["metrics"][0]["complete_hit_rate"] = 0.0
    _write_json(paths["lambda"], selection)
    source_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    source_manifest["prepared_inputs"]["input_sha256"]["lambda_selection.json"] = _sha(
        paths["lambda"]
    )
    _write_json(paths["manifest"], source_manifest)

    with pytest.raises(ValueError, match="complete_hit_rate does not match"):
        adapt_m7_generation_artifacts(
            expected_path=paths["expected"],
            records_path=paths["records"],
            answers_path=paths["answers"],
            run_manifest_path=paths["manifest"],
            gold_path=paths["gold"],
            eligibility_path=paths["eligibility"],
            lambda_selection_path=paths["lambda"],
        )


def test_adapter_rejects_duplicate_logical_matrix_cells(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    expected = json.loads(paths["expected"].read_text(encoding="utf-8"))
    duplicate = dict(expected["cases"][0])
    duplicate["run_id"] = "different-run-same-cell"
    expected["cases"].append(duplicate)
    _write_json(paths["expected"], expected)
    source_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    source_manifest["output_sha256"]["expected_experiment.json"] = _sha(paths["expected"])
    _write_json(paths["manifest"], source_manifest)

    with pytest.raises(ValueError, match="repeats a question/level/condition cell"):
        adapt_m7_generation_artifacts(
            expected_path=paths["expected"],
            records_path=paths["records"],
            answers_path=paths["answers"],
            run_manifest_path=paths["manifest"],
            gold_path=paths["gold"],
            eligibility_path=paths["eligibility"],
            lambda_selection_path=paths["lambda"],
        )


def test_adapter_rejects_tampered_generation_records(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    paths["records"].write_text(
        paths["records"].read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        adapt_m7_generation_artifacts(
            expected_path=paths["expected"],
            records_path=paths["records"],
            answers_path=paths["answers"],
            run_manifest_path=paths["manifest"],
            gold_path=paths["gold"],
            eligibility_path=paths["eligibility"],
            lambda_selection_path=paths["lambda"],
        )


def test_adapter_identity_binds_source_run_and_exact_answer(tmp_path: Path) -> None:
    first_paths = _bundle(tmp_path / "first")
    second_paths = _bundle(tmp_path / "second")
    second_manifest = json.loads(second_paths["manifest"].read_text(encoding="utf-8"))
    second_manifest["delivery_id"] = "different-run-directory"
    _write_json(second_paths["manifest"], second_manifest)

    first, _ = adapt_m7_generation_artifacts(
        expected_path=first_paths["expected"],
        records_path=first_paths["records"],
        answers_path=first_paths["answers"],
        run_manifest_path=first_paths["manifest"],
        gold_path=first_paths["gold"],
        eligibility_path=first_paths["eligibility"],
        lambda_selection_path=first_paths["lambda"],
    )
    second, _ = adapt_m7_generation_artifacts(
        expected_path=second_paths["expected"],
        records_path=second_paths["records"],
        answers_path=second_paths["answers"],
        run_manifest_path=second_paths["manifest"],
        gold_path=second_paths["gold"],
        eligibility_path=second_paths["eligibility"],
        lambda_selection_path=second_paths["lambda"],
    )
    assert first[0].run_id == second[0].run_id
    assert first[0].evaluation_id != second[0].evaluation_id
    assert first[0].source_run_sha256 != second[0].source_run_sha256
    assert first[0].answer_sha256 == hashlib.sha256(b"Because.").hexdigest()


def test_adapter_rejects_lambda_selected_with_judge_independent_rule_violation(
    tmp_path: Path,
) -> None:
    paths = _bundle(tmp_path)
    selection = json.loads(paths["lambda"].read_text(encoding="utf-8"))
    selection["lambda_weight"] = 0.1
    _write_json(paths["lambda"], selection)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["prepared_inputs"]["input_sha256"]["lambda_selection.json"] = _sha(paths["lambda"])
    _write_json(paths["manifest"], manifest)
    with pytest.raises(ValueError, match="violates the frozen rule"):
        adapt_m7_generation_artifacts(
            expected_path=paths["expected"],
            records_path=paths["records"],
            answers_path=paths["answers"],
            run_manifest_path=paths["manifest"],
            gold_path=paths["gold"],
            eligibility_path=paths["eligibility"],
            lambda_selection_path=paths["lambda"],
        )


@pytest.mark.parametrize("failure", ["incomplete-grid", "duplicate-metric"])
def test_adapter_rejects_incomplete_or_duplicate_lambda_evidence(
    tmp_path: Path,
    failure: str,
) -> None:
    paths = _bundle(tmp_path)
    selection = json.loads(paths["lambda"].read_text(encoding="utf-8"))
    if failure == "incomplete-grid":
        selection["candidate_lambdas"] = [0.0, 0.1, 0.2, 0.35]
        expected_error = "candidate grid differs"
    else:
        selection["metrics"].append(dict(selection["metrics"][0]))
        expected_error = "repeats metric row"
    _write_json(paths["lambda"], selection)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["prepared_inputs"]["input_sha256"]["lambda_selection.json"] = _sha(
        paths["lambda"]
    )
    _write_json(paths["manifest"], manifest)
    with pytest.raises(ValueError, match=expected_error):
        adapt_m7_generation_artifacts(
            expected_path=paths["expected"],
            records_path=paths["records"],
            answers_path=paths["answers"],
            run_manifest_path=paths["manifest"],
            gold_path=paths["gold"],
            eligibility_path=paths["eligibility"],
            lambda_selection_path=paths["lambda"],
        )


def test_score_import_binds_answer_hash_and_output_truncated(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    items, manifest = adapt_m7_generation_artifacts(
        expected_path=paths["expected"],
        records_path=paths["records"],
        answers_path=paths["answers"],
        run_manifest_path=paths["manifest"],
        gold_path=paths["gold"],
        eligibility_path=paths["eligibility"],
        lambda_selection_path=paths["lambda"],
    )
    scores = [
        {
            "run_id": "run-plain",
            "question_id": "q1",
            "condition_id": "P0R0_plain",
            "student_level": "beginner",
            "generator_model": "gpt-oss:20b",
            "split": "dev",
            "gold_sha256": manifest["gold_sha256"],
            "rubric_sha256": "c" * 64,
            "rubric_version": "correctness-v1",
            "answer_sha256": hashlib.sha256(b"Because.").hexdigest(),
            "run_status": "answered",
            "score_status": "scored",
            "score": 2,
            "scoring_source": "human",
            "reason": "reviewed",
            "review_record_id": "review-1",
            "human_rater_id": "rater-1",
        },
        {
            "run_id": "run-combined",
            "question_id": "q1",
            "condition_id": "P1R1_combined",
            "student_level": "beginner",
            "generator_model": "gpt-oss:20b",
            "split": "dev",
            "gold_sha256": manifest["gold_sha256"],
            "rubric_sha256": None,
            "rubric_version": None,
            "answer_sha256": None,
            "run_status": "output_truncated",
            "score_status": "scored",
            "score": 0,
            "scoring_source": "system",
            "reason": "output_truncated",
        },
    ]
    score_path = tmp_path / "scores.jsonl"
    _write_jsonl(score_path, scores)
    written = write_adapter_outputs(items, manifest, tmp_path / "adapted")
    inputs_sha256 = _sha(written["inputs"])
    binding_path = tmp_path / "score-binding.json"
    assert (
        main(
            [
                "bind-correctness-scores",
                "--inputs",
                str(written["inputs"]),
                "--adapter-manifest",
                str(written["manifest"]),
                "--scores",
                str(score_path),
                "--output",
                str(binding_path),
            ]
        )
        == 0
    )
    loaded = load_open_answer_scores(
        score_path,
        items,
        gold_sha256=str(manifest["gold_sha256"]),
        binding_path=binding_path,
        evaluation_inputs_sha256=inputs_sha256,
    )
    combined = next(item for item in items if item.run_id == "run-combined")
    assert loaded[combined.evaluation_id].run_status == "output_truncated"


def test_score_binding_rejects_same_run_ids_from_a_different_source_run(
    tmp_path: Path,
) -> None:
    first_paths = _bundle(tmp_path / "first")
    second_paths = _bundle(tmp_path / "second")
    second_source_manifest = json.loads(second_paths["manifest"].read_text(encoding="utf-8"))
    second_source_manifest["delivery_id"] = "different-run-directory"
    _write_json(second_paths["manifest"], second_source_manifest)
    first, first_manifest = adapt_m7_generation_artifacts(
        expected_path=first_paths["expected"],
        records_path=first_paths["records"],
        answers_path=first_paths["answers"],
        run_manifest_path=first_paths["manifest"],
        gold_path=first_paths["gold"],
        eligibility_path=first_paths["eligibility"],
        lambda_selection_path=first_paths["lambda"],
    )
    second, second_manifest = adapt_m7_generation_artifacts(
        expected_path=second_paths["expected"],
        records_path=second_paths["records"],
        answers_path=second_paths["answers"],
        run_manifest_path=second_paths["manifest"],
        gold_path=second_paths["gold"],
        eligibility_path=second_paths["eligibility"],
        lambda_selection_path=second_paths["lambda"],
    )
    score_path = tmp_path / "scores.jsonl"
    _write_jsonl(
        score_path,
        [
            {
                "run_id": "run-plain",
                "question_id": "q1",
                "condition_id": "P0R0_plain",
                "student_level": "beginner",
                "generator_model": "gpt-oss:20b",
                "split": "dev",
                "gold_sha256": first_manifest["gold_sha256"],
                "rubric_sha256": "c" * 64,
                "rubric_version": "correctness-v1",
                "answer_sha256": hashlib.sha256(b"Because.").hexdigest(),
                "run_status": "answered",
                "score_status": "scored",
                "score": 2,
                "scoring_source": "human",
                "reason": "reviewed",
                "review_record_id": "review-1",
                "human_rater_id": "rater-1",
            },
            {
                "run_id": "run-combined",
                "question_id": "q1",
                "condition_id": "P1R1_combined",
                "student_level": "beginner",
                "generator_model": "gpt-oss:20b",
                "split": "dev",
                "gold_sha256": first_manifest["gold_sha256"],
                "rubric_sha256": None,
                "rubric_version": None,
                "answer_sha256": None,
                "run_status": "output_truncated",
                "score_status": "scored",
                "score": 0,
                "scoring_source": "system",
                "reason": "output_truncated",
            },
        ],
    )
    first_written = write_adapter_outputs(first, first_manifest, tmp_path / "first-adapted")
    second_written = write_adapter_outputs(second, second_manifest, tmp_path / "second-adapted")
    first_inputs_sha256 = _sha(first_written["inputs"])
    binding = build_correctness_score_binding(
        score_path,
        first,
        evaluation_inputs_sha256=first_inputs_sha256,
        gold_sha256=str(first_manifest["gold_sha256"]),
    )
    binding_path = write_correctness_score_binding(binding, tmp_path / "binding.json")
    with pytest.raises(ValueError, match="current source run"):
        load_open_answer_scores(
            score_path,
            second,
            gold_sha256=str(second_manifest["gold_sha256"]),
            binding_path=binding_path,
            evaluation_inputs_sha256=_sha(second_written["inputs"]),
        )


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [("generator_model", "different-model:1"), ("split", "test")],
)
def test_score_binding_rejects_wrong_model_or_split(
    tmp_path: Path,
    field: str,
    wrong_value: str,
) -> None:
    paths = _bundle(tmp_path)
    items, manifest = adapt_m7_generation_artifacts(
        expected_path=paths["expected"],
        records_path=paths["records"],
        answers_path=paths["answers"],
        run_manifest_path=paths["manifest"],
        gold_path=paths["gold"],
        eligibility_path=paths["eligibility"],
        lambda_selection_path=paths["lambda"],
    )
    rows = [
        {
            "run_id": "run-plain",
            "question_id": "q1",
            "condition_id": "P0R0_plain",
            "student_level": "beginner",
            "generator_model": "gpt-oss:20b",
            "split": "dev",
            "gold_sha256": manifest["gold_sha256"],
            "rubric_sha256": "c" * 64,
            "rubric_version": "correctness-v1",
            "answer_sha256": hashlib.sha256(b"Because.").hexdigest(),
            "run_status": "answered",
            "score_status": "scored",
            "score": 2,
            "scoring_source": "human",
            "reason": "reviewed",
            "review_record_id": "review-1",
            "human_rater_id": "rater-1",
        },
        {
            "run_id": "run-combined",
            "question_id": "q1",
            "condition_id": "P1R1_combined",
            "student_level": "beginner",
            "generator_model": "gpt-oss:20b",
            "split": "dev",
            "gold_sha256": manifest["gold_sha256"],
            "rubric_sha256": None,
            "rubric_version": None,
            "answer_sha256": None,
            "run_status": "output_truncated",
            "score_status": "scored",
            "score": 0,
            "scoring_source": "system",
            "reason": "output_truncated",
        },
    ]
    rows[0][field] = wrong_value
    score_path = tmp_path / "wrong-scores.jsonl"
    _write_jsonl(score_path, rows)
    with pytest.raises(ValueError, match="score identity differs"):
        build_correctness_score_binding(
            score_path,
            items,
            evaluation_inputs_sha256="d" * 64,
            gold_sha256=str(manifest["gold_sha256"]),
        )


def test_cli_runs_adapter_to_nonreportable_development_report(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    adapted = tmp_path / "adapted"
    assert (
        main(
            [
                "adapt-m7-artifacts",
                "--expected-experiment",
                str(paths["expected"]),
                "--generation-records",
                str(paths["records"]),
                "--saved-answers",
                str(paths["answers"]),
                "--run-manifest",
                str(paths["manifest"]),
                "--gold",
                str(paths["gold"]),
                "--eligibility",
                str(paths["eligibility"]),
                "--lambda-selection",
                str(paths["lambda"]),
                "--output-dir",
                str(adapted),
            ]
        )
        == 0
    )
    report_dir = tmp_path / "report"
    assert (
        main(
            [
                "development-report",
                "--inputs",
                str(adapted / "generation_evaluation_inputs.jsonl"),
                "--adapter-manifest",
                str(adapted / "adapter_manifest.json"),
                "--output-dir",
                str(report_dir),
            ]
        )
        == 0
    )
    report = json.loads((report_dir / "v2_generation_evaluation.json").read_text(encoding="utf-8"))
    assert report["mode"] == "development"
    assert report["reportable"] is False
    assert report["automatic_full_run"]["correctness"]["denominator"] == 2
    assert report["unresolved_items"]
