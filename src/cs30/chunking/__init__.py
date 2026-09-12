"""Member 4: chunking and chunk metadata."""

from .candidates import CHUNKING_CANDIDATES, ChunkingCandidate, get_chunking_candidate
from .chunker import BlockAwareChunker, UnicodeWordPunctTokenCounter
from .corpus import export_retrieval_corpus, load_retrieval_corpus, verify_corpus_identity
from .fixture import FixtureChunker
from .gold_mapping import (
    GOLD_MAPPING_SCHEMA_VERSION,
    GOLD_MATCH_RULE_ID,
    GOLD_MATCH_RULE_VERSION,
    GoldSpan,
    build_evaluation_mapping,
    load_gold_spans,
    load_normalized_gold_spans,
    map_gold_spans_to_chunks,
    matching_rule,
    verify_mapping_identity,
)
from .official import (
    W5_CHUNKING_STRATEGY,
    W5_CONFIG_ID,
    W5_EMBEDDING_MODEL,
    W5_INCLUDED_TYPES,
)
from .reporting import (
    build_chunk_anomalies,
    build_chunk_statistics,
    build_traceability_samples,
)
from .strategy import BlockChunkingStrategy
from .traceback import resolve_small_to_big

__all__ = [
    "BlockAwareChunker",
    "BlockChunkingStrategy",
    "CHUNKING_CANDIDATES",
    "ChunkingCandidate",
    "FixtureChunker",
    "GOLD_MAPPING_SCHEMA_VERSION",
    "GOLD_MATCH_RULE_ID",
    "GOLD_MATCH_RULE_VERSION",
    "GoldSpan",
    "UnicodeWordPunctTokenCounter",
    "W5_CHUNKING_STRATEGY",
    "W5_CONFIG_ID",
    "W5_EMBEDDING_MODEL",
    "W5_INCLUDED_TYPES",
    "build_chunk_anomalies",
    "build_chunk_statistics",
    "build_evaluation_mapping",
    "build_traceability_samples",
    "export_retrieval_corpus",
    "get_chunking_candidate",
    "load_retrieval_corpus",
    "load_gold_spans",
    "load_normalized_gold_spans",
    "map_gold_spans_to_chunks",
    "matching_rule",
    "resolve_small_to_big",
    "verify_corpus_identity",
    "verify_mapping_identity",
]
