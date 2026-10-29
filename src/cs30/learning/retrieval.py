"""Live hybrid retrieval adapters that restore native v2 evidence identity."""

from __future__ import annotations

import json
from typing import Any

from cs30.contracts import (
    IndexArtifact as LegacyIndexArtifact,
)
from cs30.contracts import (
    RetrievalMode as LegacyRetrievalMode,
)
from cs30.retrieval.real import BM25Retriever, FaissDenseRetriever, RealRetrievalService
from cs30.retrieval.v2_adapter import materialise_v2_retrieval_view
from cs30.v2.contracts import (
    EvidenceProvenance,
    IndexArtifact,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
)
from cs30.v2.ids import sha256_bytes
from cs30.v2.io import canonical_hash


def _load_cached_embedding_model(
    model_name: str,
    *,
    revision: str | None,
    trust_remote_code: bool,
) -> Any:
    """Resolve only a local HF snapshot; the app never downloads embeddings on demand."""

    from huggingface_hub import snapshot_download

    model_path = snapshot_download(
        repo_id=model_name,
        revision=revision,
        local_files_only=True,
    )
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_path, trust_remote_code=trust_remote_code)


def build_online_hybrid_retriever(assets, config):
    """Build M6's pinned Qwen3/BM25 RRF retriever from a validated v2 index."""

    raw_index = json.loads(config.index_artifact_path.read_text(encoding="utf-8"))
    v2_artifact = IndexArtifact.model_validate(raw_index)
    materialise_v2_retrieval_view(
        v2_artifact=v2_artifact.model_dump(mode="json"),
        records=[chunk.model_dump(mode="json") for chunk in assets.corpus.chunks],
        index_source=config.index_file_path,
        output_dir=config.compatibility_index_dir,
        query_instruction=config.query_instruction,
        query_prompt_name=config.query_prompt_name,
    )
    compatibility = LegacyIndexArtifact.model_validate_json(
        (config.compatibility_index_dir / "artifact.json").read_text(encoding="utf-8")
    )

    dense = FaissDenseRetriever(
        expected_model_name=config.dense_embedding_model,
        expected_model_revision=config.dense_embedding_revision,
        query_instruction=config.query_instruction,
        query_prompt_name=config.query_prompt_name,
        model_loader=_load_cached_embedding_model,
    )
    bm25 = BM25Retriever()
    service = RealRetrievalService(
        dense=dense,
        bm25=bm25,
        rrf_k=config.rrf_k,
        input_top_k=config.candidate_k,
        dense_weight=config.dense_weight,
        bm25_weight=config.bm25_weight,
    )
    service.load_index(compatibility, LegacyRetrievalMode.HYBRID)
    return service.backend(LegacyRetrievalMode.HYBRID)


def restore_v2_retrieval_result(legacy_result, assets, config) -> RetrievalResult:
    """Attach canonical v2 metadata to a real.py result without guessing identities."""

    corpus = assets.corpus
    index = assets.index_artifact
    provenance = EvidenceProvenance(
        corpus_version=corpus.manifest.corpus_version,
        corpus_hash=corpus.manifest.corpus_hash,
        manifest_hash=corpus.manifest.manifest_hash,
        chunk_config_hash=corpus.manifest.chunk_config_hash,
        index_version=index.index_version,
        retrieval_mode=RetrievalMode.HYBRID,
        retrieval_config_hash=canonical_hash(
            {
                "backend": "cs30.retrieval.real.RRFRetriever",
                "embedding_model": config.dense_embedding_model,
                "embedding_revision": config.dense_embedding_revision,
                "dense_weight": config.dense_weight,
                "bm25_weight": config.bm25_weight,
                "rrf_k": config.rrf_k,
                "input_top_k": config.candidate_k,
                "query_instruction": config.query_instruction,
                "query_prompt_name": config.query_prompt_name,
                "index_sha256": sha256_bytes(config.index_file_path.read_bytes()),
            }
        ),
        embedding_model=config.dense_embedding_model,
        embedding_revision=config.dense_embedding_revision,
    )
    hits = []
    for hit in legacy_result.hits:
        chunk = corpus.chunks_by_id.get(hit.chunk_id)
        if chunk is None:
            raise ValueError(f"retriever returned unknown chunk_id {hit.chunk_id!r}")
        if hit.text != chunk.text:
            raise ValueError(f"retriever text differs from canonical chunk {hit.chunk_id!r}")
        hits.append(
            RetrievedEvidence(
                provider=chunk.provider,
                textbook_id=chunk.textbook_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                chapter_id=chunk.chapter_id,
                source_name=chunk.source_name,
                page_or_location=chunk.page_or_location,
                source_locator=chunk.source_locator,
                text=chunk.text,
                score=float(hit.score),
                rank=int(hit.rank),
                retriever_type=RetrievalMode(str(hit.retriever_type.value)),
            )
        )
    return RetrievalResult(
        query=legacy_result.query,
        mode=RetrievalMode.HYBRID,
        hits=tuple(hits),
        provenance=provenance,
    )
