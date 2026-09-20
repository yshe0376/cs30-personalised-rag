"""Strict v2 contracts for multi-textbook corpus assets.

The v1 contracts remain in ``cs30.contracts``.  This module intentionally does
not use their OpenStax aliases: a v2 document must carry its provider and
textbook identity as first-class fields.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SpanText = Annotated[str, Field(min_length=1)]


class V2Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ContentType(StrEnum):
    BODY = "body"
    HEADING = "heading"
    LEARNING_OBJECTIVE = "learning_objective"
    FIGURE_CAPTION = "figure_caption"
    TABLE = "table"
    EQUATION = "equation"
    FORMULA = "formula"
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
    block_id: Identifier
    chapter_id: Identifier
    section_id: Identifier | None = None
    section_title: Identifier | None = None
    content_type: ContentType = ContentType.BODY
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    page_or_location: Identifier | None = None
    asset_ref: Identifier | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_span(self) -> TextBlock:
        if self.char_end <= self.char_start:
            raise ValueError("block char_end must be greater than char_start")
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
    schema_version: Literal["2.0"] = "2.0"
    chunk_id: Identifier
    provider: Identifier
    textbook_id: Identifier
    document_id: Identifier
    chapter_id: Identifier
    source_name: Identifier
    source_uri: str | None = None
    page_or_location: str | None = None
    source_locator: Identifier
    text: SpanText
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    spans: tuple[ChunkSpan, ...] = Field(min_length=1)
    chunker_version: Identifier
    chunk_config_hash: Identifier
    token_count: int = Field(gt=0)
    embed_text: SpanText | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_traceable_text(self) -> Chunk:
        if self.char_end <= self.char_start:
            raise ValueError("chunk char_end must be greater than char_start")
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
        return self

    @property
    def embedding_input(self) -> str:
        return self.text if self.embed_text is None else self.embed_text


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
    source_uri: str | None = None
    page_or_location: str | None = None
    source_locator: Identifier
    text: SpanText
    score: float
    rank: int = Field(ge=1)
    retriever_type: RetrievalMode


class EvidenceItem(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    evidence_id: Identifier
    provider: Identifier
    textbook_id: Identifier
    document_id: Identifier
    chunk_id: Identifier
    chapter_id: Identifier
    source_name: Identifier
    source_uri: str | None = None
    page_or_location: str | None = None
    source_locator: Identifier
    text: SpanText
    rank: int = Field(ge=1)
    score: float


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
    required_textbook_ids: tuple[Identifier, ...] = Field(min_length=3)
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
