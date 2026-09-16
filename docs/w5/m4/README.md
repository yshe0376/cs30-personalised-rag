# W5 M4 official corpus and Gold mapping

This delivery is rebuilt from the current `main` branch and keeps the shared
evidence policy unchanged. It does not run the S1-S6 comparison requested in an
earlier draft.

## Inputs

- M1 prepared 34-chapter corpus: `openstax_document.json`,
  `corpus_manifest.json`, and `evidence_source_blocks.jsonl` in one directory.
- M3 raw Gold: `m3_gold/gold_v0_1_1.jsonl`.
- M1-normalized Gold v0.2 derived from that exact M3 file.

The full prepared `OpenStaxDocument` is the chunking input. Problem, summary,
and conceptual-question blocks remain excluded by the shared evidence policy.

## Rebuild

```bash
python scripts/build_w5_m4_delivery.py \
  --prepared-corpus-dir artifacts/w5/m4-v3/prepared_corpus \
  --output-dir artifacts/w5/m4-v3/retrieval_corpus

python -m cs30.evaluation.cli normalize-gold \
  --gold m3_gold/gold_v0_1_1.jsonl \
  --document artifacts/w5/m4-v3/prepared_corpus/openstax_document.json \
  --corpus-manifest artifacts/w5/m4-v3/prepared_corpus/corpus_manifest.json \
  --output artifacts/w5/m4-v3/gold_normalized/gold_v0_2_from_m3_v0_1_1.jsonl

python scripts/map_gold_spans.py \
  --gold artifacts/w5/m4-v3/gold_normalized/gold_v0_2_from_m3_v0_1_1.jsonl \
  --corpus-dir artifacts/w5/m4-v3/retrieval_corpus \
  --prepared-corpus-dir artifacts/w5/m4-v3/prepared_corpus \
  --output-dir artifacts/w5/m4-v3/gold_mapping \
  --allow-partial
```

`build_w5_m4_delivery.py` fails unless the union of all chunk
`source_block_ids` is exactly the eligible block-ID set in
`evidence_source_blocks.jsonl`. `map_gold_spans.py` repeats this check and
records the result in both the detailed mapping and delivery manifest.

The M1-compatible mapping includes a span only when its detailed entry says
`coverage_status: "full"`. Missing or partially covered spans are skipped;
questions left without any covered span are listed in `delivery_manifest.json`
and remain visible downstream as `retrieval.excluded_runs.mapping_missing`.

## Current verified result

The current `m3_gold_v0.1.1` on `main` replaces the three previously excluded
problem/summary annotations with eligible body/equation evidence. Therefore the
latest rebuild maps all 20 questions (21 spans), rather than the older expected
17 questions. The manifest explicitly records zero excluded questions instead
of preserving a stale three-question exclusion.

Generated runtime artifacts stay under `artifacts/w5/m4-v3/` and are ignored by
Git. The compact, reviewable run manifest is committed beside this README.
