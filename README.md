# CS-30 Personalised RAG

Source-code repository for a semester-long personalised AI learning assistant
using Retrieval-Augmented Generation and Large Language Models. It contains
the runnable implementation, small test fixtures, engineering contracts, and
essential technical documentation. Planning documents, source materials, and
large project assets are maintained separately in the team Google Drive.

The current milestone is `v0.1-thin-slice`: a small OpenStax Physics path used
to validate the engineering workflow. It does not report formal retrieval or
model-effectiveness results.

## Code repository scope

This is the source of truth for the project's code and engineering interfaces,
including:

1. Week 1 thin-slice integration and staging demo.
2. Dataset preparation, Evidence Alignment, and evaluation infrastructure.
3. Dense and hybrid retrieval experiments.
4. Student profiles, personalised retrieval, and personalised prompting.
5. Reliability controls, citation checks, and calibrated abstention.
6. Optional restricted knowledge-graph extensions.
7. Code supporting multi-model experiments, analysis, and the final demonstration.

## Project files

Official source files, planning documents, report drafts, presentations,
meeting records, large datasets, model files, indexes, and experiment outputs
belong in the team Google Drive. They are intentionally excluded by
`.gitignore` and must not be duplicated as editable copies in this repository.
A Drive index can be added under `docs/` after the shared folder is created.

## Week 1 scope

```text
OpenStax chapter
-> normalised document
-> structure-aware chunks
-> embedding and FAISS dense retrieval
-> student profile
-> personalised prompt
-> fixed JSON answer (or an explicit refusal)
-> citation integrity check
-> demo interface
```

Until GPU and model access are confirmed, the repository provides validated
contracts, fixtures, and a mock end-to-end pipeline so all modules can be built
in parallel.

## Quick start

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Optional local configuration can be created from the safe template. The
application reads this ignored `.env` file without overriding variables already
set by the shell or deployment platform:

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

macOS and Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

For the exact dependency versions used by the verified development environment,
install `requirements.lock` first and then install the local package without
re-resolving dependencies:

```bash
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
```

The lock file excludes the editable local package and records the current
Windows/Python 3.12 environment. The `pyproject.toml` command above remains
the normal choice for editable development or other platforms until the team
adopts a cross-platform lock format.

Then, on any platform:

```bash
cs30-demo --question "What is acceleration?" --level beginner
python -m pytest
```

`cs30-demo` and `python -m cs30.pipeline` are the same entry point. The run
returns a `PipelineRun` JSON object: question, student level, Top-K evidence,
generated answer, verified citations, and run metadata.

### Demo interface

The simplest startup path is the repository-root launcher. It creates `.venv`
and installs the project on first use, then opens the Streamlit interface.

Windows — double-click `start_demo.cmd`, or run:

```powershell
.\start_demo.cmd
```

Equivalent `.bat` aliases are included for environments that prefer that
extension.

macOS and Linux:

```bash
chmod +x start_demo.sh start_staging_preview.sh
./start_demo.sh
```

The equivalent manual command is:

```bash
python -m streamlit run src/cs30/ui/app.py
```

The browser interface lets a client choose a student level, ask a question, and
inspect the generated answer, citations, and retrieved sources. The current page
runs in fixture mode and labels that mode prominently; it must not be presented as
a real retrieval or model result. The W5 evidence layer assigns display IDs (`E1`,
`E2`, ...), maps them back to chunk IDs, and records a compact trace for each run.

Ask something the sample chapter does not cover and the system refuses instead
of inventing an answer:

```bash
cs30-demo --question "What is quantum entanglement?" --level advanced
```

Useful flags: `--level beginner|intermediate|advanced`, `--env
development|staging`, `--mode fixture|real`, `--provider mock|ollama|openai`,
`--model`, and `--top-k`.

To ask an arbitrary question through the combined local RAG corpus and the
installed Ollama model:

```bash
python -m cs30.pipeline --mode real --provider ollama --model gpt-oss:20b \
  --question "What is the difference between velocity and acceleration?" \
  --level beginner --top-k 3
```

The portable retriever searches every available evidence passage while keeping
the frozen `Retriever` and `AnswerGenerator` interfaces unchanged. It returns
an empty result for insufficient matches, causing a grounded abstention rather
than an unrelated answer. This is a local engineering path, not a formal
retrieval-effectiveness result. Although `--mode real` selects the configured
model-provider path, its `PipelineRun` and retrieval output remain labelled
`fixture` until the real Member 6 retriever and index are connected.

For a concise terminal answer, omit `--top-k` to use the configured default of
3 and add `--answer-only`:

```bash
python -m cs30.pipeline --mode real --provider ollama --model gpt-oss:20b \
  --question "What is Newton's second law?" --level beginner --answer-only
```

### Member 7 smoke delivery

The Week 1 profile, prompt, fixed JSON, retry, and citation path can be exercised
against every available local and packaged dataset without an API key:

```bash
python -m cs30.generation.demo --provider mock
```

By default it combines the original 20-question fixture, Member 3's packaged
24-question SciQ set and 8 free questions, plus the local 20-row SciQ file when
`data/raw/sciq/train_first_20.json` exists. Set `CS30_LOCAL_SCIQ_PATH` to use a
different local file. Each output row records its dataset source. Use
`--dataset original`, `--dataset team`, or `--dataset local-sciq` to run one
group. The 8 free questions explicitly abstain until a retriever supplies
matching evidence.

To use a real model without API fees, install Ollama, run
`ollama run gpt-oss:20b` once, then smoke-test the existing generation path:

```bash
python -m cs30.generation.demo --provider ollama --model gpt-oss:20b \
  --limit 1 --skip-three-level --output-dir artifacts/task7-ollama-smoke
```

The model runs on the local machine and does not require an API key. Evidence
remains explicitly labelled fixture evidence, so the smoke test must not be
reported as model-effectiveness evidence.

### Fixture mode

Until the corpus and model access are confirmed, the default `development`
environment runs stand-in modules and prints a banner saying so. `PipelineRun.mode`
records it in the output. **A fixture run must never be presented as a real
result**, and CI enforces the behavioural guarantees that make it safe to show.

### Staging preview

Before the real Member 6 and 7 adapters are integrated, use the honest,
fixture-backed staging preview:

```powershell
.\start_staging_preview.cmd
```

```bash
./start_staging_preview.sh
```

This loads the staging configuration while forcing fixture mode and labels the
page `STAGING PREVIEW · FIXTURE MODE`. It is suitable for checking startup,
configuration and the client demonstration sequence, but it is not the real
retriever or LLM. See [the staging integration plan](docs/staging-integration-plan.md)
for the proposed real-adapter boundary and deployment decision.

### Smoke test

Run the dedicated runnable-path smoke gate:

```bash
python -m pytest -m smoke
```

It checks Streamlit startup and submission, fixture index loading, the Retriever
interface, JSON round-trip validation, citation integrity, staging-preview
configuration and file logging. These checks prove runnability only; they do
not report retrieval or model quality.

### Logs, demo instructions and help

Runtime logs are written to the terminal and to `logs/cs30.log`. The file
rotates at approximately 1 MB and keeps three backups. Override its directory
with `CS30_LOG_DIR` if required.

- [Customer and tutor demonstration runbook](docs/customer-demo-runbook.md)
- [Common errors, log locations and recovery steps](docs/troubleshooting.md)
- [Real staging integration proposal](docs/staging-integration-plan.md)

## Repository layout

```text
src/cs30/contracts/     Frozen cross-module schemas
src/cs30/ports.py       Typed boundaries between computational modules
src/cs30/pipeline.py    Offline build path and online question-answering path
src/cs30/config.py      TOML + environment configuration
src/cs30/configs/       Packaged development and staging configuration
src/cs30/logging.py     Shared logging setup
src/cs30/errors.py      Typed errors
src/cs30/fixtures/      Small, non-sensitive fixtures, shipped with the package
src/cs30/ingest/        Member 2  - OpenStax parsing
src/cs30/questions/     Member 3  - validated SciQ demo questions
src/cs30/chunking/      Member 4  - chunking and metadata
src/cs30/indexing/      Member 5  - embeddings and FAISS
src/cs30/retrieval/     Member 6  - dense retrieval
src/cs30/profile/       Member 7  - student profile
src/cs30/generation/    Member 7  - prompting and LLM generation
src/cs30/ui/            Member 8  - demo interface
tests/                  Contract, pipeline, port, and config tests
docs/adr/               Architecture decision records
data/raw/               Local source data; ignored by Git
```

Each module package has a `README.md` naming its owner, integration boundary,
and week 1 acceptance criteria.

## Adding your module

1. Implement your Protocol from `src/cs30/ports.py` next to the `fixture.py` in
   your package. Member 8 consumes `PipelineRun` and its `EvidenceBundle` directly
   instead of implementing a computational Protocol.
2. Offline modules (members 2, 4, and 5) are supplied through `BuildDeps` to
   `run_build_pipeline()`. Online modules (members 6 and 7) are supplied through
   `PipelineDeps` to `run_pipeline()`. Neither orchestration function changes.
3. Member 3 implements `QuestionProvider`; its validated `SciQQuestion` can be
   passed to retrieval/generation by the UI or evaluation harness.
4. Add a real behaviour test. Runtime Protocol checks only confirm method names;
   the fixture tests also call every boundary so incorrect signatures fail.

## Collaboration rules

1. Do not commit directly to `main`; use a short-lived branch and Pull Request.
2. Every module must accept and return the schemas in `src/cs30/contracts`.
3. Submit a small working sample before scaling to the full Week 1 target.
4. Do not commit API keys, private student data, full model files, or indexes.
5. A change is mergeable only when tests pass and the mock pipeline still runs.

## Current interfaces

The first contract version includes:

- `OpenStaxDocument`
- `Chunk`
- `IndexArtifact`
- `SciQQuestion`
- `RetrievalResult`
- `EvidenceItem`
- `EvidenceBundle`
- `StudentProfile`
- `GeneratedAnswer`
- `ValidatedAnswer`
- `PipelineRun`

See [docs/interfaces.md](docs/interfaces.md) for ownership and field semantics,
and [docs/architecture-week1.md](docs/architecture-week1.md) for the component
diagram, data flow, and end-to-end call path.

Two guarantees are enforced in code, not by convention:

1. An answer may only cite chunks that retrieval actually returned.
2. When retrieval finds nothing, the system refuses rather than answering from
   unrelated evidence.
