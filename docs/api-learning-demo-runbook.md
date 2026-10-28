# API Learning Demo Runbook

Updated 2026-10-29. See the [current framework](superpowers/specs/2026-10-28-api-learning-demo-design.md).
This runbook describes the local implementation workspace. A documentation publication alone
is not a release of the implementation code.

The online app uses two API roles: answer generation and textbook question authoring.
There is no independent quiz reviewer or answer-uniqueness review. Quiz drafts feed only
the Demo learner event stream; they do not become published bank questions.

## 1. Install the local app dependencies

From the repository root:

```powershell
python -m pip install -e ".[ui,ml]"
```

The app does not download the Qwen weights on startup. The pinned local model
must already be cached for revision
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`.

## 2. Prepare the local assets

Copy `configs/learning-demo.example.toml` to the ignored local file
`configs/learning-demo.toml`, then set paths for the exact four-book v2 corpus,
Role package, Dev lambda selection, M6 Qwen3 FAISS index, and index artifact.
Do not point it at the old MiniLM/BGE index.

The M6 W6 release publishes the 69.6 MB index handoff ZIP. The separate
`m7_qwen3_d0.10_b0.90_original_top20.jsonl` is a frozen candidate set for Gold
questions, not an online FAISS index. Download the ZIP and verify its published
SHA-256 before extracting it:

```powershell
$indexDir = "artifacts/m6-index"
New-Item -ItemType Directory -Path $indexDir -Force | Out-Null
$zipPath = Join-Path $indexDir "M5_to_M6_four_book_2026-10-21.zip"
Invoke-WebRequest `
  -Uri "https://github.com/yshe0376/cs30-personalised-rag/releases/download/m6-w6-qwen3-hybrid-dev-v1/M5_to_M6_four_book_2026-10-21.zip" `
  -OutFile $zipPath
$expectedHash = "2851abf71164e131b9064de0e87385b3b7f38943cbfcbf420dad5a40c0bf8c3e"
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) { throw "Index ZIP SHA-256 mismatch: $actualHash" }
```

Inspect the archive file list before extracting it into a new, empty directory:

```powershell
python -c "from zipfile import ZipFile; print('\n'.join(ZipFile(r'artifacts/m6-index/M5_to_M6_four_book_2026-10-21.zip').namelist()))"
Expand-Archive -LiteralPath $zipPath -DestinationPath (Join-Path $indexDir "unpacked")
Get-ChildItem -Path (Join-Path $indexDir "unpacked") -Recurse -File |
  Where-Object { $_.Name -in @("artifact.json", "index.faiss") } |
  Select-Object FullName, Length
```

The ZIP contains separate BGE-M3, GTE-ModernBERT, and Qwen3 index directories.
Use only `qwen3-embedding` for this demo. Its artifact must match the exact
embedding model revision and corpus identity below; do not use the Top-20 JSONL
or one of the other model directories as the Qwen3 index.

For the Qwen3 directory produced by the extraction command above, the local
TOML paths are:

```toml
index_artifact_path = "artifacts/m6-index/unpacked/qwen3-embedding/artifact.json"
index_file_path = "artifacts/m6-index/unpacked/qwen3-embedding/index/index.faiss"
```

The source Topic-map release labels the corpus `2.0.0-rc.1`, while the selected
four-book corpus uses `2.0.0-dev.m4-four-book-main-a1fe99e`. If and only if the
corpus hash, registry version, and every mapped chunk ID match, create a new
local sidecar while preserving the source release:

```powershell
python scripts/prepare_learning_assets.py
```

The configured bound-map output must not already exist. The command writes a
provenance sidecar beside it and refuses to overwrite either file. It does not
change the Topic-map loader or Role/lambda version checks.

Run local identity diagnostics:

```powershell
python scripts/check_learning_demo_assets.py
```

This writes `artifacts/learning-demo-runtime/asset-preflight.json`. It records
file hashes, asset identity fields, model role names and whether each configured
environment variable is present. It never records key values.

## 3. Topic scope and preflight

Set `[demo].topic_ids = ["*"]` for all registered Topics (2,520 in the current assets).
An explicit non-empty list remains available for restricted scope. Each selected Topic must
occur in an answer-validated citation's map assignments; multi-Topic chunks are eligible.
One eligible candidate is selected directly; multiple candidates are sampled by rank-weighted
citation support. This support differs from retrieval weights and reranking lambda.
Unmapped citations cannot produce a Topic-based quiz.

```powershell
python -m cs30.learning.preflight
python scripts/check_learning_demo_assets.py
```

The preflight binds corpus, map, index and practice-question hashes. The historical 8/10
unique-retrieval-Topic result belongs to a curated small bank, not all-Topic coverage.
In wildcard mode the old unique-Topic-rate threshold is not an online coverage gate;
asset identity and valid cited evidence still matter. Missing/stale reports remain blockers.
Topic decisions are appended to `topic_selection_audit.jsonl` before quiz calls.

## 4. Credentials and billing limits

Copy `.env.learning.example` to the ignored `.env.learning.local` and set `DEEPINFRA_API_KEY`.
Use `[api.quiz].structured_output = "json_schema"`. The legacy verify role is unused by
this path; its credential and independent-model check are not startup requirements.
API model choices remain provisional, not a formal M7/M8 model freeze.

The checked-in example disables live calls and sets the cap to zero. Enable
`[api].live_calls_enabled` and choose `[api].total_request_cap` locally to permit calls.
Answer operations allow at most two requests. Each quiz normally uses one author request,
at most two if format or citation binding fails, with at most three quiz attempts per answer.
Comparison is a separate budgeted operation. Failed calls count toward the persistent total;
restarts and new learner sessions do not clear it. The cap is not the provider balance.
Do not upload local keys, TOML overrides, request ledgers, learner events, weights or indexes.

## 5. Start and use the demo

```powershell
.\start_learning_demo.cmd
```

On macOS/Linux use `bash start_learning_demo.sh`. Stop the old server before restarting
and open the URL printed in the terminal (normally `http://127.0.0.1:8501`).

1. Select the starting level and start a learning session.
2. Ask a physics question and inspect its textbook citations.
3. Generate Concept Check: the author supplies question, four options, answer, explanation,
   source chunk and verbatim quote. Local code locates the quote before offering the question.
4. Submit or skip to reveal the answer, explanation and quoted passage. Answers are AI-provided;
   local quote binding is not semantic validation of correctness or answer uniqueness.
5. The sidebar shows the quiz Topic's mastery, level and attempts, with history Topic switching
   and manual level adjustment. Comparison level does not edit the profile. Use the new-profile
   section to choose a fresh starting level; existing histories stay saved.

Question fields and explanations support common LaTeX delimiter normalization. Verbatim
textbook evidence stays unchanged. The UI should say all registered Topics are enabled and
that no independent model review is performed.

## 6. Failure diagnosis and limitations

No mapped cited Topic: inspect validated citations and map assignments, not a Gold question bank.
Author JSON or quote-location failure: the page lists each failed attempt without revealing answers.
Two failed author attempts produce no quiz. Existing failure summaries do not archive raw responses.
The separate Streamlit `removeChild` browser error has not been reproduced or confirmed fixed.

Local relevant checks: 17 offline tests and related Ruff checks passed at this documentation update.
No new paid end-to-end check was run for the combined version. Sample multiple textbooks and
Topics, manually inspect semantic correctness and record success/failure rates before claiming
broad coverage or educational effectiveness.
