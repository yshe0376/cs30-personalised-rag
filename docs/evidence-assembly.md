# Evidence Assembly and Citation Validation

This is the Member 8 W5 boundary between retrieval, generation and the demo.

## Data flow

```text
RetrievedEvidence / RetrievalResult
        -> EvidenceContextBuilder (fixture implementation: build_evidence_bundle)
        -> EvidenceBundle with E1, E2, ... and citation_map
        -> Member 7 generation
        -> ValidatedAnswer
        -> UI and trace log
```

`EvidenceBundle.evidence_items` preserves retrieved text and its source locator.
Display IDs are assigned in rank order and are stable within a run.
`citation_map` maps each display ID to the original chunk ID. The resolver also
accepts legacy chunk IDs during the transition from the W4 contract.

The bundle records a token estimate, retrieval mode and provenance. The current
fixture implementation uses whitespace tokens and a 1200-token budget; the
production implementation can replace the estimator when the approved tokenizer
is known.

## Validation rules

- Every evidence ID is unique.
- Every evidence ID maps to exactly one retrieved chunk.
- A non-abstained answer must cite an evidence ID or a retrieved legacy chunk ID.
- Unknown citations raise `CitationIntegrityError`.
- An abstained answer has no resolved citations and is marked `skipped`.

## Privacy and logging boundary

Trace fields contain request metadata, IDs, hashes and status values. They should
not contain API keys, full student profiles, or unnecessary personal data. The
UI shows source and evidence metadata for demonstration, while secrets remain in
the deployment environment and outside Git.
