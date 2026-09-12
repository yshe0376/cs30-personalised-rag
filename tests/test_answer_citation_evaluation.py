from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.evaluation import (
    AnswerCitationScorer,
    EvaluationRunResult,
    load_gold_samples,
    load_mappings,
    load_run_results,
    write_answer_citation_reports,
)
from cs30.evaluation.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "evaluation"
GOLD = FIXTURES / "gold_v0_1.jsonl"
RUNS = FIXTURES / "run_results_scorable_v0_2.jsonl"
MAPPING = FIXTURES / "mapping_v0_1.json"


def _inputs():
    return load_gold_samples(GOLD), load_run_results(RUNS), load_mappings(MAPPING)


def _score():
    gold, runs, mappings = _inputs()
    return AnswerCitationScorer(mappings).score(gold, runs)


def test_answer_abstention_format_and_citation_metrics_have_denominators() -> None:
    result = _score()

    assert result["total_records"] == 2
    assert result["metrics"]["answer_choice_accuracy_all"]["numerator"] == 1
    assert result["metrics"]["answer_choice_accuracy_all"]["denominator"] == 2
    assert result["metrics"]["answer_choice_accuracy_answered"]["value"] == 1.0
    assert result["metrics"]["abstention_accuracy"]["value"] == 1.0
    assert result["metrics"]["abstention_precision"]["value"] == 1.0
    assert result["metrics"]["abstention_recall"]["value"] == 1.0
    assert result["metrics"]["abstention_f1"]["value"] == 1.0
    assert result["metrics"]["raw_json_validity"]["value"] == 1.0
    assert result["metrics"]["raw_schema_validity"]["value"] == 1.0
    assert result["metrics"]["citation_validity"]["value"] == 1.0
    assert result["metrics"]["per_citation_validity"]["value"] == 1.0
    assert result["metrics"]["repaired_json_validity"]["value"] is None


def test_abstention_confusion_uses_gold_answerable_and_keeps_failures_separate() -> None:
    result = _score()

    assert result["abstention_confusion"] == {
        "correct_abstention": 1,
        "wrong_abstention": 0,
        "answered_when_unanswerable": 0,
        "answered_when_answerable": 1,
        "technical_failure": 0,
        "unresolved": 0,
    }


def test_citations_are_checked_against_evidence_actually_sent() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    answer = {
        "schema_version": "1.0",
        "final_choice": "B",
        "explanation": "The answer cites a retrieval hit that was not sent.",
        "citations": ["chunk_not_sent"],
        "abstained": False,
    }
    payload["final_answer"] = answer
    payload["citation_validation"] = {
        "schema_version": "1.0",
        "answer": answer,
        "resolved_citations": [],
        "citation_status": "failed",
    }
    invalid_run = EvaluationRunResult.model_validate(payload)

    result = AnswerCitationScorer(mappings).score(gold, [invalid_run])
    record = result["records"][0]

    assert record["citation_valid"] is False
    assert record["citation_checks"][0]["belongs_to_sent_evidence"] is False
    assert "invalid_citation" in record["failure_labels"]


def test_gold_evidence_coverage_respects_or_of_ands_mapping() -> None:
    result = _score()

    answered = next(record for record in result["records"] if record["status"] == "answered")
    assert answered["gold_evidence_covered"] is False
    assert result["metrics"]["gold_evidence_citation_coverage"]["denominator"] == 1


def test_raw_and_repaired_validity_are_reported_separately() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    payload["raw_model_output"] = "{not-json"
    payload["repaired_model_output"] = json.dumps(
        payload["final_answer"], separators=(",", ":")
    )
    payload["model_call_count"] = 2
    repaired_run = EvaluationRunResult.model_validate(payload)

    result = AnswerCitationScorer(mappings).score(gold, [repaired_run])

    assert result["metrics"]["raw_json_validity"]["value"] == 0.0
    assert result["metrics"]["repaired_json_validity"]["value"] == 1.0
    assert result["metrics"]["repaired_schema_validity"]["value"] == 1.0
    assert result["operation_counts"] == {
        "runs_retried": 1,
        "retry_attempts": 1,
        "runs_repaired": 1,
    }
    assert "invalid_output" in result["records"][0]["failure_labels"]


def test_duplicate_final_runs_fail_explicitly() -> None:
    gold, runs, mappings = _inputs()

    with pytest.raises(ValueError, match="one final run per question"):
        AnswerCitationScorer(mappings).score(gold, [runs[0], runs[0]])


def test_reports_are_deterministic_and_keep_failure_queue(tmp_path: Path) -> None:
    result = _score()
    paths = write_answer_citation_reports(result, tmp_path)
    first = {name: path.read_bytes() for name, path in paths.items()}

    write_answer_citation_reports(result, tmp_path)
    second = {name: path.read_bytes() for name, path in paths.items()}

    assert first == second
    assert "Numerator | Denominator" in paths["markdown"].read_text(encoding="utf-8")
    assert len(paths["per_question"].read_text(encoding="utf-8").splitlines()) == 2
    assert paths["csv"].read_text(encoding="utf-8").startswith("metric,numerator")


def test_cli_runs_extension_and_writes_all_report_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "scores.json"
    reports = tmp_path / "answer-reports"

    exit_code = main(
        [
            "score",
            "--gold",
            str(GOLD),
            "--runs",
            str(RUNS),
            "--mapping",
            str(MAPPING),
            "--k-values",
            "1",
            "3",
            "--output",
            str(output),
            "--answer-citation-output-dir",
            str(reports),
        ]
    )

    assert exit_code == 0
    aggregate = json.loads(output.read_text(encoding="utf-8"))
    assert "answer_citation" in aggregate["extensions"]
    assert (reports / "answer_citation_summary.json").is_file()
    assert (reports / "answer_citation_scores.jsonl").is_file()
    assert (reports / "answer_citation_summary.csv").is_file()
    assert (reports / "answer_citation_report.md").is_file()
    assert (reports / "answer_citation_failures.jsonl").is_file()
