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

macOS and Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Then, on any platform:

```bash
cs30-demo --question "What is acceleration?" --level beginner
python -m pytest
```

`cs30-demo` and `python -m cs30.pipeline` are the same entry point. The run
returns a `PipelineRun` JSON object: question, student level, Top-K evidence,
generated answer, verified citations, and run metadata.

### Demo interface

After installing the project, start the local Streamlit interface on any platform:

```bash
python -m streamlit run src/cs30/ui/app.py
```

The browser interface lets a client choose a student level, ask a question, and
inspect the generated answer, citations, and retrieved sources. The current page
runs in fixture mode and labels that mode prominently; it must not be presented as
a real retrieval or model result.

Ask something the sample chapter does not cover and the system refuses instead
of inventing an answer:

```bash
cs30-demo --question "What is quantum entanglement?" --level advanced
```

Useful flags: `--level beginner|intermediate|advanced`, `--env
development|staging`, `--mode fixture|real`.

### Fixture mode

Until the corpus and model access are confirmed, the default `development`
environment runs stand-in modules and prints a banner saying so. `PipelineRun.mode`
records it in the output. **A fixture run must never be presented as a real
result**, and CI enforces the behavioural guarantees that make it safe to show.

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
   your package. Member 8 consumes `PipelineRun` directly instead of implementing
   a Protocol.
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
- `StudentProfile`
- `GeneratedAnswer`
- `PipelineRun`

See [docs/interfaces.md](docs/interfaces.md) for ownership and field semantics,
and [docs/architecture-week1.md](docs/architecture-week1.md) for the component
diagram, data flow, and end-to-end call path.

Two guarantees are enforced in code, not by convention:

1. An answer may only cite chunks that retrieval actually returned.
2. When retrieval finds nothing, the system refuses rather than answering from
   unrelated evidence.
