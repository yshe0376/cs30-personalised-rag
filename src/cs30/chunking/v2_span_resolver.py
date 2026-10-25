"""Shared M4 resolver for v2 Gold and Concept Check evidence spans.

The durable :class:`~cs30.v2.contracts.EvidenceSpan` stores chapter-local
coordinates and no chunk IDs.  This module resolves that span against one
published corpus without changing the annotation.  Gold conversion and
Concept Check publication deliberately use this one implementation so their
leakage checks compare the same current-corpus coordinates.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from cs30.v2.contracts import (
    Chunk,
    ConceptCheckQuestion,
    ConceptCheckQuestionBinding,
    EvidenceSpan,
    EvidenceSpanBinding,
    SpanResolutionMethod,
    SpanResolutionStatus,
)
from cs30.v2.corpus import LoadedCorpus


def resolve_evidence_span(span: EvidenceSpan, corpus: LoadedCorpus) -> EvidenceSpanBinding:
    """Resolve one stable span through the frozen M4 matching order.

    Matching is fail-closed and follows the Concept Check/Gold contract:

    1. the supplied parser ``block_id``;
    2. chapter-local offsets, verified against the verbatim text/hash;
    3. one unique verbatim match in the same textbook and chapter.

    A successful result may name several chunks when a retained evidence span
    crosses a chunk boundary.  Failed resolution is returned as ``stale`` or
    ``ambiguous`` without carrying a guessed location or chunk ID.
    """

    candidates = tuple(
        chunk
        for chunk in corpus.chunks
        if chunk.textbook_id == span.textbook_id and chunk.chapter_id == span.chapter_id
    )
    if not candidates:
        return _unresolved(span, corpus, SpanResolutionStatus.STALE)

    if span.block_id is not None:
        block_locations = _block_locations(span, candidates)
        selected = _select_expected_or_unique(span, candidates, block_locations)
        if selected is not None:
            return _resolved(
                span,
                corpus,
                selected,
                SpanResolutionMethod.BLOCK_ID,
            )

    offset_locations = _chapter_offset_locations(span, candidates)
    if len(offset_locations) == 1:
        return _resolved(
            span,
            corpus,
            next(iter(offset_locations)),
            SpanResolutionMethod.CHAPTER_OFFSET,
        )
    if len(offset_locations) > 1:
        return _unresolved(span, corpus, SpanResolutionStatus.AMBIGUOUS)

    verbatim_locations = _verbatim_locations(span, candidates)
    if len(verbatim_locations) == 1:
        return _resolved(
            span,
            corpus,
            next(iter(verbatim_locations)),
            SpanResolutionMethod.VERBATIM_UNIQUE,
        )
    return _unresolved(
        span,
        corpus,
        (
            SpanResolutionStatus.AMBIGUOUS
            if len(verbatim_locations) > 1
            else SpanResolutionStatus.STALE
        ),
    )


def bind_concept_check_question(
    question: ConceptCheckQuestion,
    corpus: LoadedCorpus,
) -> ConceptCheckQuestionBinding:
    """Bind every durable practice-question anchor to one corpus version.

    Unresolved anchors remain explicit in the returned binding.  The existing
    ``ConceptCheckQuestionRelease`` publication gate then rejects stale or
    ambiguous results instead of silently dropping them.
    """

    return ConceptCheckQuestionBinding(
        question_id=question.question_id,
        corpus_version=corpus.manifest.corpus_version,
        corpus_hash=corpus.manifest.corpus_hash,
        bindings=tuple(
            resolve_evidence_span(anchor, corpus) for anchor in question.evidence_anchors
        ),
    )


Location = tuple[str, int, int, tuple[str, ...]]


def _block_locations(span: EvidenceSpan, chunks: Sequence[Chunk]) -> set[Location]:
    locations: set[Location] = set()
    for chunk in chunks:
        for block in chunk.spans:
            if block.block_id != span.block_id:
                continue
            relative_start = block.char_start - chunk.char_start
            relative_end = block.char_end - chunk.char_start
            block_text = chunk.text[relative_start:relative_end]
            search_from = 0
            while (found := block_text.find(span.verbatim_text, search_from)) >= 0:
                start = block.char_start + found
                end = start + len(span.verbatim_text)
                location = _location_for_interval(chunks, chunk.document_id, start, end)
                if location is not None:
                    locations.add(location)
                search_from = found + 1
    return locations


def _select_expected_or_unique(
    span: EvidenceSpan,
    chunks: Sequence[Chunk],
    locations: set[Location],
) -> Location | None:
    if not locations:
        return None
    expected = set(_chapter_offset_locations(span, chunks))
    matching_expected = locations.intersection(expected)
    if len(matching_expected) == 1:
        return next(iter(matching_expected))
    if len(locations) == 1:
        return next(iter(locations))
    return None


def _chapter_offset_locations(span: EvidenceSpan, chunks: Sequence[Chunk]) -> set[Location]:
    by_document: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.document_id].append(chunk)

    locations: set[Location] = set()
    for document_id, document_chunks in by_document.items():
        chapter_start = _chapter_start(document_chunks)
        if chapter_start is None:
            continue
        start = chapter_start + span.chapter_char_start
        end = chapter_start + span.chapter_char_end
        location = _location_for_interval(document_chunks, document_id, start, end)
        if location is None:
            continue
        if _text_for_interval(document_chunks, start, end) == span.verbatim_text:
            locations.add(location)
    return locations


def _chapter_start(chunks: Sequence[Chunk]) -> int | None:
    """Read the chapter base retained by the production M4 chunk metadata.

    ``parent_char_start`` may describe a section for an individual chunk, but
    the minimum value over a chapter is its parent chapter start in the frozen
    production corpus.  Corpora without that provenance skip offset matching
    and fall back to the exact verbatim rule; no base is guessed.
    """

    starts: list[int] = []
    for chunk in chunks:
        raw = chunk.metadata.get("parent_char_start")
        if raw is None:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if 0 <= value <= chunk.char_start:
            starts.append(value)
    return min(starts) if starts else None


def _verbatim_locations(span: EvidenceSpan, chunks: Sequence[Chunk]) -> set[Location]:
    locations: set[Location] = set()
    for document_id, run_start, run_text, run_chunks in _contiguous_runs(chunks):
        search_from = 0
        while (found := run_text.find(span.verbatim_text, search_from)) >= 0:
            start = run_start + found
            end = start + len(span.verbatim_text)
            location = _location_for_interval(run_chunks, document_id, start, end)
            if location is not None:
                locations.add(location)
            search_from = found + 1
    return locations


def _contiguous_runs(
    chunks: Sequence[Chunk],
) -> Iterable[tuple[str, int, str, tuple[Chunk, ...]]]:
    by_document: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.document_id].append(chunk)
    for document_id, document_chunks in sorted(by_document.items()):
        ordered = sorted(document_chunks, key=lambda item: (item.char_start, item.chunk_id))
        run: list[Chunk] = []
        for chunk in ordered:
            if run and chunk.char_start != run[-1].char_end:
                yield _run(document_id, run)
                run = []
            run.append(chunk)
        if run:
            yield _run(document_id, run)


def _run(document_id: str, chunks: Sequence[Chunk]) -> tuple[str, int, str, tuple[Chunk, ...]]:
    return document_id, chunks[0].char_start, "".join(chunk.text for chunk in chunks), tuple(chunks)


def _location_for_interval(
    chunks: Sequence[Chunk],
    document_id: str,
    start: int,
    end: int,
) -> Location | None:
    overlapping = sorted(
        (
            chunk
            for chunk in chunks
            if chunk.document_id == document_id
            and max(start, chunk.char_start) < min(end, chunk.char_end)
        ),
        key=lambda item: (item.char_start, item.chunk_id),
    )
    if not overlapping or overlapping[0].char_start > start:
        return None
    covered_end = start
    for chunk in overlapping:
        if chunk.char_start > covered_end:
            return None
        covered_end = max(covered_end, min(end, chunk.char_end))
        if covered_end >= end:
            break
    if covered_end < end:
        return None
    return document_id, start, end, tuple(chunk.chunk_id for chunk in overlapping)


def _text_for_interval(chunks: Sequence[Chunk], start: int, end: int) -> str | None:
    pieces: list[str] = []
    cursor = start
    for chunk in sorted(chunks, key=lambda item: (item.char_start, item.chunk_id)):
        overlap_start = max(start, chunk.char_start)
        overlap_end = min(end, chunk.char_end)
        if overlap_start >= overlap_end:
            continue
        if overlap_start != cursor:
            return None
        pieces.append(chunk.text[overlap_start - chunk.char_start : overlap_end - chunk.char_start])
        cursor = overlap_end
        if cursor == end:
            return "".join(pieces)
    return None


def _resolved(
    span: EvidenceSpan,
    corpus: LoadedCorpus,
    location: Location,
    method: SpanResolutionMethod,
) -> EvidenceSpanBinding:
    document_id, start, end, chunk_ids = location
    return EvidenceSpanBinding(
        span_id=span.span_id,
        textbook_id=span.textbook_id,
        corpus_version=corpus.manifest.corpus_version,
        corpus_hash=corpus.manifest.corpus_hash,
        resolution_status=SpanResolutionStatus.RESOLVED,
        resolution_method=method,
        document_id=document_id,
        char_start=start,
        char_end=end,
        chunk_ids=chunk_ids,
    )


def _unresolved(
    span: EvidenceSpan,
    corpus: LoadedCorpus,
    status: SpanResolutionStatus,
) -> EvidenceSpanBinding:
    return EvidenceSpanBinding(
        span_id=span.span_id,
        textbook_id=span.textbook_id,
        corpus_version=corpus.manifest.corpus_version,
        corpus_hash=corpus.manifest.corpus_hash,
        resolution_status=status,
    )
