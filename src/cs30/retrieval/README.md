# Member 6 - BM25, Dense, and Hybrid retrieval

Implement `cs30.ports.Retriever`:

    `load_index(artifact: IndexArtifact) -> None`
    `retrieve(query: str, top_k: int) -> RetrievalResult`

The real implementation lives in `real.py`. Team callers should construct it
through `build_real_retrieval_deps()` for retrieval-only evaluation, or through
`build_real_deps()` for the complete retrieval-and-generation path. Both paths
keep the frozen `Retriever` protocol unchanged.

## W5 model policy

The primary Dense model is M5's current official default:
`sentence-transformers/all-MiniLM-L6-v2`.

The primary index directory is
`artifacts/w5/m5_latest/all-minilm-l6-v2`, matching
`scripts/build_official_faiss.py`. All W5 retrieval and evaluation runs use
`top_k=5` and report Hit@1, Hit@3, Hit@5, Recall@1, Recall@3, Recall@5, and MRR.

The following M5 comparison indexes remain candidates only:

- `sentence-transformers/all-mpnet-base-v2`
- `intfloat/e5-base-v2`
- `BAAI/bge-base-en-v1.5`
- `BAAI/bge-m3`

M6 loads the model recorded in M5's `artifact.json` and checks it against
`retrieval.expected_embedding_model`. To evaluate a candidate, change both
`CS30_INDEX_DIR` and `CS30_EXPECTED_EMBEDDING_MODEL`; changing only one fails
with `ArtifactMismatchError` instead of silently mixing model and index.

## Week 1 acceptance

- A question reliably returns Top-K chunks.
- Results carry textbook source and chunk id.
- Member 7 can build a prompt straight from the result.
- Bad index or input returns a clear error instead of exiting.
- Dense and Hybrid can return no evidence after threshold filtering; the
  generation path then abstains with no citations.

## Notes

Finding nothing is NOT an error: return `RetrievalResult` with an empty
`hits` list and let the generator abstain. Reserve exceptions
(`IndexUnavailableError`, `EmptyQueryError`) for genuine failures.

RRF defaults to equal contributions (`1.0`, `1.0`), which preserves the
existing unweighted ranking. Candidate weights from the M6 Dev/Test notebook
are configurable, but they must be selected on Dev and frozen before Test.
