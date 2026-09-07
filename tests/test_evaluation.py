from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.config import load_config
from cs30.contracts import StudentLevel
from cs30.evaluation import (
    Answerability,
    ExecutionStatus,
    adapt_evaluation_record,
    evaluate_records,
    load_evaluation_records,
    write_evaluation_report,
)
from cs30.fixtures import load_fixture
from cs30.pipeline import build_fixture_deps, run_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "evaluation" / "hand_checked_runs.jsonl"


def test_current_m3_fields_adapt_without_inventing_answerability() -> None:
    record = adapt_evaluation_record(
        {
            "question_id": "q-current",
            "status": "completed",
            "answer": {"final_choice": "B", "abstained": False, "citations": ["c1"]},
            "retrieval": {"hits": [{"chunk_id": "c1"}]},
            "citation_integrity": "passed",
        },
        {
            "question_id": "q-current",
            "correct_choice": "B",
            "support": "Existing SciQ support text.",
            "in_scope": False,
        },
    )

    assert record.gold_choice == "B"
    assert record.answerability is Answerability.UNRESOLVED
    assert record.gold_evidence_ids == []


def test_existing_pipeline_run_and_m3_fixture_score_without_model_calls() -> None:
    run = run_pipeline(
        "What quantity describes the rate of change of velocity?",
        StudentLevel.INTERMEDIATE,
        build_fixture_deps(),
        load_config("development"),
        question_id="fixture_q001",
    )
    record = adapt_evaluation_record(
        run.model_dump(mode="json"),
        load_fixture("sciq_question.json"),
    )
    report = evaluate_records([record])

    assert record.gold_choice == "B"
    # The existing fixture generator returns an explanation but no MCQ choice,
    # so M8 correctly treats this as not matching the available gold choice.
    assert record.predicted_choice is None
    assert report.metrics["answer_choice_accuracy_all"].value == 0.0
    assert report.metrics["citation_validity"].value == 1.0


def test_explicit_answerable_alias_is_supported() -> None:
    record = adapt_evaluation_record(
        {
            "question_id": "q-explicit",
            "status": "completed",
            "answer": {"final_choice": None, "abstained": True, "citations": []},
            "retrieval": {"hits": []},
            "citation_integrity": "skipped",
        },
        {"question_id": "q-explicit", "answerable": False},
    )

    assert record.answerability is Answerability.VERIFIED_UNANSWERABLE


def test_hand_checked_metrics_and_denominators() -> None:
    records = load_evaluation_records(FIXTURE)
    report = evaluate_records(records)

    assert report.total_records == 6
    assert report.metrics["answer_choice_accuracy_all"].numerator == 2
    assert report.metrics["answer_choice_accuracy_all"].denominator == 4
    assert report.metrics["answer_choice_accuracy_answered"].value == 2 / 3
    assert report.metrics["abstention_accuracy"].value == 4 / 5
    assert report.metrics["abstention_precision"].value == 1.0
    assert report.metrics["abstention_precision"].excluded == 1
    assert report.metrics["abstention_recall"].value == 0.5
    assert report.metrics["abstention_recall"].excluded == 1
    assert report.metrics["abstention_f1"].value == 2 / 3
    assert report.metrics["raw_json_validity"].value == 3 / 4
    assert report.metrics["raw_schema_validity"].value == 0.5
    assert report.metrics["citation_validity"].value == 2 / 3
    assert report.metrics["gold_citation_hit_rate"].value == 2 / 3


def test_technical_failure_is_not_a_correct_abstention() -> None:
    records = load_evaluation_records(FIXTURE)
    report = evaluate_records(records)
    score = next(item for item in report.records if item.question_id == "q4")

    assert score.execution_status is ExecutionStatus.GENERATION_CALL_FAILURE
    assert score.answer_outcome == "technical_failure"
    assert score.abstention_correct is False


def test_zero_citations_never_score_as_valid() -> None:
    records = load_evaluation_records(FIXTURE)
    report = evaluate_records(records)
    score = next(item for item in report.records if item.question_id == "q5")

    assert score.execution_status is ExecutionStatus.CITATION_FAILURE
    assert score.citation_valid is False


def test_primary_failure_is_not_overwritten_by_citation_status() -> None:
    record = adapt_evaluation_record(
        {
            "question_id": "q-parse",
            "status": "failed",
            "failure_type": "JSON parse failure",
            "answer": None,
            "retrieval": {"hits": []},
            "citation_integrity": "failed",
        }
    )

    assert record.execution_status is ExecutionStatus.PARSE_FAILURE


def test_report_files_are_deterministic(tmp_path: Path) -> None:
    records = load_evaluation_records(FIXTURE)
    report = evaluate_records(records)
    paths = write_evaluation_report(report, records, tmp_path)
    first = {name: path.read_bytes() for name, path in paths.items()}

    write_evaluation_report(report, records, tmp_path)
    second = {name: path.read_bytes() for name, path in paths.items()}

    assert first == second
    assert "Numerator | Denominator" in paths["markdown"].read_text(encoding="utf-8")
    assert len(paths["failures"].read_text(encoding="utf-8").splitlines()) == 3


def test_separate_current_m3_gold_joins_by_question_id(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    gold = tmp_path / "gold.json"
    runs.write_text(
        json.dumps(
            {
                "question_id": "fixture_q001",
                "status": "completed",
                "answer": {"final_choice": "B", "abstained": False, "citations": ["c1"]},
                "retrieval": {"hits": [{"chunk_id": "c1"}]},
                "citation_integrity": "passed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gold.write_text(
        json.dumps(
            [
                {
                    "question_id": "fixture_q001",
                    "correct_choice": "B",
                    "support": "Acceleration is the rate of change of velocity.",
                    "in_scope": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    records = load_evaluation_records(runs, gold)

    assert records[0].gold_choice == "B"
    assert records[0].answerability is Answerability.UNRESOLVED


def test_duplicate_run_ids_fail_explicitly(tmp_path: Path) -> None:
    row = {
        "question_id": "duplicate",
        "status": "completed",
        "answer": {"final_choice": None, "abstained": True, "citations": []},
        "retrieval": {"hits": []},
        "citation_integrity": "skipped",
    }
    path = tmp_path / "runs.jsonl"
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate question_id"):
        load_evaluation_records(path)
