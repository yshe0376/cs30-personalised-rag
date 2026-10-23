"""Build the strict V2 frozen-retrieval handoff consumed by M7."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cs30.contracts import RetrievalMode as LegacyRetrievalMode
from cs30.contracts import RetrievalResult as LegacyRetrievalResult
from cs30.v2.contracts import (
    EvidenceProvenance,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
)
from cs30.v2.experiment import FrozenRetrieval
from cs30.v2.io import canonical_hash


def freeze_v2_retrieval(
    *,
    question_id: str,
    question: str,
    result: LegacyRetrievalResult,
    chunks_by_id: Mapping[str, Mapping[str, Any]],
    corpus_manifest: Mapping[str, Any],
    embedding_model: str,
    embedding_revision: str,
    index_version: str,
    retrieval_config: Mapping[str, Any],
) -> FrozenRetrieval:
    """Convert one real Hybrid result into M7's strict two-field V2 envelope."""
    cleaned_question = question.strip()
    if result.query != cleaned_question:
        raise ValueError("retrieval query must equal the original Gold question")
    if result.mode is not LegacyRetrievalMode.HYBRID:
        raise ValueError("the M6 system handoff must contain Hybrid retrieval")

    provenance = EvidenceProvenance(
        corpus_version=corpus_manifest["corpus_version"],
        corpus_hash=corpus_manifest["corpus_hash"],
        manifest_hash=corpus_manifest["manifest_hash"],
        chunk_config_hash=corpus_manifest["chunk_config_hash"],
        index_version=index_version,
        retrieval_mode=RetrievalMode.HYBRID,
        retrieval_config_hash=canonical_hash(dict(retrieval_config)),
        embedding_model=embedding_model,
        embedding_revision=embedding_revision,
    )
    hits = []
    for hit in result.hits:
        try:
            chunk = chunks_by_id[hit.chunk_id]
        except KeyError as exc:
            raise ValueError(f"retrieval returned unknown chunk_id: {hit.chunk_id}") from exc
        if hit.text != chunk["text"]:
            raise ValueError(f"retrieval text differs from corpus chunk: {hit.chunk_id}")
        hits.append(
            RetrievedEvidence(
                provider=chunk["provider"],
                textbook_id=chunk["textbook_id"],
                document_id=chunk["document_id"],
                chunk_id=hit.chunk_id,
                chapter_id=chunk["chapter_id"],
                source_name=chunk["source_name"],
                page_or_location=chunk.get("page_or_location"),
                source_locator=chunk["source_locator"],
                text=chunk["text"],
                score=float(hit.score),
                rank=hit.rank,
                retriever_type=RetrievalMode(hit.retriever_type.value),
            )
        )
    return FrozenRetrieval(
        question_id=question_id,
        retrieval=RetrievalResult(
            query=cleaned_question,
            mode=RetrievalMode.HYBRID,
            hits=tuple(hits),
            provenance=provenance,
        ),
    )
