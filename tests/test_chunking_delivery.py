"""Delivery tests for the Member 4 split and retrieval-corpus seams."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cs30.chunking import (
    CHUNKING_CANDIDATES,
    BlockAwareChunker,
    BlockChunkingStrategy,
    export_retrieval_corpus,
    get_chunking_candidate,
    load_retrieval_corpus,
    resolve_small_to_big,
)
from cs30.contracts import (
    Chunk,
    ContentType,
    OpenStaxChapter,
    OpenStaxDocument,
    TextBlock,
)


def make_typed_document() -> OpenStaxDocument:
    """Build a mixed-content document with two sections and exact spans."""

    specs = [
        ("1.1", "Motion", ContentType.BODY, "Velocity describes motion."),
        ("1.1", "Motion", ContentType.PROBLEM, "Solve this excluded exercise."),
        ("1.1", "Motion", ContentType.EXAMPLE, "A car changes velocity."),
        ("1.2", "Forces", ContentType.TABLE, "Force | Acceleration"),
        ("1.2", "Forces", ContentType.SUMMARY, "Forces change motion."),
    ]
    parts: list[str] = []
    blocks: list[TextBlock] = []
    cursor = 0
    for index, (section_id, title, content_type, block_text) in enumerate(
        specs,
        start=1,
    ):
        if parts:
            parts.append("\n\n")
            cursor += 2
        start = cursor
        parts.append(block_text)
        cursor += len(block_text)
        blocks.append(
            TextBlock(
                block_id=f"typed-{index}",
                chapter_id="1",
                section_id=section_id,
                section_title=title,
                content_type=content_type,
                char_start=start,
                char_end=cursor,
            )
        )
    text = "".join(parts)
    return OpenStaxDocument(
        document_id="typed-document",
        title="Typed test document",
        version="test-v1",
        source="fixture://typed-document",
        document_hash="sha256:typed-document",
        parser_version="fixture-parser-1.0",
        text=text,
        chapters=[
            OpenStaxChapter(
                chapter_id="1",
                title="Chapter 1",
                char_start=0,
                char_end=len(text),
            )
        ],
        blocks=blocks,
    )


def test_six_candidates_are_frozen_and_keep_the_agreed_target() -> None:
    assert [candidate.candidate_id for candidate in CHUNKING_CANDIDATES] == [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
    ]
    assert all(candidate.strategy.target_tokens == 500 for candidate in CHUNKING_CANDIDATES)
    assert all(candidate.strategy.min_tokens == 100 for candidate in CHUNKING_CANDIDATES)
    assert all(candidate.strategy.max_tokens == 600 for candidate in CHUNKING_CANDIDATES)
    assert get_chunking_candidate("s3") == CHUNKING_CANDIDATES[2]
    with pytest.raises(ValueError, match="unknown chunking candidate"):
        get_chunking_candidate("S7")


def test_include_types_filters_without_leaking_excluded_text() -> None:
    document = make_typed_document()
    strategy = BlockChunkingStrategy(
        include_types=(ContentType.BODY, ContentType.EXAMPLE),
        candidate_id="filter-test",
    )
    chunks = BlockAwareChunker(strategy=strategy).chunk(document)

    assert len(chunks) == 2
    assert all("excluded exercise" not in chunk.text for chunk in chunks)
    assert {chunk.metadata["source_block_ids"] for chunk in chunks} == {
        "typed-1",
        "typed-3",
    }
    assert all("filter-test" in chunk.chunk_id for chunk in chunks)


def test_small_to_big_resolves_the_complete_section_parent() -> None:
    document = make_typed_document()
    strategy = BlockChunkingStrategy(
        include_types=(ContentType.BODY,),
        candidate_id="parent-test",
    )
    chunk = BlockAwareChunker(strategy=strategy).chunk(document)[0]
    evidence = resolve_small_to_big(document, chunk)

    expected_parent = document.text[document.blocks[0].char_start : document.blocks[2].char_end]
    assert evidence["parent_scope"] == "section"
    assert evidence["parent_text"] == expected_parent
    assert evidence["small_text"] in evidence["parent_text"]
    assert evidence["recovered_text_matches"] is True


def test_unified_corpus_is_deterministic_and_shared_by_dense_and_bm25(
    tmp_path: Path,
) -> None:
    document = make_typed_document()
    chunks = BlockAwareChunker().chunk(document)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = export_retrieval_corpus(
        [document],
        chunks,
        first_dir,
        rebuild_command="python scripts/build_retrieval_corpus.py",
    )
    second = export_retrieval_corpus(
        [document],
        chunks,
        second_dir,
        rebuild_command="python scripts/build_retrieval_corpus.py",
    )

    assert first == second
    assert (first_dir / "records.jsonl").read_bytes() == (second_dir / "records.jsonl").read_bytes()
    assert first["consumers"]["dense"] == "records.jsonl"
    assert first["consumers"]["bm25"] == "records.jsonl"
    dense_records = load_retrieval_corpus(first_dir / first["consumers"]["dense"])
    bm25_records = load_retrieval_corpus(first_dir / first["consumers"]["bm25"])
    assert dense_records == bm25_records == chunks
    statistics = json.loads((first_dir / "statistics.json").read_text())
    assert statistics["traceback_validation"] == "fail_fast"
    assert "all_sampled_spans_match" not in statistics
    assert statistics["empty_chunks"] == 0


def test_export_rejects_mixed_chunk_configurations(tmp_path: Path) -> None:
    document = make_typed_document()
    s1_chunks = BlockAwareChunker(
        strategy=get_chunking_candidate("S1").strategy
    ).chunk(document)
    s2_chunks = BlockAwareChunker(
        strategy=get_chunking_candidate("S2").strategy
    ).chunk(document)

    with pytest.raises(ValueError, match="mixed chunk configurations"):
        export_retrieval_corpus(
            [document],
            [*s1_chunks, *s2_chunks],
            tmp_path,
            rebuild_command="python scripts/build_retrieval_corpus.py",
        )


def test_load_retrieval_corpus_ignores_blank_lines(tmp_path: Path) -> None:
    document = make_typed_document()
    chunk = BlockAwareChunker().chunk(document)[0]
    path = tmp_path / "records.jsonl"
    path.write_text(
        f"\n{chunk.model_dump_json()}\n   \n",
        encoding="utf-8",
    )

    assert load_retrieval_corpus(path) == [chunk]


def test_filter_set_is_encoded_in_main_strategy_provenance() -> None:
    document = make_typed_document()
    all_types = BlockAwareChunker().chunk(document)[0]
    body_only = BlockAwareChunker(
        strategy=BlockChunkingStrategy(include_types=(ContentType.BODY,))
    ).chunk(document)[0]

    assert all_types.metadata["candidate_id"] == "main"
    assert body_only.metadata["candidate_id"] == "main"
    assert all_types.metadata["strategy"] != body_only.metadata["strategy"]
    assert all_types.metadata["strategy"].endswith("types-all")
    assert body_only.metadata["strategy"].endswith("types-body")


def test_repository_rebuild_script_runs_against_contract_fixture(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "build_retrieval_corpus.py"),
            "--document",
            str(repository_root / "src" / "cs30" / "fixtures" / "openstax_document.json"),
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] > 0
    assert "Built" in result.stdout
    assert (tmp_path / "records.jsonl").exists()


def test_export_rejects_a_chunk_without_a_source_locator(tmp_path: Path) -> None:
    document = make_typed_document()
    chunk = BlockAwareChunker().chunk(document)[0]
    metadata = dict(chunk.metadata)
    metadata.pop("source_locator")
    invalid = Chunk.model_validate({**chunk.model_dump(), "metadata": metadata})

    with pytest.raises(ValueError, match="source_locator"):
        export_retrieval_corpus(
            [document],
            [invalid],
            tmp_path,
            rebuild_command="python scripts/build_retrieval_corpus.py",
        )
