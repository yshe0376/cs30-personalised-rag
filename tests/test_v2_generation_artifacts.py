import hashlib
import json
from pathlib import Path

import pytest

from cs30.evaluation.v2_generation_artifacts import (
    adapt_m7_generation_artifacts,
    load_open_answer_scores,
    write_adapter_outputs,
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
    paths = {
        name: tmp_path / filename
        for name, filename in {
            "expected": "expected_experiment.json",
            "records": "generation_records.jsonl",
            "answers": "saved_answers.jsonl",
            "manifest": "run_manifest.json",
            "gold": "gold.jsonl",
            "eligibility": "eligibility.jsonl",
        }.items()
    }
    _write_jsonl(paths["gold"], [{"question_id": "q1", "question": "Why?"}])
    _write_jsonl(paths["eligibility"], [{"question_id": "q1", "eligibility": "full"}])
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
                "generation_trace": {"prompt_personalised": False, "effective_level": None},
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
                },
            },
        ],
    )
    _write_json(
        paths["manifest"],
        {
            "prepared_inputs": {"input_sha256": {"gold.jsonl": _sha(paths["gold"])}},
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
    )
    assert [item.source_status.value for item in items] == ["answered", "output_truncated"]
    assert items[0].citation_ids == ["chunk-1"]
    assert items[0].generation_model_family == "gpt-oss"
    assert items[0].generation_model_revision == "20b"
    assert items[1].technical_failure is True
    assert manifest["status_counts"] == {"answered": 1, "output_truncated": 1}
    written = write_adapter_outputs(items, manifest, tmp_path / "out")
    assert written["inputs"].is_file()
    assert written["manifest"].is_file()


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
            "rubric_sha256": None,
            "rubric_version": None,
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
    loaded = load_open_answer_scores(score_path, items, gold_sha256=str(manifest["gold_sha256"]))
    assert loaded["run-combined"].run_status == "output_truncated"


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
    report = json.loads(
        (report_dir / "v2_generation_evaluation.json").read_text(encoding="utf-8")
    )
    assert report["mode"] == "development"
    assert report["reportable"] is False
    assert report["automatic_full_run"]["correctness"]["denominator"] == 2
    assert report["unresolved_items"]
