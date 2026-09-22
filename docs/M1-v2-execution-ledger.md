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

- Added `cs30.v2` provider-neutral contracts, stable identity helpers, a frozen textbook catalog (originally three books; see the 2026-09-23 ruling below), and dependency-injection ports.
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

- Branch `feat/v2-m1-three-textbooks` carries the isolated work and is pushed to GitHub; nothing is merged into `main`.
- 2026-09-23 textbook ruling: the required set is the three OpenStax books M2 parsed with parser 1.3.2 — `openstax_college_physics_2e`, `openstax_physics`, and `openstax_college_physics_ap_2e` — each pinned to its PDF SHA-256, version, and chapter range. A CK-12 book is also required but not chosen yet, so `REQUIRED_PROVIDERS = ("openstax", "ck12")` stops official builds with `REQUIRED_PROVIDER_MISSING` until M2 adds it; nothing guesses a CK-12 ID. The book count is no longer fixed at three anywhere in the contracts.
- Parsed documents must carry the catalogue provider (`PROVIDER_MISMATCH` otherwise).
- Every build writes `duplicate_blocks.json`, the cross-textbook duplicate block groups bound to the corpus hash. On M2's outputs it finds 16,677 groups, 16,456 of them between College Physics 2e and its AP edition.
- 2026-09-23 real-build ruling: M2's parser 1.3.2 is vendored unchanged at `src/cs30/v2/ingest/openstax_parser.py` (import order only), and `cs30.v2.ingest.OpenStaxPdfParser` converts its schema 1.0 output to v2 documents. M2's `document_hash` is the PDF hash and becomes `raw_source_sha256`; the v2 `document_hash`/`document_id` are recomputed from the parsed content; block IDs keep M2's prefixes so a run can be compared with M2's delivery. Verified against all three delivered outputs.
- `cs30.v2.indexing` builds one FAISS flat inner-product index over the canonical chunk order and records the model, resolved revision, dimension, metric, normalisation, and truncated-chunk count; `load_faiss_index` re-hashes `records.jsonl` and the index assets before pairing them. The encoder is injected, so tests do not download a model; the real `SentenceTransformerEncoder` path was smoke-tested offline with MiniLM (384 dimensions, 254 input tokens).
- `scripts/install_v2_sources.py` installs the pinned PDFs from a Release or a local folder, verifying each hash while reading and refusing to overwrite a different local file. `docs/v2-real-build.md` documents the flow and the remaining official-build gates.
- Parser 1.3.2 must not reach `main` before v1.0.0: the frozen v1 corpus was parsed with 1.2.0.
- Catalog-defined logical `source_name` values are required at the pipeline boundary; local filenames cannot enter locator or corpus identity.
- Explicit fixture parsers and chunkers are rejected by official pipeline builds with `FIXTURE_NOT_ALLOWED`. Topic assignments are persisted as a corpus-bound sidecar and validated against the manifest hash/version and current chunk IDs.
- An official build also requires an injected index builder. A complete corpus-only M1 run cannot claim `reportable=true`; it writes diagnostics with `INDEX_BUILDER_NOT_CONFIGURED` instead. Development builds may publish diagnostic records with `reportable=false`.
- Output overrides are revalidated, existing targets produce `PUBLISH_CONFLICT`, relative asset/record paths cannot escape the v2 output directory, and missing page data receives a stable chapter/block locator.

## Task 3/4 done

- Added isolated batch parser/chunker reports, stable error codes, official/development gate behavior, UTF-8 synthetic parser, unique `cs30-build-v2` entry point, script inventory, CLI exit tests, output conflict tests, and provenance/hash regression tests.
- Direct v2 verification: 81 tests passed; Ruff passed.
- Full repository verification (2026-09-23): 284 passed and 2 skipped (Streamlit is not installed), exit code 0, using `python -m pytest -p no:cacheprovider`; Ruff passed for the full `src` and `tests` trees.
