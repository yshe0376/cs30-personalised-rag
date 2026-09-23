"""Strict v2 contracts for multi-textbook corpus assets.

The v1 contracts remain in ``cs30.contracts``.  This module intentionally does
not use their OpenStax aliases: a v2 document must carry its provider and
textbook identity as first-class fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from cs30.evaluation.models import (
    AnnotationStatus,
    EvaluationSplit,
    EvidenceSufficiency,
    GoldOption,
    GoldSource,
    PersonalisationEligibility,
    SourceSplit,
)
from cs30.v2.ids import (
    page_location,
    sha256_text,
    source_locator,
    validate_source_locator_shape,
)

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SpanText = Annotated[str, Field(min_length=1)]
ChoiceLabel = Literal["A", "B", "C", "D"]


class V2Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _fill_page_location(data: object) -> object:
    """Derive ``page_or_location`` from a physical page range when it is omitted."""

    if (
        isinstance(data, dict)
        and data.get("page_or_location") is None
        and isinstance(data.get("page_start"), int)
        and isinstance(data.get("page_end"), int)
        and 1 <= data["page_start"] <= data["page_end"]
    ):
        return {
            **data,
            "page_or_location": page_location(data["page_start"], data["page_end"]),
        }
    return data


def _validate_page_fields(
    page_start: int | None,
    page_end: int | None,
    page_or_location: str | None,
    owner: str,
) -> None:
    """Pages come as a pair and then fix the location to ``p<start>[-<end>]``."""

    if (page_start is None) != (page_end is None):
        raise ValueError(f"{owner} page_start and page_end must be set together")
    if page_start is None or page_end is None:
        return
    if page_end < page_start:
        raise ValueError(f"{owner} page_end must not precede page_start")
    expected = page_location(page_start, page_end)
    if page_or_location != expected:
        raise ValueError(
            f"{owner} page_or_location must be {expected!r} for pages "
            f"{page_start}-{page_end}"
        )


class ContentType(StrEnum):
    """Structural role of a parsed block.

    Mathematics is always ``equation``; there is deliberately no separate
    formula type, so no parser can label maths with a value the evidence policy
    silently drops.  Image descriptions taken from PDF alt text are
    ``figure_caption``, with the parser's own record type kept in block metadata.
    ``image`` and ``asset_placeholder`` mark non-text assets.
    """

    BODY = "body"
    HEADING = "heading"
    LEARNING_OBJECTIVE = "learning_objective"
    FIGURE_CAPTION = "figure_caption"
    TABLE = "table"
    EQUATION = "equation"
    IMAGE = "image"
    EXAMPLE = "example"
    CHECK_UNDERSTANDING = "check_understanding"
    SIDEBAR = "sidebar"
    SUMMARY = "summary"
    CONCEPTUAL_QUESTION = "conceptual_question"
    PROBLEM = "problem"
    GLOSSARY = "glossary"
    ASSET_PLACEHOLDER = "asset_placeholder"
    OTHER = "other"


class RetrievalMode(StrEnum):
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"
    FIXTURE = "fixture"


class StudentLevel(StrEnum):
    """The three learner levels shared by prompts and Concept Check."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class QuestionSourceType(StrEnum):
    HUMAN_AUTHORED = "human_authored"
    SCIQ_ALIGNED = "sciq_aligned"
    LLM_GENERATED = "llm_generated"


class ConceptCheckQuestionStatus(StrEnum):
    DRAFT = "draft"
    AUTO_VALIDATED = "auto_validated"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    REJECTED = "rejected"


class TopicResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    NO_TOPIC_AVAILABLE = "no_topic_available"
    TOPIC_MAP_UNAVAILABLE = "topic_map_unavailable"
    TOPIC_MAP_MISMATCH = "topic_map_mismatch"


class ProfileSource(StrEnum):
    STATIC_PROFILE = "static_profile"
    LEARNER_STATE_REPLAY = "learner_state_replay"


class ConceptCheckResult(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    SKIPPED = "skipped"


class ConceptCheckEventType(StrEnum):
    ATTEMPT_SUBMITTED = "attempt_submitted"
    ATTEMPT_SKIPPED = "attempt_skipped"
    ATTEMPT_REVOKED = "attempt_revoked"
    TOPIC_LEVEL_OVERRIDDEN = "topic_level_overridden"


class TextbookChapter(V2Model):
    chapter_id: Identifier
    title: Identifier
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_span(self) -> TextbookChapter:
        if self.char_end <= self.char_start:
            raise ValueError("chapter char_end must be greater than char_start")
        if self.page_start and self.page_end and self.page_end < self.page_start:
            raise ValueError("chapter page_end must not precede page_start")
        return self


class TextBlock(V2Model):
    """One parser block.

    ``page_start``/``page_end`` are 1-based physical PDF pages.  When they are
    present, ``page_or_location`` is derived as ``p<start>`` or
    ``p<start>-<end>``; a printed page label belongs in ``metadata``.  Sources
    without pages leave both unset and may give a free-form location instead.
    """

    block_id: Identifier
    chapter_id: Identifier
    section_id: Identifier | None = None
    section_title: Identifier | None = None
    content_type: ContentType = ContentType.BODY
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    page_or_location: Identifier | None = None
    asset_ref: Identifier | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def derive_page_location(cls, data: object) -> object:
        return _fill_page_location(data)

    @model_validator(mode="after")
    def validate_span(self) -> TextBlock:
        if self.char_end <= self.char_start:
            raise ValueError("block char_end must be greater than char_start")
        _validate_page_fields(
            self.page_start, self.page_end, self.page_or_location, "block"
        )
        return self


class TextbookDocument(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    provider: Identifier
    textbook_id: Identifier
    document_id: Identifier
    title: Identifier
    raw_source_sha256: Identifier
    document_hash: Identifier
    parser_version: Identifier
    source_name: Identifier
    source_uri: str | None = None
    source_version: Identifier
    license: Identifier
    selected_chapters: tuple[Identifier, ...] = ()
    text: SpanText
    chapters: tuple[TextbookChapter, ...] = Field(min_length=1)
    blocks: tuple[TextBlock, ...] = Field(min_length=1)
    cleaning_version: Identifier = "clean-v2"
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_structure(self) -> TextbookDocument:
        chapter_ranges: dict[str, tuple[int, int]] = {}
        previous_end = 0
        for chapter in self.chapters:
            if chapter.chapter_id in chapter_ranges:
                raise ValueError(f"duplicate chapter_id: {chapter.chapter_id}")
            if chapter.char_end > len(self.text):
                raise ValueError(f"chapter span exceeds document text: {chapter.chapter_id}")
            if chapter.char_start < previous_end:
                raise ValueError("chapter spans must be ordered and non-overlapping")
            chapter_ranges[chapter.chapter_id] = (chapter.char_start, chapter.char_end)
            previous_end = chapter.char_end

        seen_blocks: set[str] = set()
        previous_end = 0
        for block in self.blocks:
            if block.block_id in seen_blocks:
                raise ValueError(f"duplicate block_id: {block.block_id}")
            if block.char_end > len(self.text):
                raise ValueError(f"block span exceeds document text: {block.block_id}")
            if block.char_start < previous_end:
                raise ValueError(
                    "block spans must be ordered and non-overlapping: "
                    f"{block.block_id}"
                )
            chapter_range = chapter_ranges.get(block.chapter_id)
            if chapter_range is None:
                raise ValueError(f"block references unknown chapter_id: {block.chapter_id}")
            if block.char_start < chapter_range[0] or block.char_end > chapter_range[1]:
                raise ValueError(f"block falls outside chapter {block.chapter_id}")
            seen_blocks.add(block.block_id)
            previous_end = block.char_end
        return self

    def document_text(self, block: TextBlock) -> str:
        """Return verbatim text for a document-global block span."""

        return self.text[block.char_start : block.char_end]


class Topic(V2Model):
    """One provider-neutral concept in a versioned Topic registry."""

    topic_id: Identifier
    title: NonEmptyText
    description: NonEmptyText | None = None


class TopicRegistry(V2Model):
    """The reviewed Topic vocabulary used by a retrieval sidecar."""

    schema_version: Literal["2.0"] = "2.0"
    topic_registry_version: Identifier
    topics: tuple[Topic, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_topics(self) -> TopicRegistry:
        topic_ids = [topic.topic_id for topic in self.topics]
        if len(topic_ids) != len(set(topic_ids)):
            raise ValueError("topic_ids must be unique in a Topic registry")
        return self


class TopicResolution(V2Model):
    """A deterministic retrieval/citation-to-Topic decision and its trace."""

    schema_version: Literal["2.0"] = "2.0"
    status: TopicResolutionStatus
    topic_id: Identifier | None = None
    topic_registry_version: Identifier | None = None
    support: float = Field(default=0.0, ge=0.0, le=1.0)
    topic_support: dict[Identifier, float] = Field(default_factory=dict)
    error_code: Identifier | None = None
    resolver_called: bool = True

    @model_validator(mode="after")
    def validate_resolution(self) -> TopicResolution:
        if self.status is TopicResolutionStatus.RESOLVED:
            if self.topic_id is None or self.topic_registry_version is None:
                raise ValueError("a resolved Topic requires topic_id and registry version")
            if self.support <= 0.0:
                raise ValueError("a resolved Topic requires positive support")
            if self.error_code is not None:
                raise ValueError("a resolved Topic must not carry an error code")
        elif self.topic_id is not None:
            raise ValueError("an unresolved Topic result must not carry a Topic identity")
        for topic_id, support in self.topic_support.items():
            if support < 0.0 or support > 1.0:
                raise ValueError(f"Topic support for {topic_id!r} must be between 0 and 1")
        return self


class ChunkSpan(V2Model):
    block_id: Identifier
    chapter_id: Identifier
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    content_type: ContentType

    @model_validator(mode="after")
    def validate_span(self) -> ChunkSpan:
        if self.char_end <= self.char_start:
            raise ValueError("chunk span char_end must be greater than char_start")
        return self


class Chunk(V2Model):
    """One retrievable chunk made of whole parser blocks.

    A chunk may merge several blocks, so it carries every content type in
    ``content_types`` (ordered, de-duplicated, and always equal to its spans).
    Its pages are the minimum and maximum block pages and follow the same
    ``page_or_location`` rule as :class:`TextBlock`.
    """

    schema_version: Literal["2.0"] = "2.0"
    chunk_id: Identifier
    provider: Identifier
    textbook_id: Identifier
    document_id: Identifier
    chapter_id: Identifier
    source_name: Identifier
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    page_or_location: str | None = None
    source_locator: Identifier
    text: SpanText
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    section_id: Identifier | None = None
    section_title: Identifier | None = None
    content_types: tuple[ContentType, ...] = ()
    spans: tuple[ChunkSpan, ...] = Field(min_length=1)
    chunker_version: Identifier
    chunk_config_hash: Identifier
    token_count: int = Field(gt=0)
    embed_text: SpanText | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def derive_page_location(cls, data: object) -> object:
        return _fill_page_location(data)

    @model_validator(mode="after")
    def validate_traceable_text(self) -> Chunk:
        if self.char_end <= self.char_start:
            raise ValueError("chunk char_end must be greater than char_start")
        _validate_page_fields(
            self.page_start, self.page_end, self.page_or_location, "chunk"
        )
        span_types = tuple(dict.fromkeys(span.content_type for span in self.spans))
        if not self.content_types:
            self.content_types = span_types
        elif self.content_types != span_types:
            raise ValueError(
                "content_types must equal the ordered, de-duplicated span content types"
            )
        expected_length = self.char_end - self.char_start
        if len(self.text) != expected_length:
            raise ValueError(
                f"text length {len(self.text)} does not match span "
                f"[{self.char_start}, {self.char_end}) of length {expected_length}"
            )
        if self.embed_text is not None and self.text not in self.embed_text:
            raise ValueError("embed_text must contain chunk text verbatim")
        previous_end = self.char_start
        for span in self.spans:
            if span.char_start < self.char_start or span.char_end > self.char_end:
                raise ValueError("structural chunk span falls outside the primary span")
            if span.char_start < previous_end:
                raise ValueError("structural chunk spans must be ordered and non-overlapping")
            previous_end = span.char_end
        if not self.source_locator:
            raise ValueError("source_locator must not be empty")
        validate_source_locator_shape(
            self.source_locator,
            source_name=self.source_name,
            textbook_id=self.textbook_id,
            chapter_id=self.chapter_id,
            page_or_location=self.page_or_location,
        )
        expected_locator = source_locator(
            source_name=self.source_name,
            textbook_id=self.textbook_id,
            chapter_id=self.chapter_id,
            page_or_location=self.page_or_location,
            char_start=self.char_start,
            char_end=self.char_end,
        )
        if self.source_locator != expected_locator:
            raise ValueError("source_locator does not match the chunk identity and span")
        return self

    @property
    def embedding_input(self) -> str:
        return self.text if self.embed_text is None else self.embed_text


class SpanResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    STALE = "stale"
    AMBIGUOUS = "ambiguous"


class SpanResolutionMethod(StrEnum):
    BLOCK_ID = "block_id"
    CHAPTER_OFFSET = "chapter_offset"
    VERBATIM_UNIQUE = "verbatim_unique"


class EvidenceSpan(V2Model):
    """A stable textbook span shared by v2 Gold evidence and Concept Check anchors.

    Offsets are chapter-local and half-open, so re-parsing another chapter
    cannot move them.  ``document_id``, document-global offsets and chunk IDs
    change with every rebuild; they are resolution results and live in
    :class:`EvidenceSpanBinding`, never here.  ``span_id`` must be unique across
    Gold and Concept Check (for example ``gold:<question_id>:1``).
    """

    schema_version: Literal["2.0"] = "2.0"
    span_id: Identifier
    textbook_id: Identifier
    chapter_id: Identifier
    chapter_char_start: int = Field(ge=0)
    chapter_char_end: int = Field(gt=0)
    verbatim_text: SpanText
    text_hash: Identifier
    origin_corpus_version: Identifier
    block_id: Identifier | None = None
    page_or_location: str | None = None

    @model_validator(mode="before")
    @classmethod
    def derive_text_hash(cls, data: object) -> object:
        if isinstance(data, dict) and "text_hash" not in data and "verbatim_text" in data:
            return {**data, "text_hash": sha256_text(data["verbatim_text"])}
        return data

    @model_validator(mode="after")
    def validate_span(self) -> EvidenceSpan:
        if self.chapter_char_end <= self.chapter_char_start:
            raise ValueError("evidence span chapter_char_end must exceed chapter_char_start")
        if len(self.verbatim_text) != self.chapter_char_end - self.chapter_char_start:
            raise ValueError("verbatim_text length must match the half-open chapter span")
        if self.text_hash != sha256_text(self.verbatim_text):
            raise ValueError("text_hash must be the SHA-256 of verbatim_text")
        return self


class EvidenceSpanBinding(V2Model):
    """Where one :class:`EvidenceSpan` resolves in one specific corpus.

    Gold mapping and Concept Check anchor binding produce this same record
    through one shared resolver, so the leakage gate compares like with like.
    """

    schema_version: Literal["2.0"] = "2.0"
    span_id: Identifier
    textbook_id: Identifier
    corpus_version: Identifier
    corpus_hash: Identifier
    resolution_status: SpanResolutionStatus
    resolution_method: SpanResolutionMethod | None = None
    document_id: Identifier | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, gt=0)
    chunk_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_resolution(self) -> EvidenceSpanBinding:
        located = (self.document_id, self.char_start, self.char_end)
        if self.resolution_status is SpanResolutionStatus.RESOLVED:
            if (
                self.resolution_method is None
                or self.document_id is None
                or self.char_start is None
                or self.char_end is None
            ):
                raise ValueError(
                    "a resolved binding needs its method, document_id and document span"
                )
            if self.char_end <= self.char_start:
                raise ValueError("binding char_end must exceed char_start")
            if not self.chunk_ids:
                raise ValueError("a resolved binding must name at least one chunk")
            if len(set(self.chunk_ids)) != len(self.chunk_ids):
                raise ValueError("binding chunk_ids must be unique")
        elif any(value is not None for value in located) or self.chunk_ids:
            raise ValueError(
                f"a {self.resolution_status.value} binding must not carry a location or chunks"
            )
        return self


class V2GoldEvidence(V2Model):
    """M3's semantic evidence annotation around the shared v2 span."""

    span: EvidenceSpan
    sufficiency: EvidenceSufficiency
    annotation_note: NonEmptyText | None = None


class GoldQuestion(V2Model):
    """The v2 question-layer hand-off from M3 to evaluation and retrieval.

    The existing ``cs30.evaluation`` package owns the typed M3 provenance
    enums/models.  This v2 wrapper changes only the evidence representation:
    Gold evidence uses the same chapter-local :class:`EvidenceSpan` as
    Concept Check anchors, so M4 can resolve both with one implementation.
    """

    schema_version: Literal["2.0"] = "2.0"
    question_id: Identifier
    question: NonEmptyText
    options: dict[ChoiceLabel, GoldOption]
    gold_answer: ChoiceLabel | None = None
    answerable: bool | None
    gold_core_evidence_sets: tuple[tuple[V2GoldEvidence, ...], ...] = ()
    partial_evidence: tuple[V2GoldEvidence, ...] = ()
    question_difficulty: Identifier
    question_type: Identifier
    concept_group: Identifier
    personalisation_eligibility: PersonalisationEligibility
    eligibility_reason: NonEmptyText
    split: EvaluationSplit
    corpus_version: Identifier
    source_corpus_version: Identifier | None = None
    parser_version: Identifier
    gold_annotation_version: Identifier
    annotation_status: AnnotationStatus
    review_record_id: Identifier | None = None
    source: GoldSource | None = None
    source_split: SourceSplit | None = None
    topic_id: Identifier | None = None
    topic_registry_version: Identifier | None = None

    @model_validator(mode="after")
    def validate_gold_shape(self) -> GoldQuestion:
        if set(self.options) != {"A", "B", "C", "D"}:
            raise ValueError("options must contain exactly A, B, C, and D")
        if any(not evidence_set for evidence_set in self.gold_core_evidence_sets):
            raise ValueError("gold_core_evidence_sets must not contain an empty AND group")

        all_evidence = [
            evidence
            for evidence_set in self.gold_core_evidence_sets
            for evidence in evidence_set
        ] + list(self.partial_evidence)
        span_ids = [evidence.span.span_id for evidence in all_evidence]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError("Gold evidence span_id values must be unique")

        if self.answerable is True:
            if self.gold_answer is None:
                raise ValueError("answerable Gold questions require gold_answer")
            if not self.gold_core_evidence_sets:
                raise ValueError("answerable Gold questions require complete evidence")
        elif self.answerable is False and self.gold_core_evidence_sets:
            raise ValueError("unanswerable Gold questions must not contain complete evidence")

        if self.annotation_status is AnnotationStatus.REVIEWED and self.review_record_id is None:
            raise ValueError("reviewed Gold questions require review_record_id")
        if (self.topic_id is None) != (self.topic_registry_version is None):
            raise ValueError("topic_id and topic_registry_version must be set together")
        return self


class ConceptCheckQuestion(V2Model):
    """A practice-only four-choice question with stable evidence anchors.

    Bindings are deliberately kept in :class:`ConceptCheckQuestionRelease`.
    Rebuilding a corpus therefore changes only the versioned binding, never the
    durable question or its chapter-local anchor.
    """

    schema_version: Literal["0.1"] = "0.1"
    question_id: Identifier
    question: NonEmptyText
    options: dict[ChoiceLabel, NonEmptyText]
    correct_answer: ChoiceLabel
    topic_id: Identifier
    topic_registry_version: Identifier
    difficulty: StudentLevel
    evidence_anchors: tuple[EvidenceSpan, ...] = Field(min_length=1)
    source_type: QuestionSourceType
    split_guard: Literal["practice_only"] = "practice_only"
    rationale: NonEmptyText
    review_record_id: Identifier | None = None
    status: ConceptCheckQuestionStatus = ConceptCheckQuestionStatus.DRAFT
    source: GoldSource | None = None
    source_split: SourceSplit | None = None

    @model_validator(mode="after")
    def validate_question_shape(self) -> ConceptCheckQuestion:
        if set(self.options) != {"A", "B", "C", "D"}:
            raise ValueError("options must contain exactly A, B, C, and D")
        if self.correct_answer not in self.options:
            raise ValueError("correct_answer must identify one of the four options")
        anchor_ids = [anchor.span_id for anchor in self.evidence_anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("evidence anchor span_id values must be unique")

        if self.source_type is QuestionSourceType.SCIQ_ALIGNED:
            if self.source is None or self.source.dataset.casefold() != "sciq":
                raise ValueError("sciq_aligned questions require SciQ provenance")
            if self.source_split not in {SourceSplit.TRAIN, SourceSplit.VALIDATION}:
                raise ValueError("Concept Check questions may use only SciQ train/validation")
        elif self.source is not None or self.source_split is not None:
            raise ValueError("only sciq_aligned questions may carry SciQ provenance")

        if self.status in {
            ConceptCheckQuestionStatus.REVIEWED,
            ConceptCheckQuestionStatus.PUBLISHED,
        } and self.review_record_id is None:
            raise ValueError("reviewed or published questions require review_record_id")
        return self


class ConceptCheckQuestionBinding(V2Model):
    """One question's anchor bindings for a single corpus version."""

    schema_version: Literal["0.1"] = "0.1"
    question_id: Identifier
    corpus_version: Identifier
    corpus_hash: Identifier
    bindings: tuple[EvidenceSpanBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bindings(self) -> ConceptCheckQuestionBinding:
        span_ids = [binding.span_id for binding in self.bindings]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError("question bindings must have unique span_id values")
        for binding in self.bindings:
            if binding.corpus_version != self.corpus_version:
                raise ValueError("question binding corpus_version mismatch")
            if binding.corpus_hash != self.corpus_hash:
                raise ValueError("question binding corpus_hash mismatch")
        return self


class ConceptCheckQuestionRelease(V2Model):
    """The publish-time pair of a reviewed question and resolved bindings."""

    schema_version: Literal["0.1"] = "0.1"
    question: ConceptCheckQuestion
    binding: ConceptCheckQuestionBinding

    @model_validator(mode="after")
    def validate_release_gate(self) -> ConceptCheckQuestionRelease:
        if self.question.status is not ConceptCheckQuestionStatus.PUBLISHED:
            raise ValueError("only published questions can be released")
        if self.binding.question_id != self.question.question_id:
            raise ValueError("question release binding question_id mismatch")
        expected = {anchor.span_id for anchor in self.question.evidence_anchors}
        actual = {item.span_id for item in self.binding.bindings}
        if actual != expected:
            raise ValueError("question release must bind every and only its anchors")
        if any(
            item.resolution_status is not SpanResolutionStatus.RESOLVED
            for item in self.binding.bindings
        ):
            raise ValueError("published question releases require resolved bindings")
        return self


class EvidenceProvenance(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    corpus_version: Identifier
    corpus_hash: Identifier
    manifest_hash: Identifier
    chunk_config_hash: Identifier
    index_version: Identifier
    retrieval_mode: RetrievalMode
    retrieval_config_hash: Identifier
    embedding_model: Identifier | None = None
    embedding_revision: Identifier | None = None

    @model_validator(mode="after")
    def validate_embedding_identity(self) -> EvidenceProvenance:
        if self.retrieval_mode in (RetrievalMode.DENSE, RetrievalMode.HYBRID):
            if self.embedding_model is None or self.embedding_revision is None:
                raise ValueError("dense or hybrid provenance requires embedding identity")
        if self.retrieval_mode is RetrievalMode.BM25 and self.embedding_model is not None:
            raise ValueError("BM25 provenance must not include embedding_model")
        return self


class RetrievedEvidence(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    provider: Identifier
    textbook_id: Identifier
    document_id: Identifier
    chunk_id: Identifier
    chapter_id: Identifier
    source_name: Identifier
    page_or_location: str | None = None
    source_locator: Identifier
    text: SpanText
    score: float
    rank: int = Field(ge=1)
    retriever_type: RetrievalMode

    @model_validator(mode="after")
    def validate_locator(self) -> RetrievedEvidence:
        validate_source_locator_shape(
            self.source_locator,
            source_name=self.source_name,
            textbook_id=self.textbook_id,
            chapter_id=self.chapter_id,
            page_or_location=self.page_or_location,
        )
        return self


class RetrievalResult(V2Model):
    """Top-k v2 retrieval output; an empty hit list is a valid outcome."""

    schema_version: Literal["2.0"] = "2.0"
    query: NonEmptyText
    mode: RetrievalMode
    hits: tuple[RetrievedEvidence, ...] = ()
    provenance: EvidenceProvenance | None = None

    @model_validator(mode="after")
    def validate_hits(self) -> RetrievalResult:
        ranks = [hit.rank for hit in self.hits]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("retrieval ranks must be consecutive and start at 1")
        chunk_ids = [hit.chunk_id for hit in self.hits]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("retrieval hits must have unique chunk_id values")
        if self.mode is RetrievalMode.HYBRID:
            allowed = {RetrievalMode.BM25, RetrievalMode.DENSE, RetrievalMode.HYBRID}
            if any(hit.retriever_type not in allowed for hit in self.hits):
                raise ValueError("hybrid retrieval hits must use a retrieval backend mode")
        elif any(hit.retriever_type is not self.mode for hit in self.hits):
            raise ValueError("retriever_type must match retrieval mode")
        if self.provenance is not None:
            if self.mode in {RetrievalMode.DENSE, RetrievalMode.HYBRID}:
                if self.provenance.embedding_model is None:
                    raise ValueError("dense or hybrid retrieval needs embedding provenance")
            elif self.mode is RetrievalMode.BM25 and self.provenance.embedding_model is not None:
                raise ValueError("BM25 retrieval must not carry embedding_model")
        return self


class StudentProfile(V2Model):
    """Static profile input kept compatible with the existing v1 prompt seam."""

    schema_version: Literal["2.0"] = "2.0"
    profile_id: Identifier
    level: StudentLevel
    topic_levels: dict[Identifier, StudentLevel] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TopicState(V2Model):
    """Mutable-looking state derived from the append-only event stream."""

    topic_id: Identifier
    mastery_score: float = Field(default=0.5, ge=0.0, le=1.0)
    level: StudentLevel
    attempt_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    total_attempts: int = Field(default=0, ge=0)
    attempts_since_level_change: int = Field(default=0, ge=0)
    correct_attempts: int = Field(default=0, ge=0)
    misconceptions: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_misconceptions(self) -> TopicState:
        if len(self.misconceptions) != len(set(self.misconceptions)):
            raise ValueError("misconceptions must be unique")
        if self.correct_attempts > self.total_attempts:
            raise ValueError("correct_attempts cannot exceed total_attempts")
        if self.attempts_since_level_change > self.total_attempts:
            raise ValueError("attempts_since_level_change cannot exceed total_attempts")
        return self


class LearnerState(V2Model):
    """Current learner state obtained by replaying Concept Check events."""

    schema_version: Literal["2.0"] = "2.0"
    state_id: Identifier
    profile_id: Identifier
    topic_registry_version: Identifier
    state_version: int = Field(default=0, ge=0)
    derived_from_event_version: int = Field(default=0, ge=0)
    topics: dict[Identifier, TopicState] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_topic_keys(self) -> LearnerState:
        for topic_id, topic_state in self.topics.items():
            if topic_id != topic_state.topic_id:
                raise ValueError("LearnerState topic keys must match TopicState.topic_id")
        if self.derived_from_event_version > self.state_version:
            raise ValueError("derived event version cannot exceed state version")
        return self


class LearnerContextSnapshot(V2Model):
    """One immutable-by-convention profile snapshot shared by rerank and generation."""

    schema_version: Literal["2.0"] = "2.0"
    profile: StudentProfile
    profile_source: ProfileSource
    topic_id: Identifier | None = None
    topic_state: TopicState | None = None
    attempt_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    state_version: int = Field(default=0, ge=0)
    topic_resolution: TopicResolution | None = None
    resolver_called: bool = False

    @model_validator(mode="after")
    def validate_snapshot(self) -> LearnerContextSnapshot:
        if self.topic_id is None and self.topic_state is not None:
            raise ValueError("topic_state requires topic_id")
        if self.topic_id is not None and self.topic_state is None:
            raise ValueError("topic_id requires topic_state")
        if self.topic_state is not None:
            if self.topic_state.topic_id != self.topic_id:
                raise ValueError("snapshot TopicState does not match topic_id")
            if self.attempt_coverage != self.topic_state.attempt_coverage:
                raise ValueError("snapshot attempt_coverage must mirror TopicState")
            if self.profile.level is not self.topic_state.level:
                raise ValueError("snapshot profile level must mirror the TopicState level")
        if self.profile_source is ProfileSource.STATIC_PROFILE and self.resolver_called:
            raise ValueError("static profile snapshots must not claim a resolver call")
        return self


class ConceptCheckGrade(V2Model):
    """Deterministic result of grading one submitted or skipped question."""

    schema_version: Literal["0.1"] = "0.1"
    attempt_id: Identifier
    question_id: Identifier
    selected_choice: ChoiceLabel | None = None
    correct_answer: ChoiceLabel
    result: ConceptCheckResult
    performance: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_grade(self) -> ConceptCheckGrade:
        if self.result is ConceptCheckResult.CORRECT:
            if self.selected_choice != self.correct_answer or self.performance != 1.0:
                raise ValueError("correct grades require the correct choice and performance 1.0")
        elif self.result is ConceptCheckResult.INCORRECT:
            if self.selected_choice is None or self.selected_choice == self.correct_answer:
                raise ValueError("incorrect grades require a wrong selected choice")
            if self.performance != 0.0:
                raise ValueError("incorrect grades require performance 0.0")
        elif self.selected_choice is not None or self.performance is not None:
            raise ValueError("skipped grades must not carry a choice or performance")
        return self


class ConceptCheckEvent(V2Model):
    """Append-only event used to derive a LearnerState."""

    schema_version: Literal["0.1"] = "0.1"
    event_id: Identifier
    profile_id: Identifier
    attempt_id: Identifier
    question_id: Identifier
    topic_id: Identifier
    question_difficulty: StudentLevel
    selected_choice: ChoiceLabel | None = None
    performance: float | None = Field(default=None, ge=0.0, le=1.0)
    event_type: ConceptCheckEventType
    state_version_before: int = Field(ge=0)
    stream_version: int = Field(ge=1)
    created_at: datetime
    actor: Literal["student", "system", "m3"] = "student"
    reason: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_event_payload(self) -> ConceptCheckEvent:
        if self.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED:
            if self.selected_choice is None or self.performance is None:
                raise ValueError("submitted attempts require a choice and performance")
        elif self.event_type is ConceptCheckEventType.ATTEMPT_SKIPPED:
            if self.selected_choice is not None or self.performance is not None:
                raise ValueError("skipped attempts must not carry a choice or performance")
        elif self.event_type is ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN:
            if self.actor != "student" or self.reason is None:
                raise ValueError("student level overrides require an actor and reason")
        return self


class EvidenceItem(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    evidence_id: Identifier
    provider: Identifier
    textbook_id: Identifier
    document_id: Identifier
    chunk_id: Identifier
    chapter_id: Identifier
    source_name: Identifier
    page_or_location: str | None = None
    source_locator: Identifier
    text: SpanText
    rank: int = Field(ge=1)
    score: float
    token_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_locator(self) -> EvidenceItem:
        validate_source_locator_shape(
            self.source_locator,
            source_name=self.source_name,
            textbook_id=self.textbook_id,
            chapter_id=self.chapter_id,
            page_or_location=self.page_or_location,
        )
        return self


class EvidenceBundle(V2Model):
    """Evidence context passed to generation and retained for audit."""

    schema_version: Literal["2.0"] = "2.0"
    query: NonEmptyText
    retrieval_mode: RetrievalMode
    evidence_items: tuple[EvidenceItem, ...] = ()
    prompt_context: NonEmptyText | None = None
    citation_map: dict[Identifier, Identifier] = Field(default_factory=dict)
    token_count: int = Field(default=0, ge=0)
    retrieval_provenance: EvidenceProvenance | None = None
    run_provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_evidence_map(self) -> EvidenceBundle:
        evidence_ids = [item.evidence_id for item in self.evidence_items]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        expected = {item.evidence_id: item.chunk_id for item in self.evidence_items}
        if self.citation_map != expected:
            raise ValueError("citation_map must map every evidence ID to its chunk ID")
        if self.token_count < sum(item.token_count for item in self.evidence_items):
            raise ValueError("token_count must include every evidence item")
        return self


class GeneratedAnswer(V2Model):
    """A grounded answer or an explicit refusal."""

    schema_version: Literal["2.0"] = "2.0"
    final_choice: ChoiceLabel | None = None
    explanation: NonEmptyText
    citations: tuple[Identifier, ...] = ()
    abstained: bool = False

    @model_validator(mode="after")
    def validate_answer(self) -> GeneratedAnswer:
        if len(self.citations) != len(set(self.citations)):
            raise ValueError("citations must be unique")
        if self.abstained:
            if self.final_choice is not None:
                raise ValueError("an abstained answer must not select final_choice")
            if self.citations:
                raise ValueError("an abstained answer must not cite evidence")
        elif not self.citations:
            raise ValueError("a non-abstained answer must cite at least one chunk")
        return self


class ValidatedAnswer(V2Model):
    """Answer plus citations resolved against its evidence bundle."""

    schema_version: Literal["2.0"] = "2.0"
    answer: GeneratedAnswer
    resolved_citations: tuple[Identifier, ...] = ()
    citation_status: Literal["passed", "failed", "skipped"]
    run_provenance: dict[str, str] = Field(default_factory=dict)
    abstained: bool = False

    @model_validator(mode="after")
    def derive_abstention(self) -> ValidatedAnswer:
        self.abstained = self.answer.abstained
        if self.citation_status == "passed" and not self.answer.abstained:
            if not self.resolved_citations:
                raise ValueError("a passed non-abstained answer needs resolved citations")
        return self


class IndexArtifact(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    artifact_id: Identifier
    index_type: Identifier
    index_format_version: Identifier
    location: Identifier
    asset_relpaths: tuple[Identifier, ...] = Field(min_length=1)
    corpus_version: Identifier
    corpus_hash: Identifier
    manifest_hash: Identifier
    chunk_config_hash: Identifier
    required_textbook_ids: tuple[Identifier, ...] = Field(min_length=1)
    included_textbook_ids: tuple[Identifier, ...] = Field(min_length=1)
    chunk_count: int = Field(gt=0)
    chunk_ids: tuple[Identifier, ...] = Field(min_length=1)
    embedding_model: Identifier | None = None
    embedding_revision: Identifier | None = None
    embedding_dimension: int | None = Field(default=None, gt=0)
    similarity_metric: Identifier
    normalise_embeddings: bool
    index_version: Identifier
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_compatibility_identity(self) -> IndexArtifact:
        if len(set(self.required_textbook_ids)) != len(self.required_textbook_ids):
            raise ValueError("required_textbook_ids must be unique")
        if len(set(self.included_textbook_ids)) != len(self.included_textbook_ids):
            raise ValueError("included_textbook_ids must be unique")
        if not set(self.included_textbook_ids).issubset(self.required_textbook_ids):
            raise ValueError("included_textbook_ids must be a subset of required_textbook_ids")
        if self.chunk_count != len(self.chunk_ids):
            raise ValueError("chunk_count must equal the chunk_ids length")
        if len(set(self.chunk_ids)) != len(self.chunk_ids):
            raise ValueError("chunk_ids must be unique and ordered")
        for asset_path in self.asset_relpaths:
            relative_asset = PurePosixPath(asset_path)
            if relative_asset.is_absolute() or ".." in relative_asset.parts:
                raise ValueError("asset_relpaths must remain inside the v2 output directory")
        if self.embedding_model is not None and self.embedding_dimension is None:
            raise ValueError("embedding_dimension is required with embedding_model")
        return self


class PipelineRun(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    run_id: Identifier
    environment: Literal["development", "staging", "production"]
    corpus_version: Identifier
    manifest_hash: Identifier | None = None
    retrieval_config_hash: Identifier | None = None
    generation_config_hash: Identifier | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    question: NonEmptyText | None = None
    retrieval: RetrievalResult | None = None
    evidence_bundle: EvidenceBundle | None = None
    answer: GeneratedAnswer | None = None
    validated_answer: ValidatedAnswer | None = None
    learner_context: LearnerContextSnapshot | None = None
    profile_source: ProfileSource | None = None
    resolver_called: bool | None = None
    concept_check_question_id: Identifier | None = None
