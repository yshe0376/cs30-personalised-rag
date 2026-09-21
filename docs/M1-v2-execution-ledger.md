# SDD ledger — plan: D:\\capstone\\docs\\superpowers\\plans\\2026-09-19-m1-three-textbook-contracts.md

## Pre-flight

- Date: 2026-09-20
- Isolated workspace: `C:\\Users\\m1391\\.codex\\worktrees\\v2-m1-three-textbooks\\capstone`
- Base: detached worktree at committed `16c5193` (`feat/m1-evaluation-schema`); no `v1.0*` tag exists.
- Scope ruling: implement M1 Phases 0–3 (contract/model, manifest/publish, batch pipeline and tests). Phase 4 downstream handoffs remain outside this turn.
- Isolation ruling: current `D:\\capstone` worktree has 43 uncommitted entries and is not modified or copied.
- Verification ruling: the post-review full suite completes successfully with exit code 0; the earlier non-terminating run was host-specific and is not treated as a repository failure.

## Task status

- [x] Task 1 — v2 contract models, deterministic IDs, errors, catalog, ports
- [x] Task 2 — Manifest Draft/Finalize/Write, canonical hashing, config
- [x] Task 3 — multi-textbook batch parse/chunk pipeline, reports, v2 script
- [x] Task 4 — integration fixtures/tests, output gate, full verification

## Task 1/2 done

- Added `cs30.v2` provider-neutral contracts, stable identity helpers, exact three-book catalog, and dependency-injection ports.
- Added draft/finalize/write Manifest lifecycle with canonical corpus/Manifest hashes, reportable derivation, tamper detection, versioned v2 config, and atomic publish lock.
- Direct contract/Manifest/config/publish checks pass. The v2 fixture path is diagnostic-only; official builds require real parser/chunker capabilities, pinned source hashes, and an index builder.

## Task 3 — start

- The pipeline will use the same parser/chunker interfaces and distinct `ParseBatchReport`/`ChunkBatchReport` objects. Official builds fail closed after diagnostics; development builds publish `reportable=false` diagnostics.

## Task 1 — start

- Contract tests will define the v2 provider-neutral document/chunk/index boundary before implementation.
- Isolation ruling: existing `cs30.contracts` and v1 pipeline stay untouched; v2 code lives under `cs30.v2` in this worktree until the v1 baseline is formally frozen.

## Rulings

- The managed worktree was initially detached because of repository metadata permissions; the local branch was created later without touching the v1 worktree. No GitHub push or PR will be made.

## Final implementation rulings

- Local branch `feat/v2-m1-three-textbooks` is being used for the isolated work; it is not pushed.
- The current provisional three-book IDs remain `openstax_college_physics_2e`, `ck12_peoples_physics_basic`, and `ck12_physics_concepts_intermediate`. Their final composition is still an M2 decision; parser work must not start until the intended OpenStax/CK-12 set, source files, versions, licenses, and SHA-256 pins are confirmed.
- Catalog-defined logical `source_name` values are required at the pipeline boundary; local filenames cannot enter locator or corpus identity.
- Explicit fixture parsers and chunkers are rejected by official pipeline builds with `FIXTURE_NOT_ALLOWED`. Topic assignments are persisted as a corpus-bound sidecar and validated against the manifest hash/version and current chunk IDs.
- An official build also requires an injected index builder. A complete corpus-only M1 run cannot claim `reportable=true`; it writes diagnostics with `INDEX_BUILDER_NOT_CONFIGURED` instead. Development builds may publish diagnostic records with `reportable=false`.
- Output overrides are revalidated, existing targets produce `PUBLISH_CONFLICT`, relative asset/record paths cannot escape the v2 output directory, and missing page data receives a stable chapter/block locator.

## Task 3/4 done

- Added isolated batch parser/chunker reports, stable error codes, official/development gate behavior, UTF-8 synthetic parser, unique `cs30-build-v2` entry point, script inventory, CLI exit tests, output conflict tests, and provenance/hash regression tests.
- Direct v2 verification: 52 tests passed; Ruff passed with `--no-cache`.
- Full repository verification: 255 tests passed with exit code 0 using `python -m pytest -q -p no:cacheprovider`; Ruff passed for the full `src` and `tests` trees.
