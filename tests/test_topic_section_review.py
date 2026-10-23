"""Tests for the offline v2 Topic section review generator."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.build_topic_section_review import (
    build_candidate_review,
    build_section_rows,
    normalize_title,
)


def _section(
    textbook_id: str,
    chapter_id: str,
    section_id: str,
    title: str,
    chunk_id: str,
) -> dict[str, object]:
    return {
        "textbook_id": textbook_id,
        "chapter_id": chapter_id,
        "section_id": section_id,
        "section_title": title,
        "chunk_ids": [chunk_id],
        "block_ids": [f"block-{chunk_id}"],
        "token_count": 12,
    }


def test_normalize_title_strips_numbering_and_normalizes_quotes() -> None:
    assert normalize_title(' Section 2.1: Newton’s “First Law” ') == (
        'newton\'s "first law"'
    )
    assert normalize_title("1-Dimensional Motion") == "1-dimensional motion"


def test_candidate_merge_keeps_sources_and_chunk_ids() -> None:
    review = build_candidate_review(
        [
            _section(
                "openstax_college_physics_2e",
                "4",
                "4.2",
                "Newton’s First Law of Motion: Inertia",
                "chunk-a",
            ),
            _section(
                "openstax_physics",
                "5",
                "5.1",
                "Newton's First Law of Motion: Inertia",
                "chunk-b",
            ),
        ],
        corpus_version="2.0.0-dev.test",
        corpus_hash="sha256:test",
        chunk_count=2,
    )

    assert len(review["candidates"]) == 1
    candidate = review["candidates"][0]
    assert candidate["normalized_title"] == "newton's first law of motion: inertia"
    assert {source["textbook_id"] for source in candidate["source_sections"]} == {
        "openstax_college_physics_2e",
        "openstax_physics",
    }
    assert {
        chunk_id
        for source in candidate["source_sections"]
        for chunk_id in source["chunk_ids"]
    } == {"chunk-a", "chunk-b"}


def test_candidate_review_excludes_chapter_intros_and_counts_missing_titles() -> None:
    review = build_candidate_review(
        [
            _section(
                "openstax_physics", "1", "1.chapter_outline", "Chapter Outline", "outline"
            ),
            _section(
                "openstax_physics", "1", "1.introduction", "Introduction to Physics", "intro"
            ),
            _section(
                "openstax_physics",
                "1",
                "1.1",
                "Introduction to One-Dimensional Kinematics",
                "concept",
            ),
            _section("openstax_physics", "1", "", "", "untitled"),
        ],
        corpus_version="2.0.0-dev.test",
        corpus_hash="sha256:test",
        chunk_count=4,
    )

    assert [candidate["normalized_title"] for candidate in review["candidates"]] == [
        "introduction to one-dimensional kinematics"
    ]
    assert review["summary"]["sections_without_titles"] == 1
    assert review["summary"]["chunks_in_sections_without_titles"] == 1
    assert review["summary"]["excluded_source_section_count"] == 2


def test_section_rows_sum_tokens_and_retain_block_provenance() -> None:
    chunks = (
        SimpleNamespace(
            textbook_id="openstax_physics",
            chapter_id="2",
            section_id="2.1",
            section_title="Kinematics",
            chunk_id="chunk-a",
            spans=(SimpleNamespace(block_id="block-a"),),
            token_count=10,
        ),
        SimpleNamespace(
            textbook_id="openstax_physics",
            chapter_id="2",
            section_id="2.1",
            section_title="Kinematics",
            chunk_id="chunk-b",
            spans=(
                SimpleNamespace(block_id="block-a"),
                SimpleNamespace(block_id="block-b"),
            ),
            token_count=15,
        ),
    )

    rows = build_section_rows(chunks)

    assert len(rows) == 1
    assert rows[0]["token_count"] == 25
    assert rows[0]["chunk_ids"] == ["chunk-a", "chunk-b"]
    assert rows[0]["block_ids"] == ["block-a", "block-b"]
