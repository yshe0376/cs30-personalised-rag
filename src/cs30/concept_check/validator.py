"""Fail-closed automatic publication checks using M3/M4 supplied evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from cs30.evaluation.models import AnnotationStatus, EvaluationSplit
from cs30.v2.contracts import (
    ConceptCheckQuestion,
    ConceptCheckQuestionBinding,
    ConceptCheckQuestionRelease,
    EvidenceSpanBinding,
    GoldQuestion,
    QuestionSourceType,
    SpanResolutionStatus,
)


@dataclass(frozen=True)
class LeakageTrace:
    checker_version: str
    similarity_threshold: float
    matched_gold_ids: tuple[str, ...]
    evidence_overlap_gold_ids: tuple[str, ...]
    similarity_outcome: Literal["clear", "suspected", "cleared_by_m3"]


class LeakageValidationError(ValueError):
    """A blocked candidate with the structured leakage result retained for M3."""

    def __init__(self, message: str, trace: LeakageTrace) -> None:
        super().__init__(message)
        self.trace = trace


class PublicationValidator:
    """Use frozen Gold and external M3/M4 checkers; never auto-publish a draft."""

    def __init__(
        self,
        *,
        corpus_version: str,
        corpus_hash: str,
        gold_questions: Sequence[GoldQuestion],
        gold_bindings: Mapping[str, EvidenceSpanBinding],
        existing_practice_ids: Sequence[str],
        checker_version: str,
        similarity_threshold: float,
        similarity_matches: Callable[
            [ConceptCheckQuestion, Sequence[GoldQuestion], float], Sequence[str]
        ],
        cross_book_overlap: Callable[[EvidenceSpanBinding, EvidenceSpanBinding], bool],
        similarity_clearances: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        if not gold_questions:
            raise ValueError("frozen Gold is required for Concept Check validation")
        if not checker_version.strip() or not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("a versioned similarity checker and threshold are required")
        self.corpus_version = corpus_version
        self.corpus_hash = corpus_hash
        self.gold_questions = tuple(gold_questions)
        self.gold_bindings = dict(gold_bindings)
        self.existing_practice_ids = frozenset(existing_practice_ids)
        self.checker_version = checker_version
        self.similarity_threshold = similarity_threshold
        self.similarity_matches = similarity_matches
        self.cross_book_overlap = cross_book_overlap
        # M3 supplies decisions keyed by its review record ID. A bare ID is not a clearance.
        self.similarity_clearances = {
            review_id: frozenset(ids) for review_id, ids in (similarity_clearances or {}).items()
        }
        if any(
            gold.annotation_status is not AnnotationStatus.REVIEWED
            or gold.split
            not in {EvaluationSplit.DEV, EvaluationSplit.TEST, EvaluationSplit.HOLDOUT}
            for gold in self.gold_questions
        ):
            raise ValueError("Gold must be reviewed and frozen")
        self.evaluation_gold = tuple(
            gold
            for gold in self.gold_questions
            if gold.split in {EvaluationSplit.DEV, EvaluationSplit.TEST}
        )
        for gold in self.evaluation_gold:
            evidence = [item for group in gold.gold_core_evidence_sets for item in group]
            evidence.extend(gold.partial_evidence)
            for item in evidence:
                binding = self.gold_bindings.get(item.span.span_id)
                if (
                    binding is None
                    or binding.resolution_status is not SpanResolutionStatus.RESOLVED
                ):
                    raise ValueError("every Gold span needs a resolved M4 binding")
                if (
                    binding.span_id != item.span.span_id
                    or binding.textbook_id != item.span.textbook_id
                ):
                    raise ValueError("Gold binding identity does not match its span")
                if (binding.corpus_version, binding.corpus_hash) != (corpus_version, corpus_hash):
                    raise ValueError("Gold binding does not match the current corpus")

    def check(
        self,
        question: ConceptCheckQuestion,
        binding: ConceptCheckQuestionBinding,
    ) -> LeakageTrace:
        if question.question_id in self.existing_practice_ids:
            raise ValueError("duplicate practice question_id")
        if (binding.corpus_version, binding.corpus_hash) != (
            self.corpus_version,
            self.corpus_hash,
        ) or binding.question_id != question.question_id:
            raise ValueError("practice binding does not match the current corpus or question")
        anchors = {anchor.span_id: anchor for anchor in question.evidence_anchors}
        if {item.span_id for item in binding.bindings} != set(anchors):
            raise ValueError("every practice anchor needs exactly one binding")
        if any(
            item.resolution_status is not SpanResolutionStatus.RESOLVED for item in binding.bindings
        ):
            raise ValueError("practice anchors must all resolve through M4")
        if any(item.textbook_id != anchors[item.span_id].textbook_id for item in binding.bindings):
            raise ValueError("practice binding textbook_id mismatch")
        source_id = question.source.source_question_id if question.source else None
        gold_source_ids = {
            gold.source.source_question_id
            for gold in self.gold_questions
            if gold.source is not None
        }
        if question.source_type is QuestionSourceType.SCIQ_ALIGNED and source_id in gold_source_ids:
            raise ValueError("SciQ source question already belongs to frozen Gold")

        overlaps: set[str] = set()
        for gold in self.evaluation_gold:
            evidence = [item for group in gold.gold_core_evidence_sets for item in group]
            evidence.extend(gold.partial_evidence)
            for item in evidence:
                gold_span = item.span
                gold_binding = self.gold_bindings[gold_span.span_id]
                for practice_binding in binding.bindings:
                    practice_span = anchors[practice_binding.span_id]
                    same_text = practice_span.text_hash == gold_span.text_hash
                    same_bound_overlap = (
                        practice_binding.textbook_id == gold_binding.textbook_id
                        and practice_binding.document_id == gold_binding.document_id
                        and practice_binding.char_start < gold_binding.char_end
                        and gold_binding.char_start < practice_binding.char_end
                    )
                    duplicate_overlap = self.cross_book_overlap(practice_binding, gold_binding)
                    if same_text or same_bound_overlap or duplicate_overlap:
                        overlaps.add(gold.question_id)
        matched = (
            tuple(
                sorted(
                    set(
                        self.similarity_matches(
                            question, self.evaluation_gold, self.similarity_threshold
                        )
                    )
                )
            )
            if self.evaluation_gold
            else ()
        )
        known_gold_ids = {gold.question_id for gold in self.evaluation_gold}
        if not set(matched).issubset(known_gold_ids):
            raise ValueError("similarity checker returned an unknown Gold question ID")
        cleared_ids = self.similarity_clearances.get(question.review_record_id or "", frozenset())
        cleared = bool(matched) and set(matched).issubset(cleared_ids)
        trace = LeakageTrace(
            checker_version=self.checker_version,
            similarity_threshold=self.similarity_threshold,
            matched_gold_ids=matched,
            evidence_overlap_gold_ids=tuple(sorted(overlaps)),
            similarity_outcome="cleared_by_m3" if cleared else "suspected" if matched else "clear",
        )
        if overlaps:
            raise LeakageValidationError(
                f"practice evidence overlaps Gold: {trace.evidence_overlap_gold_ids}", trace
            )
        if matched and not cleared:
            raise LeakageValidationError(f"gold_leakage_suspected: {trace.matched_gold_ids}", trace)
        return trace

    def validate(self, release: ConceptCheckQuestionRelease) -> LeakageTrace:
        return self.check(release.question, release.binding)
