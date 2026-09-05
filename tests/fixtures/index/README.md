# Shared Real-Retrieval CI Fixture

This directory is the canonical repository fixture for deterministic real-mode
retrieval tests. Tests and CI should reuse it instead of creating a second
fixture with different semantics.

## Files

- `artifact.json` describes the BM25 fixture artifact.
- `chunks.json` contains the searchable evidence.
- No `index.faiss` file is required because the BM25 backend reads only the
  chunk map.

## Invariants

- `artifact.json.chunk_count` must equal the number of entries in `chunks.json`.
- `position` values must be unique and consecutive from `0`.
- `chunk_id` values must be unique.
- Each chunk must contain `text`, `chapter_id`, and `source`.
- The fixture must remain deterministic and require no network access, external
  API, model download, or secret.
- Do not add evidence about quantum entanglement. That topic is deliberately
  absent so CI can verify that an out-of-scope question produces no hits and an
  abstained answer.

## Current Coverage

The fixture contains eight chunks across the `motion`, `forces`, and `energy`
chapters. It supports both sides of the real BM25 CI gate:

1. `What is acceleration?` must return evidence and a grounded answer.
2. `What is quantum entanglement?` must return no evidence and must abstain.

When changing this fixture, update `chunk_count`, keep positions consecutive,
and run the complete test suite before committing.