# Unified online Concept Check

Concept Check prefers mapped Topics. If validated cited passages have no eligible
Topic, it generates textbook-based practice directly from those passages. These
questions can be graded or skipped, with answers, explanations and located quotations;
they do not update Topic mastery or level. Their local attempt log is separate from
Topic progress reports. Citation validation and asset identity checks remain required.

The M8 page now hosts the textbook-grounded online learning workflow. Run
`start_v2_demo.cmd` and choose **Demo Mode → Online learning · textbook quizzes**.
When `configs/learning-demo.toml` (or `CS30_LEARNING_CONFIG`) exists, this mode is
selected on first opening. `start_learning_demo.cmd` opens the same page directly
in online mode; `learning_app.py` is a compatibility entry, not a separate UI.

Online mode uses the existing `cs30.learning` backend: API answers, weighted
selection of Topics mapped to validated citations, API question authoring,
local quotation binding, grading, event replay, manual Topic levels and undo.
Answers and sources use M8's adjacent cards; practice uses its two-column option
styles. Questions stay drafts and answers/explanations appear after submit or skip.
The sidebar exports the same CSV/JSON/Markdown session reports as M8's page.

Models and hybrid retrieval for online mode come from the learning configuration.
Team V2's existing model/retriever controls apply to Team V2 mode only. Both Team V2
and the offline fixture mode remain available in the same mode dialog.

Copy `configs/learning-demo.example.toml` to `configs/learning-demo.toml` and follow
[the setup runbook](../../../docs/api-learning-demo-runbook.md). Local configuration,
keys, indexes, request counters and learner events are ignored by Git. Online mode
requires the existing asset checks and a positive saved request cap before clients
are created; changing mode or rendering the page sends no generation requests.

# Member 8 UI interfaces

## V2 learning layout

Run `start_v2_demo.cmd` on Windows, or use:

```bash
python -m streamlit run src/cs30/ui/v2_app.py --theme.base light --theme.primaryColor '#f06f54' --theme.font sans-serif
```

Install the `ui` extra first. The Windows launcher uses `.venv` when available;
`CS30_PYTHON` can select an existing Python environment and `CS30_PORT` defaults
to 8512. It does not install dependencies or call a model API.

The V2 entry has one **Ask a question** page. Its UI-owned composition calls
retrieval, the shared Topic/snapshot service, V2 evidence builder,
M7 `V2AnswerGenerator` and citation validator in order. It displays the exact
generation-time profile, sources and optional Concept Check decision.
Starting level and Enable Concept Check appear above the question input.
**Session report** opens the native left sidebar; **Demo Mode** opens a small
settings dialog without resizing the learning page. The older fixture layout
remains in `v2_fixture.py`, but is not a second page in the V2 navigation.

The redesigned layout integrates the local `cs30-v3-ui-preview` presentation
into this checkout. The existing `v2_app.py` entry and Windows launcher now open
the redesigned page; no sibling preview directory or separate server is needed.
It adds a compact header with a visible mode badge, learning-settings and
question cards, an answer beside a numbered Sources card, a practice card with
two-column options, and a progress section. Sources retain passage text,
chapter, rank, chunk ID and locator. Answer text retains Streamlit's Markdown
rendering. Narrow screens stack the cards and quiz options vertically.

`qa_app.py` owns the page layout. `qa_quiz.py` owns the redesigned quiz
presentation and imports the existing `QuizAttemptView` type so shared grading
callbacks and event handling remain compatible. `v2_runtime.py`, shared
contracts, retrieval/generation logic, and learner-state/report rules are not
changed by this layout integration. The standalone fixture demo continues to
use `concept_check.py`.

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
The **Try an example** row offers three question pills. These fill the input
and never trigger generation.

Set `DEEPINFRA_API_KEY` and `CS30_UI_CORPUS` in the
server environment. API requests happen only when the user clicks Generate
answer; page load never calls a model. The UI allows at most two HTTP attempts
per submitted question (one repair, no transport retry), with separate local
API-cache/audit data. This is a UI demonstration limit, not the experiment budget.
The public model alias is not an immutable model revision.

The corpus loader verifies the released manifest and exact record bytes.
The Topic map/registry are loaded from the checked-in rc.1 release. Team mode
defaults to **Qwen3 Dense 0.10 / BM25 0.90 hybrid** through M6's existing
`materialise_v2_retrieval_view` / `build_real_retrieval_deps` path and M7's
`freeze_v2_retrieval` converter. It uses weighted RRF k=60 with top-20 inputs,
then sends the fused top-5 to generation. BM25 remains an explicit comparison
option. A missing or incompatible hybrid index causes an error, not a fallback.

Hybrid setup requires the `ml` extra (`pip install -e ".[ui,ml]"`) and the
`qwen3-embedding` index folder from the
[M6 release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/m6-w6-qwen3-hybrid-dev-v1)
asset `M5_to_M6_four_book_2026-10-21.zip`. Set `CS30_UI_HYBRID_INDEX` to the folder
containing `artifact.json` and `index/index.faiss`; the default is
`artifacts/v2/m6_qwen3_hybrid`. The shared loader checks index bytes and identities.
The embedding model/revision is `Qwen/Qwen3-Embedding-0.6B` /
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, with query prompt `query`.
Model weights, corpus records and indexes are external assets and are not
included in this Git branch. The first hybrid submission may download the model.

**Fixture mode** executes the V2 chain with the shared synthetic
corpus, BM25 retrieval and M7's existing mock JSON client. It is explicitly
labelled simulated, cannot establish answer quality, and never silently replaces
a failed live request. Its available synthetic releases drive practice/feedback.

The switch controls dynamic Topic state and practice together. Off mode hides
write controls and uses the static starting profile without deleting history.
Each starting level uses a separate fixture profile, as in the existing demo.
Changing the level clears the previous Q&A output; another submission generates
a new answer with the new snapshot. Temporary single-session logs are not a durable
student account or cross-session storage.

### Development-demo limits and verification (2026-10-29)

This branch is a development demo, not a completed real-model end-to-end release.

- M7's level-aware Role reranking with Dev-selected lambda=0.1 is not connected
  to this UI. Direct fused top-5 generation is not the experimental top-20
  candidate -> Role reranking -> evidence-selection path.
- The real-corpus path has no installed compatible reviewed practice releases.
  It uses an empty provider and reports the shared selection reason. Synthetic
  questions are never offered against real data. Topic/citation eligibility
  can also refuse a question before provider selection; those guards stay intact.
- No real DeepInfra request was made for this UI audit. Credentials and a manual
  live smoke are still required to verify actual hosted generation. Fixture or
  injected-mock success does not establish model quality or real quiz readiness.
- The installed FAISS file matches the released index SHA-256, but an offline
  real-embedding smoke failed because this machine lacks a complete cached Qwen3
  model. Download the pinned model before claiming live hybrid readiness; the
  passing hybrid regression uses a test embedding model, not real Qwen weights.
- The redesigned-page offline regression passed **116 tests** covering free-text Q&A,
  hybrid composition with a test embedding model, citation validation,
  learner-state controls, selection/refusal, reports and fixture UI. UI/test
  Ruff checks passed. Browser checks covered question -> answer/evidence -> quiz
  -> feedback -> native sidebar report/downloads, dialog settings, sidebar
  resizing/collapse, floating-button positioning, and a 390px mobile viewport
  without document horizontal overflow. These tests were run locally; they do
  not rely on the preview author's cloud test results.
- Loading the real 6,184-chunk corpus and BM25 with an injected mock passed
  citation validation. The average-acceleration example returned
  `TOPIC_SUPPORT_BELOW_THRESHOLD`; this is a refusal, not completed real practice.

M6/M7 configuration is checked against the current
[generation handoff](https://github.com/yshe0376/cs30-personalised-rag/blob/main/docs/results/m7_api_dev_20261026/README.md)
and [Concept Check contract](https://github.com/yshe0376/cs30-personalised-rag/blob/main/docs/member7-concept-check-handoff.md).
GitHub main was `573a80cf6f7ec939562262edc080c65e52168972` at this audit.
V1 and the original standalone demo remain available. The V2 page consumes
UI-owned `QuestionRun` / `DemoRuntime`; the V1 page below consumes `PipelineRun`.

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

The student controls use the shared `revoke`, reason-required `override_level`
and feature-toggle service paths; learner-state rules stay in the shared runtime.

The Concept Check selection trace includes the shared selection status and stable
error code. Refusals display their specific reason. Event reports validate Topic
IDs against the supplied registry as well as checking the declared version.
