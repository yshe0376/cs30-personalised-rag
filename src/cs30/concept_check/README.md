# Member 7 Concept Check runtime

This package implements the standalone v2 Concept Check path. It does not run
from the v2 corpus-build pipeline or the formal four-condition experiment.
`ConceptCheckConfig.enabled` defaults to `false`; `ConceptCheckService.prepare`
then returns a static profile without reading the event store or calling a Topic
resolver.

With the feature enabled, call `prepare` after retrieval and pass its one
`LearnerContextSnapshot` to both reranking and answer generation. After M8 has
validated the answer and its citations, `select` may choose a published,
current-corpus practice question. `submit` grades deterministically, appends a
single event, and replays state. `JsonlEventStore` is for a single-writer demo;
its JSONL stream is the source of truth.

Retries compare event content independently of the audit timestamp. A repeated
attempt or repeated override/revocation event does not append a second record;
reusing an identifier with different content remains an error. Reading events
does not replay state. Selection reads each stream once, and submission leaves
stream-version assignment and write validation to the store. Only an incomplete
final JSONL record without a line terminator is skipped with a warning; the next
append removes that partial tail. Malformed complete records still fail.

The profile passed to enabled `prepare` must match the replayer's static
profile. Recreate both from the same updated profile when a student changes
their starting level. Unreviewed online questions are currently unsupported:
`allow_unreviewed_questions=true` is rejected by this runtime rather than silently
ignored. The published-question gate remains in effect.

`FixtureQuestionProvider` accepts only `ConceptCheckQuestionRelease` objects,
whose contracts require reviewed publication and resolved bindings. The
`OfflineDraftGenerator` runs only with the development flag and always returns
draft questions. Prefer `OfflineDraftGenerator.from_runtime_config(client,
runtime_config)` to obtain both flags and environment from the owning
`V2Config`. Direct construction requires an explicit environment; omitting it
is not permitted.
`PublicationValidator` requires frozen reviewed Gold, current
M4 span bindings, and injected versioned similarity and cross-book duplicate
checkers. Until those inputs exist, no real question can pass that gate. Fixture
tests use synthetic Gold, bindings, and checkers and do not establish official
question quality or evaluation results.

The answer generator in `cs30.v2.generation` adapts the selected bundle to the
existing M7 `PromptBuilder`, reusing its three level guidance texts, seven
grounding rules, and shared JSON parser. Source identity remains in the prompt.
Each invalid output gets at most one repair section built from the original
prompt. Provider failures retry that original prompt, and input or exhausted
generation failures carry a `V2GenerationTrace` on `V2GenerationFailure`.
