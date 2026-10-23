# v2 Restricted KG

The Restricted KG is an evidence-bound sidecar over one immutable v2 corpus.
It does not modify retrieval chunks or the M1-owned Topic registry and
chunk-topic map.

## Contract

- The graph records `schema_version`, `kg_version`, `corpus_version`, and
  `corpus_hash`.
- The allowed relation types are `prerequisite_of`, `applied_to`, and
  `next_concept`.
- Every concept and relation carries one or more exact source excerpts. Each
  excerpt identifies a corpus `chunk_id`, document-global character range,
  verbatim text, and SHA-256 hash.
- `candidate` and `quarantined` items must carry review reasons. `accepted`
  items must not carry unresolved review reasons.
- An accepted relation must connect two accepted concepts. Duplicate accepted
  triples, missing endpoints, invalid evidence, and two-way accepted
  prerequisite edges fail the audit.

## Candidate extraction

The initial extractor uses numbered textbook sections to create 50–150
provider-neutral concept candidates. It uses section order for
`next_concept` candidates and weaker `prerequisite_of` candidates; titles that
contain “application” may add `applied_to` candidates. These heuristics never
auto-accept a relation. Human review remains responsible for semantic
direction, ambiguity, duplication, and support.

Run:

```bash
python scripts/build_restricted_kg.py \
  artifacts/v2/textbooks/2.0.0-dev.m4-structure-v2-main-3553825 \
  artifacts/v2/restricted-kg/three-book-dev-v1
```

The output directory contains:

- `restricted_kg_candidates.json`: the versioned graph sidecar;
- `review_queue.jsonl`: every non-accepted item and its evidence;
- `audit_report.json`: counts and integrity findings.

The current three-book corpus is development-only. Its KG is therefore also
development-only and must be rebuilt against the official four-provider
corpus before reportable evaluation.
