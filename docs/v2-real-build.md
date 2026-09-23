# v2 build from the real textbook PDFs

Install with `python -m pip install -e ".[ml,parse]"`: `[parse]` is PyMuPDF and
pdfplumber for M2's OpenStax parser, `[ml]` is FAISS and sentence-transformers
for the dense index.

## 1. Install the pinned sources

The catalogue pins each textbook's PDF SHA-256, so the installer verifies every
file while it reads it and never overwrites a local file that differs.

```sh
python scripts/install_v2_sources.py                       # from the Release
python scripts/install_v2_sources.py --from-dir ~/Downloads  # from local PDFs
python scripts/install_v2_sources.py --print-sha256sums    # for the Release notes
```

PDFs land in `data/raw/v2/<textbook_id>.pdf`, which is git-ignored. `--from-dir`
matches files by hash, not by name, so it also checks a delivery before it is
uploaded: files that match no pin are listed and skipped.

## 2. Build a diagnostic corpus from the PDFs

```sh
python scripts/build_v2_corpus.py --config real-development \
  --output-dir artifacts/v2/textbooks/2.0.0-dev.2 \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2
```

This runs M2's parser 1.3.2 through `cs30.v2.ingest.OpenStaxPdfParser`, chunks
with M1's block adapter, writes `records.jsonl`, `manifest.json`,
`duplicate_blocks.json`, `run_report.json`, and — when a model is given — an
index under `index/` plus `artifact.json`. Without `--embedding-model` the build
publishes the corpus and no index. Parsing three full books takes minutes.

Every development build is marked `reportable=false`: it is for M4, M5, and M6
to work against, never a formal result.

## 3. What an official build still needs

`--config staging` runs `corpus_mode=official`, which fails closed. Today it
stops at:

| Gate | Failure code | Who clears it |
|---|---|---|
| M1's block chunker is a fixture | `FIXTURE_NOT_ALLOWED` | M4's production chunker |
| No CK-12 book in the catalogue | `REQUIRED_PROVIDER_MISSING` | M2 chooses the CK-12 book |
| No embedding model configured | `INDEX_BUILDER_NOT_CONFIGURED` | M5 picks the v2 model |

An official build also needs every source hash pinned (all three OpenStax books
already are), the parser provider to match the catalogue, and the index artifact
to match the staged corpus; the pipeline checks all of that itself.

## Reading an index back

```python
from cs30.v2.indexing import load_faiss_index

loaded = load_faiss_index(Path("artifacts/v2/textbooks/2.0.0-dev.2"))
loaded.search(query_vectors, top_k=5)   # [(chunk_id, score), ...] per query
```

The loader re-hashes `records.jsonl` against the manifest and checks the
artifact's chunk order, so an index can never be paired with a different corpus.
FAISS row *i* is always record line *i*.

## Notes for M2 and M5

- The adapter keeps M2's schema 1.0 output unchanged. M2's `document_hash` is
  the PDF's SHA-256 and becomes the v2 `raw_source_sha256`; the v2
  `document_hash` and `document_id` are recomputed from the parsed content.
- Block IDs keep M2's own document-ID prefixes, so a pipeline run can be
  compared with M2's delivered outputs.
- The document records `library.PyMuPDF`, `library.pdfplumber`, and
  `library.pdfminer.six` in its metadata: parser output depends on those
  versions, and M2 validated 1.3.2 with PyMuPDF 1.26.6 and pdfplumber 0.11.8.
- The index artifact records the model, its resolved revision, dimension,
  metric, normalisation, and how many chunks exceed the model's input limit.
