# Backlog

Ordering follows the project rule in `CLAUDE.md`: **an evaluation set exists
before any optimisation is attempted.** Without a baseline, every later
"improvement" is unfalsifiable.

## Must land before any tuning

| # | Item | Owner | Depends on | Done when |
|---|---|---|---|---|
| B1 | Confirm the supervisor corpus: form, language, size, structure, whether Q&A pairs ship with it | Leader | — | R1 closed; embedding and parser choices unblocked |
| B2 | Confirm GPU / model access; decide local vs API per model | Leader | — | R2 closed; multi-model comparison is schedulable |
| B3 | Evidence Alignment: map SciQ `support` to OpenStax char spans | M3 + M2 | B1 | Answerable set produced; unalignable items listed, not silently dropped |
| B4 | Evaluation set, 30–50 pairs: gold answer, gold support span, difficulty tier | M3 | B3 | Covers several chapters and all three levels |
| B5 | Dev/Test split isolated by chapter or concept group, never random | Leader + M3 | B4 | Split is reproducible and documented |

## Real modules replacing fixtures

| # | Item | Owner | Done when |
|---|---|---|---|
| B6 | Real OpenStax parsing for 2–3 chapters (depends on B1) | M2 | Byte-identical re-parse; 10+ passages hand-checked. **This is the parser freeze gate: no ablation runs before it passes** |
| B7 | Structure-aware chunking over `document.blocks`, one ~500-token size target | M4 | Span invariant holds across the whole corpus; chunk lengths comparable |
| B8 | Real embeddings + FAISS `IndexFlatIP`, save/load | M5 | Index rebuilds identically; build/load returns a valid `IndexArtifact` |
| B9 | Real dense retriever behind the `Retriever` protocol | M6 | Loads member 5's `IndexArtifact`; `build_real_deps()` swaps it in; empty results still abstain. **Note the asymmetry:** BM25 abstains because query-side stopword removal can leave no content term to match. `IndexFlatIP` returns top_k unconditionally, so dense — and therefore the default `hybrid` — cannot abstain at all until `dense_min_similarity` is calibrated (B20) |
| B10 | Real LLM adapter with JSON schema validation and retries | M7 | 10–20 questions end to end; one API failure does not abort the batch |
| B11 | Demo interface on `PipelineRun` | M8 | Level selector, question box, answer, sources, visible mode banner |

## Measurement infrastructure

| # | Item | Owner | Done when |
|---|---|---|---|
| B12 | Retrieval metrics: Hit@K, Recall@K, MRR against gold spans | M6 + Leader | Reproducible from a single command |
| B13 | Ablation harness: one run per knob setting, `PipelineRun.metadata` into one table row | Leader | A table row can be traced back to its exact configuration. Each row carries the full record required by `RAG优化旋钮清单.md`: retrieval mode, corpus version, evaluation-set version, embedding model, every knob value, retrieval metrics, and abstention metrics where unanswerable questions are included |
| B19 | Freeze the retrieval configuration before the multi-model comparison starts | Leader | The four-model run (B10 follow-up) is launched against one recorded retrieval config. Running it earlier confounds model differences with retrieval differences and makes the comparison unattributable — the report's central table depends on this ordering |
| B20 | Calibrate `dense_min_similarity` on the Dev split, then extend the CI abstention gate to `dense` and `hybrid` | M6 + Leader | Threshold selected on the validation split only and frozen before the test split is touched; the unfiltered dense baseline is reported alongside it; the smoke job asserts abstention in all three modes, not only `bm25`, using deterministic offline fixtures. Step breakdown and acceptance criteria live in M6's `docs/retrieval-ablation-plan.md` (RET-01, RET-02); the calibration protocol is mirrored in `RAG优化旋钮清单.md` |
| B14 | Personalisation evaluation dimensions (explanation depth match, skipped steps, unexplained jargon) | Leader + M7 | Rubric agreed before more personalisation is built — see R9 |

## Engineering debt

| # | Item | Owner |
|---|---|---|
| B15 | Dependency lock file (R7) | M8 |
| B16 | Branch protection on `main`; stop direct pushes (R8) | Leader |
| B17 | Contract v1.1 decision on non-text content, only after B1 (R3) | Leader |
| B18 | Add `document_id` to `RetrievalHit` before a second document enters the corpus | Leader |
| B21 | Meta-test: every `RetrievalConfig` field must be covered by a config-reaches-the-retriever assertion | Leader |
| B22 | Decide `RealRetrievalService`: make `load_index` mode-aware so BM25 stays dependency-free, or delete it and retire the `RetrievalService` port | Leader + M6 |

## Explicitly still out of scope

Restricted KG, level-aware reranking, and the longitudinal student simulator.
These stay parked until the retrieval and evaluation baselines exist.

Calibrated abstention thresholds move out of this list and into B20. The knobs
themselves now exist and are reachable from configuration
(`retrieval.bm25_min_score`, `retrieval.dense_min_similarity`); what is still
parked is choosing their values, which needs the Dev split from B5. Until then
`dense_min_similarity` ships as `None` — off — so no unexplained constant
enters the ablation table.
