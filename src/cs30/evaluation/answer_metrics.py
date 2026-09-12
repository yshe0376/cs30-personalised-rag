"""M8 answer, abstention, format, and citation scoring extension."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from cs30.contracts import GeneratedAnswer

from .mapping import GoldChunkMapping, QuestionChunkMapping
from .models import EvaluationRunResult, EvaluationSplit, ExecutionMode, GoldSample, RunStatus

_TECHNICAL_STATUSES = {
    RunStatus.RETRIEVAL_ERROR,
    RunStatus.GENERATION_ERROR,
    RunStatus.PARSE_ERROR,
}


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


def _raw_answer_is_missing_required_citation(text: str | None) -> bool:
    """Expose a zero-citation answer even when contract validation rejects it."""

    if text is None:
        return False
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("abstained") is False
        and payload.get("citations") == []
    )


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
    if run.final_answer is None:
        return []

    by_identifier = {}
    if run.evidence_sent_to_model is not None:
        for item in run.evidence_sent_to_model.evidence_items:
            by_identifier[item.evidence_id] = item
            by_identifier[item.chunk_id] = item

    checks = []
    for citation_id in run.final_answer.citations:
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
    for evidence_set in gold.gold_core_evidence_sets:
        path_complete = True
        for span in evidence_set:
            span_mapping = mapped_spans.get(span.span_id)
            if span_mapping is None:
                return None, True
            span_covered = any(
                set(chunk_set).issubset(cited_chunk_ids)
                for chunk_set in span_mapping.acceptable_chunk_sets
            )
            if not span_covered:
                path_complete = False
                break
        if path_complete:
            return True, False
    return False, False


def _answer_outcome(gold: GoldSample, run: EvaluationRunResult) -> str:
    if run.execution_mode is ExecutionMode.RETRIEVAL_ONLY:
        return "not_applicable"
    if run.status in {RunStatus.RETRIEVAL_ERROR, RunStatus.GENERATION_ERROR}:
        return "call_failed"
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
) -> dict[str, Any]:
    generation_run = run.execution_mode is ExecutionMode.RETRIEVAL_AND_GENERATION
    successful = run.status in {RunStatus.ANSWERED, RunStatus.ABSTAINED}
    answer_correct = None
    if generation_run and gold.gold_answer is not None:
        answer_correct = bool(
            run.status is RunStatus.ANSWERED
            and run.final_answer is not None
            and run.final_answer.final_choice == gold.gold_answer
        )

    parsed_answer_correct = None
    if successful and gold.gold_answer is not None:
        parsed_answer_correct = bool(
            run.status is RunStatus.ANSWERED
            and run.final_answer is not None
            and run.final_answer.final_choice == gold.gold_answer
        )

    answered_choice_correct = None
    if (
        run.status is RunStatus.ANSWERED
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
    missing_required_citation = _raw_answer_is_missing_required_citation(
        run.raw_model_output
    )

    citation_checks = _citation_checks(run)
    citation_valid = None
    if run.status is RunStatus.ANSWERED:
        citation_valid = bool(
            citation_checks
            and all(check["valid"] for check in citation_checks)
            and run.citation_validation is not None
            and run.citation_validation.citation_status == "passed"
        )
    elif missing_required_citation:
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
    if run.status in {RunStatus.RETRIEVAL_ERROR, RunStatus.GENERATION_ERROR}:
        labels.add("call_failure")
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
        "mode": run.retrieval.mode.value if run.retrieval is not None else "unknown",
        "status": run.status.value,
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

    predicted_abstentions = [
        record
        for record in records
        if record["execution_mode"] == ExecutionMode.RETRIEVAL_AND_GENERATION.value
        and record["status"] == RunStatus.ABSTAINED.value
        and record["abstention_correct"] is not None
    ]
    gold_unanswerable = [
        record
        for record in records
        if record["execution_mode"] == ExecutionMode.RETRIEVAL_AND_GENERATION.value
        and record["abstention_correct"] is not None
        and record["gold_answerable"] is False
    ]
    true_abstentions = sum(
        record["abstention_correct"] is True for record in predicted_abstentions
    )
    precision_denominator = len(predicted_abstentions)
    recall_denominator = len(gold_unanswerable)
    precision = None if precision_denominator == 0 else true_abstentions / precision_denominator
    recall = None if recall_denominator == 0 else true_abstentions / recall_denominator
    if precision is None or recall is None:
        f1_numerator, f1_denominator = 0.0, 0.0
    elif precision + recall == 0:
        f1_numerator, f1_denominator = 0.0, 1.0
    else:
        f1_numerator, f1_denominator = 2 * precision * recall, precision + recall

    metrics = {
        "answer_choice_accuracy_all": boolean_metric(
            "answer_correct",
            "Correct choices divided by generation runs with a gold choice; technical "
            "failures and abstentions count as incorrect.",
        ),
        "answer_choice_accuracy_parsed": boolean_metric(
            "parsed_answer_correct",
            "Correct choices divided by successfully parsed answer or abstention outcomes.",
        ),
        "answer_choice_accuracy_answered": boolean_metric(
            "answered_choice_correct",
            "Correct choices divided by non-abstained answers with a gold choice.",
        ),
        "abstention_accuracy": boolean_metric(
            "abstention_correct",
            "Correct abstain/non-abstain decisions divided by generation runs with resolved "
            "answerability; technical failures count as incorrect.",
        ),
        "abstention_precision": _metric(
            true_abstentions,
            precision_denominator,
            eligible=precision_denominator,
            total=total,
            definition="Correct abstentions divided by all predicted abstentions.",
        ),
        "abstention_recall": _metric(
            true_abstentions,
            recall_denominator,
            eligible=recall_denominator,
            total=total,
            definition="Correct abstentions divided by gold-unanswerable generation runs.",
        ),
        "abstention_f1": _metric(
            f1_numerator,
            f1_denominator,
            eligible=min(precision_denominator, recall_denominator),
            total=total,
            definition="Harmonic mean of abstention precision and recall.",
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
            "to the model and pass upstream validation.",
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

    return {
        "total_records": total,
        "metrics": metrics,
        "answer_outcome_counts": dict(
            sorted(Counter(record["answer_outcome"] for record in records).items())
        ),
        "abstention_confusion": dict(confusion),
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
    ) -> None:
        self._mappings = mappings
        self._expected_split = (
            EvaluationSplit(expected_split) if expected_split is not None else None
        )
        self._dataset_version = dataset_version

    def score(
        self,
        gold_samples: Sequence[GoldSample],
        run_results: Sequence[EvaluationRunResult],
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

        records = []
        for run in run_results:
            gold = gold_by_id.get(run.question_id)
            if gold is None:
                raise ValueError(f"run result has no matching Gold sample: {run.question_id}")
            record = _score_pair(gold, run, self._mappings)
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
            observed_splits = {gold_by_id[question_id].split for question_id in run_ids}
            expected_ids = {
                sample.question_id
                for sample in gold_samples
                if sample.split in observed_splits
            }
        else:
            expected_ids = set(gold_by_id)
        missing_run_question_ids = sorted(expected_ids - set(run_ids))

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
            groups.append(
                {
                    "mode": key[0],
                    "condition_id": key[1],
                    "data_version": key[2],
                    "split": key[3],
                    "corpus_version": key[4],
                    **_summarise(grouped[key]),
                }
            )
        return {
            **summary,
            "missing_run_count": len(missing_run_question_ids),
            "missing_run_question_ids": missing_run_question_ids,
            "groups": groups,
            "records": records,
        }
