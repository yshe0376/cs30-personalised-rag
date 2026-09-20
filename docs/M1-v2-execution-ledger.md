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
- [x] Task 3 — multi-textbook batch parse/chunk pipeline, reports, v2 script
- [x] Task 4 — integration fixtures/tests, output gate, full verification

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

- The managed worktree was initially detached because of repository metadata permissions; the local branch was created later without touching the v1 worktree. No GitHub push or PR will be made.

## Final implementation rulings

- Local branch `codex/v2-m1-three-textbooks` is now created in the managed worktree; it is not pushed.
- M1's explicit three-book contract set is `openstax_college_physics_2e`, `ck12_peoples_physics_basic`, and `ck12_physics_concepts_intermediate`. The current repository has no retained raw CK-12 files or pinned SHA-256 values, so official input is intentionally rejected with `SOURCE_HASH_NOT_PINNED` until M2 supplies them.
- An official build also requires an injected index builder. A complete corpus-only M1 run cannot claim `reportable=true`; it writes diagnostics with `INDEX_BUILDER_NOT_CONFIGURED` instead. Development builds may publish diagnostic records with `reportable=false`.
- Output overrides are revalidated, existing targets produce `PUBLISH_CONFLICT`, relative asset/record paths cannot escape the v2 output directory, and missing page data receives a stable chapter/block locator.

## Task 3/4 done

- Added isolated batch parser/chunker reports, stable error codes, official/development gate behavior, UTF-8 synthetic parser, unique `cs30-build-v2` entry point, script inventory, CLI exit tests, output conflict tests, and provenance/hash regression tests.
- Direct v2 verification: 38 test functions passed; Ruff passed with `--no-cache`.
- Full repository pytest was attempted from this branch. It reaches the same pre-existing v1 failure at `tests/test_chunking_delivery.py::test_unified_corpus_is_deterministic_and_shared_by_dense_and_bm25` and then does not terminate in this host; no v2 test failure was observed in the direct v2 run.
