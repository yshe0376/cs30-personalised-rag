# Member 7 - personalised prompt and LLM generation

Implement `cs30.ports.AnswerGenerator`:

    `generate(question, profile, evidence) -> GeneratedAnswer`

Member 8 constructs the `EvidenceBundle` before this boundary. The generator
must use its evidence IDs in the fixed JSON citations. Drop the real
implementation next to `fixture.py`, then swap it into `build_real_deps()` in
`src/cs30/pipeline.py`.

## Week 1 acceptance

- Output parses into the fixed JSON schema.
- Citation ids come from the supplied `EvidenceBundle` and resolve to the
  original retrieved chunks through its `citation_map`.
- Three levels reach the prompt.
- One API failure does not abort the batch.

## Notes

Abstention is a first-class outcome: set `abstained=True` with no
`final_choice` and no citations. The contract rejects an answer that
cites nothing without abstaining, so an ungrounded claim cannot be built.
