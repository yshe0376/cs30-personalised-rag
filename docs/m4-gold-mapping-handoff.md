# M4 Gold-to-chunk mapping handoff

Status: W5 evaluation contract, 2026-09-12.

This document is the concrete handoff between M1's Gold normalization and
M4's chunk mapping. It does not change M3's source artifact.

## Coordinate contract

M3's raw `gold_v0_1.jsonl` remains immutable. In that file:

- `char_start` and `char_end` are half-open offsets within `chapter_id`;
- `document_id`, `chapter_id`, `block_id`, and `verbatim_text` identify and
  replay the annotated evidence;
- `corpus_version` may be the short source/document identity supplied by M3.

M1's separate normalized v0.2 file copies the local offsets to
`chapter_char_start`/`chapter_char_end` and derives
`corpus_char_start`/`corpus_char_end` against one prepared merged corpus. It
records the full separator-bound `corpus_version`, `resolution_status`, and,
when successful, `resolved_block_id`. The original `char_start`/`char_end`
fields remain chapter-local in every version.

M4 should use the normalized file and its prepared `corpus_manifest.json` as
the input identity, but it does not need to map spans by global character
offset. Block-based mapping remains the source of truth for chunk coverage.

## Concrete input and output

One normalized span can look like this (irrelevant Gold fields omitted):

```json
{
  "span_id": "q-001-core-a",
  "document_id": "openstax-cp2e-a052d9fae2a90e13",
  "chapter_id": "18",
  "block_id": "ch18-block-0042",
  "char_start": 120,
  "char_end": 167,
  "chapter_char_start": 120,
  "chapter_char_end": 167,
  "corpus_char_start": 523410,
  "corpus_char_end": 523457,
  "verbatim_text": "...the annotated evidence...",
  "resolved_block_id": "ch18-block-0042",
  "resolution_status": "resolved",
  "resolution_method": "block_id"
}
```

M4 turns the span into the existing mapping shape:

```json
{
  "schema_version": "0.1",
  "question_id": "q-001",
  "corpus_version": "openstax-cp2e-...-v<fingerprint>",
  "chunk_config_hash": "chunks-<hash>",
  "mapping_version": "mapping-<date-or-hash>",
  "spans": [
    {
      "span_id": "q-001-core-a",
      "acceptable_chunk_sets": [["chunk-18-0042"]]
    }
  ]
}
```

The mapping must include every core and partial `span_id`. Core evidence-set
semantics stay in Gold: alternatives are outer OR and required spans within a
set are inner AND. Partial spans are diagnostic inputs for noise and partial
coverage metrics.

## When to regenerate

| Change | M1 normalized Gold | M4 mapping |
|---|---|---|
| Chunker or chunk configuration only | Keep it; the corpus coordinate system is unchanged | Regenerate with a new `chunk_config_hash` and `mapping_version` |
| Chapter order or separator | Re-normalize from immutable M3 raw Gold for the new corpus version | Regenerate for the new corpus version |
| Parser or source textbook text | Create a new corpus version and re-run normalization | Regenerate after normalization succeeds |
| Block split/merge or block text changed | M1 attempts block/text resolution; stale, ambiguous, and cross-block failures are reported by `span_id` | Wait for M3 review of failed spans, then regenerate |

The normalized Gold, corpus manifest, and mapping are append-only artifacts.
Do not overwrite a previous version: an old score must remain reproducible
against its original `corpus_version`, `chunk_config_hash`, and
`mapping_version`.

## Handoff checklist

1. M1 gives M4 the immutable raw Gold path, normalized Gold path, prepared
   corpus manifest, and normalization report.
2. M4 confirms that its mapping `corpus_version` exactly matches the
   normalized Gold and prepared manifest.
3. M4 records a new `chunk_config_hash` whenever chunking changes and a new
   `mapping_version` for every mapping artifact.
4. M4 sends stale/ambiguous span IDs back to M3; no fallback match is accepted
   when it is non-unique or crosses block boundaries.
5. M1's compatibility check must pass before a reportable run or score is
   published.
