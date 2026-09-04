# Shared fixture index

A tiny, hand-written stand-in for the artifact directory Member 5's
`FaissIndexBuilder` writes. It exists so CI and unit tests can exercise the
**real** retrieval path without building a real index.

```
artifact.json   IndexArtifact manifest (metadata mirrors a real M5 build)
chunks.json     chunk map, same field set M5 persists, positions 0..8
```

Nine chunks of paraphrased introductory physics across three chapters
(`ch01_motion`, `ch02_forces`, `ch03_energy`).

## What it is for

CI's `smoke` job asserts two properties against it in `--mode real`:

- an out-of-scope question (`"What is quantum entanglement?"`) retrieves
  nothing and the pipeline abstains;
- an in-scope question (`"What is acceleration?"`) retrieves evidence and
  every citation is grounded in that evidence.

Both directions are needed. The first alone would also pass for a retriever
that always returns nothing.

## BM25 only, on purpose

There is **no `index.faiss` here**. `BM25Retriever.load_index` reads only
`chunks.json`, so the BM25 path runs on a core-only install with no FAISS and
no sentence-transformers. `metadata.index_file` still names the file a real
build would produce; dense and hybrid retrieval against this directory raise
`IndexUnavailableError`, which is intended.

## If you edit it

- `chunk_count` in `artifact.json` must equal the number of entries in
  `chunks.json`, and `position` must run consecutively from zero, or
  `_load_chunk_map` rejects the artifact.
- Do not add the words `quantum` or `entanglement` to any chunk. The
  out-of-scope assertion depends on them being absent.
- This directory is shared. Reuse it from new tests rather than writing a
  second fixture index with different semantics.
