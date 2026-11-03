# Online learning Demo: installation and startup

Use this guide to run the integrated textbook Q&A and Concept Check Demo on a new
computer. The implementation is available on `main` following PR #219.

Cloning the repository is only the first step. Online mode also requires matching
textbook assets, a local retrieval model, and a working DeepInfra API key. The
launchers do not install dependencies or download these assets automatically.
For a walkthrough without live API calls, the separate offline fixture mode is
available through `start_v2_demo.cmd`; it is not a live textbook/API demonstration.

## 1. Download the code and install dependencies

Install Git and Python 3.11 or later. In Windows PowerShell:

```powershell
git clone https://github.com/yshe0376/cs30-personalised-rag.git capstone
cd capstone
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[ui,ml]"
```

On macOS/Linux:

```bash
git clone https://github.com/yshe0376/cs30-personalised-rag.git capstone
cd capstone
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[ui,ml]"
```

Run the following commands from the repository root, using this virtual
environment's Python. On Windows, no PowerShell activation-policy change is needed
when using the explicit `.venv\Scripts\python.exe` path shown here.
Create the virtual environment on the new computer; do not copy an old `.venv`.

## 2. Obtain a matching asset set

Obtain the following from the project's asset handoff or a working installation.
Large local assets are not all included in GitHub source downloads.

| Configuration field | Required asset |
|---|---|
| `corpus_dir` | Complete four-book corpus directory, including its manifest and referenced files |
| `source_topic_map_path` | Original chunk-to-Topic mapping JSON |
| `topic_registry_path` | Matching Topic registry JSON |
| `role_manifest_path` | Role provenance manifest plus every package file it references |
| `lambda_selection_path` | Dev selection JSON matching the corpus, Role package and retrieval settings; current loader requires lambda 0.1 |
| `index_artifact_path` | Qwen3 embedding index metadata, `artifact.json` |
| `index_file_path` | Matching Qwen3 `index.faiss` |
| `question_bank_path` in `[demo]` | Offline preflight input questions; the template defaults to the checked-in `configs/learning-demo-questions.json` |

The current corpus identity is `2.0.0-dev.m4-four-book-main-a1fe99e`. Asset hashes,
versions and chunk identities must agree; changing filenames or version fields
does not make incompatible assets usable. Copy entire corpus and Role package
directories, not just their manifests. Do not copy private session histories or
request ledgers merely to get a new installation running.

The [M6 index release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/m6-w6-qwen3-hybrid-dev-v1)
provides the index handoff. The [runbook](api-learning-demo-runbook.md#2-prepare-the-local-assets)
contains the exact archive URL, SHA-256 check and Qwen3 extraction paths. That
archive is not a complete online Demo bundle. A Top-20 candidate JSONL is not a
replacement for the FAISS index.

One possible local layout is:

```text
capstone/
  local-assets/                 # Keep outside Git; use an untracked local location
    corpus/                    # Complete corpus directory
    topics/                    # Original map and registry
    roles/                     # Complete Role package
    selection/selected-lambda.json
    qwen3/artifact.json
    qwen3/index/index.faiss
```

If placing assets inside the checkout, add `local-assets/` to `.git/info/exclude`
before staging files, or use the already ignored `artifacts/` directory instead.

## 3. Create local configuration and credentials

Windows:

```powershell
Copy-Item configs/learning-demo.example.toml configs/learning-demo.toml
Copy-Item .env.learning.example .env.learning.local
```

macOS/Linux:

```bash
cp configs/learning-demo.example.toml configs/learning-demo.toml
cp .env.learning.example .env.learning.local
```

Do this once; do not overwrite a working configuration on subsequent startups.
Edit `configs/learning-demo.toml`. Replace its `[assets]` section with paths to
your files. For the example layout above:

```toml
[assets]
corpus_dir = "local-assets/corpus"
source_topic_map_path = "local-assets/topics/chunk_topic_map_topics-0.2.json"
topic_registry_path = "local-assets/topics/topic_registry_v0.2.json"
topic_map_path = "artifacts/learning-demo-runtime/topic_map_bound.json"
role_manifest_path = "local-assets/roles/role_labels_v2_provenance_manifest.json"
lambda_selection_path = "local-assets/selection/selected-lambda.json"
index_artifact_path = "local-assets/qwen3/artifact.json"
index_file_path = "local-assets/qwen3/index/index.faiss"
compatibility_index_dir = "artifacts/learning-demo-runtime/retrieval-view"
state_dir = "artifacts/learning-demo-runtime"
preflight_report_path = "artifacts/learning-demo-runtime/topic-preflight.json"
```

These paths are examples: preserve the internal structure of the supplied packages
and adjust paths to the actual layout. Relative paths resolve from the repository
root, not from `configs/`. Avoid paths pointing to another computer's user folder
or worktree. On Windows, use forward slashes inside TOML strings.

Keep the other template sections. In its existing `[api]` section, enable calls
and choose the cumulative request allowance, for example:

```toml
live_calls_enabled = true
total_request_cap = 200
```

In `.env.learning.local`, set:

```dotenv
DEEPINFRA_API_KEY=YOUR_OWN_API_KEY
```

This key needs access to the configured answer and quiz models and sufficient
provider credit. The current online route does not call the template's legacy
`verify` role. The request allowance is a local request limit, not a provider
balance. Never commit filled credential files or local configuration.

The app normally reads `configs/learning-demo.toml` in the checkout containing
its source. If `CS30_LEARNING_CONFIG` is set, that variable selects the config
instead. Check it when a configuration edit appears to have no effect.

## 4. Download the pinned retrieval model

Online mode requires this exact Qwen3 revision in the local Hugging Face cache.
It does not download model weights during application startup.

Windows:

```powershell
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen3-Embedding-0.6B', revision='97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3')"
```

macOS/Linux, with the virtual environment active:

```bash
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen3-Embedding-0.6B', revision='97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3')"
```

Use the same operating-system user and Hugging Face cache settings for downloading
and running the app. The local embedding model is separate from the remote API
models that generate answers and quizzes.

## 5. Prepare and validate the local assets

On the first setup, generate a bound Topic-map sidecar from the original map.
The output file and its provenance sidecar must not already exist. This command
validates compatibility and refuses to overwrite files or rebind incompatible data.

```powershell
.\.venv\Scripts\python.exe scripts/prepare_learning_assets.py
.\.venv\Scripts\python.exe -m cs30.learning.preflight
.\.venv\Scripts\python.exe scripts/check_learning_demo_assets.py
```

On macOS/Linux, replace `.\.venv\Scripts\python.exe` with `python` after activation.
If reusing an existing matching bound map, skip the first command. Regenerate
preflight after changing assets or its input questions. These commands perform
local preparation and retrieval diagnostics; they do not generate paid API answers.
Resolve failed setup checks before starting a learning session. A passing offline
preflight does not guarantee that every live answer or Concept Check succeeds.

## 6. Start and use the Demo

Windows:

```powershell
.\start_learning_demo.cmd
```

Keep the command window running and open
[http://127.0.0.1:8512/](http://127.0.0.1:8512/).
The Windows launcher defaults to port 8512; `CS30_PORT` can select another port.

macOS/Linux, with the virtual environment active:

```bash
bash start_learning_demo.sh
```

The shell launcher uses Streamlit's default port unless separately configured,
normally [http://127.0.0.1:8501/](http://127.0.0.1:8501/). Follow the URL printed
by the server. To explicitly use port 8512:

```bash
python -m streamlit run src/cs30/ui/learning_app.py --server.address=127.0.0.1 --server.port=8512
```

On the page:

1. Select a starting learner level and click **Start learning session**.
2. Ask, for example, **What does Ohm's law state about voltage, current, and resistance?**
3. Inspect the answer and expand its textbook evidence.
4. Click **Generate Concept Check**, then submit or skip the question for feedback.
5. Inspect Topic progress and the session report when a mapped Topic is available.

Only eligible scored Topic-linked attempts update Topic progress. Practice generated
directly from unmapped cited textbook passages leaves the Topic profile unchanged.
For full behaviour, see the [current Concept Check framework](superpowers/specs/2026-10-28-api-learning-demo-design.md).

## 7. Restarting and common issues

After a reboot, return to the same project folder and run the launcher again.
You do not need to reinstall packages, recreate configuration or download assets.
Use Ctrl+C in the server terminal to stop it. Online answer and quiz generation
requires internet access and a working API account.

| Symptom | What to check |
|---|---|
| Browser cannot connect | Start the server, keep its terminal open, and use its printed port |
| `streamlit` or another module is missing | Install `.[ui,ml]` using the same virtual environment as the launcher |
| Setup reports missing files | Replace every placeholder and verify package files, not only manifest paths |
| Qwen3 cache check fails | Download the pinned revision as the user running the server |
| Corpus, Role, map, lambda or index mismatch | Obtain matching assets; do not edit identity fields to bypass checks |
| Offline preflight is missing or stale | Run `python -m cs30.learning.preflight` with the configured assets |
| API cap still shows the old value | Edit the active checkout's config; check `CS30_LEARNING_CONFIG`; recreate the learning session so its runtime uses the new value |
| API calls fail | Check the configured key, provider access/credit, network and displayed request limits |

To recreate a learning session after a cap edit, expand **Start a new learner
profile**, click **Start new learner session**, then **Start learning session**.
Existing histories remain saved; the current on-page session is replaced. Refresh,
new profiles and server restarts do not reset the cumulative request ledger.

`127.0.0.1` refers to the computer running the browser. Opening the same URL on a
different computer does not connect to the original server. Remote access needs
a separately configured deployment or remote desktop; this guide runs locally.
