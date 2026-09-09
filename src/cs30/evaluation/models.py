"""Frozen W5 evaluation sample and per-question run-result contracts."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from cs30.contracts import (
    EvidenceBundle,
    GeneratedAnswer,
    Identifier,
    NonEmptyText,
    RetrievalResult,
    SpanText,
    ValidatedAnswer,
)
from cs30.contracts.models import ChoiceLabel, ContractModel


class PersonalisationEligibility(StrEnum):
    FULL = "full"
    ENDPOINT_ONLY = "endpoint_only"
    NONE = "none"
    PENDING = "pending"


class EvaluationSplit(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROPOSED = "proposed"


class AnnotationStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    DISPUTED = "disputed"
    UNRESOLVED = "unresolved"


class GoldEvidenceSpan(ContractModel):
    """One auditable half-open span in canonical ``document.text``."""

    span_id: Identifier
    document_id: Identifier
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    verbatim_text: SpanText

    @model_validator(mode="after")
    def validate_span_shape(self) -> "GoldEvidenceSpan":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if len(self.verbatim_text) != self.char_end - self.char_start:
            raise ValueError("verbatim_text length must match the half-open character span")
        return self


class GoldSample(ContractModel):
    """One M3 gold item consumed unchanged by the M1 and M8 evaluators.

    The outer ``gold_core_evidence_sets`` list is OR. Every span in one inner
    list is AND. ``partial_evidence`` is diagnostic only and never contributes
    to a complete Gold hit.
    """

    schema_version: Literal["0.1"] = "0.1"
    question_id: Identifier
    question: NonEmptyText
    options: dict[ChoiceLabel, NonEmptyText]
    gold_answer: ChoiceLabel | None
    answerable: bool | None
    gold_core_evidence_sets: list[list[GoldEvidenceSpan]] = Field(default_factory=list)
    partial_evidence: list[GoldEvidenceSpan] = Field(default_factory=list)
    question_difficulty: Identifier
    question_type: Identifier
    concept_group: Identifier
    personalisation_eligibility: PersonalisationEligibility
    eligibility_reason: NonEmptyText
    split: EvaluationSplit
    corpus_version: Identifier
    parser_version: Identifier
    gold_annotation_version: Identifier
    annotation_status: AnnotationStatus
    review_record_id: Identifier | None

    @model_validator(mode="after")
    def validate_gold_semantics(self) -> "GoldSample":
        if set(self.options) != {"A", "B", "C", "D"}:
            raise ValueError("options must contain exactly A, B, C, and D")
        if any(not evidence_set for evidence_set in self.gold_core_evidence_sets):
            raise ValueError("gold_core_evidence_sets must not contain an empty AND group")

        all_spans = [
            span
            for evidence_set in self.gold_core_evidence_sets
            for span in evidence_set
        ] + self.partial_evidence
        span_ids = [span.span_id for span in all_spans]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError("span_id values must be unique across core and partial evidence")

        if self.answerable is True:
            if self.gold_answer is None:
                raise ValueError("answerable samples require gold_answer")
            if not self.gold_core_evidence_sets:
                raise ValueError("answerable samples require a complete gold evidence set")
        elif self.answerable is False and self.gold_core_evidence_sets:
            raise ValueError("unanswerable samples must not contain complete gold evidence sets")

        if self.annotation_status is AnnotationStatus.REVIEWED:
            if self.answerable is None:
                raise ValueError("reviewed samples must resolve answerable")
            if self.review_record_id is None:
                raise ValueError("reviewed samples require review_record_id")
        if self.annotation_status is AnnotationStatus.UNRESOLVED and self.answerable is not None:
            raise ValueError("unresolved samples must use null answerable")
        if self.answerable is None and self.annotation_status not in {
            AnnotationStatus.DISPUTED,
            AnnotationStatus.UNRESOLVED,
        }:
            raise ValueError("null answerable is allowed only for disputed or unresolved samples")
        return self


class RunStatus(StrEnum):
    RETRIEVAL_ERROR = "retrieval_error"
    GENERATION_ERROR = "generation_error"
    PARSE_ERROR = "parse_error"
    ABSTAINED = "abstained"
    ANSWERED = "answered"


class ErrorStage(StrEnum):
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    PARSING = "parsing"


class EvaluationRunError(ContractModel):
    stage: ErrorStage
    error_type: Identifier
    message: NonEmptyText


class EvaluationRunResult(ContractModel):
    """Complete trace for one evaluated question under one condition."""

    schema_version: Literal["0.1"] = "0.1"
    run_id: Identifier
    question_id: Identifier
    condition_id: Identifier
    status: RunStatus
    retrieval: RetrievalResult | None
    evidence_sent_to_model: EvidenceBundle | None
    raw_model_output: str | None
    repaired_model_output: str | None
    final_answer: GeneratedAnswer | None
    citation_validation: ValidatedAnswer | None
    error: EvaluationRunError | None

    def _validate_trace_links(self) -> None:
        """Keep the persisted retrieval, prompt, and citation trace on one path."""

        assert self.retrieval is not None
        assert self.evidence_sent_to_model is not None
        bundle = self.evidence_sent_to_model
        retrieval = self.retrieval

        if bundle.query != retrieval.query:
            raise ValueError("prompt evidence query must match retrieval query")
        if bundle.retrieval_mode != retrieval.mode:
            raise ValueError("prompt evidence mode must match retrieval mode")

        hits_by_id = {hit.chunk_id: hit for hit in retrieval.hits}
        for item in bundle.evidence_items:
            hit = hits_by_id.get(item.chunk_id)
            if hit is None:
                raise ValueError(
                    f"prompt evidence chunk {item.chunk_id!r} is absent from retrieval hits"
                )
            for field in (
                "text",
                "chapter_id",
                "source",
                "source_locator",
                "rank",
                "score",
            ):
                if getattr(item, field) != getattr(hit, field):
                    raise ValueError(
                        f"prompt evidence {field} does not match retrieval hit "
                        f"{item.chunk_id!r}"
                    )

        if self.citation_validation is None or self.final_answer is None:
            return
        validated = self.citation_validation
        allowed_chunk_ids = set(bundle.citation_map.values())
        if any(citation not in allowed_chunk_ids for citation in validated.resolved_citations):
            raise ValueError("resolved citations must refer to prompt evidence chunks")
        if validated.citation_status == "passed":
            expected_citations = [
                bundle.citation_map.get(citation, citation)
                for citation in self.final_answer.citations
            ]
            if any(citation not in allowed_chunk_ids for citation in expected_citations):
                raise ValueError("passed citations must refer to prompt evidence chunks")
            if validated.resolved_citations != expected_citations:
                raise ValueError("resolved citations must match final answer citations")

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "EvaluationRunResult":
        technical_errors = {
            RunStatus.RETRIEVAL_ERROR,
            RunStatus.GENERATION_ERROR,
            RunStatus.PARSE_ERROR,
        }
        if self.status in technical_errors:
            if self.final_answer is not None or self.citation_validation is not None:
                raise ValueError("technical error runs must not contain a final answer")
            if self.error is None:
                raise ValueError("technical error runs require error details")
            expected_stage = {
                RunStatus.RETRIEVAL_ERROR: ErrorStage.RETRIEVAL,
                RunStatus.GENERATION_ERROR: ErrorStage.GENERATION,
                RunStatus.PARSE_ERROR: ErrorStage.PARSING,
            }[self.status]
            if self.error.stage is not expected_stage:
                raise ValueError(f"{self.status.value} requires error stage {expected_stage.value}")
            if self.status is RunStatus.RETRIEVAL_ERROR:
                if self.retrieval is not None or self.evidence_sent_to_model is not None:
                    raise ValueError("retrieval_error must stop before retrieval output exists")
            elif self.retrieval is None or self.evidence_sent_to_model is None:
                raise ValueError(
                    "generation and parse errors require retrieval and prompt evidence"
                )
            if self.status is not RunStatus.RETRIEVAL_ERROR:
                self._validate_trace_links()
            if self.status is RunStatus.PARSE_ERROR and self.raw_model_output is None:
                raise ValueError("parse_error requires raw_model_output")
            return self

        if self.error is not None:
            raise ValueError("normal outcomes must not contain technical error details")
        if self.retrieval is None or self.evidence_sent_to_model is None:
            raise ValueError("normal outcomes require retrieval and prompt evidence")
        if self.raw_model_output is None:
            raise ValueError("normal outcomes require raw_model_output")
        if self.final_answer is None:
            raise ValueError("normal outcomes require final_answer")
        if self.citation_validation is None:
            if self.status is RunStatus.ANSWERED:
                raise ValueError("answered runs require citation validation")
            raise ValueError("abstained runs require citation validation")
        if self.final_answer != self.citation_validation.answer:
            raise ValueError("citation validation must refer to final_answer")
        self._validate_trace_links()

        if self.status is RunStatus.ABSTAINED:
            if not self.final_answer.abstained:
                raise ValueError("abstained status requires an abstained final answer")
            if self.citation_validation.citation_status != "skipped":
                raise ValueError("abstained runs must skip citation validation")
        else:
            if self.final_answer.abstained:
                raise ValueError("answered status must not contain an abstained final answer")
            if self.citation_validation.citation_status == "skipped":
                raise ValueError("answered runs must pass or fail citation validation")
        return self
