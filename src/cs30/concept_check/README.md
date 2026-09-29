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

`FixtureQuestionProvider` accepts only `ConceptCheckQuestionRelease` objects,
whose contracts require reviewed publication and resolved bindings. The
`OfflineDraftGenerator` runs only with the development flag and always returns
draft questions. `PublicationValidator` requires frozen reviewed Gold, current
M4 span bindings, and injected versioned similarity and cross-book duplicate
checkers. Until those inputs exist, no real question can pass that gate. Fixture
tests use synthetic Gold, bindings, and checkers and do not establish official
question quality or evaluation results.
