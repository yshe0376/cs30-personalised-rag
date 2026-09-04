# Member 7 - personalised prompt and LLM generation

The real Week 1 implementation is `PersonalisedAnswerGenerator`:

```python
generate(question, profile, retrieval) -> GeneratedAnswer
```

It implements `cs30.ports.AnswerGenerator` without changing the frozen
cross-module contracts.

## What is implemented

- Beginner, intermediate, and advanced prompt guidance.
- A fixed model-facing JSON object with exactly `final_choice`, `explanation`,
  and `citations`.
- OpenAI Responses API adapter using Structured Outputs.
- Free local Ollama adapter using its native structured-output chat API.
- Strict local JSON parsing and Pydantic validation.
- Citation allow-list validation against the actual `RetrievalResult.hits`.
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

On this workspace it writes `artifacts/task7/batch_72_results.json` and
`artifacts/task7/three_level_sample.json`: 20 original fixture questions, 24
packaged SciQ questions, 8 packaged free questions, and 20 local SciQ rows.
The local rows are included when `data/raw/sciq/train_first_20.json` exists;
`CS30_LOCAL_SCIQ_PATH` can point to a different local file. These files are
ignored by Git and are not model-effectiveness results.
The packaged free questions have no supplied evidence, so they intentionally
produce abstentions until Member 6's real retriever is connected.

## SciQ question smoke run

To run only a local Hugging Face dataset-server rows response, place it in the
ignored `data/raw/` directory, then run:

```bash
python -m cs30.generation.demo --provider mock --dataset local-sciq \
  --sciq-json data/raw/sciq/train_first_20.json \
  --output-dir artifacts/task7-sciq
```

This uses real SciQ questions and answer choices. The SciQ `support` field is
wrapped as `fixture://sciq-support/train` evidence only while Member 6's real
retriever is unavailable. Correct answers are placed at A solely so the
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
  --limit 1 --skip-three-level --output-dir artifacts/task7-ollama-smoke
```

This route runs locally, needs no API key, and has no per-token API charge. Set
`OLLAMA_BASE_URL` only when Ollama is not available at its default
`http://localhost:11434` address.

### OpenAI API (optional, paid)

Set `OPENAI_API_KEY` and an accessible `LLM_MODEL`, then run:

```bash
python -m cs30.generation.demo --provider openai --limit 1 --skip-three-level \
  --output-dir artifacts/task7-openai-smoke
```

Remove the two limiting flags only after the first request succeeds.

Never put a real key in source code, a test fixture, a commit, or a screenshot.
The adapter sends `store=false`, applies the configured timeout, requests the
fixed JSON schema, and still validates the result locally.

## Integration boundaries

- Member 3: pass a validated `SciQQuestion` through
  `format_sciq_question()` so all four choices reach the prompt.
- Member 6: pass `RetrievalResult` directly; no member-7 conversion model is
  required.
- Leader: `build_real_deps()` now wires `Week1ProfileProvider`, the portable
  task-7 combined retriever, and `PersonalisedAnswerGenerator`. Member 6's later
  dense retriever can replace it behind the unchanged Protocol.
