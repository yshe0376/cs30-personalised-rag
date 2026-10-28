# Member 8 UI interfaces

## V2 learning layout

Run `start_v2_demo.cmd` on Windows, or use:

```bash
python -m streamlit run src/cs30/ui/v2_app.py --theme.base light --theme.primaryColor '#f06f54' --theme.font sans-serif
```

Install the `ui` extra first. The Windows launcher uses `.venv` when available;
`CS30_PYTHON` can select an existing Python environment and `CS30_PORT` defaults
to 8512. It does not install dependencies or call a model API.

The default **Ask a question** page accepts free text. Its UI-owned composition
calls the shared BM25 backend, Topic/snapshot service, V2 evidence builder,
M7 `V2AnswerGenerator` and citation validator in order. It displays the exact
generation-time profile, sources and optional Concept Check decision. The
secondary **Concept Check examples** page retains the old prepared scenarios.

**Team V2 / DeepInfra** offers three independent answer models through the existing
`OpenAICompatibleClient`, with M7's recorded per-model settings:

| Model | Output format | Output limit | Extra settings |
|---|---|---:|---|
| `openai/gpt-oss-20b` (default/main) | JSON Object | 4096 | `reasoning_effort=low` |
| `google/gemma-3-12b-it` | JSON Schema | 2048 | none |
| `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` | JSON Object | 2048 | none |

All use temperature 0. One selected model answers each submitted question; this
is not an ensemble, vote, automatic routing or a three-model parallel request.
Changing the model clears old output; the completed trace records the actual
response model. Offline mode disables model selection because it uses a mock.
The examples row follows V1: **Examples** followed by three one-click question
buttons. These fill the input and never trigger generation.

Set `DEEPINFRA_API_KEY` and `CS30_UI_CORPUS` in the
server environment. API requests happen only when the user clicks Generate
answer; page load never calls a model. The UI allows at most two HTTP attempts
per submitted question (one repair, no transport retry), with separate local
API-cache/audit data. This is a UI demonstration limit, not the experiment budget.
The public model alias is not an immutable model revision.

The corpus loader verifies the released manifest and exact record bytes.
The Topic map/registry are loaded from the checked-in rc.1 release. BM25 is the
existing baseline, **not** the selected Qwen3 Dense 0.10 / BM25 0.90 experiment
retriever. The published M6 frozen candidates cannot answer arbitrary new
queries. No replacement hybrid algorithm or transferred lambda is invented.

**Offline integration** executes the same V2 chain with the shared synthetic
corpus, BM25 retrieval and M7's existing mock JSON client. It is explicitly
labelled simulated, cannot establish answer quality, and never silently replaces
a failed live request. Its available synthetic releases drive practice/feedback.

The switch controls dynamic Topic state and practice together. Off mode hides
write controls and uses the static starting profile without deleting history.
Each starting level uses a separate fixture profile, as in the existing demo.
Changing the level clears the previous Q&A output; another submission generates
a new answer with the new snapshot. The fixed examples page still never
regenerates its saved answers. Temporary single-session logs are not a durable
student account or cross-session storage.

The real-corpus path has no installed compatible reviewed practice releases.
It uses an empty provider and reports the shared selection reason; synthetic
questions are never offered against the real corpus. A real practice pack and
the arbitrary-query selected hybrid index/runtime remain integration dependencies.
V1 and the original standalone demo remain available. No paid API smoke has been
run as part of this local UI change.

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
