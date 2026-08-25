import pytest
from pydantic import TypeAdapter, ValidationError

from cs30.citation import validate_citations
from cs30.contracts import (
    Chunk,
    ContentType,
    GeneratedAnswer,
    OpenStaxDocument,
    RetrievalResult,
    SciQQuestion,
    TextBlock,
)
from cs30.errors import CS30Error
from cs30.fixtures import load_fixture


def test_openstax_document_fixture_is_valid() -> None:
    document = OpenStaxDocument.model_validate(load_fixture("openstax_document.json"))
    assert document.chapters[0].char_end == len(document.text)

    chunks = TypeAdapter(list[Chunk]).validate_python(load_fixture("chunks.json"))
    for chunk in chunks:
        assert document.text[chunk.char_start : chunk.char_end] == chunk.text


def test_sciq_question_requires_exactly_four_choices() -> None:
    payload = load_fixture("sciq_question.json")
    SciQQuestion.model_validate(payload)
    payload["choices"].pop("D")
    with pytest.raises(ValidationError):
        SciQQuestion.model_validate(payload)


def test_generated_answer_rejects_unknown_citation() -> None:
    retrieval = RetrievalResult.model_validate(load_fixture("retrieval_result.json"))
    answer = GeneratedAnswer(
        final_choice="B",
        explanation="Fixture explanation",
        citations=["chunk_missing"],
    )
    with pytest.raises(CS30Error, match="unknown citation"):
        validate_citations(answer, retrieval)


def test_chunk_text_keeps_boundary_whitespace() -> None:
    """Chunk text is bound to a span, so it must never be normalised."""

    raw = "  boundary whitespace matters  "
    chunk = Chunk(
        chunk_id="chunk_ws",
        document_id="doc",
        chapter_id="ch01",
        text=raw,
        source="fixture://openstax/physics#ch01",
        char_start=10,
        char_end=10 + len(raw),
        token_count=4,
    )
    assert chunk.text == raw


def test_chunk_rejects_span_length_mismatch() -> None:
    with pytest.raises(ValidationError, match="does not match span"):
        Chunk(
            chunk_id="chunk_bad",
            document_id="doc",
            chapter_id="ch01",
            text="four",
            source="fixture://openstax/physics#ch01",
            char_start=0,
            char_end=99,
            token_count=1,
        )


def test_chunk_identifier_fields_are_normalised() -> None:
    chunk = Chunk(
        chunk_id="  chunk_ws_id  ",
        document_id="doc",
        chapter_id="ch01",
        text="exact",
        source="fixture://openstax/physics#ch01",
        char_start=0,
        char_end=5,
        token_count=1,
    )
    assert chunk.chunk_id == "chunk_ws_id"


def test_retrieval_result_allows_no_hits() -> None:
    """Finding nothing is a valid outcome, not a failure."""

    result = RetrievalResult(query="unrelated question")
    assert result.hits == []


def test_generated_answer_allows_abstention() -> None:
    answer = GeneratedAnswer(
        explanation="The retrieved evidence does not support an answer.",
        abstained=True,
    )
    assert answer.citations == []
    assert answer.final_choice is None


def test_abstained_answer_must_not_select_a_choice() -> None:
    with pytest.raises(ValidationError, match="must not select a final_choice"):
        GeneratedAnswer(
            final_choice="B",
            explanation="Cannot answer, yet picked one anyway.",
            abstained=True,
        )


def test_abstained_answer_must_not_cite_evidence() -> None:
    with pytest.raises(ValidationError, match="must not cite evidence"):
        GeneratedAnswer(
            explanation="Cannot answer, yet cited something.",
            citations=["chunk_ch01_0001"],
            abstained=True,
        )


def test_non_abstained_answer_requires_a_citation() -> None:
    with pytest.raises(ValidationError, match="must cite at least one chunk"):
        GeneratedAnswer(explanation="Ungrounded claim with no evidence.")


def test_abstained_answer_passes_citation_integrity() -> None:
    retrieval = RetrievalResult(query="unrelated question")
    answer = GeneratedAnswer(
        explanation="The retrieved evidence does not support an answer.",
        abstained=True,
    )
    validate_citations(answer, retrieval)


def test_packaged_answer_fixture_still_validates() -> None:
    """Reference payload for member 7; kept valid so it cannot rot."""

    answer = GeneratedAnswer.model_validate(load_fixture("generated_answer.json"))
    assert answer.abstained is False
    assert answer.citations


def _document_payload(**overrides: object) -> dict:
    """Smallest valid document; individual tests break one rule at a time."""

    payload: dict = {
        "document_id": "doc",
        "title": "Doc",
        "version": "v1",
        "source": "fixture://doc",
        "document_hash": "hash",
        "parser_version": "parser-1",
        "text": "First sentence. Second sentence.",
        "chapters": [
            {"chapter_id": "ch01", "title": "One", "char_start": 0, "char_end": 32}
        ],
        "blocks": [{"chapter_id": "ch01", "char_start": 0, "char_end": 15}],
    }
    payload.update(overrides)
    return payload


def test_blocks_locate_their_text_in_the_document() -> None:
    """Blocks hold offsets only; the document text stays the single source."""

    document = OpenStaxDocument.model_validate(load_fixture("openstax_document.json"))
    assert document.blocks
    for block in document.blocks:
        assert document.block_text(block) == document.text[block.char_start : block.char_end]
        assert document.block_text(block).strip()


def test_block_content_type_defaults_to_body() -> None:
    block = TextBlock(chapter_id="ch01", char_start=0, char_end=15)
    assert block.content_type is ContentType.BODY


def test_block_rejects_unknown_content_type() -> None:
    with pytest.raises(ValidationError):
        TextBlock(
            chapter_id="ch01", char_start=0, char_end=15, content_type="exercise_maybe"
        )


def test_document_requires_at_least_one_block() -> None:
    with pytest.raises(ValidationError):
        OpenStaxDocument.model_validate(_document_payload(blocks=[]))


def test_blocks_must_be_ordered_and_non_overlapping() -> None:
    with pytest.raises(ValidationError, match="ordered and non-overlapping"):
        OpenStaxDocument.model_validate(
            _document_payload(
                blocks=[
                    {"chapter_id": "ch01", "char_start": 0, "char_end": 20},
                    {"chapter_id": "ch01", "char_start": 10, "char_end": 30},
                ]
            )
        )


def test_block_must_stay_inside_its_chapter() -> None:
    """Catches the mislabelled-section bug class at construction."""

    with pytest.raises(ValidationError, match="falls outside chapter"):
        OpenStaxDocument.model_validate(
            _document_payload(
                chapters=[
                    {"chapter_id": "ch01", "title": "One", "char_start": 0, "char_end": 16}
                ],
                blocks=[{"chapter_id": "ch01", "char_start": 0, "char_end": 32}],
            )
        )


def test_block_rejects_unknown_chapter_id() -> None:
    with pytest.raises(ValidationError, match="unknown chapter_id"):
        OpenStaxDocument.model_validate(
            _document_payload(
                blocks=[{"chapter_id": "ch99", "char_start": 0, "char_end": 15}]
            )
        )


def test_block_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="duplicate block_id"):
        OpenStaxDocument.model_validate(
            _document_payload(
                blocks=[
                    {"block_id": "b1", "chapter_id": "ch01", "char_start": 0, "char_end": 15},
                    {"block_id": "b1", "chapter_id": "ch01", "char_start": 16, "char_end": 32},
                ]
            )
        )


def test_block_span_may_not_exceed_document_text() -> None:
    with pytest.raises(ValidationError, match="exceeds document text"):
        OpenStaxDocument.model_validate(
            _document_payload(
                blocks=[{"chapter_id": "ch01", "char_start": 0, "char_end": 99}]
            )
        )


def _chunk(**overrides: object) -> Chunk:
    payload: dict = {
        "chunk_id": "chunk_embed",
        "document_id": "doc",
        "chapter_id": "ch01",
        "text": "Acceleration is the rate of change of velocity.",
        "source": "fixture://openstax/physics#ch01",
        "char_start": 0,
        "char_end": 47,
        "token_count": 9,
    }
    payload.update(overrides)
    return Chunk(**payload)


def test_embedding_input_falls_back_to_chunk_text() -> None:
    chunk = _chunk()
    assert chunk.embed_text is None
    assert chunk.embedding_input == chunk.text


def test_embed_text_carries_added_context() -> None:
    """Contextual enrichment changes what is embedded, not what is cited."""

    chunk = _chunk(
        embed_text=(
            "From chapter 1, section 1.1 (Physics: An Introduction): "
            "Acceleration is the rate of change of velocity."
        )
    )
    assert chunk.embedding_input.startswith("From chapter 1")
    assert chunk.text == "Acceleration is the rate of change of velocity."
    assert chunk.text in chunk.embedding_input


def test_embed_text_must_contain_the_chunk_text() -> None:
    """Retrieval may not match on wording absent from the cited evidence."""

    with pytest.raises(ValidationError, match="must contain the chunk text"):
        _chunk(embed_text="A paraphrase that drops the original wording.")


def test_embed_text_does_not_relax_the_span_invariant() -> None:
    with pytest.raises(ValidationError, match="does not match span"):
        _chunk(char_end=999, embed_text="prefix Acceleration is the rate of change of velocity.")
