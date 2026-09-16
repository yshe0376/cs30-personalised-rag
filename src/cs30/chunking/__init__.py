"""Member 4: chunking and chunk metadata."""

from .candidates import CHUNKING_CANDIDATES, ChunkingCandidate, get_chunking_candidate
from .chunker import BlockAwareChunker, UnicodeWordPunctTokenCounter
from .corpus import export_retrieval_corpus, load_retrieval_corpus
from .fixture import FixtureChunker
from .gold_mapping import (
    GoldSpan,
    build_evaluation_mapping,
    load_normalized_gold_spans,
    map_gold_spans_to_chunks,
    validate_chunk_source_blocks,
    verify_mapping_identity,
)
from .official import W5_CHUNKING_STRATEGY, W5_CONFIG_ID, W5_EMBEDDING_MODEL
from .reporting import build_chunk_statistics, build_traceability_samples
from .strategy import BlockChunkingStrategy
from .traceback import resolve_small_to_big

__all__ = [
    "BlockAwareChunker",
    "BlockChunkingStrategy",
    "CHUNKING_CANDIDATES",
    "ChunkingCandidate",
    "FixtureChunker",
    "GoldSpan",
    "UnicodeWordPunctTokenCounter",
    "W5_CHUNKING_STRATEGY",
    "W5_CONFIG_ID",
    "W5_EMBEDDING_MODEL",
    "build_evaluation_mapping",
    "build_chunk_statistics",
    "build_traceability_samples",
    "export_retrieval_corpus",
    "get_chunking_candidate",
    "load_retrieval_corpus",
    "load_normalized_gold_spans",
    "map_gold_spans_to_chunks",
    "resolve_small_to_big",
    "validate_chunk_source_blocks",
    "verify_mapping_identity",
]
