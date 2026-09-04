# W3 proposal update: delivery, evidence and risk

## Background

The project is a personalised learning assistant that retrieves OpenStax
evidence, generates an answer at a learner level, and exposes evidence and
citation status to the tutor/demo user. Member 8 makes the evidence-to-answer
boundary inspectable: selected passages receive stable display IDs, prompt
context is token-bounded, and citations resolve back to retrieved sources.

## Literature position

The implementation follows the retrieval-augmented generation pattern:
retrieval supplies source passages, generation produces an answer constrained by
those passages, and citation validation checks that the answer points back to
the same retrieved evidence. Personalisation changes explanation guidance and
learner level; it does not change the evidence source of truth or permit an
unsupported citation. These engineering checks remain separate from formal
retrieval or model-quality evaluation.

## Timeline and delivery state

| Area | Current state | Next integration step |
|---|---|---|
| Evidence assembly | Implemented with EvidenceBundle, stable E-IDs, deduplication and token budget | Confirm the final M7 hand-off shape |
| Citation governance | Implemented with resolver, validator, ValidatedAnswer and trace | Confirm artifact-version fields with the Leader |
| Demo UI | Fixture-backed, reviewable and runnable with offline fallback | Replace fixture adapters when approved M6/M7 adapters are available |
| Dependency reproducibility | Pinned requirements.lock added and verified against the local environment | Reconfirm the team's preferred lock-tool format |

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| M7 and M8 disagree on the EvidenceBundle hand-off | Integration delay or duplicate conversion logic | Keep the current RetrievalResult path compatible and obtain Leader/M7 confirmation before changing the generator protocol |
| Fixture data is mistaken for real retrieval or model evaluation | Misleading demo or report claims | Keep fixture-mode banners, source labels, runbook wording and explicit scope statements |
| Index/corpus versions are omitted from a trace | A citation cannot be reproduced exactly | Record index and corpus version fields in the pipeline trace |
| Dependency drift between machines | CI/demo startup failures | Use requirements.lock and verify it against the active environment |
| Secrets or private student data enter logs or Git | Privacy/security exposure | Keep keys in environment/secret storage and restrict traces to IDs, hashes and status metadata |

## Report boundary

The branch documents implemented engineering behaviour and identifies pending
integration decisions. It does not claim retrieval quality, model accuracy, or
real-LLM performance from the fixture demo.
