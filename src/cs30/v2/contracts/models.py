"""Strict v2 contracts for multi-textbook corpus assets.

The v1 contracts remain in ``cs30.contracts``.  This module intentionally does
not use their OpenStax aliases: a v2 document must carry its provider and
textbook identity as first-class fields.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from cs30.v2.ids import (
    page_location,
    sha256_text,
    source_locator,
    validate_source_locator_shape,
)

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SpanText = Annotated[str, Field(min_length=1)]


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
