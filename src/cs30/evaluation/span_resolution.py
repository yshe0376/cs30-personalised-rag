"""Resolve raw M3 chapter-local Gold spans against a merged corpus."""

from __future__ import annotations

from dataclasses import dataclass

from cs30.contracts import OpenStaxDocument, TextBlock

from .models import GoldEvidenceSpan, SpanResolutionMethod, SpanResolutionStatus
from .openstax_archive import OpenStaxArchiveCorpus


@dataclass(frozen=True, slots=True)
class SpanResolution:
    """The auditable outcome of resolving one raw M3 evidence span."""

    span_id: str
    status: SpanResolutionStatus
    method: SpanResolutionMethod | None
    chapter_char_start: int
    chapter_char_end: int
    corpus_char_start: int | None
    corpus_char_end: int | None
    original_block_id: str | None
    resolved_block_id: str | None
    message: str


def resolve_span_to_corpus(
    span: GoldEvidenceSpan,
    corpus: OpenStaxArchiveCorpus | OpenStaxDocument,
) -> SpanResolution:
    """Resolve a chapter-local span without changing its raw M3 coordinates."""

    document = corpus.document if isinstance(corpus, OpenStaxArchiveCorpus) else corpus
    base = {
        "span_id": span.span_id,
        "chapter_char_start": span.char_start,
        "chapter_char_end": span.char_end,
        "original_block_id": span.block_id,
    }

    if span.document_id != document.document_id:
        return _unresolved(
            base,
            SpanResolutionStatus.STALE,
            "span document_id does not match the selected corpus",
        )

    chapter = next((item for item in document.chapters if item.chapter_id == span.chapter_id), None)
    if chapter is None:
        return _unresolved(
            base,
            SpanResolutionStatus.STALE,
            f"chapter {span.chapter_id!r} is absent from the selected corpus",
        )

    chapter_text = document.text[chapter.char_start : chapter.char_end]
    if span.char_end > len(chapter_text) or (
        chapter_text[span.char_start : span.char_end] != span.verbatim_text
    ):
        return _unresolved(
            base,
            SpanResolutionStatus.STALE,
            "chapter-local coordinates do not match the span verbatim text",
        )

    blocks = [block for block in document.blocks if block.chapter_id == chapter.chapter_id]
    identified_block = _block_by_id(document.blocks, span.block_id)
    if identified_block is not None and identified_block.chapter_id != chapter.chapter_id:
        return _unresolved(
            base,
            SpanResolutionStatus.STALE,
            "span block_id belongs to a different chapter",
        )

    corpus_start = chapter.char_start + span.char_start
    corpus_end = chapter.char_start + span.char_end
    if identified_block is not None and _contains(identified_block, corpus_start, corpus_end):
        return SpanResolution(
            **base,
            status=SpanResolutionStatus.RESOLVED,
            method=SpanResolutionMethod.BLOCK_ID,
            corpus_char_start=corpus_start,
            corpus_char_end=corpus_end,
            resolved_block_id=identified_block.block_id,
            message="resolved from the chapter-local span and block_id",
        )

    matches = _verbatim_matches(chapter_text, span.verbatim_text)
    if not matches:
        return _unresolved(
            base,
            SpanResolutionStatus.STALE,
            "span verbatim text does not occur in its chapter",
        )
    if len(matches) != 1:
        return _unresolved(
            base,
            SpanResolutionStatus.AMBIGUOUS,
            "span verbatim text occurs multiple times in its chapter",
        )

    match_start = chapter.char_start + matches[0]
    match_end = match_start + len(span.verbatim_text)
    containing_blocks = [
        block for block in blocks if _contains(block, match_start, match_end)
    ]
    if len(containing_blocks) != 1:
        return _unresolved(
            base,
            SpanResolutionStatus.STALE,
            "unique verbatim match is not contained in one text block",
        )

    block = containing_blocks[0]
    return SpanResolution(
        **base,
        status=SpanResolutionStatus.RESOLVED,
        method=SpanResolutionMethod.VERBATIM_UNIQUE,
        corpus_char_start=match_start,
        corpus_char_end=match_end,
        resolved_block_id=block.block_id,
        message="resolved from a unique same-chapter verbatim match",
    )


def _unresolved(
    base: dict[str, object],
    status: SpanResolutionStatus,
    message: str,
) -> SpanResolution:
    return SpanResolution(
        **base,
        status=status,
        method=None,
        corpus_char_start=None,
        corpus_char_end=None,
        resolved_block_id=None,
        message=message,
    )


def _block_by_id(blocks: list[TextBlock], block_id: str | None) -> TextBlock | None:
    if block_id is None:
        return None
    return next((block for block in blocks if block.block_id == block_id), None)


def _contains(block: TextBlock, start: int, end: int) -> bool:
    return block.char_start <= start <= end <= block.char_end


def _verbatim_matches(text: str, verbatim_text: str) -> list[int]:
    matches: list[int] = []
    offset = 0
    while True:
        found = text.find(verbatim_text, offset)
        if found == -1:
            return matches
        matches.append(found)
        offset = found + 1
