# Member 8 UI interfaces

This module consumes `PipelineRun`.

## Week 1 acceptance

- A new member can start the system from the README.
- The client can pick a level, ask a question, and see the answer and sources.
- No real key reaches the repository.

## Notes

Always surface `PipelineRun.mode`. A fixture run must never be presented
as a real result, and an abstained answer must be shown as a refusal
rather than as an empty answer.

## Run locally

Install the project as described in the repository README, then start the UI:

```bash
python -m streamlit run src/cs30/ui/app.py
```

The first version intentionally calls the fixture pipeline. Replace the dependency
builder at the composition boundary only after the leader wires the real adapters.

## Independent Concept Check fixture demo

The v1 question-and-answer page is unchanged. Start the standalone multipage
demo with the same command above, then select **Concept Check Demo** in the
Streamlit navigation. It can also be launched directly:

```bash
python -m streamlit run src/cs30/ui/pages/1_Concept_Check_Demo.py
```

The page is visibly labelled test-data-only. It uses the shared
`load_fixture_releases()` and `fixture_retrieval_result()` assets, calls
`ConceptCheckService.prepare`, `select`, and `submit`, and stores events in one
temporary JSONL directory per Streamlit session. No LLM is called.

`cs30.ui.concept_check.render_quiz` is the reusable M8-1 component. It accepts
one published `ConceptCheckQuestionRelease` plus submit and skip callbacks, so
the future v2 answer flow can embed it without copying presentation logic.
Answers, rationale, and evidence stay hidden until submit or skip.

Each submission or skip creates an immutable attempt record. After feedback is
revealed, the same question cannot be retried as a new scored attempt. The result
view shows the correct answer, rationale, textbook/chapter evidence, and the
replay-derived LearnerState change. Skips are explicitly marked as not counted.

The fixture page also rebuilds a current-session report automatically after each
submit or skip event. It displays compact overall and grouped metrics and exposes
the same CSV, JSON, and Markdown outputs as download buttons. The generated files
remain in the session's temporary directory; they are not repository artifacts.

## Concept Check event report

Generate CSV, JSON, and Markdown summaries from one JSONL event stream:

```bash
cs30-concept-check-report path/to/events.jsonl path/to/output --starting-level beginner
```

The report includes submitted attempts, accuracy, skip rate, revocation rate,
topic/difficulty breakdowns, promotion/demotion counts, and final states rebuilt
with M7's `EventReplayer`.

The student control panel (revoke/override/feature toggle) remains deferred until
M7's control-event signatures are finalized.
