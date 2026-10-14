# v2 build from the real textbooks

Real builds read M2's parsed delivery, not the PDFs. The three OpenStax JSON
files come from [`M2_data_ingestion`](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/M2_data_ingestion);
the CK-12 JSON comes from [`M2_ck12`](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/M2_ck12).
Install with `python -m pip install -e ".[ml]"`; `[ml]` is FAISS and
sentence-transformers for the dense index. `[parse]` (PyMuPDF and pdfplumber)
is only needed to re-parse the PDFs (see the last section).

## 1. Install M2's parsed delivery

The catalogue pins the SHA-256 of each book's parsed JSON, so the installer
verifies every file while it reads it and never overwrites a local file that
differs.

```sh
python scripts/install_v2_sources.py                          # from M2's Release
python scripts/install_v2_sources.py --from-archive openstax_parser_v1_3_2_r1.zip \
  --from-archive ck12_parser_v1_1_0.2.zip
```

The files land in `data/parsed/v2/<textbook_id>.json`, which is git-ignored.
The first command downloads each provider archive, verifies the pinned JSON
files, installs them, and deletes the temporary archives. The CK-12 archive
contains an `openstax_document.json` for legacy compatibility; v2 routes it
through the CK-12 adapter.

## 2. Build a diagnostic corpus

```sh
python scripts/build_v2_corpus.py --config real-development \
  --output-dir artifacts/v2/textbooks/2.0.0-dev.2 \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2
```

The current CK-12 entry has `source_approved=false`, so the v2 pipeline stops
with `SOURCE_NOT_APPROVED` before parsing any source. Do not run the build until
the source-specific licence terms and manual parser QA have been cleared.

The three OpenStax files use `cs30.v2.ingest.OpenStaxParsedParser`; CK-12 uses
`cs30.v2.ingest.CK12ParsedParser`. The build chunks with M4's production
structure-aware chunker and writes `records.jsonl`,
`manifest.json`,
`duplicate_blocks.json`, `run_report.json`, and — when a model is given — an
index under `index/` plus `artifact.json`. The `real-development` profile names
`Alibaba-NLP/gte-modernbert-base`, so a build indexes with it unless told
otherwise; `--embedding-model ""` publishes the development corpus and no
index.

The profile also names the `corpus_version` written to the manifest.
`--corpus-version` overrides it, which is how a delivered corpus is reproduced
byte for byte: the same pinned sources, chunker, and version string give the same
`records.jsonl`, `manifest.json`, and `duplicate_blocks.json`. For example, M4's
three-book handoff of 2026-10-07 (built at `3553825`):

```sh
python scripts/build_v2_corpus.py --config real-development \
  --output-dir artifacts/v2/textbooks/2.0.0-dev.m4-structure-v2-main-3553825 \
  --corpus-version 2.0.0-dev.m4-structure-v2-main-3553825 \
  --embedding-model ""
```

The pipeline checks each file against its pin (`SOURCE_HASH_MISMATCH`) and
checks that the document names the pinned PDF as its raw source
(`HASH_MISMATCH`). The manifest's `raw_source_sha256` is therefore always the
PDF hash, whichever route built the corpus.

Every development build is marked `reportable=false`: it is for M4, M5, and M6
to work against, never a formal result.

## 3. What an official build still needs

`--config staging` runs `corpus_mode=official`, which fails closed. The CK-12
adapter is wired, but the current source is not approved for any v2 build yet:

| Gate | Failure code | Who clears it |
|---|---|---|
| CK-12 source-specific licence terms and parser QA are pending | `SOURCE_NOT_APPROVED` | M1/M2 confirm the applicable terms and complete manual QA |

The CK-12 release has ten manually sampled blocks, all still marked `pending`,
and records 13 parser issues. See [the CK-12 integration note](v2-ck12-integration.md)
for source pins and the license review gate. The catalogue pins both the PDF
and parsed JSON hashes for all four books; the pipeline also checks that the
parser provider and index artifact match the staged corpus.

## Reading an index back

```python
from cs30.v2.indexing import load_faiss_index

loaded = load_faiss_index(Path("artifacts/v2/textbooks/2.0.0-dev.2"))
loaded.search(query_vectors, top_k=5)   # [(chunk_id, score), ...] per query
```

The loader re-hashes `records.jsonl` against the manifest and checks the
artifact's chunk order, so an index can never be paired with a different corpus.
FAISS row *i* is always record line *i*.

## Reading the records back

```python
from cs30.v2.corpus import load_corpus_records

corpus = load_corpus_records(Path("artifacts/v2/textbooks/2.0.0-dev.2"))
corpus.chunks                     # v2 Chunk objects, in record (= index row) order
corpus.chunks_by_id[chunk_id]     # one chunk
corpus.manifest.reportable        # False for every development build
```

The loader needs no index. It refuses records whose bytes no longer hash to the
manifest (`CORPUS_HASH_MISMATCH`), any line that is not a v2 chunk — v1 records
included (`CORPUS_RECORD_INVALID`) — and records whose order, counts, documents,
or chunk config disagree with the manifest. `cs30.chunking.load_retrieval_corpus`
remains the v1 reader and cannot read a v2 corpus.

## Re-parsing from the PDFs

The OpenStax adapter can re-parse PDFs through M2's vendored parser 1.3.2.
That is not a complete v2 source route yet: CK-12 is required, but its raw PDF
parser is not vendored. The source installer therefore rejects `--format raw`
for the current four-book catalogue. Use the pinned parsed releases for a full
development corpus.

## M4 production chunking policy

Real builds use `V2ProductionChunker`; synthetic fixture builds retain the
one-block adapter. The production chunker groups whole parser blocks toward a
500-token target, keeps chunks within one chapter and (by default) one section,
and records every source block as a structural span. The accepted range is
100–600 tokens, except when one indivisible parser block is itself oversized.

The frozen ruler is the BERT WordPiece tokenizer from
`google-bert/bert-base-uncased`, pinned at revision
`86b5e0934494bd15c9632b12f734a8a67f723594`. Both values are recorded in the
chunk config hash and metadata. Retrieval includes body, example,
figure-caption, glossary, table, and equation blocks. Assessment-like problem
and summary blocks remain excluded to avoid evaluation leakage.

Evidence policy `v2-retrieval-evidence-v2` also applies structural exclusions
before token grouping. Every block in sections named `Section Summary`,
`Conceptual Questions`, `Problems & Exercises`, `Problems and Exercises`, or
`Chapter Review` (and section names beginning with `Test Prep`) is excluded,
including media blocks whose own `content_type` is otherwise eligible. A
`check_understanding` block starts a CYU exclusion run. The run ends at a new
section or chapter, an `example` or `glossary` block, or the next formal
heading. Short `Strategy`, `Solution`, and `Discussion` headings do not end a
CYU run; outside one, they remain attached to their worked example as heading
spans instead of forcing tiny standalone chunks.

The three-book development validation using M2 parser 1.3.2 data produced the
following distribution. It is diagnostic-only and must be rerun when the
official source set changes.

| Metric | Structure-aware v2 result |
| --- | ---: |
| Chunk count | 5,976 |
| Chunks below 100 tokens | 875 (14.6%) |
| Chunks below 30 tokens | 182 |
| Median token count | 364 |
| Oversized indivisible chunks | 3 |

Corpus duplicate QA reports exact normalized source-block reuse across
textbooks. It does not treat ordinary repeated phrases within one book as
duplicates. Exact duplicate chunk text remains available at each source
location by default; setting `reject_duplicate_text=true` instead makes a build
fail closed at the chunk layer.

## Notes for M2, M4 and M5

- The adapter keeps M2's schema 1.0 output unchanged. M2's `document_hash` is
  the PDF's SHA-256 and becomes the v2 `raw_source_sha256`; the v2
  `document_hash` and `document_id` are recomputed from the parsed content.
- Block IDs keep M2's own document-ID prefixes, and a delivered JSON whose
  `document_id` breaks M2's prefix rule is rejected (`ASSET_VERSION_MISMATCH`),
  so both routes give the same IDs.
- A new M2 delivery means new pins: update `expected_parsed_sha256` in
  `src/cs30/v2/catalog.py`, and the archive name and member paths in
  `src/cs30/v2/sources.py`.
- M4's chunker receives the `TextbookDocument` this build parses; it never
  reads M2's files directly.
- The index artifact records the model, its resolved revision, dimension,
  metric, normalisation, and how many chunks exceed the model's input limit.
