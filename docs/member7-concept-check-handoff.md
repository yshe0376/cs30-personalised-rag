# Member 7 V2 generation and Concept Check handoff

V2 generation accepts complete multiple-choice inputs, and Concept Check returns
an explainable selection decision. Topic identities are checked against a pinned
registry before events can reach the append-only log. This delivery updates the
shared contracts and the M8 demo/report consumers together.

## Generation inputs

Pass a complete `GoldQuestion` to `V2AnswerGenerator.generate` or `generate_batch`
for evaluation. The adapter extracts only the question and option texts; Gold
labels, reference answers, evidence annotations and other metadata are never
serialised into the prompt. Retrieval can continue using `gold.question` alone.

For a question without a Gold record, use the shared `GenerationQuestion`:

```python
from cs30.v2.contracts import GenerationQuestion

question = GenerationQuestion(
    kind="multiple_choice",
    question="What acceleration opposes velocity and reduces speed?",
    options={"A": "calibration", "B": "progression", "C": "extraction", "D": "deceleration"},
)
answer = generator.generate(question, profile, evidence)
```

`multiple_choice` requires exactly four nonblank A-D options. The prompt preserves
the original letter mapping and includes every option in both personalised and
baseline conditions, including repairs. A null model choice is rejected and
repaired through the bounded validation path; an exhausted repair is a generation
failure rather than a successful letterless MCQ answer.

Open-ended Gold, `GenerationQuestion(kind="open_ended", question=...)`, and plain
strings remain supported. A plain string is treated as open-ended: a bare stem
cannot reveal whether choices were lost upstream. Evaluation consumers must pass
the complete Gold object or an explicitly typed MCQ, not `gold.question`.

The V1 provisional 144-row experiment is unchanged and remains non-reportable.
These fixes do not retroactively validate its outputs or constitute a model rerun.

## Topic registry and student controls

Compose `EventReplayer(static_profile, topic_registry, config)` with the actual
shared `TopicRegistry`, not just its version string. It pins the registry version
and known IDs, and rejects unknown static profile Topic keys and event Topic IDs.
The event store validates IDs before reading/writing the log and still replays
the proposed stream under its writer lock before append.

`override_level(topic_id, new_level, *, reason, event_id, created_at=None)` checks
membership before constructing or appending an event. A typo leaves both state
and log bytes unchanged. `submit` checks question Topic membership as well.
Unknown resolver identities become `UNKNOWN_TOPIC` refusals instead of entering
a learner snapshot. Existing logs containing unknown Topics fail validation and
are left intact; any correction or deletion requires the controlled storage
procedure in design spec §7.

`revoke(attempt_id, *, event_id, created_at=None)` derives the Topic from the
original submitted attempt. Only the latest surviving scored attempt for that
Topic can be revoked. Reuse `event_id` on retries; a changed payload under the
same ID is rejected. Overrides reset the mastery/coverage epoch while retaining
historical scored-attempt counters. Disabled controls reject before dependency
access.

## Selection contract and M8 migration

The Leader requires `select` itself to return a structured decision. The public
API is now:

```python
selection = service.select(prepared, retrieval, validated)
selection.status      # ConceptCheckSelectionStatus
selection.question    # ConceptCheckQuestionRelease | None
selection.error_code  # ConceptCheckErrorCode | None
```

`ConceptCheckSelection` lives in `cs30.v2.contracts`, uses schema version `0.1`,
and is immutable. Status and error code are string enums with stable JSON values.
`offered` requires a question and no error; `disabled` carries neither; both
refusal statuses require an error and forbid a question. Invalid combinations
and unrecognised codes fail validation. The former `select_result` method is
replaced by this single public decision API.

| Decision | Status | Error code |
| --- | --- | --- |
| Feature off | `disabled` | none |
| Retrieval/citation Topic unresolved | `no_topic_available` | shared resolver reason |
| Missing/wrong map or registry | `no_topic_available` | corresponding `TOPIC_*` code |
| Unknown Topic identity | `no_topic_available` | `UNKNOWN_TOPIC` |
| Answer abstains | `no_question_available` | `ANSWER_ABSTAINED` |
| Citation validation fails | `no_question_available` | `CITATION_VALIDATION_FAILED` |
| No resolved citations | `no_question_available` | `NO_CITATIONS` |
| No eligible unused question | `no_question_available` | `NO_USABLE_QUESTION` |
| Current question available | `offered` | none |

M8's demo reads `selection.question`, shows a reason for refusal, and records the
status/code in its selection trace. It uses the shared `ChunkTopicResolver` with
the same config as the service. Stale question registry versions are excluded
before selecting a fallback; submitted/skipped question IDs stay excluded after
revocation. The deterministic fixture regression asserts the exact next question.

The event report also requires an independently supplied registry, so it cannot
accept a typo merely because the event declares a matching version:

```bash
cs30-concept-check-report events.jsonl output --starting-level beginner \
  --topic-registry path/to/reviewed-topic-registry.json
```

## Generation traces

Prompt versions are `member7-v2-prompt-v2` and `member7-v2-base-prompt-v2`.
Trace selection calls the prompt builder's `version(personalise=...)` method.
Changes to shared V1 template content still require an explicit V2 version bump.

Each attempt's `latency_ms` measures local elapsed time around `client.complete`,
for successful responses, invalid outputs, and provider failures alike. The run
trace sums these durations. `provider_latency_ms` separately retains a returned
client's reported duration, or is null when no response exists. Token usage and
response IDs retain provider values; failed calls without responses add no
reported tokens. No-call paths have zero call latency/usage and no prompt version.

## Verification and remaining scope

Regression tests cover MCQ option preservation, missing-option input rejection,
Gold data isolation, MCQ null-choice repair, open-ended compatibility, registry
membership at service/store/replay/report boundaries, immutable selection enums,
UI refusal reasons, deterministic fallback, and consistent call timing.

Run `python -m ruff check .` and `python -m pytest` for current verification.
Fixture and mocked-provider tests establish runtime behaviour, not formal model
quality. A real published practice pool, M3 seed authoring, anchor resolution,
and formal four-condition model runs remain separate deliverables.
