# Member 7 Concept Check completion

This delivery covers M7-1 through M7-4 from the leader's follow-up. It changes
only M7 runtime/generation code, M7 tests, and this handoff. Shared contracts,
Topic algorithms, fixtures, UI, evaluation/reporting, corpus builders, and other
members' implementations remain outside this change.

## M7-1: Topic resolver adapter

`cs30.concept_check.topics.ChunkTopicResolver(topic_map, registry, config)`
implements the runtime-checkable `cs30.v2.ports.TopicResolver` Protocol. Supply
a `LoadedChunkTopicMap` validated at load time, a `TopicRegistry`, and the same
`ConceptCheckConfig` used for the runtime.

Both resolver methods delegate directly to `cs30.v2.topics`, forwarding
`config.min_topic_support`. The adapter introduces no voting algorithm or map
validation. It preserves ties, insufficient support, missing maps, and corpus
or registry mismatch errors from the shared implementation.

## M7-2: Student controls

The service exposes:

```python
revoke(attempt_id, *, event_id, created_at=None) -> LearnerState
override_level(topic_id, new_level, *, reason, event_id, created_at=None) -> LearnerState
```

`revoke` finds the student's submitted attempt and takes its Topic directly
from that record. It appends `ATTEMPT_REVOKED`; store/replay validation permits
only the most recent surviving scored submission for that Topic. Unknown,
skipped, older, or already-revoked attempts fail without appending a record.

`override_level` appends `TOPIC_LEVEL_OVERRIDDEN` with actor `student` and a
required nonblank reason. Replay resets mastery, coverage and the Topic epoch
window while retaining scored-history counters. Both controls reject calls
when disabled before reading dependencies.

Reuse the same `event_id` on retry. The existing store ignores audit-time
differences, appends no duplicate record, and rejects a changed payload under
the same ID. Each successful control returns the replayed current state.

## M7-3: Selection result and M8 compatibility

The current M8 demo already consumes `select(...) -> question | None`. To honour
the user's explicit instruction not to change another member's code, this
delivery keeps that interface as a thin wrapper and introduces:

```python
selection = service.select_result(prepared, retrieval, validated)
selection.status      # offered / no_topic_available / no_question_available / disabled
selection.question    # ConceptCheckQuestionRelease, or None
selection.error_code  # machine-readable refusal reason, or None
```

M8 can adopt `select_result` when adding reason displays and counts. The
existing UI continues to run without modifications. This is a deliberate
compatibility adjustment to the screenshot's requested `select` return change.

| Decision | Status | Error code |
| --- | --- | --- |
| Feature off | `disabled` | none |
| Retrieval/citation Topic unresolved | `no_topic_available` | shared resolver error |
| Map missing or bound to another corpus | `no_topic_available` | `TOPIC_MAP_UNAVAILABLE` / `TOPIC_MAP_MISMATCH` |
| Resolved Topic uses an old registry | `no_topic_available` | `TOPIC_REGISTRY_MISMATCH` |
| Answer abstains | `no_question_available` | `ANSWER_ABSTAINED` |
| Citation validation fails | `no_question_available` | `CITATION_VALIDATION_FAILED` |
| No resolved citations | `no_question_available` | `NO_CITATIONS` |
| No usable question remains | `no_question_available` | `NO_USABLE_QUESTION` |
| Current question available | `offered` | none |

Selection refuses before cited resolution when retrieval has no unique Topic.
It uses the Topic from the answer's citations, which may differ from retrieval.
Stale question registry versions are excluded before accepting the provider's
next ranked candidate. Attempted/skipped questions remain excluded after
revocation. Evidence overlap remains only a ranking bonus.

## M7-4: v2 generation traces

Each `V2GenerationAttempt` now records `usage`, `latency_ms`, and `response_id`,
including invalid responses that require repair. `V2GenerationTrace` aggregates
usage and call latency across retries and records the last available response
ID, `prompt_version`, `prompt_personalised`, and `effective_level`.

The personalised and baseline v2 prompts use independent version identifiers:
`member7-v2-prompt-v1` and `member7-v2-base-prompt-v1`. Personalised traces record
the supplied snapshot's actual level. Baseline prompts use no student level,
so `effective_level` is null. With no prompt/model call, prompt version and level
are null, personalisation is false, and usage/latency are zero. Provider failures
record measured elapsed time; absent provider responses contribute no reported
tokens or response ID. These zero token values do not claim the provider billed
nothing. Failed generations retain the same trace on `V2GenerationFailure`.

## Verification and deferred work

Acceptance regressions are in `tests/test_member7_completion.py` and
`tests/test_v2_generation_adapter.py`. They exercise the shared fixtures,
configured support, M8's existing interface, refusal ordering, stale-question
fallback, student controls, restart/replay, retry conflicts, prompt switches,
response metadata, repaired output and failed generation.

The complete suite is run in a local clone containing only this delivery so an
unrelated pre-existing local edit in `src/cs30/contracts/models.py` is preserved
and excluded from both validation and the commit. Tests use fixtures and mocks;
they do not establish real-model or formal evaluation results.

Local verification: **788 passed, 2 skipped**; repository-wide Ruff lint passed.

As requested, this work does not implement `anchors.py`, a real practice pool,
offline questions from M3 seed passages, or multi-turn scenario experiments.
