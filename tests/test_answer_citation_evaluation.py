from __future__ import annotations

import csv
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
    return AnswerCitationScorer(mappings).score(gold, runs, mode="development")


def test_answer_abstention_format_and_citation_metrics_have_denominators() -> None:
    result = _score()

    assert result["total_records"] == 4
    assert result["metrics"]["answer_choice_accuracy_all"]["numerator"] == 1
    assert result["metrics"]["answer_choice_accuracy_all"]["denominator"] == 4
    assert result["metrics"]["answer_choice_accuracy_answered"]["value"] == 1.0
    assert result["metrics"]["abstention_accuracy"]["value"] == 0.75
    assert result["metrics"]["abstention_precision"]["value"] == pytest.approx(2 / 3)
    assert result["metrics"]["abstention_recall"]["value"] == 1.0
    assert result["metrics"]["abstention_f1"]["value"] == pytest.approx(0.8)
    assert result["metrics"]["abstention_f1"]["numerator"] == 4
    assert result["metrics"]["abstention_f1"]["denominator"] == 5
    assert result["metrics"]["abstention_f1"]["excluded"] == 0
    assert result["metrics"]["model_abstention_accuracy"]["value"] == pytest.approx(
        2 / 3
    )
    assert result["metrics"]["model_abstention_precision"]["value"] == 0.5
    assert result["metrics"]["model_abstention_recall"]["value"] == 1.0
    assert result["metrics"]["model_abstention_f1"]["value"] == pytest.approx(2 / 3)
    assert result["metrics"]["model_abstention_f1"]["numerator"] == 2
    assert result["metrics"]["model_abstention_f1"]["denominator"] == 3
    assert result["metrics"]["model_abstention_f1"]["excluded"] == 1
    assert result["metrics"]["raw_json_validity"]["value"] == 1.0
    assert result["metrics"]["raw_schema_validity"]["value"] == 1.0
    assert result["metrics"]["citation_validity"]["value"] == 1.0
    assert result["metrics"]["per_citation_validity"]["value"] == 1.0
    assert result["metrics"]["repaired_json_validity"]["value"] is None
    assert result["missing_run_count"] == 0
    assert result["missing_run_question_ids"] == []


def test_abstention_confusion_uses_gold_answerable_and_keeps_failures_separate() -> None:
    result = _score()

    assert result["abstention_confusion"] == {
        "correct_abstention": 2,
        "wrong_abstention": 1,
        "answered_when_unanswerable": 0,
        "answered_when_answerable": 1,
        "technical_failure": 0,
        "unresolved": 0,
    }


def test_abstention_cause_is_scored_at_system_and_model_levels() -> None:
    result = _score()
    records = {record["question_id"]: record for record in result["records"]}

    assert records["fixture_unanswerable"]["abstention_cause"] == "no_retrieval_hits"
    assert (
        records["fixture_model_abstain_unanswerable"]["abstention_cause"]
        == "model_abstained_with_evidence"
    )
    assert records["fixture_model_abstain_unanswerable"]["abstention_correct"] is True
    assert records["fixture_model_abstain_answerable"]["abstention_correct"] is False
    assert result["abstention_cause_counts"] == {
        "no_retrieval_hits": 1,
        "model_abstained_with_evidence": 2,
    }
    assert result["abstention_confusion_by_cause"] == {
        "no_retrieval_hits": {
            "correct_abstention": 1,
            "wrong_abstention": 0,
            "unresolved": 0,
        },
        "model_abstained_with_evidence": {
            "correct_abstention": 1,
            "wrong_abstention": 1,
            "unresolved": 0,
        },
    }

    system_definition = result["metric_definitions"]["abstention_precision"]
    model_definition = result["metric_definitions"]["model_abstention_precision"]
    assert "no_retrieval_hits" in system_definition
    assert "model_abstained_with_evidence" in system_definition
    assert "no_retrieval_hits" in model_definition
    assert "resolved Gold" in model_definition
    assert "excluded" in model_definition


def test_unresolved_abstention_remains_visible_in_cause_breakdown() -> None:
    gold, runs, mappings = _inputs()
    unresolved_gold = gold[2]
    unresolved_run = runs[1].model_copy(
        update={
            "question_id": unresolved_gold.question_id,
            "run_id": "run_unresolved_no_retrieval_hits",
        }
    )

    result = AnswerCitationScorer(mappings).score(
        [unresolved_gold], [unresolved_run], mode="development"
    )

    assert result["records"][0]["abstention_cause"] == "no_retrieval_hits"
    assert result["metrics"]["abstention_precision"]["value"] is None
    assert result["metrics"]["answer_choice_accuracy_all"]["denominator"] == 0
    assert result["metrics"]["answer_choice_accuracy_parsed"]["denominator"] == 0
    assert result["metrics"]["answer_choice_accuracy_answered"]["denominator"] == 0
    assert result["unresolved_count"] == 1
    assert "unresolved_answerability" in result["records"][0]["failure_labels"]
    assert result["abstention_confusion"]["unresolved"] == 1
    assert result["abstention_cause_counts"]["no_retrieval_hits"] == 1
    assert result["abstention_confusion_by_cause"]["no_retrieval_hits"] == {
        "correct_abstention": 0,
        "wrong_abstention": 0,
        "unresolved": 1,
    }


def test_citations_are_checked_against_evidence_actually_sent() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    answer = {
        "schema_version": "1.0",
        "final_choice": "A",
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

    result = AnswerCitationScorer(mappings).score(
        gold, [invalid_run], mode="development"
    )
    record = result["records"][0]

    assert record["citation_valid"] is False
    assert record["citation_checks"][0]["belongs_to_sent_evidence"] is False
    assert {"gold_missed", "wrong_option", "invalid_citation"}.issubset(
        record["failure_labels"]
    )


def test_resolved_citation_sequence_must_match_upstream_validation() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    payload["citation_validation"]["resolved_citations"] = ["chunk_gamma"]
    run = EvaluationRunResult.model_validate(payload)

    record = AnswerCitationScorer(mappings).score(
        [gold[0]], [run], mode="development"
    )["records"][0]

    assert record["citation_validation_matches"] is False
    assert record["citation_valid"] is False
    assert "citation_validation_mismatch" in record["failure_labels"]


def test_gold_evidence_coverage_respects_or_of_ands_mapping() -> None:
    result = _score()

    answered = next(record for record in result["records"] if record["status"] == "answered")
    assert answered["gold_evidence_covered"] is False
    assert result["metrics"]["gold_evidence_citation_coverage"]["denominator"] == 1


def test_gold_evidence_coverage_checks_later_or_path_after_missing_mapping() -> None:
    gold, runs, mappings = _inputs()
    question_mapping = mappings.items[0]
    partial_mapping = mappings.model_copy(
        update={
            "items": [
                question_mapping.model_copy(
                    update={
                        "spans": [
                            span
                            for span in question_mapping.spans
                            if span.span_id == "span_gamma"
                        ]
                    }
                )
            ]
        }
    )
    payload = runs[0].model_dump(mode="json")
    payload["retrieval"]["hits"][0].update(
        chunk_id="chunk_gamma",
        text="Gamma.",
        source_locator="[13,19)",
    )
    payload["evidence_sent_to_model"]["evidence_items"][0].update(
        chunk_id="chunk_gamma",
        text="Gamma.",
        source_locator="[13,19)",
    )
    payload["evidence_sent_to_model"]["citation_map"] = {"E1": "chunk_gamma"}
    payload["final_answer"]["citations"] = ["chunk_gamma"]
    payload["citation_validation"]["answer"]["citations"] = ["chunk_gamma"]
    payload["citation_validation"]["resolved_citations"] = ["chunk_gamma"]
    run = EvaluationRunResult.model_validate(payload)

    record = AnswerCitationScorer(partial_mapping).score(
        [gold[0]], [run], mode="development"
    )["records"][0]

    assert record["gold_evidence_covered"] is True
    assert "mapping_missing" not in record["failure_labels"]


def test_raw_and_repaired_validity_are_reported_separately() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    payload["raw_model_output"] = "{not-json"
    payload["repaired_model_output"] = json.dumps(
        payload["final_answer"], separators=(",", ":")
    )
    payload["model_call_count"] = 2
    repaired_run = EvaluationRunResult.model_validate(payload)

    result = AnswerCitationScorer(mappings).score(
        gold, [repaired_run], mode="development"
    )

    assert result["metrics"]["raw_json_validity"]["value"] == 0.0
    assert result["metrics"]["repaired_json_validity"]["value"] == 1.0
    assert result["metrics"]["repaired_schema_validity"]["value"] == 1.0
    assert result["operation_counts"] == {
        "runs_retried": 1,
        "retry_attempts": 1,
        "runs_repaired": 1,
    }
    assert "invalid_output" in result["records"][0]["failure_labels"]


def test_repaired_zero_citation_answer_is_reported_as_missing() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    payload.update(
        status="parse_error",
        raw_model_output="{not-json",
        repaired_model_output=json.dumps(
            {
                "schema_version": "1.0",
                "final_choice": "B",
                "explanation": "The repaired answer still omitted evidence.",
                "citations": [],
                "abstained": False,
            }
        ),
        final_answer=None,
        citation_validation=None,
        error={
            "stage": "parsing",
            "error_type": "ValidationError",
            "message": "A non-abstained answer must cite evidence.",
        },
        model_call_count=2,
    )
    run = EvaluationRunResult.model_validate(payload)

    record = AnswerCitationScorer(mappings).score(
        [gold[0]], [run], mode="development"
    )["records"][0]

    assert record["repaired_json_valid"] is True
    assert record["repaired_schema_valid"] is False
    assert record["missing_required_citation"] is True
    assert record["citation_valid"] is False
    assert {"invalid_output", "invalid_citation", "missing_citation"}.issubset(
        record["failure_labels"]
    )


def test_successful_repair_clears_the_missing_citation_diagnostic() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    payload["raw_model_output"] = json.dumps(
        {
            "schema_version": "1.0",
            "final_choice": "B",
            "explanation": "The first attempt omitted evidence.",
            "citations": [],
            "abstained": False,
        }
    )
    payload["repaired_model_output"] = json.dumps(payload["final_answer"])
    payload["model_call_count"] = 2
    run = EvaluationRunResult.model_validate(payload)

    record = AnswerCitationScorer(mappings).score(
        [gold[0]], [run], mode="development"
    )["records"][0]

    assert record["raw_schema_valid"] is False
    assert record["repaired_schema_valid"] is True
    assert record["missing_required_citation"] is False
    assert record["citation_valid"] is True
    assert "missing_citation" not in record["failure_labels"]


def test_invalid_citation_survives_failed_generation_for_review() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    invalid_answer = {
        "schema_version": "1.0",
        "final_choice": "B",
        "explanation": "The attempted answer cites evidence that was not sent.",
        "citations": ["chunk_not_sent"],
        "abstained": False,
    }
    payload.update(
        status="generation_error",
        raw_model_output=json.dumps(invalid_answer),
        repaired_model_output=json.dumps(invalid_answer),
        final_answer=None,
        citation_validation=None,
        error={
            "stage": "generation",
            "error_type": "GenerationError",
            "message": "Citation validation failed after retries.",
        },
        model_call_count=2,
    )
    run = EvaluationRunResult.model_validate(payload)

    record = AnswerCitationScorer(mappings).score(
        [gold[0]], [run], mode="development"
    )["records"][0]

    assert record["citation_checks"][0]["belongs_to_sent_evidence"] is False
    assert record["citation_valid"] is False
    assert {"generation_failure", "invalid_citation"}.issubset(
        record["failure_labels"]
    )


def test_duplicate_final_runs_fail_explicitly() -> None:
    gold, runs, mappings = _inputs()

    with pytest.raises(ValueError, match="one final run per question"):
        AnswerCitationScorer(mappings).score(
            gold, [runs[0], runs[0]], mode="development"
        )


def test_duplicate_gold_ids_fail_explicitly() -> None:
    gold, runs, mappings = _inputs()

    with pytest.raises(ValueError, match="duplicate question_id in Gold"):
        AnswerCitationScorer(mappings).score(
            [gold[0], gold[0]], [runs[0]], mode="development"
        )


@pytest.mark.parametrize("invalid_line", ["{not-json\n", '{"schema_version":"0.2"}\n'])
def test_invalid_saved_run_json_or_schema_fails_before_scoring(
    tmp_path: Path, invalid_line: str
) -> None:
    invalid_runs = tmp_path / "invalid_runs.jsonl"
    invalid_runs.write_text(invalid_line, encoding="utf-8")

    with pytest.raises(ValueError, match=r"invalid_runs\.jsonl:1:"):
        load_run_results(invalid_runs)


def test_retrieval_failure_without_output_is_not_invalid_json() -> None:
    gold, _, mappings = _inputs()
    run = EvaluationRunResult.model_validate(
        {
            "schema_version": "0.2",
            "run_id": "run-call-failure",
            "question_id": "fixture_joint",
            "condition_id": "fixture_condition",
            "execution_mode": "retrieval_and_generation",
            "status": "retrieval_error",
            "retrieval": None,
            "evidence_sent_to_model": None,
            "raw_model_output": None,
            "repaired_model_output": None,
            "final_answer": None,
            "citation_validation": None,
            "error": {
                "stage": "retrieval",
                "error_type": "FixtureError",
                "message": "The fixture retriever failed.",
            },
            "model_call_count": 0,
            "abstention_cause": None,
        }
    )

    result = AnswerCitationScorer(mappings, expected_mode="bm25").score(
        gold, [run], mode="development"
    )
    record = result["records"][0]

    assert record["answer_outcome"] == "retrieval_failed"
    assert record["mode"] == "bm25"
    assert result["groups"][0]["mode"] == "bm25"
    assert record["failure_labels"] == ["retrieval_failure"]
    assert result["metrics"]["raw_json_validity"]["denominator"] == 0
    assert "invalid_output" not in record["failure_labels"]


def test_retrieval_and_generation_failures_have_distinct_attribution() -> None:
    gold, runs, mappings = _inputs()
    retrieval_payload = runs[0].model_dump(mode="json")
    retrieval_payload.update(
        status="retrieval_error",
        retrieval=None,
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error={
            "stage": "retrieval",
            "error_type": "FixtureError",
            "message": "retrieval failed",
        },
        model_call_count=0,
    )
    generation_payload = runs[0].model_dump(mode="json")
    generation_payload.update(
        status="generation_error",
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error={
            "stage": "generation",
            "error_type": "FixtureError",
            "message": "generation failed",
        },
        model_call_count=1,
    )

    retrieval_record = AnswerCitationScorer(mappings).score(
        [gold[0]],
        [EvaluationRunResult.model_validate(retrieval_payload)],
        mode="development",
    )["records"][0]
    generation_record = AnswerCitationScorer(mappings).score(
        [gold[0]],
        [EvaluationRunResult.model_validate(generation_payload)],
        mode="development",
    )["records"][0]

    assert retrieval_record["answer_outcome"] == "retrieval_failed"
    assert retrieval_record["failure_labels"] == ["retrieval_failure"]
    assert generation_record["answer_outcome"] == "generation_failed"
    assert generation_record["failure_labels"] == ["generation_failure"]


def test_zero_citation_answer_is_visible_after_schema_rejection() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    payload.update(
        status="parse_error",
        raw_model_output=json.dumps(
            {
                "schema_version": "1.0",
                "final_choice": "B",
                "explanation": "An answer without required evidence.",
                "citations": [],
                "abstained": False,
            }
        ),
        final_answer=None,
        citation_validation=None,
        error={
            "stage": "parsing",
            "error_type": "ValidationError",
            "message": "A non-abstained answer must cite evidence.",
        },
    )
    run = EvaluationRunResult.model_validate(payload)

    result = AnswerCitationScorer(mappings).score(
        gold, [run], mode="development"
    )
    record = result["records"][0]

    assert record["answer_outcome"] == "format_failed"
    assert record["raw_json_valid"] is True
    assert record["raw_schema_valid"] is False
    assert record["citation_valid"] is False
    assert {"invalid_output", "invalid_citation", "missing_citation"}.issubset(
        record["failure_labels"]
    )


def test_all_abstain_and_no_computable_denominator_cases_remain_visible() -> None:
    gold, runs, mappings = _inputs()
    unanswerable_gold = gold[1]
    unanswerable_run = runs[1]
    second_gold = unanswerable_gold.model_copy(update={"question_id": "fixture_unanswerable_2"})
    second_run = unanswerable_run.model_copy(
        update={
            "question_id": "fixture_unanswerable_2",
            "run_id": "run_scorable_unanswerable_2",
        }
    )

    all_abstain = AnswerCitationScorer(mappings).score(
        [unanswerable_gold, second_gold],
        [unanswerable_run, second_run],
        mode="development",
    )
    no_positive_class = AnswerCitationScorer(mappings).score(
        [gold[0]], [runs[0]], mode="development"
    )

    assert all_abstain["answer_outcome_counts"] == {
        "correct": 0,
        "wrong": 0,
        "abstained": 2,
        "retrieval_failed": 0,
        "generation_failed": 0,
        "format_failed": 0,
    }
    assert all_abstain["metrics"]["abstention_precision"]["value"] == 1.0
    assert all_abstain["metrics"]["answer_choice_accuracy_all"]["value"] == 0.0
    assert no_positive_class["metrics"]["abstention_precision"]["value"] is None
    assert no_positive_class["metrics"]["abstention_recall"]["value"] is None
    assert no_positive_class["metrics"]["abstention_f1"]["value"] is None


def test_groups_use_retrieval_mode_not_only_execution_mode() -> None:
    result = _score()

    modes = {group["mode"] for group in result["groups"]}
    splits = {group["split"] for group in result["groups"]}
    assert modes == {"fixture"}
    assert splits == {"dev", "test"}


def test_retrieval_only_answer_metrics_are_not_applicable() -> None:
    gold, runs, mappings = _inputs()
    payload = runs[0].model_dump(mode="json")
    payload.update(
        execution_mode="retrieval_only",
        status="retrieved",
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
    )
    run = EvaluationRunResult.model_validate(payload)

    result = AnswerCitationScorer(mappings).score(
        [gold[0]], [run], mode="development"
    )

    assert result["applicability"] == "not_applicable"
    assert result["metrics"] == {}
    assert result["answer_outcome_counts"] == {"not_applicable": 1}
    assert result["groups"][0]["metrics"] == {}


def test_missing_runs_are_reported_only_within_the_expected_split() -> None:
    gold, runs, mappings = _inputs()
    missing_dev = gold[0].model_copy(update={"question_id": "missing_dev"})

    result = AnswerCitationScorer(mappings, expected_split="dev").score(
        [gold[0], missing_dev, gold[1]], [runs[0]], mode="development"
    )

    assert result["missing_run_count"] == 1
    assert result["missing_run_question_ids"] == ["missing_dev"]

    with pytest.raises(ValueError, match="missing expected run results"):
        AnswerCitationScorer(mappings, expected_split="dev").score(
            [gold[0], missing_dev, gold[1]], [runs[0]], mode="reportable"
        )


@pytest.mark.parametrize(
    ("scorer_kwargs", "reason"),
    [
        ({"expected_split": "test"}, "split_mismatch"),
        ({"expected_mode": "bm25"}, "mode_mismatch"),
        ({"expected_condition": "another-condition"}, "condition_mismatch"),
    ],
)
def test_scope_mismatches_are_excluded_in_development_and_fail_when_reportable(
    scorer_kwargs: dict[str, str], reason: str
) -> None:
    gold, runs, mappings = _inputs()
    scorer = AnswerCitationScorer(mappings, **scorer_kwargs)

    development = scorer.score([gold[0]], [runs[0]], mode="development")

    assert development["records"] == []
    assert development["groups"] == []
    assert development["excluded_runs"][reason] == 1
    assert development["excluded_runs"]["total"] == 1
    assert sum(
        count
        for key, count in development["excluded_runs"].items()
        if key != "total"
    ) == 1

    with pytest.raises(ValueError, match=reason):
        scorer.score([gold[0]], [runs[0]], mode="reportable")


def test_orphan_run_is_excluded_from_answer_scoring_in_both_modes() -> None:
    gold, runs, mappings = _inputs()
    orphan = runs[0].model_copy(
        update={"question_id": "orphan-question", "run_id": "orphan-run"}
    )

    for mode in ("development", "reportable"):
        result = AnswerCitationScorer(mappings).score(
            [gold[0]], [orphan], mode=mode
        )
        assert result["excluded_runs"] == {
            "total": 1,
            "missing_gold": 1,
            "split_mismatch": 0,
            "mode_mismatch": 0,
            "condition_mismatch": 0,
        }
        assert result["records"] == []
        assert result["groups"] == []


def test_reports_are_deterministic_and_keep_failure_queue(tmp_path: Path) -> None:
    result = _score()
    paths = write_answer_citation_reports(result, tmp_path)
    first = {name: path.read_bytes() for name, path in paths.items()}

    write_answer_citation_reports(result, tmp_path)
    second = {name: path.read_bytes() for name, path in paths.items()}

    assert first == second
    assert "Numerator | Denominator" in paths["markdown"].read_text(encoding="utf-8")
    per_question = paths["per_question"].read_text(encoding="utf-8")
    markdown = paths["markdown"].read_text(encoding="utf-8")
    csv_report = paths["csv"].read_text(encoding="utf-8")
    failures = paths["failures"].read_text(encoding="utf-8")

    assert len(per_question.splitlines()) == 4
    assert '"abstention_cause": "model_abstained_with_evidence"' in per_question
    assert paths["csv"].read_text(encoding="utf-8").startswith("metric,numerator")
    assert "Abstention confusion by cause" in markdown
    assert "Overall diagnostic aggregate" in markdown
    assert "### dev | fixture | fixture_condition" in markdown
    assert "### test | fixture | fixture_condition" in markdown
    assert "model_abstained_with_evidence" in markdown
    assert "cause,outcome" in csv_report.splitlines()[0]
    assert "model_abstained_with_evidence" in csv_report
    assert '"abstention_cause": "model_abstained_with_evidence"' in failures
    assert all(
        "definition" not in metric
        for group in result["groups"]
        for metric in group["metrics"].values()
    )
    assert "abstention_precision" in result["metric_definitions"]

    csv_rows = list(csv.DictReader(csv_report.splitlines()))
    cause_rows = {
        (row["cause"], row["outcome"]): row
        for row in csv_rows
        if row["cause"] and row["scope"] == "overall"
    }
    assert cause_rows[("no_retrieval_hits", "correct_abstention")]["denominator"] == "1"
    assert cause_rows[("no_retrieval_hits", "correct_abstention")]["excluded"] == "3"
    assert (
        cause_rows[("model_abstained_with_evidence", "wrong_abstention")][
            "denominator"
        ]
        == "2"
    )
    grouped_metrics = [
        row
        for row in csv_rows
        if row["scope"] == "group" and row["metric"] == "abstention_precision"
    ]
    assert {row["split"] for row in grouped_metrics} == {"dev", "test"}
    assert all(row["mode"] == "fixture" for row in grouped_metrics)
    assert all(row["condition_id"] == "fixture_condition" for row in grouped_metrics)
    assert all(row["data_version"] == "gold-fixture-0.1" for row in grouped_metrics)
    assert all(row["corpus_version"] == "fixture-corpus-0.1" for row in grouped_metrics)
    assert (
        cause_rows[("model_abstained_with_evidence", "wrong_abstention")]["excluded"]
        == "2"
    )


def test_cli_runs_extension_and_writes_all_report_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "new-output" / "scores.json"
    reports = tmp_path / "new-output" / "answer-reports"

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
    assert "records" not in aggregate["extensions"]["answer_citation"]
    assert (reports / "answer_citation_summary.json").is_file()
    assert (reports / "answer_citation_scores.jsonl").is_file()
    assert (reports / "answer_citation_summary.csv").is_file()
    assert (reports / "answer_citation_report.md").is_file()
    assert (reports / "answer_citation_failures.jsonl").is_file()
