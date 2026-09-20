# M6 W5 BGE-M3 Retrieval Handoff

The runnable notebook is `M6_W5_retrieval_dev_test.ipynb` in this checkout.
This revision configures `BAAI/bge-m3` Hybrid retrieval with the matching
1024-dimensional FAISS index from the updated M5 Release. Weighted RRF uses
Dense 25% / BM25 75%, `rrf_k=60`, and 50 candidates per retriever, matching
the local comparison settings. Previous BM25 and BGE-M3 Dense runs remain
under ignored `artifacts/w5/m6/`; this experiment uses a new ID and does not
overwrite them. The source notebook is checked in without execution outputs. It can be reproduced
locally with the released M4/M5 inputs in the project `.venv`. The Dev metrics
below were recorded from that local run; Test remained locked.
The 25/75 weights and 50-candidate depth match the earlier local comparison.

## Local setup

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ml,notebook]"
.\.venv\Scripts\python.exe scripts\install_w5_m6_release_artifacts.py
```

The installer pins the M4 archives and the new `m5_release_v2.zip` SHA-256,
extracts only `bge-m3/{artifact.json,chunks.json,index.faiss}`, and refuses
to overwrite different local files. The Release contains a separate `bge/`
directory for `BAAI/bge-base-en-v1.5`; that model is **not** used here.
The BGE-M3 `artifact.json` has a UTF-8 BOM, which the shared loader now
accepts without changing the Release file.

The selected files are installed under:

```text
artifacts/w5/m4-v3/prepared_corpus/
artifacts/w5/m4-v3/gold_normalized/
artifacts/w5/m4-v3/gold_mapping/
artifacts/w5/m5_release_v2/bge-m3/
```

The notebook checks the model name, 1024-dimensional index, 3,684 chunks,
and M4 corpus identity before retrieval. Its `CS30_INDEX_DIR` and
`CS30_EXPECTED_EMBEDDING_MODEL` settings point to that same BGE-M3 artifact.
Both the smoke check and evaluation CLI receive the same 25/75 RRF settings.
M1's `cs30.evaluation.cli run` and `score` produce the metrics; M6 does not
introduce a second metric formula or a new retrieval-result schema.

## Dev and Test interpretation

Run the 12-question `proposed_dev` split first. BGE-M3 Hybrid 25/75 is the
user's requested configuration, not a claim that it won a new Dev comparison.
Earlier BM25 and BGE-M3 Dense experiments already ran the eight `proposed_test`
questions. If this notebook also runs Hybrid on Test, it is another
**exploratory Test use**, not an untouched one-time final Test. It must not be used to reselect a model while
claiming Test remained held out.

The default notebook execution keeps Test locked. To run Dev only:

```powershell
Remove-Item Env:CS30_RUN_FROZEN_TEST -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe _execute_m6_notebook.py `
  --output artifacts/w5/m6/M6_W5_bge_m3_hybrid_25_75_dev_executed.ipynb
```

To run the already-used Test questions as an explicitly exploratory Hybrid
check after the Hybrid Dev artifact exists:

```powershell
$env:CS30_RUN_FROZEN_TEST = '1'
.\.venv\Scripts\python.exe _execute_m6_notebook.py `
  --output artifacts/w5/m6/M6_W5_bge_m3_hybrid_25_75_test_executed.ipynb
```

The experiment writes separately named Hybrid run JSONL, score JSON,
per-question scores, failure reports, `frozen_selection_bge_m3_hybrid_25_75_v2.json`,
and `handoff_manifest_bge_m3_hybrid_25_75_v2.json` under ignored `artifacts/w5/m6/`.
Re-executing the notebook reuses an existing matching run rather than
re-running the Test retrieval. The independent checker verifies question
IDs, ranks, provenance, no exclusions, MRR, Hit@K, Recall@K, and the Test
selection's Dev score hash:

```powershell
.\.venv\Scripts\python.exe scripts\validate_w5_m6_dev.py `
  --experiment-id w5-bge-m3-hybrid-25-75-release-v2 --modes hybrid `
  --expected-model BAAI/bge-m3 --require-clean
.\.venv\Scripts\python.exe scripts\validate_w5_m6_dev.py `
  --split proposed_test --experiment-id w5-bge-m3-hybrid-25-75-release-v2 `
  --modes hybrid --expected-model BAAI/bge-m3 `
  --selection-file frozen_selection_bge_m3_hybrid_25_75_v2.json --require-clean
```

The user accepted M3/M5 inputs for this experiment. The released Gold still
records `annotation_status=m3_initial`, so the CLI keeps these real runs
`reportable=false` with `--provisional`; source review metadata is not
rewritten. All 20 Gold questions are answerable, so controlled refusal tests
do not calibrate a production abstention threshold.

The executed Hybrid Dev run completed all 12 questions, with zero exclusions.
The independent M6 checker reproduced the M1 retrieval metrics:

| Split        | Mode                | Questions |  Hit@1 |  Hit@3 |  Hit@5 | Recall@5 |    MRR |
| ------------ | ------------------- | --------: | -----: | -----: | -----: | -------: | -----: |
| Proposed Dev | BGE-M3 Hybrid 25/75 |        12 | 0.5000 | 0.7500 | 0.8333 |   0.8333 | 0.6319 |

The run manifest records `BAAI/bge-m3`, `hybrid`, `top_k=5`, a clean Git
snapshot, and `reportable=false`. No Hybrid Test run was performed here.

The earlier BGE-M3 **Dense-only** notebook had these verified historical
results. They are not Hybrid results:

| Split         | Questions |  Hit@5 | Recall@5 |    MRR | Interpretation                        |
| ------------- | --------: | -----: | -------: | -----: | ------------------------------------- |
| Proposed Dev  |        12 | 0.5833 |   0.5833 | 0.3569 | Historical Dense-only run             |
| Proposed Test |         8 | 0.7500 |   0.7500 | 0.4688 | Historical Dense-only exploratory run |

The prior run manifests identify `BAAI/bge-m3`, `dense`, and `top_k=5`.

## GitHub scope

Commit the notebook, generator, and this handoff. The installer, shared BOM
compatibility fix, validator, and tests are already in this branch. Do not force-add `artifacts/`, indexes,
model weights, or the downloaded Release ZIP; `.gitignore` excludes them.
No GitHub push or PR is performed by the local notebook workflow.
