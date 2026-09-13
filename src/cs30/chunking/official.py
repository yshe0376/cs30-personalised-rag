"""Frozen Week 5 Member 4 chunking configuration."""

from __future__ import annotations

from cs30.chunking.strategy import BlockChunkingStrategy
from cs30.contracts import ContentType

W5_CONFIG_ID = "w5-m4-official-v2"
W5_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# M3's Gold evidence includes problem and summary blocks. Keep those source
# types in the shared corpus so the Gold-to-chunk mapping and M5 index use
# exactly the same evidence universe. Other non-evidence navigation material
# remains excluded.
W5_INCLUDED_TYPES = (
    ContentType.BODY,
    ContentType.EXAMPLE,
    ContentType.FIGURE_CAPTION,
    ContentType.GLOSSARY,
    ContentType.TABLE,
    ContentType.EQUATION,
    ContentType.PROBLEM,
    ContentType.SUMMARY,
)

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
