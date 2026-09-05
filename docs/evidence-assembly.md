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
implementation. The current legacy generator path still receives the selected
`RetrievalResult` directly; adopting the bundle as the generator input is a
downstream M7 integration step.

The documented target is a 1500-token retrieved-context budget. The final
Member 7 generation model and its corresponding tokenizer cannot currently be
confirmed from the available Member 7 branch, so fixture mode temporarily
records a whitespace-based word-count estimate instead. This estimate is
observational rather than a strict token limit; when it exceeds the target,
the builder warns but keeps all selected evidence so generation and validation
do not receive different evidence sets. Once the generation model is confirmed,
the estimate will be replaced by that model's tokenizer and the 1500-token
budget will be enforced against real model tokens.
`retrieval_provenance` preserves the structured corpus and index identity supplied
by the retrieval contract, while `run_provenance` records run-level information
such as the environment and request ID. A model-specific tokenizer and strict
budget enforcement require a team-approved model/tokenizer and a downstream
bundle-consuming generator.

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
