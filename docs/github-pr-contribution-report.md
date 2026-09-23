# Pull Request Change and Integration Ledger

> Last synchronised: 2026-09-23
> Repository: [yshe0376/cs30-personalised-rag](https://github.com/yshe0376/cs30-personalised-rag)
> Scope: All 57 pull requests currently recorded in GitHub.
> Purpose: Record who delivered each change, what changed, what problems were found, how they were resolved, and which interface owner receives the next hand-off.

This is a living engineering ledger, not a substitute for the GitHub diff or review thread. GitHub is the source of truth for state, authorship, commits, and CI. Technical summaries below are based on PR descriptions, changed files, commits, repository contracts, and recorded review findings. An item marked **inferred** is an integration conclusion rather than a statement made by the PR author.

## 1. Current status and critical hand-offs

As of the synchronisation date, 48 PRs are merged, 8 are closed without merge, and 1 remains open.

| PR | Owner | State | Current decision or blocker | Next owner/action |
|---:|---|---|---|---|
| [#115](https://github.com/yshe0376/cs30-personalised-rag/pull/115) | `skyshylsylsy` | Merged | Generation supports the four W5 conditions and native `EvidenceBundle`; the Role-label owner is M3. Formal personalisation remains limited by Gold-candidate coverage and the v1.0 scope decision. | Keep the merged generation path compatible with the v1.0 release branch; formal personalisation evaluation is deferred to v2.0. |
| [#137](https://github.com/yshe0376/cs30-personalised-rag/pull/137) | `novel-peng` | Closed draft, not merged | Withdrawn on 2026-09-14. Its partial 17-question mapping and widened-filter experiments are historical only; no functionality from this PR is delivered on `main`. | Use the merged #147/#148 implementation instead. Do not reopen #137 or treat its artifacts as the current official hand-off. |
| [#138](https://github.com/yshe0376/cs30-personalised-rag/pull/138) | `ZOEY-YUNYI` | Merged | The initial abstention-cause attribution problem was fixed before merge. Reports now preserve the cause and expose system-level, model-level, and cause-specific views. | M1/M3/M4 must provide reportable Gold, mapping, and saved runs before formal benchmark values can be produced. |
| [#139](https://github.com/yshe0376/cs30-personalised-rag/pull/139) | `yshe0376` | Merged | Publishes this living PR ledger and makes it discoverable from the README. | Keep the ledger synchronised when PRs, interfaces, or hand-offs change. |
| [#140](https://github.com/yshe0376/cs30-personalised-rag/pull/140) | `yshe0376` | Merged | Freezes the W5 retrieval evidence filter and records why excluded textbook exercises and summaries must not be indexed. | The replacement M3/M4 hand-off was completed by #144/#148; use the official path rather than the withdrawn #137 partial mapping. |
| [#141](https://github.com/yshe0376/cs30-personalised-rag/pull/141) | `yshe0376` | Merged | Synchronises this ledger with the PR #137 documentation update and current GitHub state. | Keep the ledger synchronised when PRs, interfaces, or hand-offs change. |
| [#142](https://github.com/yshe0376/cs30-personalised-rag/pull/142) | `yshe0376` | Merged | Updated this ledger after the PR #137 withdrawal and the subsequent M1-M4 hand-offs. | Keep the ledger synchronised with later v1/v2 work. |
| [#143](https://github.com/yshe0376/cs30-personalised-rag/pull/143) | `yshe0376` | Merged | Publishes the shared evidence policy, source-block list, dual coordinate fields, and policy-aware span-resolution gate. | M3 consumes chapter-local coordinates; M4 and all consumers use the shared policy/list. |
| [#144](https://github.com/yshe0376/cs30-personalised-rag/pull/144) | `leahwang126` | Merged | Publishes clean M3 Gold v0.1.1 with self-reported `content_type` removed, complete corpus identity, and updated validation/provenance files. | M4 uses the normalised Gold for mapping; M3 remains responsible for future Gold and Role-label versions. |
| [#145](https://github.com/yshe0376/cs30-personalised-rag/pull/145) | `yshe0376` | Merged | Makes prepared corpus files byte-stable across Windows and Linux by writing all three files as bytes. | Rebuild downstream checksums from the resulting prepared outputs. |
| [#146](https://github.com/yshe0376/cs30-personalised-rag/pull/146) | `yshe0376` | Merged | Adds the real `cs30-build`/`cs30.build` entry point and saved FAISS/metadata artifacts. | Use the official candidate for the frozen W5 mapping; do not present `main` or S1-S6 as the official W5 build. |
| [#147](https://github.com/yshe0376/cs30-personalised-rag/pull/147) | `novel-peng` | Merged | Adds M4's `official.py` and imports the shared evidence policy without changing the official content tuple. | The official configuration is the only current W5 chunking path for reportable evaluation. |
| [#148](https://github.com/yshe0376/cs30-personalised-rag/pull/148) | `novel-peng` | Merged | Completes the M4 W5 hand-off with strict mapping, exact source-block-set validation, build commands, and 20/20 Gold coverage. | M5 rebuilds the index from the delivered records; M6 uses that index for retrieval. |
| [#149](https://github.com/yshe0376/cs30-personalised-rag/pull/149) | `yshe0376` | Merged | Makes the frozen `official` chunk candidate the default for `cs30-build`; keeps other candidates reachable for local checks. | Use `official` for v1.0 evaluation; S1-S6 remain out of scope for the present design. |
| [#150](https://github.com/yshe0376/cs30-personalised-rag/pull/150) | `Ntan0927` | Merged | Rebuilds M5 FAISS indexes from the latest 3,684-chunk corpus and adds BGE-M3. | M6 uses the identity-matched BGE-M3 or approved index for retrieval evaluation. |
| [#151](https://github.com/yshe0376/cs30-personalised-rag/pull/151) | `yshe0376` | Merged | Commits the corpus-bound Gold and mapping inputs required by scoring and ignores release archives. | M1/M8 use the paired inputs; M3 review status still controls formal reportability. |
| [#152](https://github.com/yshe0376/cs30-personalised-rag/pull/152) | `ZOEY-YUNYI` | Merged | Adds formal reporting, provenance receipts, blind-rating inputs, and fail-closed comparison checks. | M8 consumes reviewed Gold, complete role labels, and bound run artifacts for formal reports. |
| [#153](https://github.com/yshe0376/cs30-personalised-rag/pull/153) | `syj-111-s` | Merged | Delivers the reproducible M6 W5 retrieval notebook with BGE-M3 Hybrid 25/75 and frozen parameters. | M1/M8 consume the identity-validated retrieval results and metrics. |
| [#154](https://github.com/yshe0376/cs30-personalised-rag/pull/154) | `syj-111-s` | Merged | Replaces the invalid internal-hash comparison with corpus and record-count identity checks. | Preserve artifact identity fields in future M6 runs and notebooks. |
| [#155](https://github.com/yshe0376/cs30-personalised-rag/pull/155) | `yshe0376` | Closed | Placeholder v2 multi-textbook M1 attempt; superseded by the isolated v2 foundation work in #162. | Do not treat this branch as delivered; use #162 for the v2 M1 base. |
| [#156](https://github.com/yshe0376/cs30-personalised-rag/pull/156) | `skyshylsylsy` | Merged | Adds formal λ selection and the four personalisation conditions using the M3/M8 Role-label manifest. | Formal λ conclusions wait for complete candidate-pool labels and approved v2 evaluation inputs. |
| [#157](https://github.com/yshe0376/cs30-personalised-rag/pull/157) | `leahwang126` | Merged | Publishes the M3 Role-label package and mapping contract. | M7 consumes the versioned manifest; M3 owns taxonomy, labels, and future coverage. |
| [#158](https://github.com/yshe0376/cs30-personalised-rag/pull/158) | `yshe0376` | Merged | Enforces LF checkout for JSON/JSONL and adds Windows CI coverage. | Keep cross-platform byte identity in all provenance and hashed artifacts. |
| [#159](https://github.com/yshe0376/cs30-personalised-rag/pull/159) | `yshe0376` | Merged | Marks Gold reviewed, finalises `split-v1` at 12 Dev / 8 Test, and enables reportable v1.0 retrieval evaluation. | Use the frozen reviewed Gold and split for v1.0; keep role-label limits explicit. |
| [#160](https://github.com/yshe0376/cs30-personalised-rag/pull/160) | `yshe0376` | Merged | Cuts `release/1.0.0`, sets version `1.0.0`, and runs CI on release branches. | Stabilise v1.0 fixes on the release branch and merge them back carefully. |
| [#161](https://github.com/yshe0376/cs30-personalised-rag/pull/161) | `yshe0376` | Merged | Starts v2.0 development on `main` and records the v1.0 branch/scope model. | Keep v1.0 on `release/1.0.0`; develop multi-textbook and Concept Check work on `main`. |
| [#162](https://github.com/yshe0376/cs30-personalised-rag/pull/162) | `yshe0376` | Merged | Adds v2 M1 foundations for three OpenStax books, PDF ingestion, FAISS building, source installation, and provenance gates. | M4 must provide the production chunker; the CK-12 provider gate and v2 build gates remain open. |
| [#163](https://github.com/yshe0376/cs30-personalised-rag/pull/163) | `yshe0376` | Merged | Publishes the Concept Check design and v2 decisions of record. | M7/M3/M8 implement the staged runtime and data contracts. |
| [#164](https://github.com/yshe0376/cs30-personalised-rag/pull/164) | `yshe0376` | Open | Adds Phase 1 Concept Check runtime contracts, topic/citation fail-closed seams, and snapshot logic. All five CI checks pass. | Review/merge after contract review; deferred event store, leakage gate, reviewed fixtures, full reachability, LLM fallback, and UI work remain. |

### Current decision recorded for PR #137 and its replacements

PR #137 was withdrawn and closed without merge on 2026-09-14. Its widened-filter experiment and 17-question partial mapping are historical and must not be treated as delivered `main` functionality.

The current official path is the merged sequence #143, #144, #145, #147, and #148. M3 v0.1.1 replaced the three out-of-policy Gold spans with eligible body/equation evidence, so the official M4 hand-off now reports 20 questions, 21 spans, and 20/20 question coverage. The shared policy remains the single definition used by the source-block list and `official.py`.

The current design does not run S1-S6 chunking ablation. `official` is the frozen reportable configuration; `main` and S1-S6 remain reachable only for local checks or future explicitly versioned work. The present project also does not require M6 or M8 to review, double-label, or calculate IAA for Evidence Role. M3 owns the taxonomy and labels; M8 checks only provenance and format.

### Current v1.0/v2.0 release boundary

PRs #159-#161 establish the current release model. v1.0 is stabilised on `release/1.0.0` with one textbook, 20 reviewed Gold records, `split-v1` (12 Dev / 8 Test), and reportable retrieval/answer evaluation. Formal personalisation/λ conclusions remain outside the v1.0 scope because Role labels cover Gold chunks rather than the complete candidate pool. `main` is now the v2.0 development line at `2.0.0.dev0`.

PRs #162-#164 establish the v2 foundation: three pinned OpenStax books, a required-but-not-yet-selected CK-12 provider, the `gte-modernbert-base` chunk ruler, stable evidence anchors, Concept Check design, and Phase 1 runtime contracts. The v2 build is not yet an official multi-provider release; the CK-12 gate, production M4 chunking, event store, leakage registry, reviewed fixtures, and UI remain open follow-ups.

## 2. Contributor overview

| GitHub account | PRs | Primary ownership shown by the PR history |
|---|---:|---|
| [yshe0376](https://github.com/yshe0376) | 32 | Shared framework, contracts, Pipeline integration, CI, configuration, project documentation, M1 evaluation infrastructure, evidence-policy/build integration, release management, and v2 foundations |
| [novel-peng](https://github.com/novel-peng) | 6 | M4 structure-aware chunking, corpus construction, trace-back, Gold-to-chunk mapping, and official strategy delivery |
| [chongshao223](https://github.com/chongshao223) | 4 | M2 OpenStax College Physics parser iterations and final parser delivery |
| [leahwang126](https://github.com/leahwang126) | 4 | M3 SciQ questions, Gold Evidence data, Gold v0.1.1 hand-off, and Role labels |
| [skyshylsylsy](https://github.com/skyshylsylsy) | 3 | M7 personalised generation, evidence consumption, reranking, and λ selection |
| [ZOEY-YUNYI](https://github.com/ZOEY-YUNYI) | 3 | M8 evidence governance, citation validation, UI, answer/citation evaluation, and formal reporting |
| [Ntan0927](https://github.com/Ntan0927) | 2 | M5 FAISS vector-index construction, persistence, and embedding comparison |
| [syj-111-s](https://github.com/syj-111-s) | 3 | M6 Dense, BM25, RRF Hybrid retrieval, and W5 retrieval evaluation |

Closed, unmerged PRs are included in the counts so attempted work and superseded submissions remain visible. They are not counted as delivered `main`-branch functionality.

## 3. PR index

| PR | Author | State | Delivery / outcome |
|---:|---|---|---|
| [#1](https://github.com/yshe0376/cs30-personalised-rag/pull/1) | `yshe0376` | Merged | Week 1 modular framework, contracts, Protocols, Pipeline, fixtures, CI, and core documentation |
| [#2](https://github.com/yshe0376/cs30-personalised-rag/pull/2) | `yshe0376` | Merged | Removed planning documents from Git tracking; later partly reversed by #104 |
| [#3](https://github.com/yshe0376/cs30-personalised-rag/pull/3) | `yshe0376` | Merged | Added structured text blocks and separated cited text from embedding text |
| [#4](https://github.com/yshe0376/cs30-personalised-rag/pull/4) | `novel-peng` | Closed | Test-only chunking upload, superseded by #5 |
| [#5](https://github.com/yshe0376/cs30-personalised-rag/pull/5) | `novel-peng` | Merged | Structure-aware chunking and diagnostics |
| [#6](https://github.com/yshe0376/cs30-personalised-rag/pull/6) | `leahwang126` | Merged | SciQ and free-form demo questions |
| [#7](https://github.com/yshe0376/cs30-personalised-rag/pull/7) | `skyshylsylsy` | Merged | Personalised prompting, Ollama/OpenAI generation, citations, and abstention |
| [#8](https://github.com/yshe0376/cs30-personalised-rag/pull/8) | `Ntan0927` | Merged | FAISS index construction, persistence, and loading |
| [#90](https://github.com/yshe0376/cs30-personalised-rag/pull/90) | `yshe0376` | Merged | Retrieval contracts and provenance identities |
| [#91](https://github.com/yshe0376/cs30-personalised-rag/pull/91) | `yshe0376` | Merged | Fixed eager optional-dependency loading in the indexing package |
| [#92](https://github.com/yshe0376/cs30-personalised-rag/pull/92) | `novel-peng` | Merged | Reproducible M4 corpus hand-off and small-to-big trace-back |
| [#93](https://github.com/yshe0376/cs30-personalised-rag/pull/93) | `chongshao223` | Closed | First parser upload, superseded by #96 |
| [#94](https://github.com/yshe0376/cs30-personalised-rag/pull/94) | `chongshao223` | Closed | Second parser upload, superseded by #96 |
| [#95](https://github.com/yshe0376/cs30-personalised-rag/pull/95) | `chongshao223` | Closed | Parser interface revision, superseded by #96 |
| [#96](https://github.com/yshe0376/cs30-personalised-rag/pull/96) | `chongshao223` | Merged | Final M2 OpenStax College Physics 2e parser |
| [#97](https://github.com/yshe0376/cs30-personalised-rag/pull/97) | `ZOEY-YUNYI` | Merged | Evidence governance, citation validation, tracing, and Streamlit UI |
| [#98](https://github.com/yshe0376/cs30-personalised-rag/pull/98) | `yshe0376` | Merged | Fixed parser entry point, dependencies, and run instructions |
| [#101](https://github.com/yshe0376/cs30-personalised-rag/pull/101) | `syj-111-s` | Merged | Dense, BM25, and RRF Hybrid retrieval |
| [#102](https://github.com/yshe0376/cs30-personalised-rag/pull/102) | `yshe0376` | Closed | Proposed real-retrieval CI gate; not merged |
| [#103](https://github.com/yshe0376/cs30-personalised-rag/pull/103) | `yshe0376` | Merged | Added the missing EvidenceBundle contract decision record |
| [#104](https://github.com/yshe0376/cs30-personalised-rag/pull/104) | `yshe0376` | Merged | Restored the shared project decision log and corrected stale planning content |
| [#105](https://github.com/yshe0376/cs30-personalised-rag/pull/105) | `yshe0376` | Merged | Prevented unrelated profile fields from silently changing prompts |
| [#106](https://github.com/yshe0376/cs30-personalised-rag/pull/106) | `yshe0376` | Merged | Published the shared optimisation checklist and project backlog |
| [#107](https://github.com/yshe0376/cs30-personalised-rag/pull/107) | `yshe0376` | Merged | Added configuration-reachability tests and the BM25 stopword switch |
| [#115](https://github.com/yshe0376/cs30-personalised-rag/pull/115) | `skyshylsylsy` | Merged | Four-condition W5 personalisation and real generation; formal personalisation limits remain explicit |
| [#133](https://github.com/yshe0376/cs30-personalised-rag/pull/133) | `yshe0376` | Closed draft | Broad evaluation/build proposal split into smaller PRs; not merged wholesale |
| [#134](https://github.com/yshe0376/cs30-personalised-rag/pull/134) | `yshe0376` | Merged | Provider-neutral textbook interface and catalogue |
| [#135](https://github.com/yshe0376/cs30-personalised-rag/pull/135) | `leahwang126` | Merged | M3 Gold Evidence v0.1 and validation material |
| [#136](https://github.com/yshe0376/cs30-personalised-rag/pull/136) | `yshe0376` | Merged | Corpus-bound Gold normalisation, evaluation runner, and retrieval scoring |
| [#137](https://github.com/yshe0376/cs30-personalised-rag/pull/137) | `novel-peng` | Closed draft | Official 34-chapter M4 corpus and audited 17-question partial Gold mapping; leakage rejected, three spans returned to M3; withdrawn before merge |
| [#138](https://github.com/yshe0376/cs30-personalised-rag/pull/138) | `ZOEY-YUNYI` | Merged | Cause-aware answer, abstention, format, and citation scoring |
| [#139](https://github.com/yshe0376/cs30-personalised-rag/pull/139) | `yshe0376` | Merged | Publishes the living PR change and integration ledger |
| [#140](https://github.com/yshe0376/cs30-personalised-rag/pull/140) | `yshe0376` | Merged | Freezes the W5 retrieval evidence filter and records its evaluation-leakage rationale |
| [#141](https://github.com/yshe0376/cs30-personalised-rag/pull/141) | `yshe0376` | Merged | Synchronises the living ledger with the closed #137 state and latest PR history |
| [#142](https://github.com/yshe0376/cs30-personalised-rag/pull/142) | `yshe0376` | Merged | Updates the ledger after the PR #137 withdrawal and the subsequent M1-M4 hand-offs |
| [#143](https://github.com/yshe0376/cs30-personalised-rag/pull/143) | `yshe0376` | Merged | Shared evidence policy, source-block list, dual coordinates, and policy-aware span resolution |
| [#144](https://github.com/yshe0376/cs30-personalised-rag/pull/144) | `leahwang126` | Merged | Clean M3 Gold v0.1.1 hand-off and corpus-bound validation/provenance files |
| [#145](https://github.com/yshe0376/cs30-personalised-rag/pull/145) | `yshe0376` | Merged | Cross-platform byte-stable prepared corpus files and reproducibility checks |
| [#146](https://github.com/yshe0376/cs30-personalised-rag/pull/146) | `yshe0376` | Merged | Real `cs30-build` entry point and saved FAISS/metadata artifacts |
| [#147](https://github.com/yshe0376/cs30-personalised-rag/pull/147) | `novel-peng` | Merged | M4 official strategy using the shared evidence policy |
| [#148](https://github.com/yshe0376/cs30-personalised-rag/pull/148) | `novel-peng` | Merged | Strict M4 Gold mapping, source-block-set validation, and completed W5 hand-off |
| [#149](https://github.com/yshe0376/cs30-personalised-rag/pull/149) | `yshe0376` | Merged | Makes the frozen `official` candidate the default for `cs30-build` |
| [#150](https://github.com/yshe0376/cs30-personalised-rag/pull/150) | `Ntan0927` | Merged | Rebuilds M5 indexes for the latest corpus and adds BGE-M3 |
| [#151](https://github.com/yshe0376/cs30-personalised-rag/pull/151) | `yshe0376` | Merged | Commits corpus-bound evaluation inputs and ignores release archives |
| [#152](https://github.com/yshe0376/cs30-personalised-rag/pull/152) | `ZOEY-YUNYI` | Merged | Adds formal evaluation reporting and provenance checks |
| [#153](https://github.com/yshe0376/cs30-personalised-rag/pull/153) | `syj-111-s` | Merged | M6 W5 retrieval evaluation notebook and frozen BGE-M3 Hybrid settings |
| [#154](https://github.com/yshe0376/cs30-personalised-rag/pull/154) | `syj-111-s` | Merged | Fixes M6 artifact identity validation |
| [#155](https://github.com/yshe0376/cs30-personalised-rag/pull/155) | `yshe0376` | Closed | Placeholder v2 M1 three-textbook attempt, superseded by #162 |
| [#156](https://github.com/yshe0376/cs30-personalised-rag/pull/156) | `skyshylsylsy` | Merged | Formal λ selection and four-condition personalisation workflow |
| [#157](https://github.com/yshe0376/cs30-personalised-rag/pull/157) | `leahwang126` | Merged | M3 Role-label package and mapping contract |
| [#158](https://github.com/yshe0376/cs30-personalised-rag/pull/158) | `yshe0376` | Merged | Windows LF checkout rules and Windows CI coverage |
| [#159](https://github.com/yshe0376/cs30-personalised-rag/pull/159) | `yshe0376` | Merged | Reviewed Gold status and final 12/8 Dev/Test split |
| [#160](https://github.com/yshe0376/cs30-personalised-rag/pull/160) | `yshe0376` | Merged | v1.0 release branch and release-branch CI |
| [#161](https://github.com/yshe0376/cs30-personalised-rag/pull/161) | `yshe0376` | Merged | v2.0 mainline branch model and v1.0 scope record |
| [#162](https://github.com/yshe0376/cs30-personalised-rag/pull/162) | `yshe0376` | Merged | v2 M1 three-OpenStax foundation and build gates |
| [#163](https://github.com/yshe0376/cs30-personalised-rag/pull/163) | `yshe0376` | Merged | Concept Check design and v2 decisions of record |
| [#164](https://github.com/yshe0376/cs30-personalised-rag/pull/164) | `yshe0376` | Open | Phase 1 Concept Check runtime contracts |

## 4. Detailed change ledger

### PR #1 — Week 1 modular framework

- **Owner:** `yshe0376`
- **Delivered:** Shared Pydantic contracts, seven Protocol boundaries, configuration, fixture adapters, offline/online Pipelines, typed errors, logging, abstention, citation-integrity checks, CI, and architecture documentation.
- **Problem and resolution:** The project had no stable seams for parallel module work. This PR established dependency-injected boundaries. No material review defect is recorded in this ledger.
- **Interface hand-off:** Produces the shared contracts and `ports.py` interfaces consumed by M2-M8. Shared-contract and Pipeline integration ownership remains with `yshe0376`.
- **Verification/outcome:** Merged on 2026-08-24. The PR explicitly limited its claims to framework and fixture behaviour, not real parser, retrieval, model, or UI quality.

### PR #2 — Keep planning documents out of GitHub

- **Owner:** `yshe0376`
- **Delivered:** Removed five planning/reporting documents from tracking and added ignore rules while preserving local copies.
- **Problem and resolution:** This made the project decision log unavailable to contributors after clone. PR #104 later reversed this decision for the decision log only; the other private/local documents remained excluded.
- **Interface hand-off:** Documentation-governance change; no runtime interface changed. Project documentation ownership remains with the integration lead.
- **Verification/outcome:** Merged on 2026-08-24; partially superseded by #104.

### PR #3 — Structured text and citation-safe embedding contracts

- **Owner:** `yshe0376`
- **Delivered:** Added `TextBlock`, `ContentType`, and `Chunk.embed_text`; retained canonical character spans and required cited text to remain present verbatim in embedding input.
- **Problem and resolution:** The previous document boundary discarded section, page, equation, and exercise structure, forcing M4 to rediscover it. The new contract preserved parser structure and rejected invalid or cross-chapter spans.
- **Interface hand-off:** M2 produces structured blocks; M4 consumes them; M5 embeds `Chunk.embedding_input`; M8 cites the unchanged `Chunk.text`.
- **Verification/outcome:** Merged on 2026-08-25. The project intentionally gave up a fixed-window-only baseline in favour of structure-aware candidates.

### PR #4 — Initial chunking test upload

- **Owner:** `novel-peng`
- **Delivered:** A first upload of `tests/test_real_chunker.py`.
- **Problem and resolution:** The test was separated from its implementation. The author closed the PR and moved both implementation and tests into the coherent PR #5.
- **Interface hand-off:** None from this PR because it was not merged.
- **Verification/outcome:** Closed without merge; superseded by #5.

### PR #5 — Structure-aware chunking

- **Owner:** `novel-peng`
- **Delivered:** `BlockAwareChunker`, chunking strategy validation, diagnostics, oversized-block handling, duplicate checks, and source span/chapter/section/page traceability.
- **Problem and resolution:** Raw fixed-window chunking could lose parser structure. Grouping whole `TextBlock` boundaries solved the traceability problem while retaining size constraints.
- **Interface hand-off:** Consumes M2 `TextbookDocument`/`TextBlock`; produces `Chunk` records for M5 indexing and M6 retrieval.
- **Verification/outcome:** Merged on 2026-08-26 with boundary and diagnostic tests.

### PR #6 — SciQ demo questions

- **Owner:** `leahwang126`
- **Delivered:** 24 multiple-choice SciQ Physics questions, 8 free-form questions, and a stable `DemoQuestionProvider`.
- **Problem and resolution:** No material implementation problem is recorded. The key limitation is scope: the records are smoke/demo inputs, not the formal evaluation set.
- **Interface hand-off:** M3 provides stable question IDs to Pipeline/demo consumers; formal Gold evidence follows separately in #135.
- **Verification/outcome:** Merged on 2026-08-27.

### PR #7 — Personalised local RAG generation

- **Owner:** `skyshylsylsy`
- **Delivered:** Beginner/intermediate/advanced prompting, Ollama and OpenAI generators, evidence retrieval inside the generation module, grounded citations, and no-evidence abstention.
- **Problem and resolution:** The initial implementation needed to coexist with M3 questions and the future M6 boundary. It preserved the question fixture contract and isolated its combined-evidence retriever under generation.
- **Known limitation:** Real mode still used fixture-labelled smoke evidence and could not support claims about retrieval or model effectiveness. PR #115 is the W5 follow-up.
- **Interface hand-off:** Consumes `StudentProfile`, questions, and retrieval evidence; produces generated answers and traces for M8 validation/evaluation.
- **Verification/outcome:** Merged on 2026-09-02; citation, retry, missing-data, and abstention paths were covered.

### PR #8 — FAISS index

- **Owner:** `Ntan0927`
- **Delivered:** Embedding dependencies, FAISS index construction, artifact persistence/loading, and index tests.
- **Problem and resolution:** The eager public export later caused core-only installations to import optional ML dependencies. PR #91 fixed that package-boundary issue without changing the public name.
- **Interface hand-off:** Consumes M4 chunks; produces `IndexArtifact`, FAISS vectors, and chunk-map data for M6 Dense retrieval.
- **Verification/outcome:** Merged on 2026-09-03. The final merge check included a smoke failure later addressed by #91.

### PR #90 — Retrieval contracts and identities

- **Owner:** `yshe0376`
- **Delivered:** Froze `RetrievalMode`, `EvidenceProvenance`, `RetrievedEvidence`, and `RetrievalService`; retained `RetrievalHit` as a compatibility alias.
- **Problem and resolution:** Retrieval modes and provenance did not have a stable shared seam. This PR added validation and typed errors while deliberately leaving adapter implementations to M6.
- **Interface hand-off:** M6 implements `RetrievalService`; Pipeline and M7 consume `RetrievedEvidence`; M8 relies on provenance fields for citation checks.
- **Verification/outcome:** Merged on 2026-09-02 with fixture and contract tests.

### PR #91 — Lazy FAISS export

- **Owner:** `yshe0376`
- **Delivered:** Replaced eager `FaissIndexBuilder` import with lazy package export.
- **Problem and resolution:** A core-only installation could not import `cs30.pipeline` because importing indexing pulled in `sentence_transformers`. The failure now occurs only when FAISS functionality is actually requested, with the missing optional package identified.
- **Interface hand-off:** Preserved the M5 public import while restoring the core Pipeline/fixture path.
- **Verification/outcome:** Merged on 2026-09-03; parser/index behaviour was unchanged.

### PR #92 — Split-ready chunking and unified corpus hand-off

- **Owner:** `novel-peng`
- **Delivered:** Content-type filtering, six reproducible S1-S6 candidates, parent section/chapter trace-back, deterministic corpus export, and one shared Dense/BM25 retrieval corpus.
- **Problems and resolution:** Review fixes added pre-write mixed-configuration rejection, fail-fast trace-back, a real build script, blank-line handling, provenance-based cross-chapter counts, canonical filter identity, and an explicit M4-to-M5/M6 metadata seam.
- **Deferred:** Optional parent-block indexing and a sampling-helper refactor were intentionally left out.
- **Interface hand-off:** M4 produces corpus records/manifests; M5 indexes them; M6 must use the same chunk map and identity.
- **Verification/outcome:** Merged on 2026-09-05 after 117 tests, Ruff, three-chapter regeneration, and byte-identical rebuild evidence reported in the PR.

### PR #93 — First parser upload

- **Owner:** `chongshao223`
- **Delivered:** First upload of OpenStax parser files and documentation.
- **Problem and resolution:** The submission was not accepted as the final parser. Work continued through #94 and #95 and was consolidated in #96.
- **Interface hand-off:** None from this PR because it was not merged.
- **Verification/outcome:** Closed without merge.

### PR #94 — Second parser upload

- **Owner:** `chongshao223`
- **Delivered:** A second revision of the same parser files.
- **Problem and resolution:** This upload still did not become the accepted integration. It was superseded by #96.
- **Interface hand-off:** None from this PR because it was not merged.
- **Verification/outcome:** Closed without merge.

### PR #95 — Parser interface revision attempt

- **Owner:** `chongshao223`
- **Delivered:** Revised parser command/interface code under “fix cl error and interface”.
- **Problem and resolution:** The branch was replaced by the final integration PR #96.
- **Interface hand-off:** None from this PR because it was not merged.
- **Verification/outcome:** Closed without merge.

### PR #96 — Final M2 OpenStax parser

- **Owner:** `chongshao223`
- **Delivered:** OpenStax College Physics 2e parsing, PDF-outline chapter/section boundaries, Tagged-PDF `alt_text` equation recovery, contract JSON, JSONL blocks, QA reports, metadata, and manifests.
- **Problem and resolution:** The final parser logic merged, but packaging and run instructions still had loose ends. PR #98 fixed the import path, dependency declarations, entry point, and README commands.
- **Interface hand-off:** M2 produces the canonical document and blocks consumed by M4. Character offsets remain relative to the complete document text.
- **Verification/outcome:** Merged on 2026-09-04; operational fixes followed in #98.

### PR #97 — Evidence governance and Streamlit UI

- **Owner:** `ZOEY-YUNYI` (`yzho0933`)
- **Delivered:** `EvidenceItem`, `EvidenceBundle`, `ValidatedAnswer`, token-budgeted context assembly, stable evidence IDs, deduplication, citation resolution/validation, trace enrichment, Streamlit UI, fallback mode, and runbooks.
- **Problems and resolution:** The PR preserved the legacy generation entry point for compatibility. Its contract rationale was missing from the ADR and was added by #103. Native generation consumption and Pipeline switching continued in #115.
- **Known limitation:** The staging demo used fixture retrieval and did not establish real retrieval or model effectiveness.
- **Interface hand-off:** M6 supplies retrieval results; M8 builds governed evidence; M7 consumes the bundle; Pipeline integration is shared with `yshe0376`.
- **Verification/outcome:** Merged on 2026-09-05 with success/failure citation tests and an EvidenceBundle fixture.

### PR #98 — Parser entry point and dependency fix

- **Owner:** `yshe0376`
- **Delivered:** Importable parser package, `cs30-parse-openstax`, `parse` optional dependencies, and corrected README commands/imports.
- **Problem and resolution:** PR #96 referenced a nonexistent `requirements.txt`, used an invalid top-level import, and relied on an unstated working directory. This PR corrected those operational faults without changing parser behaviour.
- **Interface hand-off:** Restored a usable M2 command-line entry point for M4 corpus production.
- **Verification/outcome:** Merged on 2026-09-04.

### PR #101 — Dense, BM25, and RRF Hybrid retrieval

- **Owner:** `syj-111-s`
- **Delivered:** FAISS Dense retrieval, BM25, RRF Hybrid fusion, query caching, artifact loading, thresholds, and Pipeline wiring.
- **Problems and resolution:** BM25 could match out-of-scope questions through stopwords, and configuration fields could exist without reaching retriever constructors. #107 later made stopword filtering configurable and added reachability/behaviour tests. #102 separately proposed a stronger real-mode CI gate but was not merged.
- **Interface hand-off:** Consumes M5 artifacts and M4 chunk metadata; implements the #90 retrieval seam; provides results to EvidenceBundle/M7 and saved runs to M1/M8.
- **Verification/outcome:** Merged on 2026-09-05 with retrieval, abstention, and fixture tests.

### PR #102 — Proposed real-retrieval CI gate

- **Owner:** `yshe0376`
- **Delivered on branch:** A core-only BM25 fixture gate requiring an out-of-scope query to return no evidence and an in-scope query to return grounded evidence.
- **Problem and resolution:** Existing smoke assertions exercised fixture mode rather than a real index, so CI could remain green while BM25 failed abstention. This PR demonstrated the gap but was closed without merge. Configuration and stopword controls were later strengthened in #107; this exact gate is not attributed to `main` through #102.
- **Interface hand-off:** Proposed a quality gate across M5 artifacts, M6 retrieval, and Pipeline citation behaviour.
- **Verification/outcome:** Closed without merge on 2026-09-04.

### PR #103 — EvidenceBundle ADR

- **Owner:** `yshe0376`
- **Delivered:** Recorded the #97 contract revision, citation-ID choice, token-budget semantics, schema-version decision, compatibility cost, and intentionally empty fields.
- **Problem and resolution:** #97 changed shared contracts without the required ADR entry. This documentation-only PR closed that governance gap.
- **Interface hand-off:** Gives M7, M8, and future contract maintainers the rationale needed to evolve EvidenceBundle safely.
- **Verification/outcome:** Merged on 2026-09-05; no code or fixture changes.

### PR #104 — Shared project decision log

- **Owner:** `yshe0376`
- **Delivered:** Restored the repository's shared project decision log, removed personal scheduling details, and corrected stale decisions about chunking, FAISS, evaluation, embeddings, and personalisation.
- **Problem and resolution:** The decision log named by project instructions was hidden by #2, so contributors could not access it. This PR restored only the project-relevant log and kept unrelated/private documents excluded.
- **Interface hand-off:** Shared decision record for all module owners; no runtime contract changed.
- **Verification/outcome:** Merged on 2026-09-05.

### PR #105 — Explicit prompt profile fields

- **Owner:** `yshe0376`
- **Delivered:** Added `PROMPT_PROFILE_FIELDS` and golden prompt/hash tests.
- **Problem and resolution:** Serialising the whole `StudentProfile` meant a future timestamp or persistence field could silently alter model input. The fixed allow-list now makes a contract addition fail visibly until prompt impact is reviewed.
- **Interface hand-off:** M5/profile owners may extend `StudentProfile`; M7 prompt owners must explicitly decide whether each new field belongs in model input.
- **Verification/outcome:** Merged on 2026-09-05; current prompt bytes remained unchanged.

### PR #106 — Published optimisation checklist and backlog

- **Owner:** `yshe0376`
- **Delivered:** Moved retrieval documents to the correct location, published the shared RAG knob checklist and project backlog, renamed the outdated week-specific backlog, and repaired links.
- **Problem and resolution:** Ignored project-level documents caused another contributor to create conflicting module-local copies. Publishing one canonical set removed the ownership and merge ambiguity.
- **Interface hand-off:** Shared experiment and dependency planning for M1-M8; no runtime interface changed.
- **Verification/outcome:** Merged on 2026-09-05.

### PR #107 — Retrieval configuration reachability

- **Owner:** `yshe0376`
- **Delivered:** A registry/meta-test for every `RetrievalConfig` field, constructor wiring checks, behaviour checks, and `retrieval.bm25_stopwords` / `CS30_BM25_STOPWORDS`.
- **Problem and resolution:** `bm25_min_score` and `dense_min_similarity` had previously validated but did not reach the real retrievers. BM25 stopword filtering also could not be changed for ablation. The new tests fail when a field is unwired or behaviour does not change.
- **Interface hand-off:** Configuration owner defines knobs; M6 must register and wire each retrieval knob; M1 can now treat the settings as real experimental variables.
- **Verification/outcome:** Merged on 2026-09-05.

### PR #115 — W5 four-condition personalisation and real generation

- **Owner:** `skyshylsylsy`
- **Delivered:** `P0R0_plain`, `P1R0_prompt_only`, `P0R1_reranking_only`, and `P1R1_combined`; level-aware soft reranking; native `EvidenceBundle` support; stable citations; raw provider-attempt traces; repair/failure distinctions; and Mock/Ollama/OpenAI demonstration paths.
- **Problem and current boundary:** No blocking review defect is recorded. The PR uses fixture Role labels because M3's taxonomy/versioned labels are not yet frozen, and `lambda_weight` remains an engineering fixture until selected on Dev data. The shared Pipeline still passes `RetrievalResult` despite native bundle support.
- **Interface hand-off:** M3 owns Evidence Role labels; M7 owns prompts/reranking/generation; the shared Pipeline owner must switch the call seam; M1/M8 own formal four-condition runs and scoring.
- **Verification/outcome:** The PR remains open as of 2026-09-16. Its recorded 339 local tests, four successful mock conditions, and four successful local Ollama conditions are engineering checks, not answer-quality or validated-personalisation results.

### PR #133 — Broad evaluation and multi-textbook build draft

- **Owner:** `yshe0376`
- **Delivered on branch:** Evaluation contracts, provider-neutral document naming, textbook catalogue, local-PDF build path, identity validation, truncation guards, cleanup, and real-build tests.
- **Problems and resolution:** Pre-landing review found silent embedding truncation, disconnected persisted evidence traces, arbitrary PDF-to-textbook labelling, and incomplete build cleanup; the branch added fixes. The broad PR was then closed and selected work was split: #134 delivered the textbook seam and #136 delivered evaluation. The `cs30-build` command from this draft is not present on `main` as of this ledger date.
- **Interface hand-off:** The surviving interface work moved to M2/#134 and M1/#136. Any future multi-textbook build command needs a new owned PR.
- **Verification/outcome:** Closed as a draft without merge on 2026-09-12; do not count the complete branch as delivered functionality.

### PR #134 — Provider-neutral textbook interface

- **Owner:** `yshe0376`
- **Delivered:** `TextbookSpec` catalogue metadata for OpenStax College Physics 2e and five CK-12 sources, plus `TextbookDocument`/`TextbookChapter` compatibility names.
- **Problem and resolution:** The ingestion seam was OpenStax-specific. Provider-neutral naming allows later CK-12 adapters without forcing downstream modules to depend on a provider-specific contract.
- **Scope boundary:** No CK-12 PDFs/parser, `cs30-build`, multi-textbook corpus, indexing change, or evaluation implementation was included.
- **Interface hand-off:** M2 owns source adapters and catalogue identity; M4 consumes provider-neutral documents without payload-schema or Pipeline changes.
- **Verification/outcome:** Merged on 2026-09-09.

### PR #135 — M3 Gold Evidence v0.1

- **Owner:** `leahwang126`
- **Delivered:** 20 `m3_initial` Gold records, JSON Schema, character-level validation, Dev/Test split plan, personalisation candidates, and an M3 manual-review record.
- **Problems and current boundary:** The original v0.1 history contains 20 records, all with `gold_answer=D` and `answerable=true`; that version alone cannot support a balanced answer or refusal evaluation. It was superseded by the clean v0.1.1 hand-off in #144. Evidence Role taxonomy and labels are now explicitly owned by M3, with no M6/M8 double-label or IAA track.
- **Interface hand-off:** M3 owns Gold and Role annotations; M4 maps spans to chunks; M1 normalises and validates them; M8 scores saved runs and checks Role-label provenance only.
- **Verification/outcome:** Merged on 2026-09-11. Current formal reporting still requires the expanded W6 Gold set, appropriate answerability coverage, final mapping, frozen index, and saved evaluation runs.

### PR #136 — Corpus-bound Gold and retrieval evaluation

- **Owner:** `yshe0376`
- **Delivered:** Evaluation v0.2 models, JSONL I/O, batch runner, retrieval-only dependency path, offline metrics, CLI, manifests, fixtures, corpus-bound Gold normalisation, and prompt/model provenance traces.
- **Problems and resolution:** The implementation added explicit stale/ambiguous classification, chapter/text consistency checks, no-overwrite protection, and a retrieval-only path that does not initialise an LLM. It preserved raw M3 data rather than overwriting it with normalised records.
- **Scope boundary:** The PR did not claim unreviewed M3 Gold was reportable and did not contain the real M4 mapping artifact. #137 contained a candidate M4 hand-off but was closed without merge, so no reportable mapping is delivered to `main` through #137.
- **Interface hand-off:** Consumes M3 Gold and M4 mapping; runs M6/M7; produces saved results and retrieval metrics consumed by M8.
- **Verification/outcome:** Merged on 2026-09-12.

### PR #137 — Official 34-chapter M4 corpus and Gold mapping

- **Owner:** `novel-peng`
- **Delivered on branch:** Reproducible 34-chapter corpus build, real all-MiniLM-L6-v2 tokenisation, corpus QA, source trace-back, duplicate provenance, identity guards, Gold normalisation, and an M1-compatible mapping candidate.
- **Initial problem:** M4 v1 excluded assessment-like `problem` blocks and `summary`, while three M3 Gold spans used exactly those types. It correctly failed closed at 17/20 and withheld the formal mapping instead of silently producing an incomplete artifact.
- **Resolution:** A widened v2 filter including `problem` and `summary` was published and then withdrawn. The original PR was closed without merge, and the implementation was replaced by the merged #147/#148 sequence. M3 v0.1.1 replaced the three out-of-policy spans with eligible body/equation evidence, so the current hand-off no longer depends on the partial 17-question mapping.
- **Downstream handling:** The partial mapping, widened-filter experiment, and its leakage discussion remain historical evidence only. They must not be used as the current M5/M6 input.
- **Interface hand-off:** The replacement M4 delivery consumes M1/M3's current contracts and produces the official corpus records, source-block-set validation, strict `GoldChunkMapping`, and build instructions for M5/M6.
- **Verification/outcome:** Closed as a draft without merge on 2026-09-14; `mergedAt` is null, so this PR delivered no functionality to `main`. The current official result is recorded under #148: 34 chapters, 23,378 eligible source blocks, 20 questions, 21 spans, and 20/20 question coverage. Do not reopen #137 as an implicit merge.

### PR #138 — Cause-aware answer, abstention, format, and citation scoring

- **Owner:** `ZOEY-YUNYI` (`yzho0933`)
- **Delivered:** Offline answer, abstention, raw/repaired format, citation, traceability, and Gold-coverage metrics; development/reportable modes; JSON/JSONL/CSV/Markdown reports; failure labels; and CLI integration.
- **Initial problem:** The first implementation did not read `abstention_cause`, so `no_retrieval_hits` and `model_abstained_with_evidence` could not be distinguished or attributed. Per-question reports also omitted the cause.
- **Resolution:** Commit `0303412` preserved the cause per question, added cause counts/confusion views, and separated system-level abstention from model-only abstention metrics. Commit `75ec759` aligned the remaining answer-scoring rules and tests with the review contract.
- **Interface hand-off:** Consumes M1 v0.2 run results, M3 answerability/answers, and M4 OR-of-AND mapping; produces auditable evaluation artifacts for experiment and report owners. It does not rerun retrieval or generation.
- **Verification/outcome:** Merged on 2026-09-13 after all four GitHub CI checks passed. The PR reports Ruff passing and 344 tests. Formal numbers still require frozen/reviewed Gold, a valid mapping, and reportable saved runs.

### PR #139 — Pull request change and integration ledger

- **Owner:** `yshe0376`
- **Delivered:** This English living ledger, initially a 32-PR index and now being synchronised to 57 PRs, with a current hand-off dashboard, contributor overview, interface ownership register, maintenance rules, and a README link.
- **Problem and resolution:** PR work, review findings, superseding changes, and downstream ownership were previously spread across PR pages and conversations. This PR consolidates them into one version-controlled reference. No material implementation issue is recorded.
- **Interface hand-off:** All module owners update their own PR facts; the shared integration/documentation owner maintains cross-module status and ownership links.
- **Verification/outcome:** Merged on 2026-09-13. Before creation, the branch passed 334 tests, Ruff, whitespace checks, relative-link checks, and a complete comparison against the pre-existing GitHub PR IDs. This self-entry was added after GitHub assigned PR #139; the ledger was subsequently extended through #164.

### PR #140 — Frozen W5 retrieval evidence policy

- **Owner:** `yshe0376`
- **Delivered:** The frozen W5 retrieval evidence filter and its evaluation-leakage rationale in `docs/interfaces.md` and `docs/构思与待定.md`.
- **Problem and resolution:** The repository needed one authoritative decision for which content types may enter retrieval. The PR records that `body`, `example`, `figure_caption`, `glossary`, `table`, and `equation` are included, while `conceptual_question`, `problem`, and `summary` remain excluded. It also records why textbook exercises and summaries must not be added merely to rescue provisional Gold spans.
- **Interface hand-off:** The policy constrains M4 corpus construction and M5 indexing; M3 owns Gold evidence and Role labels; M1/M8 consume the resulting mapping and report provenance and coverage explicitly.
- **Verification/outcome:** Merged on 2026-09-13. Documentation-only; Ruff and the full test suite passed on the branch.

### PR #141 — Synchronise the PR hand-off ledger

- **Owner:** `yshe0376`
- **Delivered:** Updated this ledger from 33 to 34 recorded PRs, corrected #137 from open draft to closed without merge, added #140 and #141 lifecycle records, and retained the commit-level audit for the recent M3-M8 hand-off chain.
- **Problem and resolution:** The live GitHub state changed after the previous ledger update: #137 was withdrawn without merge and #141 was merged. This PR synchronised the status totals, contributor count, index, detailed entries, and current hand-offs so the shared document does not describe #137 as delivered functionality.
- **Interface hand-off:** Documentation/integration ownership remains with `yshe0376`; module owners use the corrected #137 status and the M3/M4 follow-up recorded in the ledger.
- **Verification/outcome:** Merged on 2026-09-14. Documentation-only; the branch passed the local test suite, Ruff, and `git diff --check` before merge. The status and implementation details were subsequently superseded by #143-#149.

### PR #142 — Record PR #137 withdrawal and synchronise the ledger

- **Owner:** `yshe0376`
- **Delivered:** The original update corrected the #137 withdrawal, added the #141 lifecycle record, and repaired the related status tables. This follow-up synchronised the same ledger through #149 before the later v1.0/v2.0 updates in this file.
- **Problem and resolution:** The previous ledger stopped at 34 recorded PRs and retained stale descriptions of the withdrawn #137 partial mapping, M5 Role ownership, and the pre-#143 corpus path. The update replaced those statements with the merged #143/#144/#145/#147/#148 hand-off and the then-current #149 build-default PR.
- **Interface hand-off:** This is documentation only. It records M3 as the Evidence Role owner, M4 as the official chunk/mapping owner, M5 as the index owner, and M1/M8 as the evaluation consumers.
- **Verification/outcome:** Merged on 2026-09-19. The update was later extended in this same ledger to include PRs #150-#164 and the v1.0/v2.0 transition.

### PR #143 — Shared evidence source-block policy

- **Owner:** `yshe0376`
- **Delivered:** Added `cs30.evidence_policy`, the six eligible evidence content types, `evidence_source_blocks.jsonl`, dual chapter/corpus coordinates, manifest counts/digests, and the shared loader/policy gate.
- **Problem and resolution:** Gold annotation and M4 filtering previously used an implicit boundary, while a bare character offset could be interpreted as chapter-local or corpus-global. The source-block artifact now exposes the eligible list and both coordinate systems explicitly.
- **Interface hand-off:** M3 copies chapter-local coordinates from the source-block list; M4 imports the shared policy; normalisation derives corpus-global coordinates and records resolution status.
- **Verification/outcome:** Merged on 2026-09-14. The real 34-chapter check reported 35,905 blocks, 23,378 eligible blocks, 12,527 excluded blocks, zero coordinate/text mismatches, and byte-identical consecutive exports.

### PR #144 — Clean M3 Gold v0.1.1 hand-off

- **Owner:** `leahwang126`
- **Delivered:** Replaced superseded v0.1 Gold files with versioned v0.1.1 files, removed the Gold self-reported `content_type`, bound records to the full corpus identity, and updated Gold documentation, schemas, validation, and split/candidate filenames.
- **Problem and resolution:** The earlier Gold hand-off mixed an older version, incomplete corpus identity, and a redundant content-type assertion. v0.1.1 is now the current Gold hand-off used by M1 normalisation and M4 mapping.
- **Interface hand-off:** M3 supplies Gold spans and metadata; M1 normalises them; M4 maps the normalised spans; M8 consumes saved results and checks provenance.
- **Verification/outcome:** Merged on 2026-09-15. The v0.1.1 hand-off is the current W5 Gold source; W6 still requires expansion to 240 records and a documented answerability distribution.

### PR #145 — Cross-platform prepared-corpus bytes

- **Owner:** `yshe0376`
- **Delivered:** Changed prepared document, evidence-list, and manifest writes to byte-based output and extended reproducibility tests to cover all prepared files and line endings.
- **Problem and resolution:** Windows newline translation produced CRLF for two files and LF for the evidence list, making checksums depend on the operating system. All three prepared outputs are now written with stable bytes.
- **Interface hand-off:** M1's prepared-corpus artifacts are safe for cross-platform checksum verification; downstream M3/M4 checksum hand-offs must be regenerated from the resulting files.
- **Verification/outcome:** Merged on 2026-09-15. The PR reports LF-only, byte-identical repeated exports and an unchanged evidence-list digest.

### PR #146 — Real index-build entry point

- **Owner:** `yshe0376`
- **Delivered:** Added `cs30.build`/`cs30-build`, real-document adaptation for the existing build pipeline, saved `artifact.json`, `chunks.json`, and `index.faiss`, and reload verification through BM25.
- **Problem and resolution:** A prepared corpus could be normalised but there was no command that built a retrievable index, so the real evaluation chain stopped before retrieval. The new entry point closes that missing seam.
- **Interface hand-off:** M4 supplies the chunk source; M5 accepts the resulting index; M6 consumes the index for retrieval; M1/M8 consume saved run outputs.
- **Verification/outcome:** Merged on 2026-09-15. A three-chapter real build produced 237 chunks and a successful retrieval-to-citation smoke run. The PR also exposed that S2-S6 abort on duplicate filtered text; because the current design does not run S1-S6, this is out of scope for the official path.

### PR #147 — Official chunking strategy uses shared policy

- **Owner:** `novel-peng`
- **Delivered:** Added `src/cs30/chunking/official.py` and made the official strategy import `EVIDENCE_CONTENT_TYPES` from the shared policy module.
- **Problem and resolution:** The official chunker needed to use the same evidence boundary as M1 and M3 instead of carrying another hard-coded tuple. The content tuple and official configuration identity remain unchanged.
- **Interface hand-off:** M4's official strategy is the source for the frozen W5 chunk artifact; M5/M6 use the resulting chunks and M1/M8 use the resulting mapping.
- **Verification/outcome:** Merged on 2026-09-16. The PR changed one source file, added no generated data, and passed the reported full test and Ruff checks.

### PR #148 — Completed M4 W5 Gold hand-off

- **Owner:** `novel-peng`
- **Delivered:** Rebuilt the M4 delivery on current `main`, added strict `coverage_status` validation, consumed normalised Gold v0.2 derived from `m3_gold_v0.1.1`, validated the exact source-block set, and added reproducible build/mapping commands and tests.
- **Problem and resolution:** The withdrawn #137 branch had a partial mapping and stale alignment assumptions. #148 is the merged replacement and uses the clean v0.1.1 Gold plus the shared source-block list.
- **Interface hand-off:** M4 produces the authoritative W5 records, mapping, manifest, and source-block-set validation for M5/M6; M1/M8 consume mapping and provenance.
- **Verification/outcome:** Merged on 2026-09-16. The reported real-data result is 34 chapters, 23,378 eligible source blocks, exact source-block-set match, 20 questions, 21 spans, and zero excluded questions. No S1-S6 comparison work is included.

### PR #149 — Default `cs30-build` to the frozen official candidate

- **Owner:** `yshe0376`
- **Delivered:** Added an `official` build candidate resolving to the frozen M4 strategy and made it the default while keeping `main` and S1-S6 reachable for local checks.
- **Problem and resolution:** The previous default `main` candidate applied no evidence filter, so its chunk IDs did not correspond to M4's official mapping. The default now builds the same 3,684-chunk official set verified by the M4 delivery.
- **Interface hand-off:** M5 must build the index from the `official` output; M6 must retrieve from that index; M1/M8 must compare only identity-matched artifacts.
- **Verification/outcome:** Merged on 2026-09-16. The reported real-corpus check found identical chunk-ID sets between `cs30-build --candidate official` and the M4 build, with all 20 mapped chunks present. S1-S6 remain out of scope for the current design.

### PR #150 — M5 indexes for the latest corpus and BGE-M3

- **Owner:** `Ntan0927`
- **Delivered:** Rebuilt the MiniLM, MPNet, E5, BGE-base, and BGE-M3 FAISS indexes against the current 3,684-chunk M4 corpus, added low-memory embedding batches, and updated the model comparison report.
- **Problem and resolution:** The M4 corpus hash changed, so existing indexes were stale. E5 and BGE-base also reported 314 of 3,684 chunks above the effective 510-token limit; BGE-M3 completed without that warning and produced 1,024-dimensional embeddings. The PR rebuilt and reloaded the indexes without changing public contracts.
- **Interface hand-off:** M5 produces identity-matched indexes for M6 retrieval; M1/M8 consume the resulting artifact and run identities.
- **Verification/outcome:** Merged on 2026-09-18. All five indexes were built/reloaded according to the PR; no index or model artifacts were committed.

### PR #151 — Corpus-bound evaluation inputs and release-archive ignore

- **Owner:** `yshe0376`
- **Delivered:** Added the paired `eval_inputs/` Gold and mapping files required by `cs30-evaluate score` and ignored release `*.zip` archives.
- **Problem and resolution:** Scoring inputs existed only in chat transfer, so no contributor could reproduce a saved-run score. A root-level corpus archive could also be accidentally committed. The small corpus-bound inputs are now versioned together and the corpus remains a Release asset.
- **Interface hand-off:** M1/M8 consume the paired inputs; M3 owns the annotation status and future regeneration. The inherited `m3_initial` status was later corrected by #159.
- **Verification/outcome:** Merged on 2026-09-19. The PR verified 20 questions, 21 resolved spans, zero mapping exclusions, matching corpus/chunk/mapping identities, and complete chunk references.

### PR #152 — Formal evaluation reporting and provenance checks

- **Owner:** `ZOEY-YUNYI`
- **Delivered:** W6 reporting extension with explicit denominators/exclusions, blind-rating materials, compatible λ comparisons, role-label provenance checks, run/score SHA receipts, expected-experiment manifests, and Markdown/JSON/table reports.
- **Problem and resolution:** Formal reporting needed to fail closed on technical failures, incomplete rating files, wrong experiment cells, inconsistent role-label packages, or replaced/truncated score artifacts. The extension separates pending/incomplete development outputs from reportable results and verifies each artifact against its source run.
- **Interface hand-off:** M8 consumes M1 run manifests, M3 Gold/Role labels, M4 mapping, M5/M6 identities, and M7 outputs; it produces the formal report sidecars and client-readable report.
- **Verification/outcome:** Merged on 2026-09-18 with the reported 398-test suite and targeted integrity checks. Formal numbers still require eligible reviewed inputs.

### PR #153 — M6 W5 retrieval evaluation notebook

- **Owner:** `syj-111-s`
- **Delivered:** Reproducible BGE-M3 Hybrid retrieval notebook using weighted RRF with Dense 0.25, BM25 0.75, RRF `k=60`, 50 candidates per retriever, Top-K 5, Hit@K, Recall@K, and MRR.
- **Problem and resolution:** Retrieval evaluation needed fixed parameters, experiment signatures, cache validation, and chunk-configuration checks before results could be compared. The notebook freezes those inputs and rejects incompatible cached artifacts.
- **Interface hand-off:** M6 produces identity-validated retrieval metrics for M1/M8 and the final report.
- **Verification/outcome:** Merged on 2026-09-20. Ruff, the test suite, and the BGE-M3 25/75 configuration checks passed according to the PR.

### PR #154 — M6 artifact identity validation

- **Owner:** `syj-111-s`
- **Delivered:** Corrected M6 artifact compatibility checks and regenerated the W5 notebook.
- **Problem and resolution:** M6 compared an internal M5 chunk hash directly with the M4 Gold-mapping hash, although those hashes represent different identities. Validation now uses corpus ID and record count, while M6 manifests record the official M4 `chunk_config_hash`.
- **Interface hand-off:** M5/M4 identities remain distinct but explicitly bound; M6 passes the validated artifact identity to M1/M8.
- **Verification/outcome:** Merged on 2026-09-20; 424 tests and notebook regeneration were reported as passing.

### PR #155 — Superseded v2 three-textbook attempt

- **Owner:** `yshe0376`
- **Delivered on branch:** An initial v2 M1 multi-textbook attempt with no completed PR description or verification evidence.
- **Problem and resolution:** The branch was a placeholder and was closed without merge. The isolated, reviewed v2 foundation was rebuilt in #162.
- **Interface hand-off:** None from this PR; use #162 for the current v2 M1 contracts and build path.
- **Verification/outcome:** Closed without merge on 2026-09-21; not delivered functionality.

### PR #156 — Formal λ selection and four-condition personalisation

- **Owner:** `skyshylsylsy`
- **Delivered:** M7 λ selection, Role-label manifest loading, four conditions, candidate-pool guards, coverage reporting, split-manifest sizing, and byte-stable provisional outputs.
- **Problem and resolution:** M7 needed to consume the merged M3/M8 Role-label contract without relabelling data. The current 12-question run has labels for Gold chunks only (`10/55` unique chunks and `12/60` occurrences), so formal λ selection correctly refuses and provisional selection reports `not_interpretable` rather than making a false personalisation claim.
- **Interface hand-off:** M3 owns taxonomy and labels; M7 consumes them; M8 validates provenance; formal v2 evaluation still needs complete candidate-pool labels and an approved split.
- **Verification/outcome:** Merged on 2026-09-22. Full tests, Ruff, tamper checks, and repeated-output determinism were reported as passing.

### PR #157 — M3 Role-label package

- **Owner:** `leahwang126`
- **Delivered:** Versioned M3 Role-label package and the M4 mapping contract used by M7/M8.
- **Problem and resolution:** The project needed a stable producer-owned label artifact rather than module-specific or implicit labels. The package is consumed through its provenance manifest; M3 remains the owner of taxonomy, labels, and future coverage decisions.
- **Interface hand-off:** M3 supplies Role labels; M7 reads them for reranking/λ selection; M8 checks provenance and format without relabelling or calculating IAA.
- **Verification/outcome:** Merged on 2026-09-22. The PR description was minimal; the two committed package/contract changes are the basis for this scope summary.

### PR #158 — Windows LF checkout and CI coverage

- **Owner:** `yshe0376`
- **Delivered:** `.gitattributes` LF rules for JSON/JSONL and a Windows Python 3.12 test matrix entry.
- **Problem and resolution:** Windows `core.autocrlf` changed the bytes of hashed Role-label JSONL, causing every Windows loader to reject the manifest. Linux-only CI could not see the fault. The repository now preserves LF and tests Windows explicitly.
- **Interface hand-off:** All provenance and hashed JSON/JSONL consumers receive platform-stable bytes; release and v2 branches inherit the Windows gate.
- **Verification/outcome:** Merged on 2026-09-22. The reported Windows suite passed with 443 tests and two skips.

### PR #159 — Reviewed Gold and final Dev/Test split

- **Owner:** `yshe0376`
- **Delivered:** Marked the 20 Gold records reviewed, adopted `split-v1` with 12 Dev and 8 Test questions, and added the machine-readable split manifest.
- **Problem and resolution:** Formal scoring was blocked by a stale `annotation_status: m3_initial` field even though M3's review file accepted all 20 records. The PR updated only status/split fields, regenerated normalized Gold, and preserved evidence coordinates and mapping identity.
- **Interface hand-off:** M1 can run reportable retrieval evaluation; M7/M8 consume the split and reviewed Gold; Role-label coverage remains a separate limitation.
- **Verification/outcome:** Merged on 2026-09-22. A reportable Dev run and the 12-question/8-question split were verified; formal λ selection still refuses incomplete Role coverage.

### PR #160 — v1.0 release branch

- **Owner:** `yshe0376`
- **Delivered:** Version `1.0.0` on `release/1.0.0` and CI triggers for release branches.
- **Problem and resolution:** CI previously ran on pushes to `main` only, so release-branch pushes were not tested. The release branch now carries the v1.0 code and receives the same CI coverage.
- **Interface hand-off:** v1.0 fixes target `release/1.0.0`; merge-backs must preserve `main`'s `2.0.0.dev0` version.
- **Verification/outcome:** Merged on 2026-09-22. Version parsing and Linux/Windows CI passed according to the PR.

### PR #161 — v1.0/v2.0 branch model

- **Owner:** `yshe0376`
- **Delivered:** Set `main` to `2.0.0.dev0`, enabled release-branch CI, and recorded the v1.0 branch model and scope.
- **Problem and resolution:** After cutting v1.0, the team needed to stabilise the release without blocking v2 development. The decision is now explicit: v1.0 stays on `release/1.0.0`; `main` is the v2 line.
- **Interface hand-off:** v1.0 owns one textbook, 20 reviewed Gold records, reportable retrieval/answer evaluation, and no formal λ conclusion; v2 owns multi-textbook and formal personalisation expansion.
- **Verification/outcome:** Merged on 2026-09-22 with the reported version, workflow, full-suite, and Ruff checks passing.

### PR #162 — v2 M1 foundations

- **Owner:** `yshe0376`
- **Delivered:** v2 contracts and manifests, the three-OpenStax catalogue, vendored M2 parser 1.3.2, PDF adapter, FAISS index builder, source installer, physical page ranges, shared evidence spans, duplicate-group reporting, and the `cs30-build-v2` entry point.
- **Problem and resolution:** v2 needed to grow beyond the frozen v1 module path without changing the v1 corpus or contracts. The new `src/cs30/v2/` boundary isolates that work while pinning textbook/source identity and model/token ruler metadata.
- **Interface hand-off:** M1 v2 produces provider-bound documents, chunks, manifests, and indexes; M2 supplies the pinned OpenStax parser outputs; M4 still must provide the production chunker. The required CK-12 provider gate is declared but not yet satisfied.
- **Verification/outcome:** Merged on 2026-09-23. The PR reports 581 passed and three skipped, with full-parser-output checks and offline embedding smoke tests.

### PR #163 — Concept Check design and v2 decisions

- **Owner:** `yshe0376`
- **Delivered:** Published the Concept Check specification and recorded v2 decisions for stable evidence anchors, deterministic topic resolution, event-sourced learner state, bidirectional leakage gates, closed-by-default feature flags, and the v2 textbook/chunk contracts.
- **Problem and resolution:** The design existed only on a local branch, so M7, M3, and M8 could not review the intended interfaces. The finalized design is now versioned in `main`; implementation remains staged.
- **Interface hand-off:** M7 owns runtime generation/Concept Check behaviour; M3 owns Gold/Role labels; M8 owns evaluation/provenance; M4 owns corpus bindings and leakage inputs.
- **Verification/outcome:** Merged on 2026-09-23. Documentation-only; two later v2 contract rows explicitly remain deferred to their owners.

### PR #164 — Concept Check Phase 1 runtime contracts

- **Owner:** `yshe0376`
- **Delivered:** Concept Check snapshot state, deterministic topic/citation resolution seams, fail-closed topic-map validation, event payload semantics, corpus-bound published question release contracts, trace flags, and v2 configuration invariants.
- **Problem and resolution:** The v2 design needed executable contract boundaries before the event store, question release, leakage gates, or UI could be implemented. Phase 1 adds those boundaries and explicitly defers the remaining work instead of pretending the runtime is complete.
- **Contract risk:** `EvidenceItem.token_count` becomes required in the existing v2 schema. No current v2 persisted consumer uses it, but M8 must be notified before adopting the type.
- **Interface hand-off:** M7 implements runtime Concept Check behaviour; M3/M4 provide Gold, question, and corpus bindings; M8 validates provenance and formal reporting; the event store and UI remain follow-up work.
- **Verification/outcome:** Open as of 2026-09-23, mergeable with five CI checks passing. Deferred work includes the JSONL event store/replay, bidirectional leakage registry, reviewed fixtures, full configuration reachability, online LLM fallback, and UI integration.

## Commit-level audit for the recent hand-off chain

The PR index and detailed ledger cover all 57 repository PRs. The tables below add the requested commit-level audit for the current M3-M8 hand-off chain. Each row names the GitHub author, the concrete change, the problem or limitation exposed at that point, and the follow-up that resolved it or remains assigned. `No material issue recorded` is intentional where a commit only adds tests or documentation.

### PR #137 commits — `novel-peng`

| Commit | Change | Problem, resolution, or next hand-off |
|---|---|---|
| [`50180f9`](https://github.com/yshe0376/cs30-personalised-rag/commit/50180f9) | Added the W5 M4 corpus-build and mapping scripts. | Established the initial M4 implementation; the resulting corpus and mapping are handed to M5, M1, and M8. |
| [`5c268d2`](https://github.com/yshe0376/cs30-personalised-rag/commit/5c268d2) | Implemented the official corpus and Gold mapping. | Established the initial evidence scope; later alignment review found three M3 spans outside that scope. |
| [`80755a4`](https://github.com/yshe0376/cs30-personalised-rag/commit/80755a4) | Added M4 delivery tests. | Added regression coverage; the later partial-delivery path required additional explicit tests. |
| [`f975f6f`](https://github.com/yshe0376/cs30-personalised-rag/commit/f975f6f) | Published M4 delivery evidence. | Made the artifact auditable; subsequent documentation commits recorded the changing alignment decision. |
| [`2b1613d`](https://github.com/yshe0376/cs30-personalised-rag/commit/2b1613d) | Recorded M3 alignment blockers. | Exposed the three out-of-scope spans and handed them back to M3 rather than hiding the mismatch. |
| [`eda3d13`](https://github.com/yshe0376/cs30-personalised-rag/commit/eda3d13) | Added the W5 M4 delivery manifest. | Added identity and count evidence for downstream consumers; no material issue recorded. |
| [`29801e4`](https://github.com/yshe0376/cs30-personalised-rag/commit/29801e4) | Temporarily broadened the source scope to match M3 evidence content types. | This rescued the apparent 20/20 alignment but introduced the evaluation-leakage risk; the change was later superseded. |
| [`f67a51b`](https://github.com/yshe0376/cs30-personalised-rag/commit/f67a51b) | Added tests for the temporarily aligned M3 content scope. | Locked the temporary behaviour in tests; those expectations were restored when the original policy was reinstated. |
| [`7af8501`](https://github.com/yshe0376/cs30-personalised-rag/commit/7af8501) | Documented the temporary resolved alignment. | Recorded an intermediate state; it was superseded after the leakage risk was accepted as a release-blocking concern. |
| [`e7e5c1c`](https://github.com/yshe0376/cs30-personalised-rag/commit/e7e5c1c) | Reverted to the original evidence filter. | Final root decision: do not index assessment-like or summary content just to rescue Gold spans; return the three spans to M3. |
| [`221bd86`](https://github.com/yshe0376/cs30-personalised-rag/commit/221bd86) | Restored tests for the original evidence scope. | Kept regression coverage consistent with the final frozen filter; no material issue recorded. |
| [`dab80a1`](https://github.com/yshe0376/cs30-personalised-rag/commit/dab80a1) | Restored the M3 alignment status documentation. | Corrected the written state so the repository no longer described the withdrawn widened scope as final. |
| [`320a185`](https://github.com/yshe0376/cs30-personalised-rag/commit/320a185) | Skipped uncovered spans when building the M1-compatible mapping. | Prevented an apparently complete mapping from hiding missing evidence; `mapping_missing` remains visible to downstream scoring. |
| [`e394b81`](https://github.com/yshe0376/cs30-personalised-rag/commit/e394b81) | Emitted the audited partial mapping bundle. | Created a usable 17-question development hand-off while preserving diagnostics for all 20 questions. |
| [`0620a57`](https://github.com/yshe0376/cs30-personalised-rag/commit/0620a57) | Added tests for the 17-question partial delivery. | Proved that uncovered spans are reported rather than silently treated as retrieval failures. |
| [`da1bbc1`](https://github.com/yshe0376/cs30-personalised-rag/commit/da1bbc1) | Published the audited 17-question mapping. | Completed the current M4 artifact; reportable scoring still waits for M3 to re-annotate the three spans. |
| [`e35c866`](https://github.com/yshe0376/cs30-personalised-rag/commit/e35c866) | Added separate downstream hand-off packages. | Reduced the risk that M3 annotation inputs and M5 retrieval inputs are confused by giving each consumer its own package. |
| [`1771848`](https://github.com/yshe0376/cs30-personalised-rag/commit/1771848) | Tested the separated hand-off packages. | Added regression coverage for the consumer-specific packaging; no material issue recorded. |
| [`5da353d`](https://github.com/yshe0376/cs30-personalised-rag/commit/5da353d) | Documented the separated downstream packages. | Clarified package ownership and the next M3/M5 hand-offs; no material issue recorded. |

### PR #138 commits — `ZOEY-YUNYI`

| Commit | Change | Problem, resolution, or next hand-off |
|---|---|---|
| [`d2b7afd`](https://github.com/yshe0376/cs30-personalised-rag/commit/d2b7afd) | Added the offline M8 scoring framework. | Established answer, abstention, format, and citation scoring; later review found that abstention causes were not yet consumed. |
| [`050392c`](https://github.com/yshe0376/cs30-personalised-rag/commit/050392c) | Completed the M8 scoring breakdowns. | Expanded the metric surface, but the cause distinction remained unrepresented in the calculation path. |
| [`7efcda5`](https://github.com/yshe0376/cs30-personalised-rag/commit/7efcda5) | Integrated answer and citation scoring with evaluation v0.2. | Connected the scorer to the evaluation contracts; the abstention-attribution definition still needed correction. |
| [`e8991a0`](https://github.com/yshe0376/cs30-personalised-rag/commit/e8991a0) | Aligned scoring with acceptance criteria. | Tightened contract behaviour; citation and reporting edge cases remained for follow-up tests. |
| [`61ee3b8`](https://github.com/yshe0376/cs30-personalised-rag/commit/61ee3b8) | Covered citation and reporting edge cases. | Closed output-path gaps; no second issue of the same severity was identified. |
| [`0303412`](https://github.com/yshe0376/cs30-personalised-rag/commit/0303412) | Distinguished abstention causes in reports. | Root fix for the main review finding: `no_retrieval_hits` is no longer treated as proof of model refusal with evidence. |
| [`75ec759`](https://github.com/yshe0376/cs30-personalised-rag/commit/75ec759) | Aligned answer scoring with the review contract. | Completed the final contract/test alignment before merge; formal values still require reportable Gold and mapping inputs. |

### PR #139 and #140 documentation commits

| PR | Commit | Author | Change and follow-up |
|---|---|---|---|
| #139 | [`6762720`](https://github.com/yshe0376/cs30-personalised-rag/commit/6762720) | `yshe0376` | Added the initial English living ledger covering the repository PR history. |
| #139 | [`5ac03dd`](https://github.com/yshe0376/cs30-personalised-rag/commit/5ac03dd) | `yshe0376` | Recorded the ledger PR itself so the index remained complete after GitHub assigned #139. |
| #139 | [`d557b9b`](https://github.com/yshe0376/cs30-personalised-rag/commit/d557b9b) | `yshe0376` | Corrected the #137 filter decision and delivery figures after review; this update keeps those corrections current. |
| #140 | [`7fe42e9`](https://github.com/yshe0376/cs30-personalised-rag/commit/7fe42e9) | `yshe0376` | Froze the retrieval evidence policy and documented the evaluation-leakage rationale; M3/M4 receive the next hand-off. |
| #141 | [`cdcdbbe`](https://github.com/yshe0376/cs30-personalised-rag/commit/cdcdbbe) | `yshe0376` | Updated the status totals, #137 withdrawal record, and commit-level audit; this was the documentation update later merged into `main`. |
| #141 | [`0fd193b`](https://github.com/yshe0376/cs30-personalised-rag/commit/0fd193b) | `yshe0376` | Kept the ledger scope and #139 self-entry current after the update; no material issue recorded. |

### PR #143-#149 commits — current replacement hand-off

| PR | Commit | Author | Change and follow-up |
|---|---|---|---|
| #143 | [`43168ed`](https://github.com/yshe0376/cs30-personalised-rag/commit/43168ed) | `yshe0376` | Added the shared evidence source-block list, dual coordinate fields, loader validation, and policy gate. |
| #143 | [`066fbc6`](https://github.com/yshe0376/cs30-personalised-rag/commit/066fbc6) | `yshe0376` | Added excluded-block totals and per-content-type counts to the manifest. |
| #144 | [`727e9bf`](https://github.com/yshe0376/cs30-personalised-rag/commit/727e9bf) | `leahwang126` | Published the clean Gold v0.1.1 file and removed the superseded v0.1 hand-off. |
| #144 | [`0d88b3e`](https://github.com/yshe0376/cs30-personalised-rag/commit/0d88b3e) | `leahwang126` | Aligned Gold checksum metadata with the prepared corpus outputs. |
| #144 | [`a265dacc`](https://github.com/yshe0376/cs30-personalised-rag/commit/a265dacc) | `leahwang126` | Added corpus provenance and content-checksum validation. |
| #145 | [`90a9493`](https://github.com/yshe0376/cs30-personalised-rag/commit/90a9493) | `yshe0376` | Made all prepared corpus files byte-stable across platforms and extended line-ending tests. |
| #146 | [`a1c2871`](https://github.com/yshe0376/cs30-personalised-rag/commit/a1c2871) | `yshe0376` | Added the real index-build command and saved-artifact reload verification. |
| #147 | [`80c0477`](https://github.com/yshe0376/cs30-personalised-rag/commit/80c0477) | `novel-peng` | Added the official chunking strategy using the shared evidence policy. |
| #148 | [`962258a`](https://github.com/yshe0376/cs30-personalised-rag/commit/962258a) | `novel-peng` | Added reproducible M4 delivery/build commands on current `main`. |
| #148 | [`5bc0941`](https://github.com/yshe0376/cs30-personalised-rag/commit/5bc0941) | `novel-peng` | Added strict Gold mapping and explicit `coverage_status` handling. |
| #148 | [`860b036`](https://github.com/yshe0376/cs30-personalised-rag/commit/860b036) | `novel-peng` | Added tests for the completed official hand-off and exact source-block set. |
| #148 | [`32aae71`](https://github.com/yshe0376/cs30-personalised-rag/commit/32aae71) | `novel-peng` | Documented the verified 20-question/21-span M4 delivery. |
| #149 | [`58361e0`](https://github.com/yshe0376/cs30-personalised-rag/commit/58361e0) | `yshe0376` | Made the frozen `official` candidate the default for `cs30-build`; the real corpus confirmed identical official chunk IDs and the PR merged. |

### PR #150-#164 substantive commit index

The following index extends the commit-level record to the v1.0 closure and v2.0 transition. Merge-only branch synchronisation commits are omitted; every substantive commit is retained by its short SHA and can be opened from the corresponding PR or commit history.

| PR | Author | Substantive commits | Commit-level issue or follow-up |
|---:|---|---|---|
| #150 | `Ntan0927` | `7c6a4b7`, `9c66cdb`, `cb37e47`, `5284f90`, `977702d` | Rebuilt the latest-corpus indexes, added BGE-M3, then corrected FAISS corpus metadata and review issues. Follow-up: M6 must use identity-matched artifacts. |
| #151 | `yshe0376` | `2dd6c11`, `8571d69` | Closed the release-archive risk and committed the paired Gold/mapping inputs so scoring is reproducible. Follow-up: M3 review status remains authoritative. |
| #152 | `ZOEY-YUNYI` | `bfe631a`, `de1daa0`, `4bc6ecd`, `3956c4f`, `453abd2`, `d662a34`, `06de9b0`, `8574626`, `de6d97e` | Added reporting, then tightened rubric, comparison, refusal-F1, manifest-binding, and formal-integrity gates. Follow-up: formal reports wait for complete eligible inputs. |
| #153 | `syj-111-s` + `Codex` hand-off | `c955fd8`, `eaa0c90`, `25db491`, `4107cdf`, `12a39c4`, `b98a729`, `3eda4cd`, `f8829a`, `9354ae3`, `04845af`, `9de2545`, `a646436`, `fdeb7a8`, `11e6941`, `0dd7730`, `fde372a`, `8cd975d`, `78692a5`, `4fac0c5` | Built the reproducible M6 notebook, switched to BGE-M3, froze 25/75 RRF, and bound cache/results to evaluation identities. Follow-up: preserve the notebook provenance in future runs. |
| #154 | `syj-111-s` | `60cf66c` | Replaced the invalid cross-module hash comparison with corpus/record-count identity validation. |
| #155 | `yshe0376` | `16c5193`, `d242992`, `b01df33`, `b7054b8`, `ec78d36` | Initial v2 M1 attempt was hardened and documented but closed without merge; work was superseded by #162. |
| #156 | `skyshylsylsy` | `5ea41b3`, `9fdca0f`, `ea67a9b` | Added λ selection, aligned the Role-label manifest, and made artifacts byte-stable. Follow-up: incomplete candidate coverage keeps formal results `not_interpretable`. |
| #157 | `leahwang126` | `3102eb4`, `98dd514` | Added the M3 Role-label package and corrected the M4 mapping contract. Follow-up: M3 owns taxonomy and coverage. |
| #158 | `yshe0376` | `a23b5c6`, `ed853a6` | Fixed cross-platform JSON/JSONL checkout bytes and exposed the fault with a Windows CI job. |
| #159 | `yshe0376` | `a09a39c` | Corrected stale Gold review status and finalized the 12/8 split; mapping coordinates remained unchanged. |
| #160 | `yshe0376` | `9d82ac1` | Versioned the v1.0 release branch and added release-branch CI. Follow-up: keep version-line merge conflicts intentional. |
| #161 | `yshe0376` | `96d6813` | Switched `main` to the v2.0 development line and recorded the release/scope boundary. |
| #162 | `yshe0376` | `07c0559`, `a740a99`, `548d6a4`, `6638e4f`, `6fe6478`, `3e8f1a1`, `5074694`, `3075083`, `0f35288`, `e239e19`, `d4aaf89`, `7c0637c`, `f0affd2`, `4f36ef0` | Built and reviewed the v2 M1 foundation, then froze source identity, page/evidence contracts, parser boundary, PDF/FAISS path, provider gate, and chunk ruler. Follow-up: CK-12, M4 production chunking, and M5 model selection remain open. |
| #163 | `yshe0376` | `4867967` | Published the Concept Check design and v2 decision record so M7/M3/M8 can review it. |
| #164 | `yshe0376` | `ebb7421`, `31c678a`, `46c5000` | Added and tightened Phase 1 Concept Check runtime contracts. Follow-up: event store, leakage registry, reviewed fixtures, full reachability, fallback, and UI remain deferred. |

## 5. Interface ownership and dependency register

This table describes the current practical ownership inferred from PR authorship and the documented module allocation. It should be updated when the team formally reassigns an interface.

| Interface / artifact | Producer or maintainer | Consumed by | Current hand-off risk |
|---|---|---|---|
| Shared contracts and `ports.py` | `yshe0376` | M2-M8 | Contract changes require compatibility review and ADR/update discipline. |
| Canonical textbook document and blocks | M2: `chongshao223`; shared/catalogue integration: `yshe0376` | M4 | Current W5 is the verified OpenStax 34-chapter hand-off; the six-textbook W6 corpus is future work. |
| Gold questions, spans, answers, and review status | M3: `leahwang126` | M4, M1, M8 | v0.1.1 is the current W5 Gold hand-off; the current 20 records are not the final 240-record W6 set. |
| Frozen retrieval evidence policy | Shared policy: `yshe0376`; applied by M4 | M3 annotation, M4 mapping, M5 indexing, M1/M8 evaluation | The policy must remain identical across source blocks, official chunking, Gold mapping, and evaluation. |
| Chunking strategy, corpus records, manifest, Gold mapping | M4: `novel-peng` | M5, M6, M1, M8 | #148 is the current official W5 hand-off with exact source-block-set validation and 20/20 question coverage. |
| Dense index and embedding configuration | M5: `Ntan0927`; real build seam: `yshe0376` | M6 | Build the reportable index from the `official` candidate; #149 makes that candidate the default. BGE-M3 is the current evaluated long-context candidate. |
| Retrieval service and evidence provenance | M6: `syj-111-s`; contract/config integration: `yshe0376` | EvidenceBundle, M7, M1, M8 | Thresholds and stopword behaviour must remain wired and recorded per run. |
| EvidenceBundle, citation validation, UI | M8: `ZOEY-YUNYI` | M7, demo users, evaluation | Shared Pipeline still needs the native EvidenceBundle hand-off used by #115. |
| Personalised prompt, reranking, and generation | M7: `skyshylsylsy`; prompt-field integration: `yshe0376` | M1 runner, M8 scorer | M3 Role-label taxonomy/versioning and the shared Pipeline seam remain open for formal runs. |
| M3 Role-label taxonomy and package | M3: `leahwang126` | M7 reranking/λ selection, M8 provenance | Current labels cover Gold chunks only; complete candidate-pool coverage is required before formal personalisation conclusions. |
| Evaluation contracts, runner, retrieval metrics | M1/integration: `yshe0376` | M8 scoring and final report | Formal runs require the #148 identity-matched mapping, the official index, and expanded reportable Gold. |
| Answer/citation scoring and reports | M8: `ZOEY-YUNYI` | Experiment owners and final report | Metric values are not formal until reportable inputs exist. |
| v2 textbook catalogue and source gate | M1/v2: `yshe0376`; M2 parser input | M4/v2 chunking, M5/v2 indexing, M7/M8 Concept Check | Three OpenStax books are pinned; the required CK-12 provider is declared but not selected. |
| v2 Concept Check contracts and runtime seams | M1/v2: `yshe0376`; M7 runtime owner | M3 Gold/Role labels, M4 corpus bindings, M8 provenance | Phase 1 is open in #164; event store, leakage registry, reviewed fixtures, full reachability, LLM fallback, and UI are deferred. |

## 6. How to maintain this ledger

Update this file at three points in every PR lifecycle:

1. **When the PR opens:** add the owner, intended delivery, changed interface, upstream dependency, downstream consumer, and stated verification.
2. **When review finds a problem:** record one root cause, its user/research impact, the requested change, and whether it blocks merge. Do not list several derived symptoms as unrelated defects.
3. **When the PR merges or closes:** update the final state, name the resolving commit or superseding PR, record the verification result, and assign every remaining hand-off to an interface owner.

For an active or recently reviewed PR, also append one commit-level row for every substantive commit: author, concrete change, problem or limitation exposed, and the resolving commit or next owner. Test-only and documentation-only commits may say `No material issue recorded`, but they should not be silently omitted from the audit.

Use these rules to keep the document auditable:

- Do not describe a closed, unmerged PR as delivered functionality.
- Separate author-declared test results from independently rerun checks.
- Record accepted limitations, especially evaluation leakage and fixture-only evidence.
- Prefer stable PR, commit, contract, corpus, and mapping identities over prose such as “latest version”.
- Write `No material issue recorded` when no review evidence exists; do not invent a defect to fill the field.
- Update the date, totals, contributor counts, current-status table, PR index, detailed entry, commit-level audit, and interface register together.

### Entry template

```markdown
### PR #NNN — Short title

- **Owner:** `github-account`
- **Delivered:** Concrete files, behaviour, or artifacts introduced.
- **Problem and resolution:** Root cause, impact, requested change, and final fix; or `No material issue recorded`.
- **Interface hand-off:** Upstream producer, interface owner, and downstream consumer.
- **Verification/outcome:** CI/local checks, merge state, accepted limitations, and remaining follow-up.
```
