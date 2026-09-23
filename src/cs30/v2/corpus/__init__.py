"""Versioned v2 corpus identity, manifest, and publish helpers."""

from cs30.v2.corpus.canonical import (
    canonical_corpus_bytes,
    canonical_manifest_bytes,
    corpus_hash,
    manifest_hash,
)
from cs30.v2.corpus.duplicates import (
    DuplicateBlockGroup,
    DuplicateBlockMember,
    DuplicateBlockReport,
    find_cross_textbook_duplicates,
    load_duplicate_report,
    write_duplicate_report,
)
from cs30.v2.corpus.manifest import (
    CorpusDocument,
    CorpusManifest,
    CorpusManifestDraft,
    build_manifest_draft,
    finalize_manifest,
    load_corpus_manifest,
    write_corpus_manifest,
)
from cs30.v2.topics import (
    ChunkTopicAssignment,
    ChunkTopicMap,
    LoadedChunkTopicMap,
    canonical_chunk_topic_map,
    load_chunk_topic_map,
    load_validated_chunk_topic_map,
    resolve_topic_from_citations,
    validate_chunk_topic_map,
    write_chunk_topic_map,
)

__all__ = [
    "CorpusDocument",
    "CorpusManifest",
    "CorpusManifestDraft",
    "ChunkTopicAssignment",
    "ChunkTopicMap",
    "LoadedChunkTopicMap",
    "DuplicateBlockGroup",
    "DuplicateBlockMember",
    "DuplicateBlockReport",
    "build_manifest_draft",
    "find_cross_textbook_duplicates",
    "load_duplicate_report",
    "write_duplicate_report",
    "canonical_corpus_bytes",
    "canonical_chunk_topic_map",
    "canonical_manifest_bytes",
    "corpus_hash",
    "finalize_manifest",
    "load_corpus_manifest",
    "load_chunk_topic_map",
    "load_validated_chunk_topic_map",
    "resolve_topic_from_citations",
    "manifest_hash",
    "validate_chunk_topic_map",
    "write_corpus_manifest",
    "write_chunk_topic_map",
]
