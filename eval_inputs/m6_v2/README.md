# M6 W6 four-book retrieval inputs

`M6_W6_v2_retrieval_dev_test_full.ipynb` uses the following immutable inputs:

| File | SHA-256 | Git policy |
|---|---|---|
| `M4_to_M5_four_book_corpus_a1fe99e.zip` | `074ff89686fe3649089329f7858505f7a68d228d0284a83394a0c0b5a547a592` | External handoff or GitHub Release; ZIP files are ignored |
| `M5_to_M6_four_book_2026-10-21.zip` | `2851abf71164e131b9064de0e87385b3b7f38943cbfcbf420dad5a40c0bf8c3e` | External handoff or GitHub Release; ZIP files are ignored |
| `gold_v0_1_3.jsonl` | `7d69af416591b64198bf25806424347366eb2123fdcdcf36ad757d37c4f942b8` | Committed in this directory |
| `gold_v0_1_3_para_v1.jsonl` | `57ca94918912df01d8d66e6e9e7fed95b3faf4e6dd4254428b349823a3623696` | External handoff or GitHub Release; set `CS30_M6_GOLD` when running para-v1 |

The two ZIPs are intentionally not committed. Place them in this directory, or
set their paths explicitly:

```powershell
$env:CS30_M6_CORPUS_ZIP = "C:\path\to\M4_to_M5_four_book_corpus_a1fe99e.zip"
$env:CS30_M6_INDEX_ZIP = "C:\path\to\M5_to_M6_four_book_2026-10-21.zip"
$env:CS30_M6_GOLD = "$PWD\eval_inputs\m6_v2\gold_v0_1_3.jsonl"
```

The default notebook mode validates input hashes, rebinds all 352 Golden
Evidence spans, reproduces the deterministic 273 Dev / 68 exposed diagnostic
holdout split, verifies
the three delivered index artifacts, and displays committed lightweight result
tables. It does not rerun embedding models.

To start the expensive nine-model run:

```powershell
$env:CS30_M6_RUN_MODELS = "1"
$env:CS30_M6_DEVICE = "cuda"
python scripts/run_m6_w6_notebook.py --run-models --device cuda --timeout 7200
```

Run the para-v1 robustness query set through the exact same code path:

```powershell
python scripts/run_m6_w6_notebook.py --run-models --device cuda --timeout 7200 `
  --query-set para_v1 `
  --gold "C:\path\to\gold_v0_1_3_para_v1.jsonl"
```

The notebook asserts that para-v1 has the same 341 question IDs and identical
non-question Gold fields as the original set. The joint metric ranking uses
combined original-plus-para-v1 Dev Complete Hit@5, with mean MRR only as a
tie-breaker. The notebook records that ranking separately from the team's
operational BGE-M3 Dense 0.10 / BM25 0.90 system choice. The exposed
68-question holdout is limited to BM25 and that BGE-M3 system retriever.

Run `python scripts/run_m6_w6_notebook.py` without `--run-models` for the
lightweight provenance and saved-result preflight.

The experiment is diagnostic rather than formally reportable: the four-book
corpus manifest has `reportable=false`, Gold annotations are `draft`, and the
273/68 split is reproducible but not an approved frozen release split.
