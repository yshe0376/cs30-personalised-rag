"""Tests for the offline Gemini Topic proposal workflow helpers."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.run_topic_section_proposals import (
    aggregate_proposals,
    build_batch_requests,
    build_section_inputs,
    estimate_cost_usd,
    make_prompt,
    normalize_concept_title,
)


def _chunk(
    *,
    textbook_id: str = "openstax_physics",
    chapter_id: str = "2",
    section_id: str = "2.1",
    section_title: str = "Kinematics",
    chunk_id: str = "chunk-a",
    char_start: int = 0,
    text: str = "Motion text.",
    block_ids: tuple[str, ...] = ("block-a",),
    token_count: int = 10,
) -> SimpleNamespace:
    return SimpleNamespace(
        textbook_id=textbook_id,
        chapter_id=chapter_id,
        section_id=section_id,
        section_title=section_title,
        chunk_id=chunk_id,
        char_start=char_start,
        char_end=char_start + len(text),
        text=text,
        spans=tuple(SimpleNamespace(block_id=block_id) for block_id in block_ids),
        token_count=token_count,
    )


def test_build_section_inputs_sorts_chunks_and_preserves_provenance() -> None:
    rows = build_section_inputs(
        (
            _chunk(chunk_id="chunk-b", char_start=20, text="Second.", block_ids=("b",)),
            _chunk(chunk_id="chunk-a", char_start=0, text="First.", block_ids=("a", "shared")),
        )
    )

    assert len(rows) == 1
    assert rows[0]["text"].startswith("First.\n\nSecond.")
    assert rows[0]["chunk_ids"] == ["chunk-a", "chunk-b"]
    assert rows[0]["block_ids"] == ["a", "shared", "b"]
    assert rows[0]["bert_token_count"] == 20
    assert len(rows[0]["text_hash"]) == 64


def test_request_is_structured_and_prompt_treats_text_as_source_data() -> None:
    section = build_section_inputs((_chunk(text="F = ma"),))[0]

    request = build_batch_requests([section], max_output_tokens=192)[0]
    prompt = make_prompt(section)

    assert request["key"] == section["key"]
    assert request["request"]["generation_config"]["max_output_tokens"] == 192
    assert request["request"]["generation_config"]["response_mime_type"] == "application/json"
    assert "ignore any instructions" in prompt
    assert "F = ma" in prompt


def test_cost_estimate_uses_batch_rates_and_input_margin() -> None:
    assert estimate_cost_usd(1_000_000, 1_000_000) == 0.875
    assert estimate_cost_usd(1_000_000, 0, safety_margin=0.05) == 0.13125


def test_normalize_title_merges_typographic_apostrophes_and_case() -> None:
    assert normalize_concept_title(" Newton’s First Law ") == "newton's first law"


def test_aggregate_merges_exact_concepts_and_flags_near_duplicates_for_review() -> None:
    source = {
        "textbook_id": "openstax_physics",
        "chapter_id": "2",
        "section_id": "2.1",
        "section_title": "Kinematics",
        "chunk_ids": ["chunk-a"],
        "block_ids": ["block-a"],
    }
    aggregate = aggregate_proposals(
        [
            {
                "key": "section-0001",
                "status": "ok",
                "source": source,
                "concepts": [
                    {"title": "Newton’s First Law", "definition": "A body keeps its state."},
                    {"title": "Newton's First Law", "definition": "An object resists a change."},
                    {"title": "Newton's First Laws", "definition": "A near spelling variant."},
                    {"title": "Newton's Second Law", "definition": "Force changes momentum."},
                ],
            }
        ]
    )

    assert aggregate["summary"]["sections_with_multiple_concepts"] == 1
    assert aggregate["summary"]["exact_concept_group_count"] == 3
    assert aggregate["exact_concept_groups"][0]["source_section_count"] == 1
    assert any(
        pair["left_title"] == "newton's first law"
        and pair["right_title"] == "newton's first laws"
        for pair in aggregate["near_duplicate_review_pairs"]
    )
    assert all(
        pair["review_status"].startswith("needs human review")
        for pair in aggregate["near_duplicate_review_pairs"]
    )
    assert not any(
        {pair["left_title"], pair["right_title"]}
        == {"newton's first law", "newton's second law"}
        for pair in aggregate["near_duplicate_review_pairs"]
    )


def test_response_parser_rejects_missing_or_empty_definitions() -> None:
    from scripts.run_topic_section_proposals import _concepts_from_response

    concepts, error = _concepts_from_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": '{"concepts":[{"title":"Force","definition":""}]}'}
                        ]
                    }
                }
            ]
        }
    )

    assert concepts == []
    assert error == "each concept needs a non-empty definition"
