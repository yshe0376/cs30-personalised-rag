from __future__ import annotations

import logging

import pytest

from cs30.v2.contracts import (
    EvidenceProvenance,
    GeneratedAnswer,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
)
from cs30.v2.evidence import CitationValidatorAdapter, EvidenceBundleAdapter
from cs30.v2.ids import source_locator
from cs30.v2.ports import CitationValidator, EvidenceBundleBuilder
from cs30.v2.tokenization import RegexTokenCounter


def _hit(
    *,
    chunk_id: str,
    rank: int,
    provider: str,
    textbook_id: str,
    document_id: str,
    chapter_id: str,
    source_name: str,
    page_or_location: str,
    text: str,
) -> RetrievedEvidence:
    return RetrievedEvidence(
        provider=provider,
        textbook_id=textbook_id,
        document_id=document_id,
        chunk_id=chunk_id,
        chapter_id=chapter_id,
        source_name=source_name,
        page_or_location=page_or_location,
        source_locator=source_locator(
            source_name=source_name,
            textbook_id=textbook_id,
            chapter_id=chapter_id,
            page_or_location=page_or_location,
            char_start=rank * 10,
            char_end=rank * 10 + len(text),
        ),
        text=text,
        score=1.0 / rank,
        rank=rank,
        retriever_type=RetrievalMode.FIXTURE,
    )


def _retrieval() -> RetrievalResult:
    return RetrievalResult(
        query="How does force change motion?",
        mode=RetrievalMode.FIXTURE,
        hits=(
            _hit(
                chunk_id="chunk-openstax",
                rank=1,
                provider="openstax",
                textbook_id="openstax_college_physics_2e",
                document_id="doc-openstax",
                chapter_id="4",
                source_name="openstax_college_physics_2e",
                page_or_location="p121",
                text="Net force changes motion.",
            ),
            _hit(
                chunk_id="chunk-libretexts",
                rank=2,
                provider="libretexts",
                textbook_id="libretexts_university_physics",
                document_id="doc-libretexts",
                chapter_id="5",
                source_name="libretexts_university_physics",
                page_or_location="chapter-5",
                text="Acceleration follows the net force.",
            ),
        ),
    )


def test_builder_preserves_full_identity_and_observes_budget(
    caplog: pytest.LogCaptureFixture,
) -> None:
    builder = EvidenceBundleAdapter(
        RegexTokenCounter(),
        run_provenance={"trace_id": "trace-1"},
    )
    assert isinstance(builder, EvidenceBundleBuilder)

    with caplog.at_level(logging.WARNING):
        bundle = builder.build(_retrieval(), token_budget=1)

    assert [item.evidence_id for item in bundle.evidence_items] == ["E1", "E2"]
    assert [item.chunk_id for item in bundle.evidence_items] == [
        "chunk-openstax",
        "chunk-libretexts",
    ]
    assert bundle.citation_map == {
        "E1": "chunk-openstax",
        "E2": "chunk-libretexts",
    }
    first = bundle.evidence_items[0]
    assert first.provider == "openstax"
    assert first.textbook_id == "openstax_college_physics_2e"
    assert first.document_id == "doc-openstax"
    assert first.chapter_id == "4"
    assert first.page_or_location == "p121"
    assert first.source_locator == _retrieval().hits[0].source_locator
    assert len(bundle.evidence_items) == 2
    assert bundle.token_count == sum(item.token_count for item in bundle.evidence_items)
    assert bundle.run_provenance["trace_id"] == "trace-1"
    assert bundle.run_provenance["token_budget"] == "1"
    assert bundle.run_provenance["token_budget_policy"] == "observe_only"
    assert bundle.run_provenance["token_budget_exceeded"] == "true"
    assert '"provider": "openstax"' in bundle.prompt_context
    assert "preserving all hits" in caplog.text


def test_builder_keeps_empty_retrieval_and_provenance() -> None:
    provenance = EvidenceProvenance(
        corpus_version="2.0.0-dev.1",
        corpus_hash="sha256:corpus",
        manifest_hash="sha256:manifest",
        chunk_config_hash="sha256:chunks",
        index_version="index-1",
        retrieval_mode=RetrievalMode.FIXTURE,
        retrieval_config_hash="sha256:retrieval",
    )
    retrieval = RetrievalResult(
        query="No matching evidence",
        mode=RetrievalMode.FIXTURE,
        provenance=provenance,
    )

    bundle = EvidenceBundleAdapter().build(retrieval)

    assert bundle.evidence_items == ()
    assert bundle.citation_map == {}
    assert bundle.prompt_context is None
    assert bundle.token_count == 0
    assert bundle.retrieval_provenance == provenance


def test_builder_rejects_provenance_mode_drift() -> None:
    retrieval = _retrieval().model_copy(
        update={
            "provenance": EvidenceProvenance(
                corpus_version="2.0.0-dev.1",
                corpus_hash="sha256:corpus",
                manifest_hash="sha256:manifest",
                chunk_config_hash="sha256:chunks",
                index_version="index-1",
                retrieval_mode=RetrievalMode.BM25,
                retrieval_config_hash="sha256:retrieval",
            )
        }
    )

    with pytest.raises(ValueError, match="retrieval mode"):
        EvidenceBundleAdapter().build(retrieval)


def test_validator_accepts_only_chunk_ids_and_preserves_run_provenance() -> None:
    bundle = EvidenceBundleAdapter(run_provenance={"trace_id": "trace-2"}).build(
        _retrieval()
    )
    validator = CitationValidatorAdapter()
    assert isinstance(validator, CitationValidator)
    answer = GeneratedAnswer(
        final_choice="A",
        explanation="The first source supports the answer.",
        citations=("chunk-openstax",),
    )

    validated = validator.validate(answer, bundle)

    assert validated.citation_status == "passed"
    assert validated.resolved_citations == ("chunk-openstax",)
    assert validated.run_provenance["trace_id"] == "trace-2"

    display_id_answer = answer.model_copy(update={"citations": ("E1",)})
    display_id_result = validator.validate(display_id_answer, bundle)
    assert display_id_result.citation_status == "failed"
    assert display_id_result.resolved_citations == ()

    unknown_answer = answer.model_copy(update={"citations": ("unknown-chunk",)})
    unknown_result = validator.validate(unknown_answer, bundle)
    assert unknown_result.citation_status == "failed"
    assert unknown_result.resolved_citations == ()


def test_validator_skips_citations_for_abstention() -> None:
    bundle = EvidenceBundleAdapter().build(_retrieval())
    answer = GeneratedAnswer(
        explanation="The supplied evidence is insufficient.",
        abstained=True,
    )

    validated = CitationValidatorAdapter().validate(answer, bundle)

    assert validated.citation_status == "skipped"
    assert validated.resolved_citations == ()
    assert validated.abstained is True

