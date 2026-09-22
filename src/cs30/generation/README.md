# Member 7 - personalised prompt and LLM generation

The Member 7 implementation is `PersonalisedAnswerGenerator`:

```python
generate(question, profile, evidence_bundle) -> GeneratedAnswer
```

It implements `cs30.ports.AnswerGenerator` without changing the frozen
cross-module contracts. The third argument accepts the native `EvidenceBundle`
as well as the existing `RetrievalResult`. Its keyword remains `retrieval` for
compatibility with the current port and pipeline.

## What is implemented

- Beginner, intermediate, and advanced prompt guidance.
- A fixed model-facing JSON object with exactly `final_choice`, `explanation`,
  and `citations`.
- OpenAI Responses API adapter using Structured Outputs.
- Free local Ollama adapter using its native structured-output chat API.
- Strict local JSON parsing and Pydantic validation.
- Stable `chunk_id` citations from the selected `EvidenceBundle.evidence_items`,
  validated by Member 8's existing resolver. `E1` / `E2` are UI labels only,
  as frozen in ADR-0001 on 2026-09-05.
- Finite retry for provider, JSON, and citation failures.
- Explicit abstention without an LLM call when retrieval has no evidence.
- Per-run model, temperature, latency, token, retry, and failure metadata.
- Batch isolation so one failed request does not abort later questions.
- A combined, provenance-labelled smoke run across original, teammate, and
  locally available datasets, plus a three-level comparison.
- Four stable conditions: `P0R0_plain`, `P1R0_prompt_only`,
  `P0R1_reranking_only`, and `P1R1_combined`.
- A fixture-first, level-aware soft reranker using
  `lambda_effective = lambda_weight * profile.confidence` and min-max-normalised
  retrieval scores. Original retrieval scores are retained; only candidate
  order and rank are changed.
- Sidecar role labels keyed by `chunk_id`, so the shared evidence contracts do
  not gain an unfrozen required field. Missing and ambiguous labels use the
  recorded `retrieval_only` fallback.
- Structured attempt records containing each raw provider output, repair status,
  failure type, model, usage and response ID. Saved batch rows retain both the
  rejected output and the repaired output.
- A Dev-only global lambda search that compares a fixed candidate grid using
  MRR@k, hit rate and recall, with deterministic smallest-lambda tie breaking.
- A hash-bound selected-lambda configuration. It is marked `frozen` and
  `reportable` only when the inputs are formal and the M3 taxonomy is frozen.
- A batch four-condition runner that saves one JSONL row per
  question/profile/condition and a provenance manifest for M8.
- Formal gates for exactly 60 Dev or 180 Test questions, all three student
  levels, identical initial candidates, complete non-fixture Role labels, real
  retrieval provenance and input hashes.

## Four-condition fixture run

Run all four conditions against one fixed question, candidate set, profile and
model:

```bash
python -m cs30.generation.ablation_demo --provider mock
```

Add `--output artifacts/task7-week5/four_conditions.json` to retain the exact
structured run, including raw provider attempts. The output records generation,
evidence, and role-label modes separately, so an Ollama/OpenAI call over fixture
evidence cannot be mistaken for either a fully real run or a reportable result.

Use `--condition plain`, `--condition prompt-only`,
`--condition reranking-only`, or `--condition combined` to expose one stable
switch to an external runner. `--lambda-weight` is accepted only as an
engineering fixture value in this demo. `RerankConfig.parameter_source`
accepts only `fixture` or `dev`, preventing Test from being recorded as a
tuning source.

The personalised Prompt path is byte-for-byte unchanged. Plain and
reranking-only use a separate base Prompt that keeps the grounding, JSON and
citation rules but contains no student level or profile identifier.

The role mapping in this demonstration is explicitly a fixture using the six
candidate role names from the project design. It is not a frozen taxonomy and
must not be used for model-effectiveness claims.

## Dev lambda selection and freezing

First join the unchanged M6 retrieval rows with the M4 Gold-to-chunk mapping and
the fixed three-level StudentProfiles:

```bash
python -m cs30.generation.prepare_cases \
  --retrieval-runs artifacts/w6/m6/dev_results.jsonl \
  --retrieval-manifest artifacts/w6/m6/dev_manifest.json \
  --gold-mapping artifacts/w6/m4/gold_to_chunk_mapping.json \
  --target-split dev --input-status formal \
  --output-cases artifacts/task7/formal_dev_cases.jsonl \
  --output-manifest artifacts/task7/formal_dev_cases.manifest.json
```

The preparation step verifies the M6 execution mode and status, rejects
duplicate questions or missing Gold mappings, preserves M6 retrieval bytes in
the validated contract, creates all three fixed profiles, and records SHA-256
hashes for every upstream input. Formal preparation also requires a reportable
M6 manifest with an exact `dev`/`test` split and the required 60/180 questions.

The resulting JSONL contains one row per question and profile level:

```json
{"question_id":"q1","split":"dev","profile":{},"retrieval":{},"relevant_chunk_ids":["chunk-1"]}
```

`profile` must validate as `StudentProfile`; `retrieval` must validate as the
unchanged M6 `RetrievalResult`. Prepare M3 Role labels as JSONL:

```json
{"chunk_id":"chunk-1","roles":["definition"],"source":"m3-role-labels-v1","taxonomy_version":"m3-role-v1"}
```

Run the search only after those inputs have been joined without changing their
identities:

```bash
python -m cs30.generation.lambda_search \
  --cases artifacts/task7/formal_dev_cases.jsonl \
  --role-labels artifacts/task7/evidence_role_labels.jsonl \
  --taxonomy-version m3-role-v1 --taxonomy-status frozen \
  --input-status formal --lambdas 0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1 \
  --metric-k 5 --output artifacts/task7/lambda_dev_search.json
```

The command refuses Test rows. A formal frozen configuration additionally
requires exactly 60 unique Dev questions, Beginner/Intermediate/Advanced cases
for every question, identical M6 candidates across the three levels, retrieval
provenance, complete single-role M3 labels, and hashes for both input files.
Fixture or proposed data still produces a useful search report, but the selected
configuration is labelled `provisional` and `reportable=false`.

## Four-condition batch run

The condition runner consumes JSONL rows containing `question_id`, `split`,
`question`, `profile`, and the unchanged `retrieval` object. It accepts either a
standalone selected-lambda object or the full lambda-search output:

```bash
python -m cs30.generation.experiment \
  --cases artifacts/task7/formal_test_cases.jsonl \
  --role-labels artifacts/task7/evidence_role_labels.jsonl \
  --selected-lambda artifacts/task7/lambda_dev_search.json \
  --input-status formal --provider ollama --model gpt-oss:20b \
  --output-dir artifacts/task7/formal_test_run
```

This writes `four_condition_results.jsonl` and `run_manifest.json`. The manifest
records the model settings, prompt versions, selected lambda, taxonomy version,
Git commit, condition IDs and SHA-256 hashes of every input. A formal Test run
requires exactly 180 unique questions and all three levels per question. Mock,
fixture and proposed-data runs are always non-reportable.

## Offline smoke run

```bash
python -m cs30.generation.demo --provider mock
```

To exercise the M8 bundle input for 20 questions and all three profile levels:

```bash
python -m cs30.generation.demo --provider mock --dataset original \
  --evidence-bundle --output-dir artifacts/task7-bundle
```

This writes `batch_20_results.json` and `three_level_sample.json` with
`generation_input: "EvidenceBundle"`. The demo calls M8's `EvidenceContextBuilder`;
the generator itself only consumes the supplied bundle. Use `--dataset all`
to check all available smoke data through this same boundary.

The default combined run contains 52 packaged rows: 20 original fixture
questions, 24 packaged SciQ questions, and 8 packaged free questions. With 20
local SciQ rows it writes `artifacts/task7/batch_72_results.json`, alongside
`artifacts/task7/three_level_sample.json`.
The local rows are included when `data/raw/sciq/train_first_20.json` exists;
`CS30_LOCAL_SCIQ_PATH` can point to a different local file. These files are
ignored by Git and are not model-effectiveness results.
The packaged free questions have no supplied evidence in this smoke dataset,
so they intentionally produce abstentions.

## SciQ question smoke run

To run only a local Hugging Face dataset-server rows response, place it in the
ignored `data/raw/` directory, then run:

```bash
python -m cs30.generation.demo --provider mock --dataset local-sciq \
  --sciq-json data/raw/sciq/train_first_20.json \
  --output-dir artifacts/task7-sciq
```

This uses real SciQ questions and answer choices. The SciQ `support` field is
wrapped as `fixture://sciq-support/train` evidence in this isolated smoke path.
Correct answers are placed at A solely so the
deterministic mock remains grounded; this ordering must not be used for formal
accuracy evaluation.

## Real provider

### Free local model (recommended)

Install and start Ollama, then download the 20B open-weight model once:

```bash
ollama run gpt-oss:20b
```

After the model responds, leave Ollama running and execute a one-question smoke test:

```bash
python -m cs30.generation.demo --provider ollama --model gpt-oss:20b \
  --evidence-bundle --limit 1 --skip-three-level \
  --output-dir artifacts/task7-ollama-smoke
```

This route runs locally, needs no API key, and has no per-token API charge. Set
`OLLAMA_BASE_URL` only when Ollama is not available at its default
`http://localhost:11434` address.

### OpenAI API (optional, paid)

Set `OPENAI_API_KEY` and an accessible `LLM_MODEL`, then run:

```bash
python -m cs30.generation.demo --provider openai --limit 1 --skip-three-level \
  --evidence-bundle --output-dir artifacts/task7-openai-smoke
```

Remove the two limiting flags only after the first request succeeds.

Never put a real key in source code, a test fixture, a commit, or a screenshot.
The adapter sends `store=false`, applies the configured timeout, requests the
fixed JSON schema, and still validates the result locally.

### Data boundary and failures

The provider receives the question (including choices), the explicit
`PROMPT_PROFILE_FIELDS`, and the selected evidence text and metadata. Use only
approved material when selecting a remote provider. Bundle run provenance and
source-locator metadata remain available to M8; generation does not read raw
corpus or index files, rebuild the bundle, or independently filter its context.
Cached `prompt_context` cannot introduce evidence outside `evidence_items`.
For identical evidence, both input types preserve the existing prompt bytes.

Timeouts, HTTP errors (including rate limits), invalid JSON and unknown citations
use at most `max_retries + 1` attempts. Exhaustion raises `GenerationError`; the
batch records a failed row and continues. A provider fault is not a successful
abstention, and providers are not switched silently. Empty selected evidence
returns `abstained=True`, no choice or citations, and zero model calls. This is
an empty-evidence guard, not calibrated semantic evidence-sufficiency detection.

The model-facing response stays exactly `final_choice`, `explanation`, and
`citations`. The existing `GeneratedAnswer` wrapper carries `abstained`; its
`explanation` carries the refusal reason. No shared schema fields are added.

### Verification

```bash
python -m pytest
python -m ruff check .
```

`tests/test_generation_bundle.py` exercises M8's packaged native fixture,
all three levels, empty evidence, selected-evidence isolation, rejected display
or unknown IDs, bounded repair, and real BM25 → M8 bundle → mock generation →
M8 citation validation. Shared retry and batch-failure tests cover both input
types. These are engineering checks, not answer-quality measurements or proof
that a live OpenAI/Ollama endpoint is available.

`tests/test_generation_reranking.py` checks the score formula, confidence,
zero-lambda baseline restoration, missing/ambiguous-label fallback, bundle
integrity, four independent condition switches, unchanged model/candidate
inputs, and separate raw records for rejected and repaired outputs.

## Waiting on team artefacts

The implementation is ready, but the following formal execution inputs are not
present in the repository snapshot and therefore no formal result is claimed:

- Loading M3's Role labels, until the taxonomy decision and versioned labels
  are available.
- Executing the lambda search on the final 60-question Dev set. The current
  12-question `proposed_dev` input is explicitly non-reportable.
- Publishing formal four-condition results on the final six-textbook inputs.
  The current M6 handoff and local Member 7 demonstrations are non-reportable.

## Integration boundaries

- Member 3: pass a validated `SciQQuestion` through
  `format_sciq_question()` so all four choices reach the prompt.
- Member 8: pass `EvidenceBundle` directly. The prompt and model may cite only
  its selected stable chunk IDs. Member 8 owns display labels, the citation map,
  source resolution and context-budget policy.
- Leader: `build_real_deps()` already wires Member 6's real retrieval modes when
  an index is configured. `run_pipeline()` still passes `RetrievalResult` under
  the existing port. Switching that shared call to the already-built bundle is
  an integration-owner follow-up; this M7 change leaves orchestration intact.
