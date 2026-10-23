from __future__ import annotations

from cs30.contracts import (
    EvidenceProvenance as LegacyProvenance,
)
from cs30.contracts import (
    RetrievalMode as LegacyRetrievalMode,
)
from cs30.contracts import (
    RetrievalResult as LegacyRetrievalResult,
)
from cs30.contracts import (
    RetrievedEvidence as LegacyEvidence,
)
from cs30.retrieval.m6_handoff import freeze_v2_retrieval
from cs30.v2.experiment import FrozenRetrieval


def test_qwen_handoff_is_strict_frozen_retrieval_v2() -> None:
    result = LegacyRetrievalResult(
        query="Why does it move?",
        mode=LegacyRetrievalMode.HYBRID,
        hits=[
            LegacyEvidence(
                chunk_id="chunk-1",
                text="Evidence text.",
                chapter_id="chapter-1",
                source="book",
                score=0.25,
                rank=1,
                retriever_type=LegacyRetrievalMode.HYBRID,
            )
        ],
        provenance=LegacyProvenance(
            corpus_hash="sha256:corpus",
            chunk_config_hash="sha256:chunks",
            embedding_model="Qwen/Qwen3-Embedding-0.6B",
            index_version="qwen-index",
        ),
    )
    frozen = freeze_v2_retrieval(
        question_id="q-1",
        question="Why does it move?",
        result=result,
        chunks_by_id={
            "chunk-1": {
                "provider": "openstax",
                "textbook_id": "physics",
                "document_id": "doc-1",
                "chapter_id": "chapter-1",
                "source_name": "book",
                "page_or_location": "p. 1",
                "source_locator": (
                    "source=book|textbook=physics|chapter=chapter-1|location=p.%201|span=0:14"
                ),
                "text": "Evidence text.",
            }
        },
        corpus_manifest={
            "corpus_version": "2.0.0-dev",
            "corpus_hash": "sha256:corpus",
            "manifest_hash": "sha256:manifest",
            "chunk_config_hash": "sha256:chunks",
        },
        embedding_model="Qwen/Qwen3-Embedding-0.6B",
        embedding_revision="qwen-revision",
        index_version="qwen-index",
        retrieval_config={"dense_weight": 0.10, "bm25_weight": 0.90},
    )

    payload = frozen.model_dump(mode="json")
    assert set(payload) == {"question_id", "retrieval"}
    assert payload["retrieval"]["schema_version"] == "2.0"
    assert payload["retrieval"]["hits"][0]["schema_version"] == "2.0"
    assert payload["retrieval"]["hits"][0]["provider"] == "openstax"
    assert payload["retrieval"]["provenance"]["embedding_revision"] == "qwen-revision"
    assert FrozenRetrieval.model_validate(payload) == frozen
