# M4 v2 Four-Textbook Development Corpus

This directory records the reproducible M4 build completed after the CK-12
adapter was merged in PR #186.

## Build

```sh
python scripts/install_v2_sources.py --format parsed
python scripts/build_v2_corpus.py --config real-development \
  --output-dir artifacts/v2/textbooks/2.0.0-dev.m4-four-book-main-a1fe99e \
  --corpus-version 2.0.0-dev.m4-four-book-main-a1fe99e \
  --embedding-model ""
```

The build used repository revision `a1fe99e`, M4's frozen BERT WordPiece
chunk ruler, and the four source files pinned by the v2 catalogue. No vector
index was generated because embedding-model selection and index construction
belong to M5.

## Result

- Corpus version: `2.0.0-dev.m4-four-book-main-a1fe99e`
- Corpus SHA-256: `1af6489539026b115db6d9d2e8bc143161e0cd3832d01fe0c9706fc53b77d205`
- Chunk configuration SHA-256: `914659582bf24dd81618d55d18b9717e7e0a1d63ace5ff740966b2b0e924c191`
- Documents: 4
- Chunks: 6,184
- Failed textbooks: 0
- Cross-chapter chunks: 0
- Forbidden assessment-content chunks: 0
- Oversized indivisible chunks: 3
- Status: development-only (`reportable=false`)

| Textbook | Chapters | Chunks | Median tokens |
| --- | ---: | ---: | ---: |
| OpenStax College Physics 2e | 34 | 2,369 | 392 |
| OpenStax Physics | 23 | 1,272 | 259 |
| OpenStax College Physics for AP Courses 2e | 34 | 2,335 | 397 |
| CK-12 People's Physics Concepts | 20 | 208 | 321 |

CK-12 contributed 3,244 referenced source blocks. No CK-12 `problem`,
`summary`, `conceptual_question`, or `check_understanding` block entered the
retrieval corpus.

## Files

- `corpus_manifest.json`: source identities, hashes, chunk counts and corpus identity.
- `run_report.json`: build status and reportability gates.
- `validation_summary.json`: M4 engineering checks and per-book distributions.

The full M5 handoff is intentionally not committed because it contains the
62 MB `records.jsonl`. The local handoff archive is named
`M4_to_M5_four_book_corpus_a1fe99e.zip`; its SHA-256 is
`074ff89686fe3649089329f7858505f7a68d228d0284a83394a0c0b5a547a592`.

## Limitations

- This development build is not a formal evaluation result.
- M2's CK-12 release still records manual parser-QA work for its sampled pages
  and known source-layout issues.
- CK-12 content is CC BY-NC 3.0 and requires the attribution link
  `http://www.ck12.org/saythanks` wherever its text is shown to users.
