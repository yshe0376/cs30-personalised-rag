"""Embedding-model policy shared by M6 retrieval entry points.

M5 owns index construction. M6 never rebuilds or silently substitutes an
embedding model while loading an index: the configured expectation must match
the model recorded in ``IndexArtifact.metadata``.
"""

PRIMARY_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

CANDIDATE_EMBEDDING_MODELS = (
    "sentence-transformers/all-mpnet-base-v2",
    "intfloat/e5-base-v2",
    "BAAI/bge-base-en-v1.5",
    "BAAI/bge-m3",
)

SUPPORTED_EMBEDDING_MODELS = (
    PRIMARY_EMBEDDING_MODEL,
    *CANDIDATE_EMBEDDING_MODELS,
)
