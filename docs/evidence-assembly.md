# Evidence Assembly and Citation Validation

This is the Member 8 W5 boundary between retrieval, generation and the demo.

## Data flow

```text
RetrievedEvidence / RetrievalResult
        -> EvidenceContextBuilder (fixture implementation: build_evidence_bundle)
        -> EvidenceBundle with evidence items (E IDs are local display labels)
        -> Member 7 integration (downstream consumer)
        -> ValidatedAnswer
        -> UI and trace log
```

`EvidenceBundle.evidence_items` preserves retrieved text and its source locator.
Display IDs are assigned in rank order for the M8 UI and are stable within a run.
They are not part of the Member 7 citation interface; a downstream generator
uses the original stable chunk IDs when it consumes the bundle. The fixture is
provided for that integration; M8 does not own Member 7's prompt or LLM
implementation.

The bundle records a whitespace-based estimate capped at 1500 retrieved-token
equivalents, retrieval mode and two provenance layers.
`retrieval_provenance` preserves the structured corpus and index identity supplied
by the retrieval contract, while `run_provenance` records run-level information
such as the environment and request ID. A production tokenizer can replace the
estimate once the team approves and provisions a tokenizer for all environments.

## Validation rules

- Every evidence ID is unique.
- Every evidence ID maps to exactly one retrieved chunk.
- A non-abstained answer must cite a chunk ID from the bundle.
- Unknown citations raise `CitationIntegrityError`.
- An abstained answer has no resolved citations and is marked `skipped`.

## Privacy and logging boundary

Trace fields contain request metadata, IDs, hashes and status values. They should
not contain API keys, full student profiles, or unnecessary personal data. The
UI shows source and evidence metadata for demonstration, while secrets remain in
the deployment environment and outside Git.
