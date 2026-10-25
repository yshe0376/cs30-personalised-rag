"""M4's single v2 evidence-span resolver for Gold and Concept Check."""

from __future__ import annotations

from test_v2_corpus_records import build_corpus

from cs30.chunking import bind_concept_check_question, resolve_evidence_span
from cs30.v2.contracts import (
    ConceptCheckQuestion,
    EvidenceSpan,
    SpanResolutionMethod,
    SpanResolutionStatus,
)
from cs30.v2.corpus import LoadedCorpus, load_corpus_records


def _corpus_with_chapter_base(tmp_path) -> LoadedCorpus:
    _, path = build_corpus(tmp_path)
    corpus = load_corpus_records(path)
    first = corpus.chunks[0]
    chunks = tuple(
        chunk.model_copy(
            update={
                "metadata": chunk.metadata
                | {
                    "parent_char_start": str(first.spans[0].char_start),
                    "parent_scope": "chapter",
                }
            }
        )
        if (chunk.textbook_id, chunk.chapter_id, chunk.document_id)
        == (first.textbook_id, first.chapter_id, first.document_id)
        else chunk
        for chunk in corpus.chunks
    )
    return LoadedCorpus(manifest=corpus.manifest, chunks=chunks)


def _span(corpus: LoadedCorpus, *, start: int, text: str, block_id: str | None):
    chunk = corpus.chunks[0]
    return EvidenceSpan(
        span_id="span-1",
        textbook_id=chunk.textbook_id,
        chapter_id=chunk.chapter_id,
        chapter_char_start=start,
        chapter_char_end=start + len(text),
        verbatim_text=text,
        block_id=block_id,
        origin_corpus_version=corpus.manifest.corpus_version,
    )


def test_block_id_is_the_first_resolution_rule(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    chunk = corpus.chunks[0]
    block = chunk.spans[0]
    text = chunk.text[block.char_start - chunk.char_start : block.char_end - chunk.char_start]
    binding = resolve_evidence_span(
        _span(corpus, start=999, text=text, block_id=block.block_id), corpus
    )

    assert binding.resolution_status is SpanResolutionStatus.RESOLVED
    assert binding.resolution_method is SpanResolutionMethod.BLOCK_ID
    assert binding.chunk_ids == (chunk.chunk_id,)


def test_chapter_offset_is_verified_before_verbatim_fallback(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    chunk = corpus.chunks[0]
    text = chunk.text[2:22]
    chapter_start = int(chunk.metadata["parent_char_start"])
    binding = resolve_evidence_span(
        _span(
            corpus,
            start=chunk.char_start + 2 - chapter_start,
            text=text,
            block_id=None,
        ),
        corpus,
    )

    assert binding.resolution_status is SpanResolutionStatus.RESOLVED
    assert binding.resolution_method is SpanResolutionMethod.CHAPTER_OFFSET
    assert (binding.char_start, binding.char_end) == (
        chunk.char_start + 2,
        chunk.char_start + 22,
    )


def test_unique_verbatim_recovers_a_stale_offset(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    chunk = corpus.chunks[0]
    text = chunk.text[2:22]
    assert sum(item.text.count(text) for item in corpus.chunks) == 1

    binding = resolve_evidence_span(_span(corpus, start=1, text=text, block_id=None), corpus)

    assert binding.resolution_status is SpanResolutionStatus.RESOLVED
    assert binding.resolution_method is SpanResolutionMethod.VERBATIM_UNIQUE


def test_chapter_offset_can_bind_across_a_chunk_boundary(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    original = corpus.chunks[0]
    boundary = original.char_start + len(original.text) // 2
    left = original.model_copy(
        update={
            "chunk_id": f"{original.chunk_id}-left",
            "text": original.text[: boundary - original.char_start],
            "char_end": boundary,
            "spans": (),
        }
    )
    right = original.model_copy(
        update={
            "chunk_id": f"{original.chunk_id}-right",
            "text": original.text[boundary - original.char_start :],
            "char_start": boundary + 2,
            "char_end": original.char_end + 2,
            "spans": (),
        }
    )
    split_corpus = LoadedCorpus(
        manifest=corpus.manifest,
        chunks=(left, right, *corpus.chunks[1:]),
    )
    start = boundary - 3
    text = (
        original.text[start - original.char_start : boundary - original.char_start]
        + "\n\n"
        + original.text[
            boundary - original.char_start : boundary - original.char_start + 3
        ]
    )
    chapter_start = int(original.metadata["parent_char_start"])

    binding = resolve_evidence_span(
        _span(
            split_corpus,
            start=start - chapter_start,
            text=text,
            block_id=None,
        ),
        split_corpus,
    )

    assert binding.resolution_status is SpanResolutionStatus.RESOLVED
    assert binding.resolution_method is SpanResolutionMethod.CHAPTER_OFFSET
    assert binding.chunk_ids == (left.chunk_id, right.chunk_id)


def test_section_parent_start_is_not_guessed_as_chapter_start(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    original = corpus.chunks[0]
    text = "repeated evidence"
    first = original.model_copy(
        update={
            "chunk_id": f"{original.chunk_id}-section-a",
            "text": text,
            "char_start": 100,
            "char_end": 100 + len(text),
            "spans": (),
            "metadata": original.metadata
            | {"parent_scope": "section", "parent_char_start": "80"},
        }
    )
    second = original.model_copy(
        update={
            "chunk_id": f"{original.chunk_id}-section-b",
            "text": text,
            "char_start": 200,
            "char_end": 200 + len(text),
            "spans": (),
            "metadata": original.metadata
            | {"parent_scope": "section", "parent_char_start": "180"},
        }
    )
    section_only_corpus = LoadedCorpus(
        manifest=corpus.manifest,
        chunks=(first, second, *corpus.chunks[1:]),
    )

    binding = resolve_evidence_span(
        _span(section_only_corpus, start=20, text=text, block_id=None),
        section_only_corpus,
    )

    assert binding.resolution_status is SpanResolutionStatus.AMBIGUOUS
    assert binding.resolution_method is None
    assert binding.chunk_ids == ()


def test_repeated_or_missing_text_is_never_guessed(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    chunk = corpus.chunks[0]
    repeated = next(char for char in chunk.text if chunk.text.count(char) > 1)
    ambiguous = resolve_evidence_span(
        _span(corpus, start=len(chunk.text) + 10, text=repeated, block_id=None),
        corpus,
    )
    stale = resolve_evidence_span(
        _span(corpus, start=len(chunk.text) + 10, text="ZZZZZ", block_id=None),
        corpus,
    )

    assert ambiguous.resolution_status is SpanResolutionStatus.AMBIGUOUS
    assert stale.resolution_status is SpanResolutionStatus.STALE
    assert ambiguous.chunk_ids == stale.chunk_ids == ()


def test_concept_check_adapter_binds_every_anchor(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    chunk = corpus.chunks[0]
    block = chunk.spans[0]
    text = chunk.text[block.char_start - chunk.char_start : block.char_end - chunk.char_start]
    question = ConceptCheckQuestion(
        question_id="practice-1",
        question="Which statement follows from the evidence?",
        options={"A": "A", "B": "B", "C": "C", "D": "D"},
        correct_answer="A",
        topic_id="topic-1",
        topic_registry_version="topics-1",
        difficulty="beginner",
        evidence_anchors=(_span(corpus, start=0, text=text, block_id=block.block_id),),
        source_type="human_authored",
        rationale="The cited evidence directly supports option A.",
    )

    binding = bind_concept_check_question(question, corpus)

    assert binding.question_id == question.question_id
    assert binding.corpus_hash == corpus.manifest.corpus_hash
    assert binding.bindings[0].resolution_status is SpanResolutionStatus.RESOLVED
