"""M8 answer, abstention, format, and citation scoring extension."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import ValidationError

from cs30.contracts import GeneratedAnswer, RetrievalMode

from .mapping import GoldChunkMapping, QuestionChunkMapping
from .models import (
    AbstentionCause,
    EvaluationRunResult,
    EvaluationSplit,
    ExecutionMode,
    GoldSample,
    RunStatus,
)

_TECHNICAL_STATUSES = {
    RunStatus.RETRIEVAL_ERROR,
    RunStatus.GENERATION_ERROR,
    RunStatus.PARSE_ERROR,
}

ScoringMode = Literal["development", "reportable"]


def _metric(
    numerator: int | float,
    denominator: int | float,
    *,
    eligible: int,
    total: int,
    definition: str,
) -> dict[str, int | float | str | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
        "excluded": total - eligible,
        "definition": definition,
    }


def _output_validity(text: str | None) -> tuple[bool | None, bool | None]:
    """Return separate JSON and GeneratedAnswer-schema validity values."""

    if text is None:
        return None, None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return False, False
    try:
        GeneratedAnswer.model_validate(payload)
    except ValidationError:
        return True, False
    return True, True


def _output_missing_required_citation(text: str | None) -> bool | None:
    """Inspect one parseable output for a missing required citation."""

    if text is None:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return False
    return bool(
        payload.get("abstained") is False and not payload.get("citations")
    )


def _latest_missing_required_citation(run: EvaluationRunResult) -> bool:
    """Check the latest parseable attempt, falling back to the first output."""

    for text in (run.repaired_model_output, run.raw_model_output):
        missing = _output_missing_required_citation(text)
        if missing is not None:
            return missing
    return False


def _latest_schema_valid_answer(run: EvaluationRunResult) -> GeneratedAnswer | None:
    """Recover a diagnostic answer when a failed run has no final answer."""

    for text in (run.repaired_model_output, run.raw_model_output):
        if text is None:
            continue
        try:
            return GeneratedAnswer.model_validate_json(text)
        except (TypeError, ValueError, ValidationError):
            continue
    return None


def _question_mapping(
    mappings: GoldChunkMapping | Mapping[str, QuestionChunkMapping],
    question_id: str,
) -> QuestionChunkMapping | None:
    if isinstance(mappings, GoldChunkMapping):
        try:
            return mappings.for_question(question_id)
        except KeyError:
            return None
    return mappings.get(question_id)


def _citation_checks(run: EvaluationRunResult) -> list[dict[str, Any]]:
    answer = run.final_answer or _latest_schema_valid_answer(run)
    if answer is None:
        return []

    by_identifier = {}
    if run.evidence_sent_to_model is not None:
        for item in run.evidence_sent_to_model.evidence_items:
            by_identifier[item.evidence_id] = item
            by_identifier[item.chunk_id] = item

    checks = []
    for citation_id in answer.citations:
        evidence = by_identifier.get(citation_id)
        belongs = evidence is not None
        checks.append(
            {
                "citation_id": citation_id,
                "chunk_id": evidence.chunk_id if evidence is not None else None,
                "source": evidence.source if evidence is not None else None,
                "source_locator": evidence.source_locator if evidence is not None else None,
                "belongs_to_sent_evidence": belongs,
                "resolves_to_chunk": belongs and bool(evidence.chunk_id),
                "resolves_to_source": belongs and bool(evidence.source),
                "valid": belongs and bool(evidence.chunk_id) and bool(evidence.source),
            }
        )
    return checks


def _gold_evidence_coverage(
    gold: GoldSample,
    cited_chunk_ids: set[str],
    mappings: GoldChunkMapping | Mapping[str, QuestionChunkMapping],
) -> tuple[bool | None, bool]:
    """Check whether citations completely cover one sufficient OR path."""

    if not gold.gold_core_evidence_sets:
        return None, False
    question_mapping = _question_mapping(mappings, gold.question_id)
    if question_mapping is None:
        return None, True

    mapped_spans = {item.span_id: item for item in question_mapping.spans}
    mapping_missing = False
    for evidence_set in gold.gold_core_evidence_sets:
        path_complete = True
        for span in evidence_set:
            span_mapping = mapped_spans.get(span.span_id)
            if span_mapping is None:
                mapping_missing = True
                path_complete = False
                break
            span_covered = any(
                set(chunk_set).issubset(cited_chunk_ids)
                for chunk_set in span_mapping.acceptable_chunk_sets
            )
            if not span_covered:
                path_complete = False
                break
        if path_complete:
            return True, False
    return (None, True) if mapping_missing else (False, False)


def _answer_outcome(gold: GoldSample, run: EvaluationRunResult) -> str:
    if run.execution_mode is ExecutionMode.RETRIEVAL_ONLY:
        return "not_applicable"
    if run.status is RunStatus.RETRIEVAL_ERROR:
        return "retrieval_failed"
    if run.status is RunStatus.GENERATION_ERROR:
        return "generation_failed"
    if run.status is RunStatus.PARSE_ERROR:
        return "format_failed"
    if run.status is RunStatus.ABSTAINED:
        return "abstained"
    if gold.gold_answer is None:
        return "missing_gold"
    if run.final_answer is None or run.final_answer.final_choice is None:
        return "missing_prediction"
    return "correct" if run.final_answer.final_choice == gold.gold_answer else "wrong"


def _score_pair(
    gold: GoldSample,
    run: EvaluationRunResult,
    mappings: GoldChunkMapping | Mapping[str, QuestionChunkMapping],
    expected_mode: RetrievalMode | None = None,
) -> dict[str, Any]:
    generation_run = run.execution_mode is ExecutionMode.RETRIEVAL_AND_GENERATION
    successful = run.status in {RunStatus.ANSWERED, RunStatus.ABSTAINED}
    answer_correct = None
    if (
        generation_run
        and gold.answerable is not None
        and gold.gold_answer is not None
    ):
        answer_correct = bool(
            run.status is RunStatus.ANSWERED
            and run.final_answer is not None
            and run.final_answer.final_choice == gold.gold_answer
        )

    parsed_answer_correct = None
    if successful and gold.answerable is not None and gold.gold_answer is not None:
        parsed_answer_correct = bool(
            run.status is RunStatus.ANSWERED
            and run.final_answer is not None
            and run.final_answer.final_choice == gold.gold_answer
        )

    answered_choice_correct = None
    if (
        run.status is RunStatus.ANSWERED
        and gold.answerable is not None
        and gold.gold_answer is not None
        and run.final_answer is not None
        and run.final_answer.final_choice is not None
    ):
        answered_choice_correct = run.final_answer.final_choice == gold.gold_answer

    abstention_correct = None
    if generation_run and gold.answerable is not None:
        expected_abstention = gold.answerable is False
        abstention_correct = bool(
            successful
            and run.final_answer is not None
            and run.final_answer.abstained is expected_abstention
        )

    raw_json_valid, raw_schema_valid = _output_validity(run.raw_model_output)
    repaired_json_valid, repaired_schema_valid = _output_validity(
        run.repaired_model_output
    )
    missing_required_citation = _latest_missing_required_citation(run)

    citation_checks = _citation_checks(run)
    resolved_citation_ids = [
        check["chunk_id"]
        for check in citation_checks
        if check["chunk_id"] is not None
    ]
    citation_validation_matches = None
    if run.citation_validation is not None:
        citation_validation_matches = (
            resolved_citation_ids == run.citation_validation.resolved_citations
        )

    citation_valid = None
    if run.status is RunStatus.ANSWERED:
        citation_valid = bool(
            citation_checks
            and all(check["valid"] for check in citation_checks)
            and run.citation_validation is not None
            and run.citation_validation.citation_status == "passed"
            and citation_validation_matches
        )
    elif missing_required_citation:
        citation_valid = False
    elif citation_checks and any(not check["valid"] for check in citation_checks):
        # A failed generation can still retain a schema-valid attempted answer.
        # Keep the run excluded from successful-answer validity unless an
        # observable invalid citation needs to be surfaced for review.
        citation_valid = False

    gold_evidence_covered = None
    mapping_missing = False
    if run.status is RunStatus.ANSWERED:
        cited_chunk_ids = {
            check["chunk_id"]
            for check in citation_checks
            if check["chunk_id"] is not None
        }
        gold_evidence_covered, mapping_missing = _gold_evidence_coverage(
            gold, cited_chunk_ids, mappings
        )

    labels: set[str] = set()
    if run.status is RunStatus.RETRIEVAL_ERROR:
        labels.add("retrieval_failure")
    elif run.status is RunStatus.GENERATION_ERROR:
        labels.add("generation_failure")
    elif run.status is RunStatus.PARSE_ERROR:
        labels.add("invalid_output")
    if answered_choice_correct is False:
        labels.update({"gold_missed", "wrong_option"})
    if gold.answerable is True and run.status is RunStatus.ABSTAINED:
        labels.update({"gold_missed", "wrong_abstention"})
    if gold.answerable is False and run.status is RunStatus.ANSWERED:
        labels.add("answered_when_unanswerable")
    if any(
        value is False
        for value in (
            raw_json_valid,
            raw_schema_valid,
            repaired_json_valid,
            repaired_schema_valid,
        )
    ):
        labels.add("invalid_output")
    if citation_valid is False:
        labels.add("invalid_citation")
    if citation_validation_matches is False:
        labels.add("citation_validation_mismatch")
    if missing_required_citation:
        labels.add("missing_citation")
    if gold.answerable is None:
        labels.add("unresolved_answerability")
    if mapping_missing:
        labels.add("mapping_missing")

    return {
        "question_id": run.question_id,
        "run_id": run.run_id,
        "condition_id": run.condition_id,
        "execution_mode": run.execution_mode.value,
        "mode": (
            run.retrieval.mode.value
            if run.retrieval is not None
            else expected_mode.value if expected_mode is not None else "unknown"
        ),
        "status": run.status.value,
        "abstention_cause": (
            run.abstention_cause.value if run.abstention_cause is not None else None
        ),
        "split": gold.split.value,
        "corpus_version": gold.corpus_version,
        "gold_annotation_version": gold.gold_annotation_version,
        "answer_outcome": _answer_outcome(gold, run),
        "answer_correct": answer_correct,
        "parsed_answer_correct": parsed_answer_correct,
        "answered_choice_correct": answered_choice_correct,
        "abstention_correct": abstention_correct,
        "raw_json_valid": raw_json_valid,
        "raw_schema_valid": raw_schema_valid,
        "repaired_json_valid": repaired_json_valid,
        "repaired_schema_valid": repaired_schema_valid,
        "citation_valid": citation_valid,
        "citation_validation_matches": citation_validation_matches,
        "missing_required_citation": missing_required_citation,
        "gold_evidence_covered": gold_evidence_covered,
        "citation_checks": citation_checks,
        "failure_labels": sorted(labels),
        "model_call_count": run.model_call_count,
        "repair_used": run.repaired_model_output is not None,
    }


def _summarise(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)

    def boolean_metric(field: str, definition: str) -> dict[str, Any]:
        eligible = [record for record in records if record[field] is not None]
        return _metric(
            sum(record[field] is True for record in eligible),
            len(eligible),
            eligible=len(eligible),
            total=total,
            definition=definition,
        )

    all_system_abstentions = [
        record
        for record in records
        if record["execution_mode"] == ExecutionMode.RETRIEVAL_AND_GENERATION.value
        and record["status"] == RunStatus.ABSTAINED.value
    ]
    system_predicted_abstentions = [
        record
        for record in all_system_abstentions
        if record["abstention_correct"] is not None
    ]
    gold_unanswerable = [
        record
        for record in records
        if record["execution_mode"] == ExecutionMode.RETRIEVAL_AND_GENERATION.value
        and record["abstention_correct"] is not None
        and record["gold_answerable"] is False
    ]
    true_system_abstentions = sum(
        record["abstention_correct"] is True for record in system_predicted_abstentions
    )
    system_precision_denominator = len(system_predicted_abstentions)
    system_recall_denominator = len(gold_unanswerable)
    system_false_abstentions = (
        system_precision_denominator - true_system_abstentions
    )
    system_missed_abstentions = system_recall_denominator - true_system_abstentions

    model_decisions = [
        record
        for record in records
        if record["execution_mode"] == ExecutionMode.RETRIEVAL_AND_GENERATION.value
        and record["status"] in {RunStatus.ANSWERED.value, RunStatus.ABSTAINED.value}
        and record["model_call_count"] > 0
        and record["abstention_correct"] is not None
    ]
    model_predicted_abstentions = [
        record
        for record in model_decisions
        if record["abstention_cause"]
        == AbstentionCause.MODEL_ABSTAINED_WITH_EVIDENCE.value
    ]
    model_gold_unanswerable = [
        record for record in model_decisions if record["gold_answerable"] is False
    ]
    true_model_abstentions = sum(
        record["abstention_correct"] is True for record in model_predicted_abstentions
    )
    model_precision_denominator = len(model_predicted_abstentions)
    model_recall_denominator = len(model_gold_unanswerable)
    model_false_abstentions = model_precision_denominator - true_model_abstentions
    model_missed_abstentions = model_recall_denominator - true_model_abstentions

    system_f1_numerator = 2 * true_system_abstentions
    system_f1_denominator = (
        system_f1_numerator
        + system_false_abstentions
        + system_missed_abstentions
    )
    model_f1_numerator = 2 * true_model_abstentions
    model_f1_denominator = (
        model_f1_numerator + model_false_abstentions + model_missed_abstentions
    )

    metrics = {
        "answer_choice_accuracy_all": boolean_metric(
            "answer_correct",
            "Correct choices divided by generation runs with resolved Gold answerability "
            "and a gold choice; technical failures and abstentions count as incorrect.",
        ),
        "answer_choice_accuracy_parsed": boolean_metric(
            "parsed_answer_correct",
            "Correct choices divided by successfully parsed answer or abstention outcomes "
            "with resolved Gold answerability and a gold choice.",
        ),
        "answer_choice_accuracy_answered": boolean_metric(
            "answered_choice_correct",
            "Correct choices divided by non-abstained answers with resolved Gold "
            "answerability and a gold choice.",
        ),
        "abstention_accuracy": boolean_metric(
            "abstention_correct",
            "System-level correct abstain/non-abstain decisions divided by generation runs "
            "with resolved answerability. Both no_retrieval_hits and "
            "model_abstained_with_evidence are system abstentions; technical failures count "
            "as incorrect.",
        ),
        "abstention_precision": _metric(
            true_system_abstentions,
            system_precision_denominator,
            eligible=system_precision_denominator,
            total=total,
            definition="System-level correct abstentions divided by all system-predicted "
            "abstentions with resolved Gold answerability. The numerator and denominator "
            "include both no_retrieval_hits and model_abstained_with_evidence; abstentions "
            "with unresolved Gold answerability are reported by cause but excluded here.",
        ),
        "abstention_recall": _metric(
            true_system_abstentions,
            system_recall_denominator,
            eligible=system_recall_denominator,
            total=total,
            definition="System-level correct abstentions, including both no_retrieval_hits "
            "and model_abstained_with_evidence, divided by all gold-unanswerable generation "
            "runs with resolved answerability; technical failures remain in the denominator.",
        ),
        "abstention_f1": _metric(
            system_f1_numerator,
            system_f1_denominator if system_recall_denominator > 0 else 0,
            eligible=sum(
                record["execution_mode"]
                == ExecutionMode.RETRIEVAL_AND_GENERATION.value
                and record["abstention_correct"] is not None
                for record in records
            ),
            total=total,
            definition="System-level abstention F1 computed as 2TP / (2TP + FP + FN), "
            "where both abstention causes are predicted positives, TP is a correct "
            "abstention, FP is a wrong abstention, and FN is a gold-unanswerable run that "
            "did not abstain correctly. Only resolved Gold answerability is eligible; "
            "F1 is not applicable when the Gold set has no unanswerable runs.",
        ),
        "model_abstention_accuracy": _metric(
            sum(record["abstention_correct"] is True for record in model_decisions),
            len(model_decisions),
            eligible=len(model_decisions),
            total=total,
            definition="Model-level correct abstain/non-abstain decisions divided by "
            "successful generation runs with resolved Gold answerability where the model "
            "was invoked with evidence. no_retrieval_hits runs, unresolved Gold, and "
            "technical failures are excluded.",
        ),
        "model_abstention_precision": _metric(
            true_model_abstentions,
            model_precision_denominator,
            eligible=model_precision_denominator,
            total=total,
            definition="Correct model_abstained_with_evidence outcomes divided by all "
            "model_abstained_with_evidence outcomes with resolved Gold answerability. "
            "no_retrieval_hits and unresolved Gold are excluded.",
        ),
        "model_abstention_recall": _metric(
            true_model_abstentions,
            model_recall_denominator,
            eligible=model_recall_denominator,
            total=total,
            definition="Correct model_abstained_with_evidence outcomes divided by "
            "gold-unanswerable successful generation runs where the model was invoked with "
            "evidence. no_retrieval_hits and technical failures are excluded.",
        ),
        "model_abstention_f1": _metric(
            model_f1_numerator,
            model_f1_denominator if model_recall_denominator > 0 else 0,
            eligible=len(model_decisions),
            total=total,
            definition="Model-level abstention F1 computed as 2TP / (2TP + FP + FN), where "
            "model_abstained_with_evidence is the predicted positive. Only successful model "
            "decisions with evidence and resolved Gold answerability are eligible; F1 is "
            "not applicable when those decisions contain no gold-unanswerable runs.",
        ),
        "raw_json_validity": boolean_metric(
            "raw_json_valid",
            "Valid first-attempt JSON divided by runs retaining a first model output.",
        ),
        "raw_schema_validity": boolean_metric(
            "raw_schema_valid",
            "GeneratedAnswer-schema-valid first outputs divided by retained first outputs.",
        ),
        "repaired_json_validity": boolean_metric(
            "repaired_json_valid",
            "Valid repaired JSON divided by runs retaining a repaired output.",
        ),
        "repaired_schema_validity": boolean_metric(
            "repaired_schema_valid",
            "GeneratedAnswer-schema-valid repaired outputs divided by repaired outputs.",
        ),
        "citation_validity": boolean_metric(
            "citation_valid",
            "Answered runs whose non-empty citations resolve through evidence actually sent "
            "to the model, exactly match the upstream resolved citation sequence, and pass "
            "upstream validation.",
        ),
        "gold_evidence_citation_coverage": boolean_metric(
            "gold_evidence_covered",
            "Answered runs whose citations completely cover at least one sufficient Gold "
            "evidence path using the frozen span-to-chunk mapping.",
        ),
    }

    citation_checks = [check for record in records for check in record["citation_checks"]]
    metrics["per_citation_validity"] = _metric(
        sum(check["valid"] for check in citation_checks),
        len(citation_checks),
        eligible=len(citation_checks),
        total=len(citation_checks),
        definition="Citations resolving to a chunk and source in evidence sent to the model.",
    )

    confusion = Counter(
        {
            "correct_abstention": 0,
            "wrong_abstention": 0,
            "answered_when_unanswerable": 0,
            "answered_when_answerable": 0,
            "technical_failure": 0,
            "unresolved": 0,
        }
    )
    for record in records:
        if record["execution_mode"] != ExecutionMode.RETRIEVAL_AND_GENERATION.value:
            continue
        if record["gold_answerable"] is None:
            confusion["unresolved"] += 1
        elif record["status"] in {status.value for status in _TECHNICAL_STATUSES}:
            confusion["technical_failure"] += 1
        elif record["gold_answerable"] is False:
            key = (
                "correct_abstention"
                if record["status"] == RunStatus.ABSTAINED.value
                else "answered_when_unanswerable"
            )
            confusion[key] += 1
        else:
            key = (
                "wrong_abstention"
                if record["status"] == RunStatus.ABSTAINED.value
                else "answered_when_answerable"
            )
            confusion[key] += 1

    abstention_causes = (
        AbstentionCause.NO_RETRIEVAL_HITS.value,
        AbstentionCause.MODEL_ABSTAINED_WITH_EVIDENCE.value,
    )
    abstention_cause_counts = Counter({cause: 0 for cause in abstention_causes})
    abstention_confusion_by_cause = {
        cause: {
            "correct_abstention": 0,
            "wrong_abstention": 0,
            "unresolved": 0,
        }
        for cause in abstention_causes
    }
    for record in all_system_abstentions:
        cause = record["abstention_cause"]
        if cause not in abstention_confusion_by_cause:
            continue
        abstention_cause_counts[cause] += 1
        if record["abstention_correct"] is None:
            outcome = "unresolved"
        elif record["abstention_correct"] is True:
            outcome = "correct_abstention"
        else:
            outcome = "wrong_abstention"
        abstention_confusion_by_cause[cause][outcome] += 1

    answer_outcomes = Counter(
        {
            "correct": 0,
            "wrong": 0,
            "abstained": 0,
            "retrieval_failed": 0,
            "generation_failed": 0,
            "format_failed": 0,
        }
    )
    answer_outcomes.update(record["answer_outcome"] for record in records)

    metric_definitions = {
        name: str(metric.pop("definition")) for name, metric in metrics.items()
    }
    retrieval_only = bool(records) and all(
        record["execution_mode"] == ExecutionMode.RETRIEVAL_ONLY.value
        for record in records
    )
    if retrieval_only:
        metrics = {}
        answer_outcomes = Counter({"not_applicable": total})

    return {
        "total_records": total,
        "applicability": "not_applicable" if retrieval_only else "applicable",
        "metric_definitions": metric_definitions,
        "metrics": metrics,
        "answer_outcome_counts": dict(answer_outcomes),
        "abstention_confusion": dict(confusion),
        "abstention_cause_counts": dict(abstention_cause_counts),
        "abstention_confusion_by_cause": abstention_confusion_by_cause,
        "failure_label_counts": dict(
            sorted(
                Counter(
                    label for record in records for label in record["failure_labels"]
                ).items()
            )
        ),
        "execution_status_counts": dict(
            sorted(Counter(record["status"] for record in records).items())
        ),
        "operation_counts": {
            "runs_retried": sum(record["model_call_count"] > 1 for record in records),
            "retry_attempts": sum(
                max(record["model_call_count"] - 1, 0) for record in records
            ),
            "runs_repaired": sum(record["repair_used"] for record in records),
        },
        "unresolved_count": sum(
            record["gold_answerable"] is None for record in records
        ),
    }


class AnswerCitationScorer:
    """Offline scoring plug-in for M8-owned evaluation metrics."""

    name = "answer_citation"

    def __init__(
        self,
        mappings: GoldChunkMapping | Mapping[str, QuestionChunkMapping],
        *,
        expected_split: EvaluationSplit | str | None = None,
        dataset_version: str | None = None,
        expected_mode: RetrievalMode | str | None = None,
        expected_condition: str | None = None,
    ) -> None:
        self._mappings = mappings
        self._expected_split = (
            EvaluationSplit(expected_split) if expected_split is not None else None
        )
        self._dataset_version = dataset_version
        self._expected_mode = (
            RetrievalMode(expected_mode) if expected_mode is not None else None
        )
        self._expected_condition = expected_condition

    def score(
        self,
        gold_samples: Sequence[GoldSample],
        run_results: Sequence[EvaluationRunResult],
        *,
        mode: ScoringMode,
    ) -> Mapping[str, Any]:
        gold_by_id = {sample.question_id: sample for sample in gold_samples}
        if len(gold_by_id) != len(gold_samples):
            raise ValueError("duplicate question_id in Gold samples")

        run_ids = [result.question_id for result in run_results]
        duplicates = sorted(
            question_id for question_id, count in Counter(run_ids).items() if count > 1
        )
        if duplicates:
            raise ValueError(
                "answer/citation scoring requires one final run per question; duplicates: "
                + ", ".join(duplicates)
            )

        excluded_runs = {
            "total": 0,
            "missing_gold": 0,
            "split_mismatch": 0,
            "mode_mismatch": 0,
            "condition_mismatch": 0,
        }
        records = []
        for run in run_results:
            gold = gold_by_id.get(run.question_id)
            if gold is None:
                excluded_runs["total"] += 1
                excluded_runs["missing_gold"] += 1
                continue
            exclusion_reason = None
            if self._expected_split is not None and gold.split is not self._expected_split:
                exclusion_reason = "split_mismatch"
            elif (
                self._expected_mode is not None
                and run.retrieval is not None
                and run.retrieval.mode is not self._expected_mode
            ):
                exclusion_reason = "mode_mismatch"
            elif (
                self._expected_condition is not None
                and run.condition_id != self._expected_condition
            ):
                exclusion_reason = "condition_mismatch"
            if exclusion_reason is not None:
                if mode == "reportable":
                    raise ValueError(
                        f"reportable answer/citation scoring rejected "
                        f"{exclusion_reason} for {run.question_id!r}"
                    )
                excluded_runs["total"] += 1
                excluded_runs[exclusion_reason] += 1
                continue
            record = _score_pair(gold, run, self._mappings, self._expected_mode)
            record["gold_answerable"] = gold.answerable
            record["data_version"] = self._dataset_version or gold.gold_annotation_version
            records.append(record)

        if self._expected_split is not None:
            expected_ids = {
                sample.question_id
                for sample in gold_samples
                if sample.split is self._expected_split
            }
        elif run_ids:
            observed_splits = {
                gold_by_id[question_id].split
                for question_id in run_ids
                if question_id in gold_by_id
            }
            expected_ids = {
                sample.question_id
                for sample in gold_samples
                if sample.split in observed_splits
            }
        else:
            expected_ids = set(gold_by_id)
        missing_run_question_ids = sorted(expected_ids - set(run_ids))
        if mode == "reportable" and missing_run_question_ids:
            raise ValueError(
                "reportable answer/citation scoring is missing expected run results: "
                + ", ".join(missing_run_question_ids)
            )

        if sum(
            count for reason, count in excluded_runs.items() if reason != "total"
        ) != excluded_runs["total"]:
            raise RuntimeError("answer/citation exclusion reasons are not mutually exclusive")

        summary = _summarise(records)
        grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
        for record in records:
            key = (
                record["mode"],
                record["condition_id"],
                record["data_version"],
                record["split"],
                record["corpus_version"],
            )
            grouped.setdefault(key, []).append(record)

        groups = []
        for key in sorted(grouped):
            group_summary = _summarise(grouped[key])
            group_definitions = group_summary.pop("metric_definitions")
            if group_definitions != summary["metric_definitions"]:
                raise RuntimeError("metric definitions differ between scoring groups")
            groups.append(
                {
                    "mode": key[0],
                    "condition_id": key[1],
                    "data_version": key[2],
                    "split": key[3],
                    "corpus_version": key[4],
                    **group_summary,
                }
            )
        return {
            **summary,
            "excluded_runs": excluded_runs,
            "missing_run_count": len(missing_run_question_ids),
            "missing_run_question_ids": missing_run_question_ids,
            "groups": groups,
            "records": records,
        }
