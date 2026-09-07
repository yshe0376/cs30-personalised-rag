"""Failure-aware, deterministic M8 metric calculations."""

from __future__ import annotations

from collections import Counter

from .models import (
    Answerability,
    EvaluationRecord,
    EvaluationReport,
    ExecutionStatus,
    MetricResult,
    RecordScore,
)

_PREDICTION_STATUSES = {ExecutionStatus.COMPLETED, ExecutionStatus.CITATION_FAILURE}


def _metric(
    numerator: int,
    denominator: int,
    *,
    total: int,
    definition: str,
) -> MetricResult:
    return MetricResult(
        numerator=numerator,
        denominator=denominator,
        value=None if denominator == 0 else numerator / denominator,
        excluded=total - denominator,
        definition=definition,
    )


def _citation_valid(record: EvaluationRecord) -> bool | None:
    if record.execution_status not in _PREDICTION_STATUSES or record.abstained is not False:
        return None
    allowed = set(record.retrieved_chunk_ids)
    return bool(record.citation_ids) and set(record.citation_ids) <= allowed and (
        record.citation_status == "passed"
    )


def _score_record(record: EvaluationRecord) -> RecordScore:
    has_prediction = record.execution_status in _PREDICTION_STATUSES
    answer_correct: bool | None = None
    if record.gold_choice is not None:
        answer_correct = bool(
            has_prediction
            and record.abstained is False
            and record.predicted_choice == record.gold_choice
        )

    resolved = record.answerability is not Answerability.UNRESOLVED
    abstention_correct: bool | None = None
    if resolved:
        expected = record.answerability is Answerability.VERIFIED_UNANSWERABLE
        abstention_correct = bool(has_prediction and record.abstained is expected)

    citation_valid = _citation_valid(record)
    gold_citation_hit: bool | None = None
    if citation_valid is not None and record.gold_evidence_ids:
        gold_citation_hit = bool(set(record.citation_ids) & set(record.gold_evidence_ids))

    if record.execution_status not in _PREDICTION_STATUSES:
        outcome = "technical_failure"
    elif record.gold_choice is None:
        outcome = "missing_gold"
    elif record.abstained:
        outcome = "abstained"
    elif answer_correct:
        outcome = "correct"
    else:
        outcome = "incorrect"

    return RecordScore(
        question_id=record.question_id,
        answer_outcome=outcome,
        answer_correct=answer_correct,
        abstention_correct=abstention_correct,
        citation_valid=citation_valid,
        gold_citation_hit=gold_citation_hit,
        execution_status=record.execution_status,
    )


def evaluate_records(records: list[EvaluationRecord]) -> EvaluationReport:
    """Score saved records without retrieval, generation, or another model call."""

    scores = [_score_record(record) for record in records]
    total = len(records)

    answer_eligible = [score for score in scores if score.answer_correct is not None]
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
    gold_citation_eligible = [score for score in scores if score.gold_citation_hit is not None]
    raw_json_eligible = [record for record in records if record.raw_json_valid is not None]
    raw_schema_eligible = [record for record in records if record.raw_schema_valid is not None]

    gold_unanswerable = [
        (score, record)
        for score, record in zip(scores, records, strict=True)
        if record.answerability is Answerability.VERIFIED_UNANSWERABLE
    ]
    predicted_abstentions = [
        (score, record)
        for score, record in zip(scores, records, strict=True)
        if record.answerability is not Answerability.UNRESOLVED
        and record.execution_status in _PREDICTION_STATUSES
        and record.abstained is True
    ]
    true_abstentions = sum(
        record.answerability is Answerability.VERIFIED_UNANSWERABLE
        for _, record in predicted_abstentions
    )
    abstention_precision_denominator = len(predicted_abstentions)
    abstention_recall_denominator = len(gold_unanswerable)
    precision = (
        None
        if abstention_precision_denominator == 0
        else true_abstentions / abstention_precision_denominator
    )
    recall = (
        None
        if abstention_recall_denominator == 0
        else true_abstentions / abstention_recall_denominator
    )
    if precision is None or recall is None:
        f1_numerator = 0.0
        f1_denominator = 0.0
        f1_value = None
    elif precision + recall == 0:
        f1_numerator = 0.0
        f1_denominator = 1.0
        f1_value = 0.0
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
                "Correct non-abstained choices divided by all records with a gold choice; "
                "technical failures and abstentions count as incorrect."
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
                "Correct abstain/non-abstain decisions divided by records with resolved "
                "answerability; technical failures remain incorrect."
            ),
        ),
        "abstention_precision": MetricResult(
            numerator=true_abstentions,
            denominator=abstention_precision_denominator,
            value=precision,
            excluded=total - len(abstention_eligible),
            definition="Correct abstentions divided by all predicted abstentions.",
        ),
        "abstention_recall": MetricResult(
            numerator=true_abstentions,
            denominator=abstention_recall_denominator,
            value=recall,
            excluded=total - len(abstention_eligible),
            definition=(
                "Correct abstentions divided by all verified-unanswerable records; "
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
            definition="Valid raw model JSON divided by records that retained raw output.",
        ),
        "raw_schema_validity": _metric(
            sum(record.raw_schema_valid is True for record in raw_schema_eligible),
            len(raw_schema_eligible),
            total=total,
            definition=(
                "Raw model outputs matching the fixed answer schema divided by retained "
                "raw outputs that parsed as JSON or failed parsing."
            ),
        ),
        "citation_validity": _metric(
            sum(score.citation_valid is True for score in citation_eligible),
            len(citation_eligible),
            total=total,
            definition=(
                "Non-empty, resolved citation sets contained in the run's retrieved chunks "
                "and marked passed, divided by completed non-abstained answers."
            ),
        ),
        "gold_citation_hit_rate": _metric(
            sum(score.gold_citation_hit is True for score in gold_citation_eligible),
            len(gold_citation_eligible),
            total=total,
            definition=(
                "Answers citing at least one gold evidence ID divided by completed "
                "non-abstained answers that have gold evidence IDs."
            ),
        ),
    }

    counts = Counter(record.execution_status for record in records)
    failure_counts = {status: counts[status] for status in ExecutionStatus}
    return EvaluationReport(
        total_records=total,
        metrics=metrics,
        failure_counts=failure_counts,
        records=scores,
    )
