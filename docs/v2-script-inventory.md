# v2 脚本盘点（M1）

状态：本地 v2 worktree 的 M1 边界清单。旧脚本不会被 v2 入口隐式调用；标为 `v1-only` 的脚本只服务 v1 历史资产。

| script / entry | current responsibility | input → output | standalone | downstream | boundary / gap | decision | priority | rerun / failure | schema boundary |
|---|---|---|---|---|---|---|---|---|---|
| `scripts/build_v2_corpus.py` | v2 唯一 M1 编排入口 | `TEXTBOOK_ID=PATH` UTF-8 → versioned records/Manifest/run report | yes | v2 M2/M4 | synthetic text adapter only; real PDF/CK-12 parser is M2 | new wrapper | P0 | stable IDs; exit 2/4/5/10 | v2.0 only |
| `src/cs30/v2/pipeline.py` | parse → chunk → Manifest batch | `TextbookInput` → `BuildOutcome` | library | v2 corpus | no index implementation in M1 | new boundary | P0 | per-book failures; official fail-closed | v2.0 |
| `src/cs30/v2/fixture.py` | deterministic M1 text parser | UTF-8 text → `TextbookDocument` | library | v2 tests/CLI | not a production format parser | fixture adapter | P1 | raw hash and IDs deterministic | v2.0 |
| `scripts/prepare_corpus.py` | legacy single-document/prepared corpus | legacy document → v1 prepared assets | yes | v1 retrieval | not multi-textbook; fixed legacy paths | exclude from v2 | P0 | retain v1 behavior | v1-only |
| `scripts/build_retrieval_corpus.py` | legacy retrieval JSONL export | v1 document/chunks → `manifest.json`/records | yes | v1 dense/BM25 | old Manifest and single-document assumptions | v1-only; later adapter | P0 | preserve existing fixture tests | v1.0 |
| `scripts/build_faiss_index.py` | legacy FAISS build | v1 corpus → v1 FAISS artifact | yes | v1 dense retrieval | metadata-only compatibility fields and `data/index` defaults | v1-only until M5 adapter | P0 | never read by v2 | v1.0 |
| `scripts/build_bge_m3.py` | embedding experiment/legacy index | local corpus → experiment assets | yes | historical experiments | no v2 Manifest gate | exclude from v2 | P2 | experiment-specific | legacy |
| `scripts/build_official_faiss.py` | historical official index build | v1 prepared corpus → official FAISS | yes | v1 M5/M6 | unversioned/old artifact contract | v1-only | P0 | do not overwrite v2 | v1-only |
| `scripts/build_official_faiss_remaining.py` | historical remaining index build | v1 corpus remainder → index | yes | v1 M5 | no v2 input contract | v1-only | P2 | historical only | v1-only |
| `scripts/map_gold_spans.py` | legacy chapter-local Gold mapping | SciQ/OpenStax → mapping JSON | yes | v1 evaluation | must receive Manifest routing in v2 M3 | v1-only now; wrap in M3 | P0 | stable legacy outputs | v1.0 |
| `scripts/build_w5_m4_delivery.py` | historical M4 delivery bundle | v1 chunks → delivery bundle | yes | v1 M4/M6 | hard-coded corpus assumptions | v1-only | P0 | frozen artifact only | v1-only |
| `scripts/compare_embeddings.py` | embedding comparison experiment | corpus/models → report | yes | experiments | not a build dependency | exclude from v2 | P2 | experiment output | legacy |
| `src/cs30/ingest/textbooks.py` | v1 six-entry source catalogue | no required input → JSON catalogue | yes | v1 `cs30-build` | v2 exact three IDs must not be inferred from six candidates | v2 catalogue boundary in `cs30.v2.catalog` | P0 | deterministic catalogue | v1 + isolated v2 |
| `src/cs30/build.py` | v1 single-document build | JSON/PDF → v1 index | yes | v1 index/retrieval | single textbook, current-date/default-path risks | leave v1; v2 uses new entry | P0 | preserve v1; no v2 calls | v1-only |
| `src/cs30/ingest/openstax_parser.py` | OpenStax parser | PDF → v1 OpenStax JSON | library/script | v1 M2 | provider-specific output | wrap through v2 adapter in M2 | P0 | parser-owned QA | v1 input until adapter |
| `src/cs30/ingest/college_physics_parser.py` | CP2e parser CLI | PDF → v1 contract JSON/QA | yes | v1 M2 | CP2e hard-coding | v1-only adapter source | P1 | byte-identical v1 rebuild | v1-only |
| `src/cs30/ingest/fixture.py` | v1 packaged fixture parser | ignored path → v1 fixture document | library | v1 smoke | silently ignores source path | do not call from v2 | P0 | fixed fixture | v1-only |
| `src/cs30/chunking/corpus.py` | v1 unified corpus writer | v1 docs/chunks → legacy Manifest/JSONL | library | v1 index | v1 schema and single contract | v1-only; v2 has canonical writer | P0 | existing deterministic tests | v1.0 |
| `src/cs30/fixture_store.py` | v1 fixture loading | packaged JSON → v1 models | library | v1 smoke/evaluation | old schemas | v1-only | P1 | fixed package data | v1-only |
| `src/cs30/indexing/faiss_index.py` | v1 FAISS loader/builder | v1 chunks → v1 artifact | library | v1 retrieval | compatibility data in free metadata | M5 v2 adapter required | P0 | no v2 path reuse | v1-only |
| `src/cs30/evaluation/*` | v1 evaluation and trace | v1 runs → reports/mappings | library/scripts | v1 report | chapter-local/global and textbook routing not v2-ready | M3/M8 adapter required | P0 | existing v1 tests remain separate | v1-only |

## M1 acceptance

- v2 calls only `cs30.v2.pipeline.run_build_pipeline` through `scripts/build_v2_corpus.py`.
- v1 `data/index`, legacy `manifest.json`, and v1 fixture loaders are not default v2 inputs.
- Every failure has a machine-readable code and is represented in `run_report.json`; official partial builds do not publish a formal output directory.
- The three required IDs are explicit in `cs30.v2.catalog` and both v2 config profiles; they are not selected by “take the first three” logic.
