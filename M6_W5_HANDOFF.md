# M6 W5 Retrieval Handoff

This folder is based on the current team `main` branch and keeps the shared
contracts unchanged. The M6 implementation is in `src/cs30/retrieval/real.py`.
The runnable notebook entry point is `M6_W5_retrieval_dev_test.ipynb` in the
repository root.
The notebook was rerun in this checkout, not copied with outputs from the older
`w5_m6_code` working directory.

Install the pinned W5 release assets locally (the installer checks GitHub
Release SHA-256 values and never replaces a different local file):

```powershell
.\.venv\Scripts\python.exe scripts\install_w5_m6_release_artifacts.py
```

The formal M1 runner also requires
`artifacts/w5/m4-v3/prepared_corpus/evidence_source_blocks.jsonl`, so the
installer includes it alongside the seven files shown in the initial checklist.

Create and select the project-local environment before opening the notebook:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ml,notebook]"
```

The notebook rejects a kernel from another checkout so imports cannot silently
come from a different repository.

## Delivered scope

- BM25, Dense FAISS, and weighted-RRF Hybrid retrieval over the same M5 chunk
  map.
- Retrieval-only construction through `build_real_retrieval_deps()` for M1's
  evaluation runner, without creating an LLM client.
- M5 artifact checks for index type, model, dimension, vector count, chunk-map
  structure, provenance fields, and optional SHA-256 checksums.
- Cache keys that include every runtime ranking/filter setting.
- Deterministic Dense and Hybrid no-evidence tests that continue through the
  generation and citation layers and verify abstention with zero citations.
- Automated Dev `run` and M1 `score` execution through
  `subprocess.run(..., check=True)`.
- Raw rankings, Dev/Test JSONL, run manifests, retrieval scores, and exception
  reports under `artifacts/w5/m6/`.

## Model selection

The primary Dense model is M5's current default:

`sentence-transformers/all-MiniLM-L6-v2`

Candidate indexes are MPNet, E5-base-v2, BGE-base-en-v1.5, and BGE-M3. They are
not automatic fallbacks. A candidate run must point at the matching M5 index
and declare the same expected model and experiment ID. Set
`CS30_RUN_CANDIDATES=1` only after those indexes exist:

```powershell
$env:CS30_INDEX_DIR = 'path\to\m5\candidate-index'
$env:CS30_EXPECTED_EMBEDDING_MODEL = 'intfloat/e5-base-v2'
$env:CS30_RETRIEVAL_MODE = 'dense'
$env:CS30_RUN_CANDIDATES = '1'
```

Candidate Dev runs include Dense and Hybrid, plus explicitly identified
75/25 and 25/75 RRF weight variants. Their index and model identities remain
paired. The primary MiniLM run is evaluated first.

The query instruction is read from M5's `artifact.json`, so E5/BGE query
transformations remain paired with the index that M5 built.

## Interface used by M1

The official artifact locations are:

```text
artifacts/w5/m4-v3/prepared_corpus
artifacts/w5/m4-v3/gold_normalized
artifacts/w5/m4-v3/gold_mapping
artifacts/w5/m5_latest/all-minilm-l6-v2
```

The user accepted this M5 local rebuild, together with the M3 Gold, for this
W5 experiment. The M5 Release itself still says pending owner validation and
the Gold records still have `annotation_status=m3_initial`. We retain those
source labels and keep `reportable=false` rather than rewriting review history.
The release tags and file hashes are recorded in the installer and the local
handoff manifest.

```python
from cs30.config import load_config
from cs30.pipeline import build_real_retrieval_deps

config = load_config("staging")
deps = build_real_retrieval_deps(config)
result = deps.retriever.retrieve("What is acceleration?", top_k=5)
```

The return type is the shared `RetrievalResult`; each hit is a shared
`RetrievedEvidence`, and real results include `EvidenceProvenance`. No M6-only
result schema is introduced.

## Dev and Test rule from the reference Notebook

The source Notebook is `m6local retrievel golden evidence dev test.ipynb`.
Its split discipline is retained:

1. Use the 12 `proposed_dev` questions to compare BM25, Dense models, RRF
   weights, and any threshold.
2. Freeze one configuration using Dev only.
3. Run that one frozen configuration once on the 8 `proposed_test` questions.
4. Keep Dev selection files and final Test files separate.
5. Any top-five Test comparison is exploratory and cannot be used to reselect
   a winner while still calling Test untouched.

M1 owns Hit@K, Recall@K and MRR reporting. M6 supplies rankings, thresholds,
provenance and failure diagnostics. The notebook calls M1's existing
`cs30.evaluation.cli score` implementation rather than adding a second metric
implementation. All W5 runs use `top_k=5` and K values `1 3 5`.

The current 20-question Gold set contains only answerable questions. The M6
refusal tests are controlled engineering gates; they must not be described as
production threshold calibration.

The notebook writes `artifacts/w5/m6/handoff_manifest.json`. The default
evaluation path requires a clean Git checkout; `CS30_ALLOW_DIRTY_LOCAL=1`
explicitly permits a dirty local validation run. The currently released Gold is
`m3_initial`, not reviewed, and the M5 index is a provisional local rebuild.
User acceptance permits the frozen Test experiment but does not change those
metadata values. The notebook therefore passes `--provisional`: real retrieval and M1 scoring run,
but each run manifest stays `reportable=false` even from a clean checkout. Do
not remove that flag until the review states are actually updated and verified.
For a clean provenance-safe run,
execute to an ignored output copy so saving notebook outputs does not dirty the
source checkout:

```powershell
.\.venv\Scripts\python.exe _execute_m6_notebook.py `
  --output artifacts/w5/m6/M6_W5_retrieval_dev_test_executed.ipynb
.\.venv\Scripts\python.exe scripts\validate_w5_m6_dev.py --require-clean
```

The handoff status records completed Dev and frozen Test runs separately. The
manifest records `git_dirty`, user acceptance, original source review labels,
scores, and file hashes. If inputs are missing, the status is
`pending_official_artifacts` and every missing path is listed.

On the 12 proposed Dev questions, BM25 led (Hit@5 = 0.8333, MRR = 0.7361),
ahead of Dense and Hybrid. BM25 is the frozen Test choice. Set the gate only
for the one-time 8-question Test run:

```powershell
$env:CS30_RUN_FROZEN_TEST = '1'
$env:CS30_FROZEN_EXPERIMENT_ID = 'w5-minilm-primary-v1'
$env:CS30_FROZEN_RETRIEVAL_MODE = 'bm25'
```

MiniLM may truncate 1,446 of the 3,684 released chunks at its 254-token
effective content limit. That is a plausible contributor to weaker Dense and
Hybrid retrieval, not a proven causal explanation. The notebook recomputes
the count with the MiniLM tokenizer and reports it with the Dev comparison.

`src/cs30/retrieval/real.py` contains `_ResultCache`; its BM25, Dense and RRF
paths look up cached results before retrieval and cache copies after retrieval.
`tests/test_real_retrieval.py` verifies a repeated BM25 query does not rescore,
that cache keys reflect runtime ranking settings, and that callers cannot
mutate the cached copy. The notebook runs those tests explicitly.

Candidate indexes (MPNet, E5, BGE-base, BGE-M3) are not part of this W5
result: only their experiment definitions are ready. No candidate-model
comparison claim is made.

## Relevant tests

```powershell
python -m pytest tests/test_real_retrieval.py `
  tests/test_m6_w5_refusal.py `
  tests/test_m6_model_policy.py `
  tests/test_config_knob_reachability.py
```
