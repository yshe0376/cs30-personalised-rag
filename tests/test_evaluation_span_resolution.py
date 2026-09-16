import pytest

from cs30.contracts import OpenStaxChapter, OpenStaxDocument, TextBlock
from cs30.evaluation import (
    GoldEvidenceSpan,
    SpanResolutionMethod,
    SpanResolutionStatus,
    resolve_span_to_corpus,
)


@pytest.fixture
def test_corpus() -> OpenStaxDocument:
    first = "Alpha.\nBeta."
    second = "Gamma."
    repeated = "Repeat.\nRepeat."
    separator = "\n\n"
    text = separator.join((first, second, repeated))
    second_start = len(first) + len(separator)
    repeated_start = second_start + len(second) + len(separator)
    return OpenStaxDocument(
        document_id="test-book",
        title="Test Book",
        version="1",
        source="test",
        document_hash="test-hash",
        parser_version="test-parser",
        text=text,
        chapters=[
            OpenStaxChapter(chapter_id="one", title="One", char_start=0, char_end=len(first)),
            OpenStaxChapter(
                chapter_id="two",
                title="Two",
                char_start=second_start,
                char_end=second_start + len(second),
            ),
            OpenStaxChapter(
                chapter_id="three",
                title="Three",
                char_start=repeated_start,
                char_end=repeated_start + len(repeated),
            ),
        ],
        blocks=[
            TextBlock(block_id="one-alpha", chapter_id="one", char_start=0, char_end=6),
            TextBlock(block_id="one-beta", chapter_id="one", char_start=7, char_end=12),
            TextBlock(
                block_id="two-gamma",
                chapter_id="two",
                char_start=second_start,
                char_end=second_start + len(second),
            ),
            TextBlock(
                block_id="three-first-repeat",
                chapter_id="three",
                char_start=repeated_start,
                char_end=repeated_start + 7,
            ),
            TextBlock(
                block_id="three-second-repeat",
                chapter_id="three",
                char_start=repeated_start + 8,
                char_end=repeated_start + len(repeated),
            ),
        ],
    )


def _span(
    span_id: str,
    *,
    chapter_id: str,
    char_start: int,
    char_end: int,
    verbatim_text: str,
    block_id: str | None,
) -> GoldEvidenceSpan:
    return GoldEvidenceSpan(
        span_id=span_id,
        document_id="test-book",
        chapter_id=chapter_id,
        char_start=char_start,
        char_end=char_end,
        verbatim_text=verbatim_text,
        block_id=block_id,
    )


def test_resolves_valid_block_id_to_global_coordinates(test_corpus: OpenStaxDocument) -> None:
    valid_span = _span(
        "valid",
        chapter_id="one",
        char_start=0,
        char_end=6,
        verbatim_text="Alpha.",
        block_id="one-alpha",
    )

    result = resolve_span_to_corpus(valid_span, test_corpus)

    assert result.status is SpanResolutionStatus.RESOLVED
    assert result.method is SpanResolutionMethod.BLOCK_ID
    assert test_corpus.text[result.corpus_char_start : result.corpus_char_end] == "Alpha."


def test_rejects_wrong_chapter_block(test_corpus: OpenStaxDocument) -> None:
    wrong_chapter_span = _span(
        "wrong-chapter",
        chapter_id="two",
        char_start=0,
        char_end=6,
        verbatim_text="Gamma.",
        block_id="one-alpha",
    )

    result = resolve_span_to_corpus(wrong_chapter_span, test_corpus)

    assert result.status is SpanResolutionStatus.STALE
    assert result.corpus_char_start is None
    assert "block_id" in result.message.lower()
    assert "different chapter" in result.message.lower()


def test_rejects_verbatim_text_mismatch(test_corpus: OpenStaxDocument) -> None:
    mismatched_span = _span(
        "mismatch",
        chapter_id="one",
        char_start=0,
        char_end=6,
        verbatim_text="Omega.",
        block_id="one-alpha",
    )

    result = resolve_span_to_corpus(mismatched_span, test_corpus)

    assert result.status is SpanResolutionStatus.STALE
    assert result.corpus_char_start is None
    assert "verbatim" in result.message.lower()


def test_unique_verbatim_fallback_is_explicit(test_corpus: OpenStaxDocument) -> None:
    span_without_valid_block = _span(
        "fallback",
        chapter_id="one",
        char_start=7,
        char_end=12,
        verbatim_text="Beta.",
        block_id="stale-block-id",
    )

    result = resolve_span_to_corpus(span_without_valid_block, test_corpus)

    assert result.status is SpanResolutionStatus.RESOLVED
    assert result.method is SpanResolutionMethod.VERBATIM_UNIQUE
    assert result.resolved_block_id == "one-beta"


def test_missing_block_id_uses_replayed_chapter_offset(
    test_corpus: OpenStaxDocument,
) -> None:
    span_without_block = _span(
        "chapter-offset",
        chapter_id="three",
        char_start=0,
        char_end=7,
        verbatim_text="Repeat.",
        block_id=None,
    )

    result = resolve_span_to_corpus(span_without_block, test_corpus)

    assert result.status is SpanResolutionStatus.RESOLVED
    assert result.method is SpanResolutionMethod.CHAPTER_OFFSET
    assert result.resolved_block_id == "three-first-repeat"
    assert test_corpus.text[result.corpus_char_start : result.corpus_char_end] == "Repeat."


def test_ambiguous_verbatim_fallback_is_not_silent(test_corpus: OpenStaxDocument) -> None:
    repeated_text_span = _span(
        "ambiguous",
        chapter_id="three",
        char_start=0,
        char_end=7,
        verbatim_text="Repeat.",
        block_id="missing-block-id",
    )

    result = resolve_span_to_corpus(repeated_text_span, test_corpus)

    assert result.status is SpanResolutionStatus.AMBIGUOUS
    assert result.corpus_char_start is None
    assert result.message


def test_cross_block_span_requires_manual_review(test_corpus: OpenStaxDocument) -> None:
    cross_block_span = _span(
        "cross-block",
        chapter_id="one",
        char_start=0,
        char_end=12,
        verbatim_text="Alpha.\nBeta.",
        block_id="one-alpha",
    )

    result = resolve_span_to_corpus(cross_block_span, test_corpus)

    assert result.status is SpanResolutionStatus.AMBIGUOUS
    assert result.corpus_char_start is None
    assert "block" in result.message.lower()
