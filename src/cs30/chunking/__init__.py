"""Member 4: chunking and chunk metadata."""

from .candidates import CHUNKING_CANDIDATES, ChunkingCandidate, get_chunking_candidate
from .chunker import BlockAwareChunker, UnicodeWordPunctTokenCounter
from .corpus import export_retrieval_corpus, load_retrieval_corpus
from .fixture import FixtureChunker
from .reporting import build_chunk_statistics, build_traceability_samples
from .strategy import BlockChunkingStrategy
from .traceback import resolve_small_to_big

__all__ = [
    "BlockAwareChunker",
    "BlockChunkingStrategy",
    "CHUNKING_CANDIDATES",
    "ChunkingCandidate",
    "FixtureChunker",
    "UnicodeWordPunctTokenCounter",
    "build_chunk_statistics",
    "build_traceability_samples",
    "export_retrieval_corpus",
    "get_chunking_candidate",
    "load_retrieval_corpus",
    "resolve_small_to_big",
]
