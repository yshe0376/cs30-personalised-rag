"""Regression tests for M4's production v2 chunker."""

from __future__ import annotations

import re
from collections.abc import Sequence

import pytest

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS, get_textbook_spec
from cs30.v2.chunking import (
    V2_EVIDENCE_POLICY_ID,
    V2_EXCLUDED_SECTION_TITLES,
    V2_INLINE_HEADING_PATTERN,
    V2ChunkingStrategy,
    V2ProductionChunker,
)
from cs30.v2.contracts import ContentType, TextBlock, TextbookChapter, TextbookDocument
from cs30.v2.ids import chunk_config_hash, make_document_id, sha256_text
from cs30.v2.tokenization import CHUNK_TOKENIZER_NAME, CHUNK_TOKENIZER_REVISION


class WordCounter:
    name = "test-word-counter"
    _pattern = re.compile(r"\w+")

    def count(self, text: str) -> int:
        return len(self._pattern.findall(text))


def make_document(
    rows: Sequence[
        tuple[str, ContentType, str, int | None]
        | tuple[str, ContentType, str, int | None, str]
    ],
    *,
    document_suffix: str = "a",
) -> TextbookDocument:
    text_parts: list[str] = []
    blocks: list[TextBlock] = []
    cursor = 0
    for index, row in enumerate(rows, start=1):
        text, content_type, section_id, page = row[:4]
        section_title = row[4] if len(row) == 5 else f"Section {section_id}"
        if text_parts:
            text_parts.append("\n")
            cursor += 1
        start = cursor
        text_parts.append(text)
        cursor += len(text)
        blocks.append(
            TextBlock(
                block_id=f"b{index}",
                chapter_id="1",
                section_id=section_id,
                section_title=section_title,
                content_type=content_type,
                char_start=start,
                char_end=cursor,
                page_start=page,
                page_end=page,
                page_or_location=None if page else f"section-{section_id}",
            )
        )
    full_text = "".join(text_parts)
    textbook_id = REQUIRED_TEXTBOOK_IDS[0]
    raw_hash = sha256_text(full_text + document_suffix)
    document_hash = sha256_text(full_text + "normalized" + document_suffix)
    parser_version = "test-parser-2.0"
    return TextbookDocument(
        provider="openstax",
        textbook_id=textbook_id,
        document_id=make_document_id(
            textbook_id=textbook_id,
            raw_source_sha256=raw_hash,
            document_hash=document_hash,
            parser_version=parser_version,
            selected_chapters=("1",),
        ),
        title="Production chunking fixture",
        raw_source_sha256=raw_hash,
        document_hash=document_hash,
        parser_version=parser_version,
        source_name=get_textbook_spec(textbook_id).source_name,
        source_version="test-2.0",
        license="CC BY 4.0",
        selected_chapters=("1",),
        text=full_text,
        chapters=(
            TextbookChapter(
                chapter_id="1",
                title="Motion",
                char_start=0,
                char_end=len(full_text),
            ),
        ),
        blocks=tuple(blocks),
    )


def make_chunker(**overrides: object) -> V2ProductionChunker:
    strategy_values = {
        "tokenizer_name": WordCounter.name,
        "tokenizer_revision": None,
        "target_tokens": 5,
        "min_tokens": 3,
        "max_tokens": 6,
        **overrides,
    }
    return V2ProductionChunker(
        strategy=V2ChunkingStrategy(**strategy_values),
        token_counter=WordCounter(),
    )


def test_groups_whole_blocks_near_the_target_and_preserves_traceability() -> None:
    document = make_document(
        (
            ("one two three", ContentType.BODY, "1.1", 10),
            ("four five six", ContentType.EQUATION, "1.1", 11),
            ("seven eight nine", ContentType.EXAMPLE, "1.1", 12),
        )
    )

    chunks = make_chunker().chunk(document)

    assert [chunk.token_count for chunk in chunks] == [6, 3]
    assert [span.block_id for span in chunks[0].spans] == ["b1", "b2"]
    assert chunks[0].content_types == (ContentType.BODY, ContentType.EQUATION)
    assert chunks[0].page_start == 10
    assert chunks[0].page_end == 11
    assert chunks[0].page_or_location == "p10-11"
    assert document.text[chunks[0].char_start : chunks[0].char_end] == chunks[0].text
    assert chunks[0].metadata["parent_scope"] == "section"
    assert chunks[0].metadata["source_block_ids"] == "b1,b2"


def test_never_crosses_a_section_boundary() -> None:
    document = make_document(
        (
            ("one two", ContentType.BODY, "1.1", None),
            ("three four", ContentType.BODY, "1.2", None),
        )
    )

    chunks = make_chunker().chunk(document)

    assert len(chunks) == 2
    assert [chunk.section_id for chunk in chunks] == ["1.1", "1.2"]


def test_excluded_assessment_blocks_are_hard_boundaries_and_never_leak() -> None:
    document = make_document(
        (
            ("eligible body words", ContentType.BODY, "1.1", None),
            ("private assessment problem", ContentType.PROBLEM, "1.1", None),
            ("later eligible words", ContentType.BODY, "1.1", None),
            ("excluded chapter summary", ContentType.SUMMARY, "1.1", None),
        )
    )

    chunks = make_chunker().chunk(document)

    assert len(chunks) == 2
    assert all("assessment" not in chunk.text for chunk in chunks)
    assert all("summary" not in chunk.text for chunk in chunks)
    assert [chunk.metadata["source_block_ids"] for chunk in chunks] == ["b1", "b3"]


def test_exercise_section_excludes_eligible_media_types_by_structure() -> None:
    document = make_document(
        (
            ("retrievable introduction", ContentType.BODY, "1.1", None, "Motion"),
            (
                "[FIGURE DESCRIPTION: force diagram]",
                ContentType.FIGURE_CAPTION,
                "1.2",
                None,
                "Problems & Exercises",
            ),
            (
                "[EQUATION: F = ma]",
                ContentType.EQUATION,
                "1.2",
                None,
                "Problems & Exercises",
            ),
            ("retrievable conclusion", ContentType.BODY, "1.3", None, "Momentum"),
        )
    )

    chunks = make_chunker().chunk(document)

    assert [chunk.metadata["source_block_ids"] for chunk in chunks] == ["b1", "b4"]
    assert all("force diagram" not in chunk.text for chunk in chunks)
    assert all("F = ma" not in chunk.text for chunk in chunks)


def test_cyu_region_excludes_minor_headings_and_answers_until_formal_heading() -> None:
    document = make_document(
        (
            ("retrievable explanation", ContentType.BODY, "1.1", None),
            ("Which object moves faster?", ContentType.CHECK_UNDERSTANDING, "1.1", None),
            ("Solution", ContentType.HEADING, "1.1", None),
            ("The hidden answer is A.", ContentType.BODY, "1.1", None),
            ("Newton's Second Law", ContentType.HEADING, "1.1", None),
            ("normal content resumes here", ContentType.BODY, "1.1", None),
        )
    )

    chunks = make_chunker(max_tokens=20).chunk(document)

    assert [chunk.metadata["source_block_ids"] for chunk in chunks] == ["b1", "b6"]
    joined = "\n".join(chunk.text for chunk in chunks)
    assert "hidden answer" not in joined
    assert "normal content resumes" in joined


@pytest.mark.parametrize("stop_type", [ContentType.EXAMPLE, ContentType.GLOSSARY])
def test_cyu_region_ends_before_example_or_glossary(stop_type: ContentType) -> None:
    document = make_document(
        (
            ("Check your understanding", ContentType.CHECK_UNDERSTANDING, "1.1", None),
            ("excluded answer", ContentType.BODY, "1.1", None),
            ("retrieval restarts", stop_type, "1.1", None),
            ("continued explanation", ContentType.BODY, "1.1", None),
        )
    )

    chunks = make_chunker(max_tokens=20).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].metadata["source_block_ids"] == "b3,b4"
    assert "excluded answer" not in chunks[0].text


def test_cyu_region_ends_when_the_section_changes() -> None:
    document = make_document(
        (
            ("Check your understanding", ContentType.CHECK_UNDERSTANDING, "1.1", None),
            ("excluded answer", ContentType.BODY, "1.1", None),
            ("new section explanation", ContentType.BODY, "1.2", None),
        )
    )

    chunks = make_chunker(max_tokens=20).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].metadata["source_block_ids"] == "b3"


def test_worked_example_keeps_minor_headings_in_one_chunk() -> None:
    document = make_document(
        (
            ("Worked example setup", ContentType.EXAMPLE, "1.1", None),
            ("Strategy", ContentType.HEADING, "1.1", None),
            ("choose the relevant law", ContentType.BODY, "1.1", None),
            ("Solution", ContentType.HEADING, "1.1", None),
            ("substitute the values", ContentType.BODY, "1.1", None),
            ("Discussion", ContentType.HEADING, "1.1", None),
            ("interpret the result", ContentType.BODY, "1.1", None),
        )
    )

    chunks = make_chunker(target_tokens=30, max_tokens=40).chunk(document)

    assert len(chunks) == 1
    assert [span.content_type for span in chunks[0].spans].count(ContentType.HEADING) == 3
    assert chunks[0].metadata["source_block_ids"] == "b1,b2,b3,b4,b5,b6,b7"


def test_chunk_made_only_of_minor_headings_is_discarded() -> None:
    document = make_document(
        (
            ("Strategy", ContentType.HEADING, "1.1", None),
            ("Solution", ContentType.HEADING, "1.1", None),
            ("Ordinary topic", ContentType.HEADING, "1.1", None),
            ("retrievable explanation", ContentType.BODY, "1.1", None),
        )
    )

    chunks = make_chunker(max_tokens=20).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].metadata["source_block_ids"] == "b4"
    assert "Strategy" not in chunks[0].text


def test_ids_and_config_hash_are_stable_and_bound_to_the_document() -> None:
    document = make_document((("one two three", ContentType.BODY, "1.1", None),))
    same_chunker = make_chunker()
    changed_chunker = make_chunker(max_tokens=7)

    first = same_chunker.chunk(document)[0]
    repeated = make_chunker().chunk(document)[0]
    other_document = make_document(
        (("one two three", ContentType.BODY, "1.1", None),),
        document_suffix="b",
    )

    assert first.chunk_id == repeated.chunk_id
    assert first.chunk_config_hash == repeated.chunk_config_hash
    assert first.chunk_config_hash != changed_chunker.config_hash
    assert first.chunk_id != same_chunker.chunk(other_document)[0].chunk_id


def test_one_indivisible_large_block_is_retained_and_marked_oversized() -> None:
    document = make_document((("one two three four five six seven", ContentType.BODY, "1.1", 4),))

    chunk = make_chunker().chunk(document)[0]

    assert chunk.token_count == 7
    assert chunk.metadata["oversized_chunk"] == "true"
    assert chunk.spans[0].block_id == "b1"


def test_duplicate_text_is_preserved_by_default_but_can_fail_closed() -> None:
    document = make_document(
        (
            ("same words here", ContentType.BODY, "1.1", None),
            ("excluded", ContentType.PROBLEM, "1.1", None),
            ("same words here", ContentType.BODY, "1.1", None),
        )
    )

    assert len(make_chunker().chunk(document)) == 2
    with pytest.raises(ValueError, match="duplicate chunk text"):
        make_chunker(reject_duplicate_text=True).chunk(document)


def test_production_config_requires_and_records_a_pinned_wordpiece_revision() -> None:
    with pytest.raises(ValueError, match="tokenizer_revision"):
        V2ProductionChunker.from_config({"tokenizer_name": CHUNK_TOKENIZER_NAME})

    chunker = V2ProductionChunker.from_config(
        {
            "tokenizer_name": CHUNK_TOKENIZER_NAME,
            "tokenizer_revision": CHUNK_TOKENIZER_REVISION,
        }
    )

    assert chunker.tokenizer_name == CHUNK_TOKENIZER_NAME
    assert chunker.tokenizer_revision == CHUNK_TOKENIZER_REVISION
    assert chunker.strategy.target_tokens == 500
    assert chunker.strategy.min_tokens == 100
    assert chunker.strategy.max_tokens == 600


def test_v2_policy_identity_records_structure_aware_rules() -> None:
    chunker = make_chunker()
    identity = chunker.strategy.identity(chunker_version=chunker.version)
    new_rule_keys = {
        "excluded_section_titles",
        "excluded_section_prefixes",
        "cyu_start_content_type",
        "cyu_stop_content_types",
        "cyu_stop_on_formal_heading",
        "cyu_stop_on_scope_change",
        "inline_heading_pattern",
    }
    old_identity = {key: value for key, value in identity.items() if key not in new_rule_keys}
    old_identity["chunker_version"] = "v2-structure-aware-v1"
    old_identity["evidence_policy_id"] = "v2-retrieval-evidence-v1"

    assert chunker.version == "v2-structure-aware-v2"
    assert identity["evidence_policy_id"] == V2_EVIDENCE_POLICY_ID
    assert identity["excluded_section_titles"] == list(V2_EXCLUDED_SECTION_TITLES)
    assert identity["cyu_stop_on_formal_heading"] is True
    assert identity["inline_heading_pattern"] == V2_INLINE_HEADING_PATTERN
    assert chunker.config_hash != chunk_config_hash(old_identity)


def test_production_chunks_record_the_wordpiece_revision() -> None:
    class OneCounter:
        name = CHUNK_TOKENIZER_NAME

        def count(self, text: str) -> int:
            return 1

    chunker = V2ProductionChunker(token_counter=OneCounter())
    document = make_document((("traceable body", ContentType.BODY, "1.1", None),))

    chunk = chunker.chunk(document)[0]

    assert chunk.metadata["tokenizer_name"] == CHUNK_TOKENIZER_NAME
    assert chunk.metadata["tokenizer_revision"] == CHUNK_TOKENIZER_REVISION


def test_config_parser_rejects_unknown_and_invalid_values() -> None:
    strategy = V2ChunkingStrategy.from_config(
        {
            "target_tokens": "500",
            "include_types": "body,equation",
            "respect_section_boundaries": "true",
        }
    )
    assert strategy.include_types == (ContentType.BODY, ContentType.EQUATION)
    with pytest.raises(ValueError, match="unsupported v2 chunk configuration"):
        V2ChunkingStrategy.from_config({"unknown": "value"})
    with pytest.raises(ValueError, match="must be true or false"):
        V2ChunkingStrategy.from_config({"enrich_embed_text": "sometimes"})
