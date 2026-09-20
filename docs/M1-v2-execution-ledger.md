# SDD ledger — plan: D:\\capstone\\docs\\superpowers\\plans\\2026-09-19-m1-three-textbook-contracts.md

## Pre-flight

- Date: 2026-09-20
- Isolated workspace: `C:\\Users\\m1391\\.codex\\worktrees\\v2-m1-three-textbooks\\capstone`
- Base: detached worktree at committed `16c5193` (`feat/m1-evaluation-schema`); no `v1.0*` tag exists.
- Scope ruling: implement M1 Phases 0–3 (contract/model, manifest/publish, batch pipeline and tests). Phase 4 downstream handoffs remain outside this turn.
- Isolation ruling: current `D:\\capstone` worktree has 43 uncommitted entries and is not modified or copied.
- Baseline ruling: full pytest reached existing `test_unified_corpus_is_deterministic_and_shared_by_dense_and_bm25` and errored before hanging in the baseline run; this is recorded as pre-existing and will be rechecked after M1.

## Task status

- [x] Task 1 — v2 contract models, deterministic IDs, errors, catalog, ports
- [x] Task 2 — Manifest Draft/Finalize/Write, canonical hashing, config
- [ ] Task 3 — multi-textbook batch parse/chunk pipeline, reports, v2 script
- [ ] Task 4 — integration fixtures/tests, output gate, full verification

## Task 1/2 done

- Added `cs30.v2` provider-neutral contracts, stable identity helpers, exact three-book catalog, and dependency-injection ports.
- Added draft/finalize/write Manifest lifecycle with canonical corpus/Manifest hashes, reportable derivation, tamper detection, versioned v2 config, and atomic publish lock.
- Direct contract/Manifest/config/publish checks pass. Pytest itself prints completed results but does not terminate in this host; this is tracked as an environment baseline issue and will be reported with the final verification command.

## Task 3 — start

- The pipeline will use the same parser/chunker interfaces and distinct `ParseBatchReport`/`ChunkBatchReport` objects. Official builds fail closed after diagnostics; development builds publish `reportable=false` diagnostics.

## Task 1 — start

- Contract tests will define the v2 provider-neutral document/chunk/index boundary before implementation.
- Isolation ruling: existing `cs30.contracts` and v1 pipeline stay untouched; v2 code lives under `cs30.v2` in this worktree until the v1 baseline is formally frozen.

## Rulings

- The managed worktree is detached because branch creation is blocked by repository metadata permissions; implementation remains isolated locally. No GitHub push or PR will be made.
