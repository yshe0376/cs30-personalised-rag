"""Behaviour tests for the revised block-aware Module 4 implementation."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import TypeAdapter

from cs30.chunking import (
    BlockAwareChunker,
    BlockChunkingStrategy,
    build_chunk_statistics,
    build_traceability_samples,
)
from cs30.contracts import (
    Chunk,
    ContentType,
    OpenStaxChapter,
    OpenStaxDocument,
    TextBlock,
)
from cs30.fixtures import load_fixture
from cs30.ports import Chunker


def make_document(
    specs: Sequence[tuple[str, str, str, str]],
    *,
    document_id: str = "block-aware-test",
) -> OpenStaxDocument:
    """Build a valid document from chapter, section, title, and text tuples."""

    parts: list[str] = []
    blocks: list[TextBlock] = []
    chapter_bounds: dict[str, list[int]] = {}
    cursor = 0
    for index, (chapter_id, section_id, section_title, block_text) in enumerate(specs, start=1):
        if parts:
            parts.append("\n\n")
            cursor += 2
        char_start = cursor
        parts.append(block_text)
        cursor += len(block_text)
        char_end = cursor
        chapter_bounds.setdefault(chapter_id, [char_start, char_end])[1] = char_end
        blocks.append(
            TextBlock(
                block_id=f"block-{index:03d}",
                chapter_id=chapter_id,
                section_id=section_id,
                section_title=section_title,
                content_type=ContentType.BODY,
                char_start=char_start,
                char_end=char_end,
                page_start=index,
                page_end=index,
            )
        )
    chapters = [
        OpenStaxChapter(
            chapter_id=chapter_id,
            title=f"Chapter {chapter_id}",
            char_start=bounds[0],
            char_end=bounds[1],
        )
        for chapter_id, bounds in chapter_bounds.items()
    ]
    return OpenStaxDocument(
        document_id=document_id,
        title="Block-aware test document",
        version="test-v1",
        source="fixture://block-aware-test",
        document_hash="sha256:block-aware-test",
        parser_version="fixture-parser-1.0",
        text="".join(parts),
        chapters=chapters,
        blocks=blocks,
    )


def standard_block(index: int, token_count: int = 79) -> str:
    words = [f"Block{index}"] + ["physics"] * (token_count - 1)
    return " ".join(words)


def test_chunker_satisfies_protocol() -> None:
    assert isinstance(BlockAwareChunker(), Chunker)


def test_repository_fixture_is_accepted_and_traceable() -> None:
    document = OpenStaxDocument.model_validate(load_fixture("openstax_document.json"))
    chunks = BlockAwareChunker().chunk(document)
    TypeAdapter(list[Chunk]).validate_python(chunks)
    assert len(chunks) == 1
    assert chunks[0].metadata["source_block_ids"] == (
        "block_ch01_0001,block_ch01_0002,block_ch01_0003"
    )
    assert document.text[chunks[0].char_start : chunks[0].char_end] == chunks[0].text


def test_boundaries_follow_blocks_and_short_tail_is_rebalanced() -> None:
    specs = [("1", "1.1", "Motion", standard_block(index)) for index in range(13)]
    document = make_document(specs)
    chunks = BlockAwareChunker().chunk(document)
    block_starts = {block.char_start for block in document.blocks}
    block_ends = {block.char_end for block in document.blocks}

    assert len(chunks) == 2
    assert all(chunk.char_start in block_starts for chunk in chunks)
    assert all(chunk.char_end in block_ends for chunk in chunks)
    assert all(100 <= chunk.token_count <= 600 for chunk in chunks)
    assert sum(int(chunk.metadata["block_count"]) for chunk in chunks) == 13


def test_default_strategy_never_crosses_sections() -> None:
    specs = [
        ("1", "1.1", "Motion", standard_block(index)) for index in range(4)
    ] + [
        ("1", "1.2", "Acceleration", standard_block(index)) for index in range(4, 8)
    ]
    document = make_document(specs)
    chunks = BlockAwareChunker().chunk(document)
    assert {chunk.metadata["section_ids"] for chunk in chunks} == {"1.1", "1.2"}
    assert all("," not in chunk.metadata["section_ids"] for chunk in chunks)


def test_chunks_never_cross_chapters() -> None:
    specs = [
        ("1", "1.1", "Motion", standard_block(index)) for index in range(4)
    ] + [
        ("2", "2.1", "Forces", standard_block(index)) for index in range(4, 8)
    ]
    document = make_document(specs)
    chunks = BlockAwareChunker().chunk(document)
    assert {chunk.chapter_id for chunk in chunks} == {"1", "2"}
    for chunk in chunks:
        source_ids = chunk.metadata["source_block_ids"].split(",")
        source_blocks = [
            block for block in document.blocks if block.block_id in source_ids
        ]
        assert {block.chapter_id for block in source_blocks} == {chunk.chapter_id}


def test_single_oversized_block_is_not_split() -> None:
    document = make_document([("1", "1.1", "Motion", standard_block(1, 650))])
    chunks = BlockAwareChunker().chunk(document)
    assert len(chunks) == 1
    assert chunks[0].token_count == 650
    assert chunks[0].metadata["oversized_chunk"] == "true"
    assert chunks[0].char_start == document.blocks[0].char_start
    assert chunks[0].char_end == document.blocks[0].char_end


def test_whitespace_block_before_oversized_block_does_not_drop_text() -> None:
    document = make_document(
        [
            ("1", "1.1", "Motion", "   "),
            ("1", "1.1", "Motion", standard_block(1, 650)),
        ]
    )
    chunks = BlockAwareChunker().chunk(document)
    assert len(chunks) == 1
    assert chunks[0].token_count == 650
    assert chunks[0].metadata["source_block_ids"] == "block-001,block-002"


def test_optional_embed_text_preserves_verbatim_evidence() -> None:
    strategy = BlockChunkingStrategy(enrich_embed_text=True)
    document = make_document([("1", "1.1", "Motion", standard_block(1))])
    chunk = BlockAwareChunker(strategy=strategy).chunk(document)[0]
    assert chunk.embed_text is not None
    assert chunk.text in chunk.embed_text


def test_duplicate_chunk_text_is_rejected_by_default() -> None:
    repeated = standard_block(1)
    document = make_document(
        [
            ("1", "1.1", "Motion", repeated),
            ("2", "2.1", "Forces", repeated),
        ]
    )
    with pytest.raises(ValueError, match="duplicate chunk text"):
        BlockAwareChunker().chunk(document)


def test_statistics_and_ten_traceability_samples() -> None:
    specs = [("1", "1.1", "Motion", standard_block(index)) for index in range(70)]
    document = make_document(specs)
    chunks = BlockAwareChunker().chunk(document)
    statistics = build_chunk_statistics(chunks)
    samples = build_traceability_samples(document, chunks, sample_count=10)
    assert statistics["empty_chunks"] == 0
    assert statistics["cross_chapter_chunks"] == 0
    assert len(samples) == 10
    assert all(sample["recovered_text_matches"] is True for sample in samples)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_tokens": 0},
        {"min_tokens": 200, "target_tokens": 100},
        {"target_tokens": 500, "max_tokens": 499},
        {"chunker_version": " "},
    ],
)
def test_invalid_strategy_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        BlockChunkingStrategy(**kwargs)
