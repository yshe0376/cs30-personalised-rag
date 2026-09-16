"""Frozen Week 5 Member 4 chunking configuration."""

from __future__ import annotations

from cs30.chunking.strategy import BlockChunkingStrategy
from cs30.evidence_policy import EVIDENCE_CONTENT_TYPES

W5_CONFIG_ID = "w5-m4-official-v1"
W5_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Keep the official chunker aligned with the shared evidence policy without
# duplicating the eligible content-type list in the M4 module.
W5_INCLUDED_TYPES = EVIDENCE_CONTENT_TYPES

W5_CHUNKING_STRATEGY = BlockChunkingStrategy(
    target_tokens=500,
    min_tokens=100,
    max_tokens=600,
    respect_section_boundaries=True,
    enrich_embed_text=False,
    # The textbook legitimately repeats short equations, captions and glossary
    # text at different source locations. Preserve every location so citation
    # provenance remains complete; the corpus QA reports duplicate-text groups.
    reject_duplicate_text=False,
    candidate_id=W5_CONFIG_ID,
    include_types=W5_INCLUDED_TYPES,
    chunker_version="0.5.0",
)
