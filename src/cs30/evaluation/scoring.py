"""Failure-aware, deterministic M8 metric calculations."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import (
    Answerability,
    CitationCheck,
    EvaluationGroup,
    EvaluationRecord,
    EvaluationReport,
    ExecutionStatus,
    FailureLabel,
    MetricResult,
    RecordScore,
)

_PREDICTION_STATUSES = {ExecutionStatus.COMPLETED, ExecutionStatus.CITATION_FAILURE}
_CONFUSION_KEYS = (
    "correct_abstention",
    "wrong_abstention",
    "answered_when_unanswerable",
    "answered_when_answerable",
    "technical_failure",
    "unresolved",
)


def _metric(numerator: int, denominator: int, *, total: int, definition: str) -> MetricResult:
    return MetricResult(
        numerator=numerator,
        denominator=denominator,
        value=None if denominator == 0 else numerator / denominator,
        excluded=total - denominator,
        definition=definition,
    )


def _citation_checks(record: EvaluationRecord) -> list[CitationCheck]:
    by_identifier = {}
    for item in record.sent_evidence:
        by_identifier[item.evidence_id] = item
        by_identifier[item.chunk_id] = item

    checks: list[CitationCheck] = []
    for citation_id in record.citation_ids:
        evidence = by_identifier.get(citation_id)
        belongs = evidence is not None
        resolves_to_chunk = belongs and bool(evidence.chunk_id)
        resolves_to_source = belongs and bool(evidence.source)
        checks.append(
            CitationCheck(
                citation_id=citation_id,
                chunk_id=evidence.chunk_id if evidence else None,
                source=evidence.source if evidence else None,
                source_locator=evidence.source_locator if evidence else None,
                belongs_to_sent_evidence=belongs,
                resolves_to_chunk=resolves_to_chunk,
                resolves_to_source=resolves_to_source,
                valid=belongs and resolves_to_chunk and resolves_to_source,
            )
        )
    return checks


def _answer_outcome(record: EvaluationRecord, answer_correct: bool | None) -> str:
    if record.execution_status is ExecutionStatus.PARSE_FAILURE:
        return "format_failed"
    if record.execution_status in {
        ExecutionStatus.GENERATION_CALL_FAILURE,
        ExecutionStatus.TECHNICAL_FAILURE,
        ExecutionStatus.RETRIEVAL_FAILURE,
    }:
        return "call_failed"
    if record.abstained is True:
        return "abstained"
    if record.gold_choice is None:
        return "missing_gold"
    return "correct" if answer_correct else "wrong"


def _failure_labels(
    record: EvaluationRecord,
    *,
    answer_correct: bool | None,
    citation_valid: bool | None,
) -> list[FailureLabel]:
    labels: set[FailureLabel] = set()
    if record.gold_choice is not None and answer_correct is False:
        labels.add(FailureLabel.GOLD_MISSED)
    if (
        record.gold_choice is not None
        and record.abstained is False
        and record.predicted_choice is not None
        and record.predicted_choice != record.gold_choice
    ):
        labels.add(FailureLabel.WRONG_OPTION)
    if record.answerability is Answerability.ANSWERABLE and record.abstained is True:
        labels.add(FailureLabel.WRONG_ABSTENTION)
    if record.answerability is Answerability.VERIFIED_UNANSWERABLE and record.abstained is False:
        labels.add(FailureLabel.ANSWERED_WHEN_UNANSWERABLE)
    if (
        record.execution_status is ExecutionStatus.PARSE_FAILURE
        or record.raw_json_valid is False
        or record.raw_schema_valid is False
        or record.repaired_json_valid is False
        or record.repaired_schema_valid is False
    ):
        labels.add(FailureLabel.INVALID_OUTPUT)
    if citation_valid is False or record.execution_status is ExecutionStatus.CITATION_FAILURE:
        labels.add(FailureLabel.INVALID_CITATION)
    if record.execution_status in {
        ExecutionStatus.GENERATION_CALL_FAILURE,
        ExecutionStatus.TECHNICAL_FAILURE,
    }:
        labels.add(FailureLabel.CALL_FAILURE)
    return sorted(labels, key=lambda item: item.value)


def _score_record(record: EvaluationRecord) -> RecordScore:
    has_prediction = record.execution_status in _PREDICTION_STATUSES
    answer_correct: bool | None = None
    if record.gold_choice is not None:
        answer_correct = bool(
            has_prediction
            and record.abstained is False
            and record.predicted_choice == record.gold_choice
        )

    abstention_correct: bool | None = None
    if record.answerability is not Answerability.UNRESOLVED:
        expected = record.answerability is Answerability.VERIFIED_UNANSWERABLE
        abstention_correct = bool(has_prediction and record.abstained is expected)

    citation_checks = _citation_checks(record)
    citation_valid: bool | None = None
    if has_prediction and record.abstained is False:
        citation_valid = (
            bool(citation_checks)
            and all(check.valid for check in citation_checks)
            and record.citation_status == "passed"
        )

    gold_citation_hit: bool | None = None
    if citation_valid is not None and record.gold_evidence_ids:
        cited_chunks = {check.chunk_id for check in citation_checks if check.chunk_id is not None}
        gold_citation_hit = bool(cited_chunks & set(record.gold_evidence_ids))

    return RecordScore(
        question_id=record.question_id,
        answer_outcome=_answer_outcome(record, answer_correct),
        answer_correct=answer_correct,
        abstention_correct=abstention_correct,
        citation_valid=citation_valid,
        gold_citation_hit=gold_citation_hit,
        citation_checks=citation_checks,
        failure_labels=_failure_labels(
            record, answer_correct=answer_correct, citation_valid=citation_valid
        ),
        execution_status=record.execution_status,
    )


def _abstention_confusion(
    records: list[EvaluationRecord], scores: list[RecordScore]
) -> dict[str, int]:
    del scores
    counts = Counter({key: 0 for key in _CONFUSION_KEYS})
    for record in records:
        if record.answerability is Answerability.UNRESOLVED:
            counts["unresolved"] += 1
        elif record.execution_status not in _PREDICTION_STATUSES or record.abstained is None:
            counts["technical_failure"] += 1
        elif record.answerability is Answerability.VERIFIED_UNANSWERABLE:
            key = "correct_abstention" if record.abstained else "answered_when_unanswerable"
            counts[key] += 1
        else:
            key = "wrong_abstention" if record.abstained else "answered_when_answerable"
            counts[key] += 1
    return dict(counts)


def _summarise(records: list[EvaluationRecord], scores: list[RecordScore]) -> dict[str, Any]:
    total = len(records)
    answer_eligible = [score for score in scores if score.answer_correct is not None]
    parsed = [
        score
        for score, record in zip(scores, records, strict=True)
        if score.answer_correct is not None and record.execution_status in _PREDICTION_STATUSES
    ]
    answered = [
        score
        for score, record in zip(scores, records, strict=True)
        if score.answer_correct is not None
        and record.execution_status in _PREDICTION_STATUSES
        and record.abstained is False
        and record.predicted_choice is not None
    ]
    abstention_eligible = [score for score in scores if score.abstention_correct is not None]
    citation_eligible = [score for score in scores if score.citation_valid is not None]
    citation_checks = [check for score in scores for check in score.citation_checks]
    gold_citation_eligible = [score for score in scores if score.gold_citation_hit is not None]
    raw_json_eligible = [record for record in records if record.raw_json_valid is not None]
    raw_schema_eligible = [record for record in records if record.raw_schema_valid is not None]
    repaired_json_eligible = [
        record for record in records if record.repaired_json_valid is not None
    ]
    repaired_schema_eligible = [
        record for record in records if record.repaired_schema_valid is not None
    ]

    gold_unanswerable = [
        record for record in records if record.answerability is Answerability.VERIFIED_UNANSWERABLE
    ]
    predicted_abstentions = [
        record
        for record in records
        if record.answerability is not Answerability.UNRESOLVED
        and record.execution_status in _PREDICTION_STATUSES
        and record.abstained is True
    ]
    true_abstentions = sum(
        record.answerability is Answerability.VERIFIED_UNANSWERABLE
        for record in predicted_abstentions
    )
    precision_denominator = len(predicted_abstentions)
    recall_denominator = len(gold_unanswerable)
    precision = None if precision_denominator == 0 else true_abstentions / precision_denominator
    recall = None if recall_denominator == 0 else true_abstentions / recall_denominator
    if precision is None or recall is None:
        f1_numerator, f1_denominator, f1_value = 0.0, 0.0, None
    elif precision + recall == 0:
        f1_numerator, f1_denominator, f1_value = 0.0, 1.0, 0.0
    else:
        f1_numerator = 2 * precision * recall
        f1_denominator = precision + recall
        f1_value = f1_numerator / f1_denominator

    metrics = {
        "answer_choice_accuracy_all": _metric(
            sum(score.answer_correct is True for score in answer_eligible),
            len(answer_eligible),
            total=total,
            definition=(
                "Correct choices divided by all records with a gold choice; failures and "
                "abstentions count as incorrect."
            ),
        ),
        "answer_choice_accuracy_parsed": _metric(
            sum(score.answer_correct is True for score in parsed),
            len(parsed),
            total=total,
            definition=(
                "Correct choices divided by records with gold and a parsed prediction; "
                "abstentions count as incorrect."
            ),
        ),
        "answer_choice_accuracy_answered": _metric(
            sum(score.answer_correct is True for score in answered),
            len(answered),
            total=total,
            definition="Correct choices divided by non-abstained answers with a gold choice.",
        ),
        "abstention_accuracy": _metric(
            sum(score.abstention_correct is True for score in abstention_eligible),
            len(abstention_eligible),
            total=total,
            definition=(
                "Correct abstain/non-abstain decisions divided by resolved records; "
                "technical failures remain incorrect."
            ),
        ),
        "abstention_precision": MetricResult(
            numerator=true_abstentions,
            denominator=precision_denominator,
            value=precision,
            excluded=total - len(abstention_eligible),
            definition="Correct abstentions divided by all predicted abstentions.",
        ),
        "abstention_recall": MetricResult(
            numerator=true_abstentions,
            denominator=recall_denominator,
            value=recall,
            excluded=total - len(abstention_eligible),
            definition=(
                "Correct abstentions divided by verified-unanswerable records; "
                "technical failures count as misses."
            ),
        ),
        "abstention_f1": MetricResult(
            numerator=f1_numerator,
            denominator=f1_denominator,
            value=f1_value,
            excluded=total - len(abstention_eligible),
            definition="Harmonic mean of abstention precision and recall.",
        ),
        "raw_json_validity": _metric(
            sum(record.raw_json_valid is True for record in raw_json_eligible),
            len(raw_json_eligible),
            total=total,
            definition="Valid first-attempt JSON divided by records retaining first output.",
        ),
        "raw_schema_validity": _metric(
            sum(record.raw_schema_valid is True for record in raw_schema_eligible),
            len(raw_schema_eligible),
            total=total,
            definition="Schema-valid first outputs divided by retained first outputs.",
        ),
        "repaired_json_validity": _metric(
            sum(record.repaired_json_valid is True for record in repaired_json_eligible),
            len(repaired_json_eligible),
            total=total,
            definition="Valid repaired JSON divided by records retaining repaired output.",
        ),
        "repaired_schema_validity": _metric(
            sum(record.repaired_schema_valid is True for record in repaired_schema_eligible),
            len(repaired_schema_eligible),
            total=total,
            definition="Schema-valid repaired outputs divided by retained repaired outputs.",
        ),
        "citation_validity": _metric(
            sum(score.citation_valid is True for score in citation_eligible),
            len(citation_eligible),
            total=total,
            definition=(
                "Answers whose non-empty citation set resolves through sent evidence to a "
                "source, divided by completed non-abstained answers."
            ),
        ),
        "per_citation_validity": _metric(
            sum(check.valid for check in citation_checks),
            len(citation_checks),
            total=len(citation_checks),
            definition=(
                "Citations resolving through sent evidence to a chunk and source, divided by "
                "all emitted citations."
            ),
        ),
        "gold_citation_hit_rate": _metric(
            sum(score.gold_citation_hit is True for score in gold_citation_eligible),
            len(gold_citation_eligible),
            total=total,
            definition=(
                "Answers citing a gold evidence chunk divided by eligible non-abstained "
                "answers with gold evidence."
            ),
        ),
    }
    execution_counts = Counter(record.execution_status for record in records)
    label_counts = Counter(label for score in scores for label in score.failure_labels)
    outcome_counts = Counter(score.answer_outcome for score in scores)
    return {
        "metrics": metrics,
        "execution_status_counts": {status: execution_counts[status] for status in ExecutionStatus},
        "failure_label_counts": {label: label_counts[label] for label in FailureLabel},
        "answer_outcome_counts": dict(sorted(outcome_counts.items())),
        "abstention_confusion": _abstention_confusion(records, scores),
        "operation_counts": {
            "runs_retried": sum(record.retry_count > 0 for record in records),
            "retry_attempts": sum(record.retry_count for record in records),
            "runs_repaired": sum(record.repair_count > 0 for record in records),
            "repair_attempts": sum(record.repair_count for record in records),
        },
    }


def _group_value(value: str | None) -> str:
    return value or "unknown"


def evaluate_records(records: list[EvaluationRecord]) -> EvaluationReport:
    """Score saved records without retrieval, generation, or another model call."""

    scores = [_score_record(record) for record in records]
    summary = _summarise(records, scores)
    grouped: dict[tuple[str, str, str, str, str], list[tuple[EvaluationRecord, RecordScore]]] = {}
    for record, score in zip(records, scores, strict=True):
        key = (
            _group_value(record.mode),
            _group_value(record.condition_id),
            _group_value(record.dataset_version),
            _group_value(record.split),
            _group_value(record.corpus_version),
        )
        grouped.setdefault(key, []).append((record, score))

    groups = []
    for key in sorted(grouped):
        pairs = grouped[key]
        group_records = [pair[0] for pair in pairs]
        group_scores = [pair[1] for pair in pairs]
        group_summary = _summarise(group_records, group_scores)
        groups.append(
            EvaluationGroup(
                mode=key[0],
                condition_id=key[1],
                dataset_version=key[2],
                split=key[3],
                corpus_version=key[4],
                total_records=len(group_records),
                metrics=group_summary["metrics"],
                execution_status_counts=group_summary["execution_status_counts"],
                failure_label_counts=group_summary["failure_label_counts"],
                answer_outcome_counts=group_summary["answer_outcome_counts"],
                abstention_confusion=group_summary["abstention_confusion"],
                operation_counts=group_summary["operation_counts"],
            )
        )

    return EvaluationReport(
        total_records=len(records),
        metrics=summary["metrics"],
        failure_counts=summary["execution_status_counts"],
        failure_label_counts=summary["failure_label_counts"],
        answer_outcome_counts=summary["answer_outcome_counts"],
        abstention_confusion=summary["abstention_confusion"],
        operation_counts=summary["operation_counts"],
        groups=groups,
        records=scores,
    )
