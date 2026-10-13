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

The page is visibly labelled test-data-only. It uses the shared fixture scenarios,
question releases, `ChunkTopicResolver`, chunk-to-Topic map, and Topic registry;
calls `ConceptCheckService.prepare`, `select_result`, and `submit`; and stores
events in one temporary JSONL directory per Streamlit session. No LLM is called.
Structured selection statuses and error codes explain why a scenario has no
eligible question.

`cs30.ui.concept_check.render_quiz` is the reusable M8-1 component. It accepts
one published `ConceptCheckQuestionRelease`, submit and skip callbacks, plus
optional next-question and revoke callbacks, so the future v2 answer flow can
embed it without copying presentation logic. Answers, rationale, and evidence
stay hidden until submit or skip.

Each submission or skip creates an immutable attempt record. After feedback is
revealed, the same question cannot be retried as a new scored attempt. The result
view shows the correct answer, rationale, textbook/chapter evidence, and the
replay-derived LearnerState change. Skips are explicitly marked as not counted.

The fixture page also rebuilds a current-session report automatically after each
submit, skip, revoke, or level-override event. It displays compact overall and
grouped metrics and renders the CSV, JSON, and Markdown downloads directly in
memory. A report failure is shown as a warning and does not interrupt the quiz.

The learner setup places the optional Topic-level override beside the starting
level and requires a reason. After a scored answer, the result view offers an
**Undo latest scored attempt** action beside that attempt instead of a separate
control panel. Both actions consume shared service methods rather than editing
learner state directly, and the read-only learner-state table is rebuilt by the
shared replayer. Turning Concept Check off hides all event-writing controls,
offers no quiz, and displays the static student profile; existing events remain
available when the feature is turned on again.

The simulated previous Q&A always offers its cited source text in one collapsed
expander. This avoids a second evidence switch while still keeping the page
compact and satisfying the student-facing evidence-view requirement.

## Concept Check event report

Generate CSV, JSON, and Markdown summaries from one JSONL event stream:

```bash
cs30-concept-check-report path/to/events.jsonl path/to/output --starting-level beginner
```

The report includes submitted attempts, accuracy, skip rate, revocation rate,
topic/difficulty breakdowns, answer-driven promotion/demotion counts, and final
states rebuilt with M7's `EventReplayer`. Accuracy includes submissions that were
later revoked; revocations are reported separately. `--starting-level` is required
so a formal report cannot silently assume a beginner profile.

Formal v2-flow embedding and real question-quality rates remain deferred until
the real practice pool and frozen experiment inputs are available.
