# Member 5 - embeddings and the FAISS index

Implement `cs30.ports.IndexBuilder`:

    `build(chunks: list[Chunk]) -> IndexArtifact`
    `load() -> IndexArtifact`

Drop the real implementation next to `fixture.py`. The Leader supplies it as the
`index_builder` field of `BuildDeps`; `run_build_pipeline()` passes its manifest
to `Retriever.load_index()` without changing the orchestration code.

## Week 1 acceptance

- The same corpus and configuration rebuild the same index.
- A saved index can be loaded again.
- A loaded index returns the matching `chunk_id`.
- Member 6 can use the index through a fixed interface.

## Notes

Embed `chunk.embedding_input`, never `chunk.text` directly: it returns the
enriched text when member 4 supplied one and falls back to the verbatim text
otherwise. Record which of the two an index was built from in
`IndexArtifact.metadata`, because it is an ablation dimension.

Record the embedding model, dimension, device, and build time in
`IndexArtifact.metadata`. `location` must identify the saved FAISS index and
chunk map consistently. Raise
`IndexUnavailableError` when the index is missing or unreadable.

The fixture builder deliberately returns a process-local `memory://` artifact;
it is only an integration stand-in and does not claim persistence across runs.
