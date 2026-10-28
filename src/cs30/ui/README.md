# Member 8 UI interfaces

## V2 learning layout

Run `start_v2_demo.cmd` on Windows, or use:

```bash
python -m streamlit run src/cs30/ui/v2_app.py --theme.base light --theme.primaryColor '#f06f54' --theme.font sans-serif
```

Install the `ui` extra first. The Windows launcher uses `.venv` when available;
`CS30_PYTHON` can select an existing Python environment and `CS30_PORT` defaults
to 8512. It does not install dependencies or call a model API.

This layout reuses V1 styling and the existing Concept Check fixture runtime.
The sidebar contains the starting level, one Concept Check switch (off by
default), and existing fixture scenarios. The learning tab shows the saved
answer, synthetic cited/retrieved passages, quiz, state and optional audited
Topic override. The report tab reuses the existing event report/downloads.

The switch controls dynamic Topic state and practice together. Off mode hides
write controls and uses the static starting profile without deleting history.
Each starting level uses a separate fixture profile, as in the existing demo.
Changing the level does not regenerate a saved fixture answer. Temporary
single-session logs are not a durable student account or cross-session storage.

The page has no free-text/live Q&A adapter, production retrieval/model wiring,
or real reviewed practice corpus. These remain upstream integration work; the
fixture banner must stay visible. V1 and the original standalone demo remain
available.

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

The page is visibly labelled test-data-only. It uses the shared fixture scenarios,
question releases, chunk-to-Topic map, and Topic registry; calls
`ConceptCheckService.prepare`, `select`, and `submit`; and stores events in one
temporary JSONL directory per Streamlit session. No LLM is called.

`cs30.ui.concept_check.render_quiz` is the reusable M8-1 component. It accepts
one published `ConceptCheckQuestionRelease`, submit and skip callbacks, and an
optional next-question callback, so the future v2 answer flow can embed it
without copying presentation logic. Answers, rationale, and evidence stay hidden
until submit or skip.

Each submission or skip creates an immutable attempt record. After feedback is
revealed, the same question cannot be retried as a new scored attempt. The result
view shows the correct answer, rationale, textbook/chapter evidence, and the
replay-derived LearnerState change. Skips are explicitly marked as not counted.

The fixture page also rebuilds a current-session report automatically after each
submit or skip event. It displays compact overall and grouped metrics and renders
the CSV, JSON, and Markdown downloads directly in memory. A report failure is
shown as a warning and does not interrupt the quiz.

## Concept Check event report

Generate CSV, JSON, and Markdown summaries from one JSONL event stream:

```bash
cs30-concept-check-report path/to/events.jsonl path/to/output --starting-level beginner \
  --topic-registry path/to/reviewed-topic-registry.json
```

The report includes submitted attempts, accuracy, skip rate, revocation rate,
topic/difficulty breakdowns, answer-driven promotion/demotion counts, and final
states rebuilt with M7's `EventReplayer`. Accuracy includes submissions that were
later revoked; revocations are reported separately. `--starting-level` is required
so a formal report cannot silently assume a beginner profile.

The student control panel (revoke/override/feature toggle) remains deferred until
M7's control-event signatures are finalized.

The Concept Check selection trace includes the shared selection status and stable
error code. Refusals display their specific reason. Event reports validate Topic
IDs against the supplied registry as well as checking the declared version.
