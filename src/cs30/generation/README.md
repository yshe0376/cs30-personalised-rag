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
