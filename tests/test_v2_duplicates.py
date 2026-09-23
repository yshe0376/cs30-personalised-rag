"""Cross-textbook duplicate block reporting."""

from __future__ import annotations

import pytest
from test_v2_contracts import make_document

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.corpus import DuplicateBlockGroup, find_cross_textbook_duplicates

LONG = "Momentum is conserved whenever the net external force on a system is zero.\n"
TAIL = "[[FORMULA:p=mv]]\n[[IMAGE:fig-1]]"


def _report(*documents):
    return find_cross_textbook_duplicates(
        documents, corpus_version="2.0.0-dev.1", corpus_hash="sha256:corpus"
    )


def test_case_and_whitespace_variants_across_books_form_one_group() -> None:
    first = make_document(REQUIRED_TEXTBOOK_IDS[0], text=LONG + TAIL)
    variant = LONG.upper().replace(" ", " \t ")
    second = make_document(REQUIRED_TEXTBOOK_IDS[2], text=variant + TAIL)

    report = _report(first, second)

    assert len(report.groups) == 1
    assert [member.textbook_id for member in report.groups[0].members] == [
        REQUIRED_TEXTBOOK_IDS[0],
        REQUIRED_TEXTBOOK_IDS[2],
    ]


def test_repeats_inside_one_textbook_and_short_blocks_are_not_reported() -> None:
    first = make_document(REQUIRED_TEXTBOOK_IDS[0], text=LONG + TAIL)
    same_book = make_document(
        REQUIRED_TEXTBOOK_IDS[0], parser_version="other-parser", text=LONG + TAIL
    )

    # The shared formula and image blocks are shorter than MIN_DUPLICATE_CHARS.
    assert _report(first, same_book).groups == ()


def test_a_group_must_span_two_textbooks() -> None:
    member = {
        "textbook_id": REQUIRED_TEXTBOOK_IDS[0],
        "document_id": "doc",
        "chapter_id": "1",
        "content_type": "body",
    }
    with pytest.raises(ValueError, match="two textbooks"):
        DuplicateBlockGroup(
            text_hash="sha256:x",
            members=({**member, "block_id": "a"}, {**member, "block_id": "b"}),
        )
