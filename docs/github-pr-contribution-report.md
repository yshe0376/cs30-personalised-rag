# Pull Request Change and Integration Ledger

> Last synchronised: 2026-09-13
> Repository: [yshe0376/cs30-personalised-rag](https://github.com/yshe0376/cs30-personalised-rag)
> Scope: All 32 pull requests currently recorded in GitHub.
> Purpose: Record who delivered each change, what changed, what problems were found, how they were resolved, and which interface owner receives the next hand-off.

This is a living engineering ledger, not a substitute for the GitHub diff or review thread. GitHub is the source of truth for state, authorship, commits, and CI. Technical summaries below are based on PR descriptions, changed files, commits, repository contracts, and recorded review findings. An item marked **inferred** is an integration conclusion rather than a statement made by the PR author.

## 1. Current status and critical hand-offs

As of the synchronisation date, 23 PRs are merged, 6 are closed without merge, and 3 remain open.

| PR | Owner | State | Current decision or blocker | Next owner/action |
|---:|---|---|---|---|
| [#115](https://github.com/yshe0376/cs30-personalised-rag/pull/115) | `skyshylsylsy` | Open | Generation supports the four W5 conditions and native `EvidenceBundle`, but the shared Pipeline still passes `RetrievalResult`. M5 role labels are also not frozen. | Shared Pipeline/integration owner must switch the orchestration seam; M5 must freeze role labels; M1/M8 must run formal evaluation. |
| [#137](https://github.com/yshe0376/cs30-personalised-rag/pull/137) | `novel-peng` | Open draft, mergeable, CI passing | The original 17/20 Gold coverage blocker was resolved by versioning the corpus filter to include `problem` and `summary`. The mapping now covers 20/20 spans, but this accepts a documented evaluation-leakage risk. The PR body still reports the superseded v1 figures. | M4 must update the PR body. M2 manual QA and M3 independent Gold review remain pending. M5 must address 1,911 embedding inputs above the model ceiling. |
| [#138](https://github.com/yshe0376/cs30-personalised-rag/pull/138) | `ZOEY-YUNYI` | Merged | The initial abstention-cause attribution problem was fixed before merge. Reports now preserve the cause and expose system-level, model-level, and cause-specific views. | M1/M3/M4 must provide reportable Gold, mapping, and saved runs before formal benchmark values can be produced. |
| [#139](https://github.com/yshe0376/cs30-personalised-rag/pull/139) | `yshe0376` | Open | Publishes this living PR ledger and makes it discoverable from the README. | Review and merge the documentation; update this entry from Open to Merged after landing. |

### Important decision recorded for PR #137

The team selected the second of the two available M3/M4 alignment options: change and version the M4 corpus filter instead of asking M3 to replace three evidence spans. M4 v2 now includes `problem` and `summary`, increasing the corpus from 3,684 to 3,979 chunks and producing a complete 20/20 mapping. This preserves the existing Gold annotations, but SciQ questions may retrieve near-verbatim textbook exercise text. Every evaluation report using this corpus must disclose that limitation, and v1 and v2 results must not be compared as if the corpus were unchanged.

## 2. Contributor overview

| GitHub account | PRs | Primary ownership shown by the PR history |
|---|---:|---|
| [yshe0376](https://github.com/yshe0376) | 16 | Shared framework, contracts, Pipeline integration, CI, configuration, project documentation, and M1 evaluation infrastructure |
| [novel-peng](https://github.com/novel-peng) | 4 | M4 structure-aware chunking, corpus construction, trace-back, and Gold-to-chunk mapping |
| [chongshao223](https://github.com/chongshao223) | 4 | M2 OpenStax College Physics parser iterations and final parser delivery |
| [leahwang126](https://github.com/leahwang126) | 2 | M3 SciQ questions and Gold Evidence data |
| [skyshylsylsy](https://github.com/skyshylsylsy) | 2 | M7 personalised generation, evidence consumption, and reranking |
| [ZOEY-YUNYI](https://github.com/ZOEY-YUNYI) | 2 | M8 evidence governance, citation validation, UI, and answer/citation evaluation |
| [Ntan0927](https://github.com/Ntan0927) | 1 | M5 FAISS vector-index construction and persistence |
| [syj-111-s](https://github.com/syj-111-s) | 1 | M6 Dense, BM25, and RRF Hybrid retrieval |

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
| [#115](https://github.com/yshe0376/cs30-personalised-rag/pull/115) | `skyshylsylsy` | Open | Four-condition W5 personalisation and real generation; integration hand-off pending |
| [#133](https://github.com/yshe0376/cs30-personalised-rag/pull/133) | `yshe0376` | Closed draft | Broad evaluation/build proposal split into smaller PRs; not merged wholesale |
| [#134](https://github.com/yshe0376/cs30-personalised-rag/pull/134) | `yshe0376` | Merged | Provider-neutral textbook interface and catalogue |
| [#135](https://github.com/yshe0376/cs30-personalised-rag/pull/135) | `leahwang126` | Merged | M3 Gold Evidence v0.1 and validation material |
| [#136](https://github.com/yshe0376/cs30-personalised-rag/pull/136) | `yshe0376` | Merged | Corpus-bound Gold normalisation, evaluation runner, and retrieval scoring |
| [#137](https://github.com/yshe0376/cs30-personalised-rag/pull/137) | `novel-peng` | Open draft | Official 34-chapter M4 corpus and complete Gold mapping; leakage risk accepted and documented |
| [#138](https://github.com/yshe0376/cs30-personalised-rag/pull/138) | `ZOEY-YUNYI` | Merged | Cause-aware answer, abstention, format, and citation scoring |
| [#139](https://github.com/yshe0376/cs30-personalised-rag/pull/139) | `yshe0376` | Open | Publishes the living PR change and integration ledger |

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
- **Problem and current boundary:** No blocking review defect is recorded. The PR uses fixture role labels because M5 taxonomy/versioning is not frozen, and `lambda_weight` remains an engineering fixture until selected on Dev data. The shared Pipeline still passes `RetrievalResult` despite native bundle support.
- **Interface hand-off:** M5 owns role labels; M7 owns prompts/reranking/generation; shared Pipeline owner must switch the call seam; M1/M8 own formal four-condition runs and scoring.
- **Verification/outcome:** Open and mergeable with all CI checks passing as of 2026-09-13. The PR reports 339 local tests, four successful mock conditions, and four successful local Ollama conditions; these are engineering checks, not quality results.

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
- **Problems and current boundary:** M2 has not independently reviewed provenance. Every `gold_answer` is `D`, and all 20 records are answerable, so v0.1 cannot support credible answer-accuracy or unanswerable/abstention reporting by itself.
- **Interface hand-off:** M3 owns Gold annotations and review status; M4 maps spans to chunks; M1 validates and runs them; M8 scores saved runs.
- **Verification/outcome:** Merged on 2026-09-11. Formal reporting remains blocked until the required independent review and a suitable answerability distribution are available.

### PR #136 — Corpus-bound Gold and retrieval evaluation

- **Owner:** `yshe0376`
- **Delivered:** Evaluation v0.2 models, JSONL I/O, batch runner, retrieval-only dependency path, offline metrics, CLI, manifests, fixtures, corpus-bound Gold normalisation, and prompt/model provenance traces.
- **Problems and resolution:** The implementation added explicit stale/ambiguous classification, chapter/text consistency checks, no-overwrite protection, and a retrieval-only path that does not initialise an LLM. It preserved raw M3 data rather than overwriting it with normalised records.
- **Scope boundary:** The PR did not claim unreviewed M3 Gold was reportable and did not contain the real M4 mapping artifact; #137 supplies that hand-off.
- **Interface hand-off:** Consumes M3 Gold and M4 mapping; runs M6/M7; produces saved results and retrieval metrics consumed by M8.
- **Verification/outcome:** Merged on 2026-09-12.

### PR #137 — Official 34-chapter M4 corpus and Gold mapping

- **Owner:** `novel-peng`
- **Delivered:** Reproducible 34-chapter corpus build, real all-MiniLM-L6-v2 tokenisation, corpus QA, source trace-back, duplicate provenance, identity guards, Gold normalisation, and M1-compatible mapping.
- **Initial problem:** M4 v1 excluded assessment-like `problem` blocks and `summary`, while three M3 Gold spans used exactly those types. It correctly failed closed at 17/20 and withheld the formal mapping instead of silently producing an incomplete artifact.
- **Resolution:** Commits `29801e4`, `f67a51b`, and `7af8501` versioned M4 to v2, included `problem` and `summary`, rebuilt the corpus, and emitted a 20/20 mapping. This adopted the filter-change option instead of re-annotating M3.
- **Documentation issue:** The GitHub PR body still states the superseded v1 results: 3,684 chunks, 17/20 coverage, 1,446 over-ceiling inputs, and a withheld mapping. M4 should replace those figures with the v2 results before merge.
- **Accepted risk:** Including textbook problems can make SciQ evaluation retrieve near-verbatim source exercises. Reports must disclose leakage risk and keep v1/v2 results separate.
- **Interface hand-off:** Consumes M2 canonical blocks and M3 spans; produces corpus records/manifests for M5 plus `GoldChunkMapping` for M1/M8. M5 owns the response to 1,911 inputs above the 254-content-token ceiling.
- **Verification/outcome:** Open draft, mergeable, and all four GitHub CI checks pass as of 2026-09-13. Current verified totals are 35,905 blocks, 3,979 chunks, 20 resolved spans, 20 fully covered spans, and 0 incomplete mappings. M2 manual QA and M3 independent review remain pending.

### PR #138 — Cause-aware answer, abstention, format, and citation scoring

- **Owner:** `ZOEY-YUNYI` (`yzho0933`)
- **Delivered:** Offline answer, abstention, raw/repaired format, citation, traceability, and Gold-coverage metrics; development/reportable modes; JSON/JSONL/CSV/Markdown reports; failure labels; and CLI integration.
- **Initial problem:** The first implementation did not read `abstention_cause`, so `no_retrieval_hits` and `model_abstained_with_evidence` could not be distinguished or attributed. Per-question reports also omitted the cause.
- **Resolution:** Commit `0303412` preserved the cause per question, added cause counts/confusion views, and separated system-level abstention from model-only abstention metrics. Commit `75ec759` aligned the remaining answer-scoring rules and tests with the review contract.
- **Interface hand-off:** Consumes M1 v0.2 run results, M3 answerability/answers, and M4 OR-of-AND mapping; produces auditable evaluation artifacts for experiment and report owners. It does not rerun retrieval or generation.
- **Verification/outcome:** Merged on 2026-09-13 after all four GitHub CI checks passed. The PR reports Ruff passing and 344 tests. Formal numbers still require frozen/reviewed Gold, a valid mapping, and reportable saved runs.

### PR #139 — Pull request change and integration ledger

- **Owner:** `yshe0376`
- **Delivered:** This English living ledger, a 32-PR index, current hand-off dashboard, contributor overview, interface ownership register, maintenance rules, and a README link.
- **Problem and resolution:** PR work, review findings, superseding changes, and downstream ownership were previously spread across PR pages and conversations. This PR consolidates them into one version-controlled reference. No material implementation issue is recorded.
- **Interface hand-off:** All module owners update their own PR facts; the shared integration/documentation owner maintains cross-module status and ownership links.
- **Verification/outcome:** Open as of 2026-09-13. Before creation, the branch passed 334 tests, Ruff, whitespace checks, relative-link checks, and a complete comparison against the 31 pre-existing GitHub PR IDs. This self-entry was added after GitHub assigned PR #139.

## 5. Interface ownership and dependency register

This table describes the current practical ownership inferred from PR authorship and the documented module allocation. It should be updated when the team formally reassigns an interface.

| Interface / artifact | Producer or maintainer | Consumed by | Current hand-off risk |
|---|---|---|---|
| Shared contracts and `ports.py` | `yshe0376` | M2-M8 | Contract changes require compatibility review and ADR/update discipline. |
| Canonical textbook document and blocks | M2: `chongshao223`; shared/catalogue integration: `yshe0376` | M4 | M2 manual QA for the official corpus remains pending. |
| Gold questions, spans, answers, and review status | M3: `leahwang126` | M4, M1, M8 | v0.1 is `m3_initial`, all answers are `D`, and no records are unanswerable. |
| Chunking strategy, corpus records, manifest, Gold mapping | M4: `novel-peng` | M5, M6, M1, M8 | v2 includes problems/summaries and carries evaluation-leakage risk. |
| Dense index and embedding configuration | M5: `Ntan0927` | M6 | #137 reports 1,911 inputs above the selected model's content-token ceiling. |
| Retrieval service and evidence provenance | M6: `syj-111-s`; contract/config integration: `yshe0376` | EvidenceBundle, M7, M1, M8 | Thresholds and stopword behaviour must remain wired and recorded per run. |
| EvidenceBundle, citation validation, UI | M8: `ZOEY-YUNYI` | M7, demo users, evaluation | Shared Pipeline still needs the native EvidenceBundle hand-off used by #115. |
| Personalised prompt, reranking, and generation | M7: `skyshylsylsy`; prompt-field integration: `yshe0376` | M1 runner, M8 scorer | Role-label taxonomy and production Pipeline integration remain open. |
| Evaluation contracts, runner, retrieval metrics | M1/integration: `yshe0376` | M8 scoring and final report | Formal runs require reviewed Gold and identity-matched corpus/mapping artifacts. |
| Answer/citation scoring and reports | M8: `ZOEY-YUNYI` | Experiment owners and final report | Metric values are not formal until reportable inputs exist. |

## 6. How to maintain this ledger

Update this file at three points in every PR lifecycle:

1. **When the PR opens:** add the owner, intended delivery, changed interface, upstream dependency, downstream consumer, and stated verification.
2. **When review finds a problem:** record one root cause, its user/research impact, the requested change, and whether it blocks merge. Do not list several derived symptoms as unrelated defects.
3. **When the PR merges or closes:** update the final state, name the resolving commit or superseding PR, record the verification result, and assign every remaining hand-off to an interface owner.

Use these rules to keep the document auditable:

- Do not describe a closed, unmerged PR as delivered functionality.
- Separate author-declared test results from independently rerun checks.
- Record accepted limitations, especially evaluation leakage and fixture-only evidence.
- Prefer stable PR, commit, contract, corpus, and mapping identities over prose such as “latest version”.
- Write `No material issue recorded` when no review evidence exists; do not invent a defect to fill the field.
- Update the date, totals, contributor counts, current-status table, PR index, detailed entry, and interface register together.

### Entry template

```markdown
### PR #NNN — Short title

- **Owner:** `github-account`
- **Delivered:** Concrete files, behaviour, or artifacts introduced.
- **Problem and resolution:** Root cause, impact, requested change, and final fix; or `No material issue recorded`.
- **Interface hand-off:** Upstream producer, interface owner, and downstream consumer.
- **Verification/outcome:** CI/local checks, merge state, accepted limitations, and remaining follow-up.
```
