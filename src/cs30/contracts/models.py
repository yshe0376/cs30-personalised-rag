"""Version 1 contracts shared by all Week 1 modules.

Character spans use Python slicing semantics: ``char_start`` is inclusive and
``char_end`` is exclusive. Unknown fields are rejected so interface drift is
detected during integration rather than silently ignored.

The contract layer never rewrites payload data. Fields holding verbatim
textbook text are bound to a character span, so stripping them would move the
text without moving the offsets. Only identifier-like and free-text fields are
normalised.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ChoiceLabel = Literal["A", "B", "C", "D"]

# Identifiers and provenance labels: surrounding whitespace carries no meaning.
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Free text without span semantics; normalisation is safe.
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Verbatim source text bound to ``char_start`` / ``char_end``. Never stripped.
SpanText = Annotated[str, Field(min_length=1)]


class ContractModel(BaseModel):
    """Strict base model for frozen cross-module contracts."""

    model_config = ConfigDict(extra="forbid")


class StudentLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class OpenStaxChapter(ContractModel):
    chapter_id: Identifier
    title: NonEmptyText
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_span(self) -> "OpenStaxChapter":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if self.page_start and self.page_end and self.page_end < self.page_start:
            raise ValueError("page_end must not precede page_start")
        return self


class ContentType(StrEnum):
    """What a block of textbook text is, so retrieval can filter by role.

    Explanatory prose and a question about that prose are different things.
    Retrieving an exercise as supporting evidence yields an answer that looks
    grounded but rests on the wrong kind of text, which the citation check
    cannot detect.
    """

    BODY = "body"
    HEADING = "heading"
    LEARNING_OBJECTIVE = "learning_objective"
    FIGURE_CAPTION = "figure_caption"
    TABLE = "table"
    EQUATION = "equation"
    EXAMPLE = "example"
    CHECK_UNDERSTANDING = "check_understanding"
    SIDEBAR = "sidebar"
    SUMMARY = "summary"
    CONCEPTUAL_QUESTION = "conceptual_question"
    PROBLEM = "problem"
    GLOSSARY = "glossary"
    OTHER = "other"


class TextBlock(ContractModel):
    """One structural unit the parser recovered, addressed by span.

    A block carries no text of its own. ``OpenStaxDocument.text`` is the single
    source of truth and ``block_text()`` slices it; storing the same text twice
    would let the copies drift apart, which is what the span convention exists
    to prevent.

    Blocks preserve parser structure (section, page, role) across the module
    seam. Without them a chunker would have to re-derive that structure from
    raw text, duplicating work the parser already did.
    """

    block_id: Identifier | None = None
    chapter_id: Identifier
    section_id: Identifier | None = None
    section_title: NonEmptyText | None = None
    content_type: ContentType = ContentType.BODY
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_span(self) -> "TextBlock":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if self.page_start and self.page_end and self.page_end < self.page_start:
            raise ValueError("page_end must not precede page_start")
        return self


class OpenStaxDocument(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    document_id: Identifier
    title: NonEmptyText
    version: Identifier
    source: Identifier
    document_hash: Identifier
    parser_version: Identifier
    text: SpanText
    chapters: list[OpenStaxChapter] = Field(min_length=1)
    blocks: list[TextBlock] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_chapter_spans(self) -> "OpenStaxDocument":
        seen: set[str] = set()
        previous_end = 0
        for chapter in self.chapters:
            if chapter.chapter_id in seen:
                raise ValueError(f"duplicate chapter_id: {chapter.chapter_id}")
            if chapter.char_end > len(self.text):
                raise ValueError(f"chapter span exceeds document text: {chapter.chapter_id}")
            if chapter.char_start < previous_end:
                raise ValueError("chapter spans must be ordered and non-overlapping")
            seen.add(chapter.chapter_id)
            previous_end = chapter.char_end
        return self

    @model_validator(mode="after")
    def validate_block_spans(self) -> "OpenStaxDocument":
        chapter_spans = {c.chapter_id: (c.char_start, c.char_end) for c in self.chapters}
        seen: set[str] = set()
        previous_end = 0
        for position, block in enumerate(self.blocks):
            label = block.block_id or f"index {position}"
            if block.block_id is not None:
                if block.block_id in seen:
                    raise ValueError(f"duplicate block_id: {block.block_id}")
                seen.add(block.block_id)
            if block.char_end > len(self.text):
                raise ValueError(f"block span exceeds document text: {label}")
            if block.char_start < previous_end:
                raise ValueError(f"block spans must be ordered and non-overlapping: {label}")
            chapter_span = chapter_spans.get(block.chapter_id)
            if chapter_span is None:
                raise ValueError(
                    f"block {label} references unknown chapter_id: {block.chapter_id}"
                )
            if block.char_start < chapter_span[0] or block.char_end > chapter_span[1]:
                raise ValueError(f"block {label} falls outside chapter {block.chapter_id}")
            previous_end = block.char_end
        return self

    def block_text(self, block: TextBlock) -> str:
        """The verbatim text a block points at."""

        return self.text[block.char_start : block.char_end]


class Chunk(ContractModel):
    """One retrievable unit, and optionally an enriched form of it.

    ``text`` is verbatim corpus text bound to a span: it is what gets cited and
    shown to a student. ``embed_text`` is what the embedder sees, which may
    carry added context such as the chapter and section a passage came from.

    Keeping them apart lets retrieval be enriched without the citation drifting
    from the source. ``embed_text`` must still contain ``text`` verbatim, so a
    chunk can never be retrieved on the strength of wording that is absent from
    the evidence it cites.
    """

    schema_version: Literal["1.0"] = "1.0"
    chunk_id: Identifier
    document_id: Identifier
    chapter_id: Identifier
    text: SpanText
    source: Identifier
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    token_count: int = Field(gt=0)
    metadata: dict[str, str] = Field(default_factory=dict)
    embed_text: SpanText | None = None

    @model_validator(mode="after")
    def validate_span(self) -> "Chunk":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        expected = self.char_end - self.char_start
        if len(self.text) != expected:
            raise ValueError(
                f"text length {len(self.text)} does not match span "
                f"[{self.char_start}, {self.char_end}) of length {expected}"
            )
        if self.embed_text is not None and self.text not in self.embed_text:
            raise ValueError("embed_text must contain the chunk text verbatim")
        return self

    @property
    def embedding_input(self) -> str:
        """What the embedder receives: the enriched text when present."""

        return self.text if self.embed_text is None else self.embed_text


class IndexArtifact(ContractModel):
    """Portable manifest connecting an index builder to a retriever."""

    schema_version: Literal["1.0"] = "1.0"
    artifact_id: Identifier
    index_type: Identifier
    location: Identifier
    chunk_count: int = Field(gt=0)
    metadata: dict[str, str] = Field(default_factory=dict)


class SciQQuestion(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    question_id: Identifier
    question: NonEmptyText
    choices: dict[ChoiceLabel, NonEmptyText]
    correct_choice: ChoiceLabel
    support: NonEmptyText
    in_scope: bool = True
    source: Identifier = "SciQ"

    @model_validator(mode="after")
    def validate_choices(self) -> "SciQQuestion":
        if set(self.choices) != {"A", "B", "C", "D"}:
            raise ValueError("choices must contain exactly A, B, C, and D")
        return self


class RetrievalHit(ContractModel):
    chunk_id: Identifier
    text: SpanText
    chapter_id: Identifier
    source: Identifier
    score: float
    rank: int = Field(ge=1)


class RetrievalResult(ContractModel):
    """Top-K evidence for one query.

    An empty ``hits`` list is a valid, meaningful answer: retrieval ran and
    found nothing relevant. That is distinct from an index or input failure,
    which raises instead.
    """

    schema_version: Literal["1.0"] = "1.0"
    query: NonEmptyText
    hits: list[RetrievalHit] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ranks(self) -> "RetrievalResult":
        ranks = [hit.rank for hit in self.hits]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("retrieval ranks must be consecutive and start at 1")
        if len({hit.chunk_id for hit in self.hits}) != len(self.hits):
            raise ValueError("retrieval hits must have unique chunk_id values")
        return self


class StudentProfile(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    profile_id: Identifier
    level: StudentLevel
    topic_levels: dict[str, StudentLevel] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class GeneratedAnswer(ContractModel):
    """A grounded answer, or an explicit refusal to answer.

    Abstention is a first-class outcome rather than an error: the model may
    report that the retrieved evidence does not support an answer.
    """

    schema_version: Literal["1.0"] = "1.0"
    final_choice: ChoiceLabel | None = None
    explanation: NonEmptyText
    citations: list[Identifier] = Field(default_factory=list)
    abstained: bool = False

    @model_validator(mode="after")
    def validate_answer(self) -> "GeneratedAnswer":
        if len(set(self.citations)) != len(self.citations):
            raise ValueError("citations must be unique")
        if self.abstained:
            if self.final_choice is not None:
                raise ValueError("an abstained answer must not select a final_choice")
            if self.citations:
                raise ValueError("an abstained answer must not cite evidence")
        elif not self.citations:
            raise ValueError("a non-abstained answer must cite at least one chunk")
        return self


class PipelineRun(ContractModel):
    """One end-to-end execution, including everything needed to reproduce it.

    ``metadata`` carries run parameters (model, top_k, latency, token usage) so
    a row in a later ablation table can be traced back to its configuration.
    """

    schema_version: Literal["1.0"] = "1.0"
    run_id: Identifier
    mode: Literal["fixture", "real"]
    question: NonEmptyText
    question_id: Identifier | None = None
    profile: StudentProfile
    retrieval: RetrievalResult
    answer: GeneratedAnswer
    citation_integrity: Literal["passed", "failed", "skipped"]
    metadata: dict[str, str] = Field(default_factory=dict)
