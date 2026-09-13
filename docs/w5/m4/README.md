# Week 5 Member 4 delivery

This folder documents the M4 outputs for:

- [#122 — Rebuild the unified corpus on the frozen document](https://github.com/yshe0376/cs30-personalised-rag/issues/122)
- [#123 — Map gold spans to stable chunk sets](https://github.com/yshe0376/cs30-personalised-rag/issues/123)

The implementation and 34-chapter engineering corpus were built on 2026-09-12
from M2's local archive and M3 Gold v0.1 merged in PR #135. M3 labels all 20
records `m3_initial`, and M2's supplied QA files still mark their manual samples
pending. The generated bundle is therefore reproducible engineering evidence,
not a reportable production evaluation corpus.

## Fixed W5 configuration

`src/cs30/chunking/official.py` is the single configuration for this week:

| Setting | Value |
| --- | --- |
| Config ID | `w5-m4-official-v1` |
| Chunker version | `0.5.0` |
| Target / minimum / maximum | `500 / 100 / 600` model-token counts |
| Boundary policy | Whole parser blocks; never cross a chapter; isolate sections |
| Included content | body, example, figure caption, glossary, table, equation |
| Excluded content | headings, objectives, exercises, checks, sidebars, summaries, other |
| Embedding context | Off; cited text and embedding input are identical |
| Duplicate policy | Preserve source-distinct copies and report duplicate-text groups |
| M5 model | `sentence-transformers/all-MiniLM-L6-v2` |

The official build loads the real M5 SentenceTransformer tokenizer and reads
the model's `max_seq_length` at runtime. It records every over-limit embedding
input in `anomalies.json`; it never hides model truncation behind the 500-token
grouping target.

## Output layout

Keep generated files together and separate from source code:

```text
artifacts/w5/m4/
├── source_corpus/
│   ├── corpus_manifest.json
│   └── openstax_document.json
├── gold_normalized/
│   └── gold_v0_2.jsonl
├── corpus/
│   ├── anomalies.json
│   ├── manifest.json
│   ├── records.jsonl
│   ├── sample_records.jsonl
│   ├── schema.json
│   ├── statistics.json
│   └── traceback_records.json
└── gold_mapping_diagnostic/
    ├── alignment_issues.json
    ├── gold_to_chunk_mapping.json
    └── matching_rule.json
```

`artifacts/` is intentionally git-ignored because real textbook and evaluation
data may be large or restricted. The versioned scripts, schemas, tests and this
handoff document are committed. Share the generated bundle through the team's
approved artifact location and record its hashes in the Project issue.

## Prepare M2 and M3 inputs

Merge M2's per-chapter archive and bind M3's immutable chapter-local spans to
the resulting corpus version:

```bash
python -m cs30.evaluation.cli prepare-corpus \
  --archive PATH/TO/M2/data.zip \
  --output-dir artifacts/w5/m4/source_corpus

python -m cs30.evaluation.cli normalize-gold \
  --gold m3_gold/gold_v0_1.jsonl \
  --document artifacts/w5/m4/source_corpus/openstax_document.json \
  --corpus-manifest artifacts/w5/m4/source_corpus/corpus_manifest.json \
  --output artifacts/w5/m4/gold_normalized/gold_v0_2.jsonl
```

## Build the shared corpus

Install the M5 dependencies, then run:

```bash
python -m pip install -e ".[dev,ml]"

python scripts/build_w5_m4_delivery.py \
  --document artifacts/w5/m4/source_corpus/openstax_document.json \
  --output-dir artifacts/w5/m4/corpus
```

For a reproducibility check, preserve the first manifest and rebuild to a new
folder:

```bash
python scripts/build_w5_m4_delivery.py \
  --document PATH/TO/M2/openstax_document.json \
  --output-dir artifacts/w5/m4/corpus-rebuild \
  --expected-manifest artifacts/w5/m4/corpus/manifest.json
```

The command fails before accepting the delivery if:

- fewer than 20 chunks are available for trace-back sampling;
- samples do not cover chapter starts/ends, formulas, short source blocks and
  cross-block evidence;
- the real embedding model does not expose a sequence limit; or
- a rebuild changes corpus, document, chunk-config or embedding identity.

## M3 gold-span input

The official input is M1-normalized Gold schema v0.2. Raw M3 coordinates remain
chapter-local, while `corpus_char_start` and `corpus_char_end` bind each span to
the prepared corpus. M4 preserves core OR-of-AND grouping and partial-evidence
membership as mapping provenance and never changes M3's answers or annotations.

## Build the versioned mapping

```bash
python scripts/map_gold_spans.py \
  --gold artifacts/w5/m4/gold_normalized/gold_v0_2.jsonl \
  --corpus-dir artifacts/w5/m4/corpus \
  --document artifacts/w5/m4/source_corpus/openstax_document.json \
  --source-corpus-manifest artifacts/w5/m4/source_corpus/corpus_manifest.json \
  --output-dir artifacts/w5/m4/gold_mapping
```

The fixed rule is `same_source_half_open_overlap@1.0`: a chunk matches a gold
span only when both belong to the same document and chapter and their half-open
character intervals overlap. All matching chunk IDs are retained. Whitespace
between adjacent parser blocks does not make an otherwise complete evidence
span partial.

The normal command fails if any gold span lacks full substantive-character
coverage. `--allow-partial` exists only for diagnosing M2/M3 alignment errors.
It must not be used for the production M1 metric input.

The 2026-09-12 diagnostic resolves all 20 spans against M2's source document,
but the M4 filter covers only 17. Two spans point to `problem` blocks and one
points to a `summary` block. Those categories are intentionally excluded, so
M4 does not emit `evaluation_mapping_v0_1.json` until M3 supplies reviewed
in-filter evidence or the team approves a versioned filter change. See
`M3_ALIGNMENT_ISSUES.md`.

To prove that a rebuild did not silently change Recall units:

```bash
python scripts/map_gold_spans.py \
  --gold artifacts/w5/m4/gold_normalized/gold_v0_2.jsonl \
  --corpus-dir artifacts/w5/m4/corpus-rebuild \
  --document artifacts/w5/m4/source_corpus/openstax_document.json \
  --source-corpus-manifest artifacts/w5/m4/source_corpus/corpus_manifest.json \
  --output-dir artifacts/w5/m4/gold-mapping-rebuild \
  --expected-mapping artifacts/w5/m4/gold_mapping/gold_to_chunk_mapping.json
```

## Downstream handoff

- M5 and M6 consume the same `corpus/records.jsonl` named by the manifest.
- M5 reviews every `overlong_embedding_input` disposition before accepting the
  index.
- M1 consumes `evaluation_mapping_v0_1.json` only after every span is fully
  covered; `gold_to_chunk_mapping.json` remains the detailed M4 audit record.
- Any corpus, chunk-config, tokenizer, gold-data or rule change produces a new
  identity and requires rebuilding both the index and the gold mapping.
