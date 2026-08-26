"""Member 4: chunking and chunk metadata."""

from .chunker import BlockAwareChunker, UnicodeWordPunctTokenCounter
from .fixture import FixtureChunker
from .reporting import build_chunk_statistics, build_traceability_samples
from .strategy import BlockChunkingStrategy

__all__ = [
    "BlockAwareChunker",
    "BlockChunkingStrategy",
    "FixtureChunker",
    "UnicodeWordPunctTokenCounter",
    "build_chunk_statistics",
    "build_traceability_samples",
]
