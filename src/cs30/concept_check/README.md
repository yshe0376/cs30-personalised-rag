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

## Shared fixture pack

`cs30.concept_check.fixtures` is the one fixture set M7 and M8 build against
until real Topics, Gold and bindings exist. It ships five hand-written practice
questions over two Topics (`acceleration` at two levels, `newtons-second-law`
at all three), the `fixture-topics-v1` registry, a small synthetic corpus
paraphrasing College Physics 2e chapters 2 and 4, and bindings to that corpus:

```python
from cs30.concept_check.fixtures import (
    fixture_retrieval_result,
    load_fixture_releases,
    load_fixture_topic_registry,
)
from cs30.concept_check.provider import FixtureQuestionProvider

provider = FixtureQuestionProvider(load_fixture_releases())
retrieval = fixture_retrieval_result(("fixture-cp2e-ch4-p1",))
```

`fixture_retrieval_result` carries the fixture corpus identity, so `select`
finds these releases for it and for nothing else. The corpus hash is a fixture
value rather than a build output, and the `fixture-review:` IDs stand in for
M3 review records: these questions have not been reviewed by M3 and must never
be shown as real practice questions.

For Topic resolution the pack adds `load_fixture_manifest()` (a development
manifest for the fixture corpus) and `load_fixture_chunk_topic_map()`, which
returns a `LoadedChunkTopicMap` already validated against that manifest. Pass
it with `load_fixture_topic_registry()` to `resolve_topic_from_retrieval` and
`resolve_topic_from_citations` in `cs30.v2.topics`. Two chunks are deliberate
edge cases: `fixture-cp2e-ch4-p1` maps to both Topics, so its weight splits,
and `fixture-cp2e-ch2-p3` maps to none.

`load_fixture_scenarios()` returns named previous turns: a `title` for
selection, the student's `query`, an `answer` written only from the cited
chunks, the retrieval, and the Topic or resolver error code each resolver
should produce. `validated_answer()` returns that answer as a passed,
citation-validated answer, so a demo can display `query` and `answer` as the
turn the Concept Check follows. Tests check every expectation against the M1
resolver:

| Scenario | Retrieval Topic | Cited Topic |
|---|---|---|
| `newtons-second-law` | `newtons-second-law` | `newtons-second-law` |
| `acceleration` | `acceleration` | `acceleration` |
| `cited-topic-differs` | `newtons-second-law` | `acceleration` |
| `two-block-system` | `newtons-second-law` | `newtons-second-law` |
| `topic-tie` | none (`TOPIC_TIE`) | none (`TOPIC_TIE`) |
| `unmapped-chunk` | none (`NO_TOPIC_AVAILABLE`) | none (`NO_TOPIC_AVAILABLE`) |

The scenario sets the Topic; the learner's level sets which question comes
first, and evidence overlap only breaks ties within a level. With
`two-block-system`, a beginner gets `cc-fixture-003` and an advanced learner
gets the two-block question `cc-fixture-005`.

```python
scenario = next(s for s in load_fixture_scenarios() if s.scenario_id == "acceleration")
retrieval, validated = scenario.retrieval(), scenario.validated_answer()
```

The answer generator in `cs30.v2.generation` adapts the selected bundle to the
existing M7 `PromptBuilder`, reusing its three level guidance texts, seven
grounding rules, and shared JSON parser. Source identity remains in the prompt.
Each invalid output gets at most one repair section built from the original
prompt. Provider failures retry that original prompt, and input or exhausted
generation failures carry a `V2GenerationTrace` on `V2GenerationFailure`.
