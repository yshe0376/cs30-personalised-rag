"""Frozen W5 evaluation sample and per-question run-result contracts."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, computed_field, model_validator

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


class SourceSplit(StrEnum):
    """Split of the source question dataset recorded by M3."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class EvaluationSplit(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROPOSED = "proposed"
    PROPOSED_DEV = "proposed_dev"
    PROPOSED_TEST = "proposed_test"
    HOLDOUT = "holdout"
    PENDING = "pending"


class AnnotationStatus(StrEnum):
    DRAFT = "draft"
    M3_INITIAL = "m3_initial"
    REVIEWED = "reviewed"
    DISPUTED = "disputed"
    UNRESOLVED = "unresolved"


class EvidenceSufficiency(StrEnum):
    """M3's annotation role for one evidence span."""

    CORE_SUFFICIENT = "core_sufficient"
    JOINT_CORE = "joint_core"
    ALTERNATIVE_SUFFICIENT = "alternative_sufficient"
    PARTIAL = "partial"


class SpanResolutionStatus(StrEnum):
    """Outcome of normalizing an M3 chapter-local Gold span."""

    RESOLVED = "resolved"
    STALE = "stale"
    AMBIGUOUS = "ambiguous"


class SpanResolutionMethod(StrEnum):
    """Evidence used to resolve an M3 Gold span against the corpus."""

    BLOCK_ID = "block_id"
    VERBATIM_UNIQUE = "verbatim_unique"


class GoldOption(ContractModel):
    """An answer option and the source field from the M3 question record."""

    text: NonEmptyText
    source_field: Identifier


class GoldSource(ContractModel):
    """Source-question provenance retained from the M3 Gold artifact."""

    dataset: NonEmptyText
    source_question_id: Identifier
    support: NonEmptyText


class GoldEvidenceSpan(ContractModel):
    """One auditable half-open span in M3's canonical chapter text."""

    span_id: Identifier
    document_id: Identifier
    chapter_id: Identifier | None = None
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    verbatim_text: SpanText
    chapter_char_start: int | None = Field(default=None, ge=0)
    chapter_char_end: int | None = Field(default=None, gt=0)
    corpus_char_start: int | None = Field(default=None, ge=0)
    corpus_char_end: int | None = Field(default=None, gt=0)
    resolved_block_id: Identifier | None = None
    resolution_status: SpanResolutionStatus | None = None
    resolution_method: SpanResolutionMethod | None = None
    block_id: Identifier | None = None
    sufficiency: EvidenceSufficiency | None = None
    annotation_note: str | None = None

    @model_validator(mode="after")
    def validate_span_shape(self) -> "GoldEvidenceSpan":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if len(self.verbatim_text) != self.char_end - self.char_start:
            raise ValueError("verbatim_text length must match the half-open character span")
        if self.resolution_status is SpanResolutionStatus.RESOLVED:
            if self.corpus_char_start is None or self.corpus_char_end is None:
                raise ValueError("resolved spans require corpus_char_start/corpus_char_end")
        if self.resolution_status is not None:
            if self.chapter_char_start != self.char_start:
                raise ValueError("chapter_char_start must mirror raw char_start")
            if self.chapter_char_end != self.char_end:
                raise ValueError("chapter_char_end must mirror raw char_end")
        return self


class GoldSample(ContractModel):
    """One M3 Gold item consumed by the M1 and M8 evaluators.

    The outer ``gold_core_evidence_sets`` list is OR. Every span in one inner
    list is AND. ``partial_evidence`` is diagnostic only and never contributes
    to a complete Gold hit.  M3 v0.1 records retain their source and
    annotation metadata; optional fields keep the older engineering fixtures
    readable as well.
    """

    schema_version: Literal["0.1", "0.2"] = "0.1"
    question_id: Identifier
    source_split: SourceSplit | None = None
    question: NonEmptyText
    options: dict[ChoiceLabel, GoldOption]
    gold_answer: ChoiceLabel | None
    gold_answer_text: NonEmptyText | None = None
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
    source_corpus_version: Identifier | None = None
    normalizer_version: Identifier | None = None
    parser_version: Identifier
    gold_annotation_version: Identifier
    annotation_status: AnnotationStatus
    review_record_id: Identifier | None
    source: GoldSource | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_options(cls, value: object) -> object:
        """Wrap the original fixture's string options in the M3 option shape."""

        if not isinstance(value, dict):
            return value
        payload = dict(value)
        options = payload.get("options")
        if isinstance(options, dict):
            payload["options"] = {
                key: (
                    {"text": option, "source_field": "legacy"}
                    if isinstance(option, str)
                    else option
                )
                for key, option in options.items()
            }
        return payload

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

        if self.schema_version == "0.2":
            for span in all_spans:
                if span.resolution_status is None:
                    raise ValueError(
                        "normalized Gold samples require resolution_status "
                        f"for span {span.span_id}"
                    )
                if span.chapter_char_start != span.char_start:
                    raise ValueError(
                        "normalized Gold samples require chapter_char_start to mirror "
                        f"raw char_start for span {span.span_id}"
                    )
                if span.chapter_char_end != span.char_end:
                    raise ValueError(
                        "normalized Gold samples require chapter_char_end to mirror "
                        f"raw char_end for span {span.span_id}"
                    )
                if (
                    span.resolution_status is SpanResolutionStatus.RESOLVED
                    and (span.corpus_char_start is None or span.corpus_char_end is None)
                ):
                    raise ValueError(
                        "resolved normalized Gold spans require "
                        "corpus_char_start/corpus_char_end"
                    )

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

        m3_fields = (
            self.source_split is not None
            or self.gold_answer_text is not None
            or self.source is not None
            or self.annotation_status is AnnotationStatus.M3_INITIAL
            or any(
                span.chapter_id is not None
                or span.block_id is not None
                or span.sufficiency is not None
                or span.annotation_note is not None
                for evidence_set in self.gold_core_evidence_sets
                for span in evidence_set
            )
            or any(
                span.chapter_id is not None
                or span.block_id is not None
                or span.sufficiency is not None
                or span.annotation_note is not None
                for span in self.partial_evidence
            )
        )
        if m3_fields:
            missing = [
                name
                for name, value in (
                    ("source_split", self.source_split),
                    ("gold_answer_text", self.gold_answer_text),
                    ("source", self.source),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "M3 Gold records require source_split, gold_answer_text, and source; "
                    f"missing {', '.join(missing)}"
                )
            if self.review_record_id is None:
                raise ValueError("M3 Gold records require review_record_id")
            spans = [
                span
                for evidence_set in self.gold_core_evidence_sets
                for span in evidence_set
            ] + self.partial_evidence
            for span in spans:
                missing_span_fields = [
                    name
                    for name, value in (
                        ("chapter_id", span.chapter_id),
                        ("block_id", span.block_id),
                        ("sufficiency", span.sufficiency),
                        ("annotation_note", span.annotation_note),
                    )
                    if value is None
                ]
                if missing_span_fields:
                    raise ValueError(
                        "M3 Gold evidence spans require chapter_id, block_id, sufficiency, "
                        "and annotation_note; missing "
                        f"{', '.join(missing_span_fields)} for {span.span_id}"
                    )
        return self


class RunStatus(StrEnum):
    RETRIEVAL_ERROR = "retrieval_error"
    GENERATION_ERROR = "generation_error"
    PARSE_ERROR = "parse_error"
    RETRIEVED = "retrieved"
    ABSTAINED = "abstained"
    ANSWERED = "answered"


class ExecutionMode(StrEnum):
    """Whether a run stops after retrieval or continues to generation."""

    RETRIEVAL_ONLY = "retrieval_only"
    RETRIEVAL_AND_GENERATION = "retrieval_and_generation"


class AbstentionCause(StrEnum):
    """Why a successful generation-mode run refused to answer."""

    NO_RETRIEVAL_HITS = "no_retrieval_hits"
    MODEL_ABSTAINED_WITH_EVIDENCE = "model_abstained_with_evidence"


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

    schema_version: Literal["0.2"] = "0.2"
    run_id: Identifier
    question_id: Identifier
    condition_id: Identifier
    execution_mode: ExecutionMode
    status: RunStatus
    retrieval: RetrievalResult | None
    evidence_sent_to_model: EvidenceBundle | None
    raw_model_output: str | None
    repaired_model_output: str | None
    final_answer: GeneratedAnswer | None
    citation_validation: ValidatedAnswer | None
    error: EvaluationRunError | None
    model_call_count: int = Field(default=0, ge=0)
    abstention_cause: AbstentionCause | None = None
    prompt_evidence_chunk_ids: list[Identifier] | None = None
    prompt_sha256: Identifier | None = None

    @computed_field(return_type=bool)
    @property
    def model_invoked(self) -> bool:
        """Expose a derived convenience flag instead of a second input state."""

        return self.model_call_count > 0

    @model_validator(mode="before")
    @classmethod
    def discard_derived_input(cls, value: object) -> object:
        """Allow JSON round-trips without letting callers set the derived flag."""

        if isinstance(value, dict) and "model_invoked" in value:
            value = dict(value)
            value.pop("model_invoked", None)
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "EvaluationRunResult":
        if self.prompt_evidence_chunk_ids is not None:
            if len(set(self.prompt_evidence_chunk_ids)) != len(self.prompt_evidence_chunk_ids):
                raise ValueError("prompt evidence chunk IDs must be unique")
            if self.prompt_sha256 is None:
                raise ValueError("prompt evidence IDs require prompt_sha256")
        elif self.prompt_sha256 is not None:
            raise ValueError("prompt_sha256 requires prompt evidence chunk IDs")

        technical_errors = {
            RunStatus.RETRIEVAL_ERROR,
            RunStatus.GENERATION_ERROR,
            RunStatus.PARSE_ERROR,
        }
        if self.status in technical_errors:
            if self.abstention_cause is not None:
                raise ValueError("technical error runs must not contain abstention_cause")
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
                if (
                    self.retrieval is not None
                    or self.evidence_sent_to_model is not None
                    or self.model_call_count != 0
                    or self.raw_model_output is not None
                    or self.repaired_model_output is not None
                    or self.prompt_evidence_chunk_ids is not None
                    or self.prompt_sha256 is not None
                ):
                    raise ValueError(
                        "retrieval_error must stop before retrieval or prompt output exists"
                    )
            elif self.retrieval is None:
                raise ValueError("generation and parse errors require retrieval output")
            elif not self.retrieval.hits:
                raise ValueError("generation and parse errors require retrieval hits")
            elif self.status is RunStatus.PARSE_ERROR:
                if self.evidence_sent_to_model is None:
                    raise ValueError("parse_error requires prompt evidence")
                if self.model_call_count == 0:
                    raise ValueError("parse errors require a model call")
                if self.raw_model_output is None:
                    raise ValueError("parse_error requires raw_model_output")
            elif self.evidence_sent_to_model is None:
                # Evidence assembly and profile preparation happen before the
                # model call.  A generation failure at either seam therefore
                # has retrieval output but no prompt evidence or model output.
                if (
                    self.model_call_count != 0
                    or self.raw_model_output is not None
                    or self.repaired_model_output is not None
                    or self.prompt_evidence_chunk_ids is not None
                    or self.prompt_sha256 is not None
                ):
                    raise ValueError(
                        "generation_error without prompt evidence must not contain "
                        "model output"
                    )
            if self.repaired_model_output is not None and self.raw_model_output is None:
                raise ValueError("repaired_model_output requires raw_model_output")
            if (
                self.execution_mode is ExecutionMode.RETRIEVAL_ONLY
                and self.status is not RunStatus.RETRIEVAL_ERROR
            ):
                raise ValueError("retrieval_only runs cannot have generation errors")
            return self

        if self.execution_mode is ExecutionMode.RETRIEVAL_ONLY:
            if self.status is not RunStatus.RETRIEVED:
                raise ValueError("retrieval_only runs must finish as retrieved or retrieval_error")
            if self.retrieval is None:
                raise ValueError("retrieved runs require retrieval output")
            if (
                self.error is not None
                or self.evidence_sent_to_model is not None
                or self.raw_model_output is not None
                or self.repaired_model_output is not None
                or self.final_answer is not None
                or self.citation_validation is not None
                or self.model_call_count != 0
                or self.abstention_cause is not None
                or self.prompt_evidence_chunk_ids is not None
                or self.prompt_sha256 is not None
            ):
                raise ValueError("retrieval-only results must not contain generation output")
            return self

        if self.status is RunStatus.RETRIEVED:
            raise ValueError("retrieved status is only valid for retrieval_only runs")
        if self.error is not None:
            raise ValueError("normal outcomes must not contain technical error details")

        if self.status is RunStatus.ABSTAINED:
            if (
                self.retrieval is None
                or self.final_answer is None
                or self.citation_validation is None
            ):
                raise ValueError(
                    "abstained runs require retrieval, final_answer and citation validation"
                )
            if not self.final_answer.abstained:
                raise ValueError("abstained status requires an abstained final answer")
            if self.citation_validation.citation_status != "skipped":
                raise ValueError("abstained runs must skip citation validation")
            if self.final_answer != self.citation_validation.answer:
                raise ValueError("citation validation must refer to final_answer")
            if self.abstention_cause is AbstentionCause.NO_RETRIEVAL_HITS:
                if self.retrieval.hits:
                    raise ValueError("no_retrieval_hits requires an empty retrieval result")
                if (
                    self.evidence_sent_to_model is not None
                    or self.raw_model_output is not None
                    or self.repaired_model_output is not None
                    or self.model_call_count != 0
                ):
                    raise ValueError("no_retrieval_hits must not contain model output")
            elif self.abstention_cause is AbstentionCause.MODEL_ABSTAINED_WITH_EVIDENCE:
                if not self.retrieval.hits or self.evidence_sent_to_model is None:
                    raise ValueError("model_abstained_with_evidence requires retrieval evidence")
                if self.raw_model_output is None or self.model_call_count == 0:
                    raise ValueError("model_abstained_with_evidence requires a model response")
            else:
                raise ValueError("abstained runs require abstention_cause")
        else:
            if self.status is not RunStatus.ANSWERED:
                raise ValueError(f"unsupported normal run status: {self.status.value}")
            if self.retrieval is None or not self.retrieval.hits:
                raise ValueError("answered runs require retrieval hits")
            if self.evidence_sent_to_model is None:
                raise ValueError("answered runs require prompt evidence")
            if self.raw_model_output is None or self.model_call_count == 0:
                raise ValueError("answered runs require a model response")
            if self.final_answer is None:
                raise ValueError("answered runs require final_answer")
            if self.citation_validation is None:
                raise ValueError("answered runs require citation validation")
            if self.final_answer != self.citation_validation.answer:
                raise ValueError("citation validation must refer to final_answer")
            if self.abstention_cause is not None:
                raise ValueError("answered runs must not contain abstention_cause")
            if self.final_answer.abstained:
                raise ValueError("answered status must not contain an abstained final answer")
            if self.citation_validation.citation_status == "skipped":
                raise ValueError("answered runs must pass or fail citation validation")
        return self
