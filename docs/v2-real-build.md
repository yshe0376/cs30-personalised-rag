# v2 build from the real textbooks

Real builds read M2's parsed delivery, not the PDFs: one
`openstax_document.json` per book from the Release
[`M2_data_ingestion`](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/M2_data_ingestion).
Install with `python -m pip install -e ".[ml]"`; `[ml]` is FAISS and
sentence-transformers for the dense index. `[parse]` (PyMuPDF and pdfplumber)
is only needed to re-parse the PDFs (see the last section).

## 1. Install M2's parsed delivery

The catalogue pins the SHA-256 of each book's parsed JSON, so the installer
verifies every file while it reads it and never overwrites a local file that
differs.

```sh
python scripts/install_v2_sources.py                          # from M2's Release
python scripts/install_v2_sources.py --from-archive openstax_parser_v1_3_2_r1.zip
```

The files land in `data/parsed/v2/<textbook_id>.json`, which is git-ignored.
The first command downloads M2's archive (about 45 MB) once, takes the three
`openstax_document.json` files out of it, and deletes it.

## 2. Build a diagnostic corpus

```sh
python scripts/build_v2_corpus.py --config real-development \
  --output-dir artifacts/v2/textbooks/2.0.0-dev.2 \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2
```

This reads each file through `cs30.v2.ingest.OpenStaxParsedParser`, chunks with
M4's production structure-aware chunker, and writes `records.jsonl`,
`manifest.json`,
`duplicate_blocks.json`, `run_report.json`, and — when a model is given — an
index under `index/` plus `artifact.json`. Without `--embedding-model` the build
publishes the corpus and no index; the three books then build in well under a
minute.

The pipeline checks each file against its pin (`SOURCE_HASH_MISMATCH`) and
checks that the document names the pinned PDF as its raw source
(`HASH_MISMATCH`). The manifest's `raw_source_sha256` is therefore always the
PDF hash, whichever route built the corpus.

Every development build is marked `reportable=false`: it is for M4, M5, and M6
to work against, never a formal result.

## 3. What an official build still needs

`--config staging` runs `corpus_mode=official`, which fails closed. Today it
stops at:

| Gate | Failure code | Who clears it |
|---|---|---|
| No CK-12 book in the catalogue | `REQUIRED_PROVIDER_MISSING` | M2 chooses the CK-12 book |

An official build also needs every source hash pinned (all three OpenStax books
already pin both the PDF and the parsed JSON), the parser provider to match the
catalogue, and the index artifact to match the staged corpus; the pipeline
checks all of that itself.

## Reading an index back

```python
from cs30.v2.indexing import load_faiss_index

loaded = load_faiss_index(Path("artifacts/v2/textbooks/2.0.0-dev.2"))
loaded.search(query_vectors, top_k=5)   # [(chunk_id, score), ...] per query
```

The loader re-hashes `records.jsonl` against the manifest and checks the
artifact's chunk order, so an index can never be paired with a different corpus.
FAISS row *i* is always record line *i*.

## Re-parsing from the PDFs

`--source-format raw` runs M2's vendored parser 1.3.2 through
`cs30.v2.ingest.OpenStaxPdfParser` on the pinned PDFs instead. It needs the
`[parse]` extra, and parsing three full books takes minutes. The PDF Release
`v2-sources-openstax-v1` has not been published, so install the PDFs from a
local folder:

```sh
python scripts/install_v2_sources.py --format raw --from-dir ~/Downloads
python scripts/install_v2_sources.py --format raw --print-sha256sums  # for a PDF Release
python scripts/build_v2_corpus.py --config real-development --source-format raw \
  --output-dir artifacts/v2/textbooks/2.0.0-dev.2-raw
```

PDFs land in `data/raw/v2/<textbook_id>.pdf`. `--from-dir` matches files by
hash, not by name, so it also checks a delivery before it is uploaded. A
re-parse that reproduces M2's output yields the same documents and chunk IDs as
the parsed route. Parser output depends on the PyMuPDF and pdfplumber versions;
M2 validated 1.3.2 with PyMuPDF 1.26.6 and pdfplumber 0.11.8, and a re-parse
records the versions it used in the document metadata.

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
and summary blocks remain excluded to avoid evaluation leakage. Exact duplicate
text is retained at each source location and reported by corpus QA.

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
