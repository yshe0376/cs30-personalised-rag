# M6 W5 BGE-M3 Retrieval Handoff

The runnable notebook is `M6_W5_retrieval_dev_test.ipynb` in this checkout.
This revision uses only `BAAI/bge-m3` Dense retrieval with the matching
1024-dimensional FAISS index from the updated M5 Release. It does not run
BM25 or Hybrid evaluation. The previous MiniLM/BM25 results are retained under
ignored `artifacts/w5/m6/` as historical evidence, not silently overwritten.

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
M1's `cs30.evaluation.cli run` and `score` produce the metrics; M6 does not
introduce a second metric formula or a new retrieval-result schema.

## Dev and Test interpretation

Run the 12-question `proposed_dev` split first. BGE-M3 Dense is the user's
requested model, not a claim that it won a Dev comparison. The earlier BM25
experiment already ran the eight `proposed_test` questions. If this notebook
also runs BGE-M3 on Test, it is a **second, exploratory Test use**, not an
untouched one-time final Test. It must not be used to reselect a model while
claiming Test remained held out.

The default notebook execution keeps Test locked. To execute this exploratory
BGE-M3 Test after the BGE-M3 Dev artifact exists:

```powershell
$env:CS30_RUN_FROZEN_TEST = '1'
.\.venv\Scripts\python.exe _execute_m6_notebook.py `
  --output artifacts/w5/m6/M6_W5_bge_m3_executed.ipynb
```

The experiment writes separately named BGE-M3 run JSONL, score JSON,
per-question scores, failure reports, `frozen_selection_bge_m3_v2.json`,
and `handoff_manifest_bge_m3_v2.json` under ignored `artifacts/w5/m6/`.
Re-executing the notebook reuses an existing matching run rather than
re-running the Test retrieval. The independent checker verifies question
IDs, ranks, provenance, no exclusions, MRR, Hit@K, Recall@K, and the Test
selection's Dev score hash:

```powershell
.\.venv\Scripts\python.exe scripts\validate_w5_m6_dev.py `
  --experiment-id w5-bge-m3-release-v2 --modes dense `
  --expected-model BAAI/bge-m3 --require-clean
.\.venv\Scripts\python.exe scripts\validate_w5_m6_dev.py `
  --split proposed_test --experiment-id w5-bge-m3-release-v2 `
  --modes dense --expected-model BAAI/bge-m3 `
  --selection-file frozen_selection_bge_m3_v2.json --require-clean
```

The user accepted M3/M5 inputs for this experiment. The released Gold still
records `annotation_status=m3_initial`, so the CLI keeps these real runs
`reportable=false` with `--provisional`; source review metadata is not
rewritten. All 20 Gold questions are answerable, so controlled refusal tests
do not calibrate a production abstention threshold.

The checked-in notebook was executed in this checkout with the BGE-M3 Release
index. The independent validator found no exclusions or run errors:

| Split | Questions | Hit@5 | Recall@5 | MRR | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| Proposed Dev | 12 | 0.5833 | 0.5833 | 0.3569 | Provisional Dev result |
| Proposed Test | 8 | 0.7500 | 0.7500 | 0.4688 | Second, exploratory Test use |

Both run manifests identify `BAAI/bge-m3`, `dense`, `top_k=5`, and a clean
Git snapshot. Neither result is marked formally reportable.

## GitHub scope

Commit the notebook, generator, installer, shared BOM compatibility fix,
validator, tests, and this handoff. Do not force-add `artifacts/`, indexes,
model weights, or the downloaded Release ZIP; `.gitignore` excludes them.
No GitHub push or PR is performed by the local notebook workflow.
