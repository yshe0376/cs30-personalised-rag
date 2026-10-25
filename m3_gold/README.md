# M3 Gold Dataset v0.1.3

This directory contains the final M3 Gold v0.1.3 delivery: reviewed Strong and
Multi candidate pools, the integrated Gold JSONL, its schema, and the scripts
used to build and screen the dataset.

## Files

- `final_v0_1_1/gold_v0_1_3.jsonl`: authoritative final Gold JSONL.
- `final_v0_1_1/CHANGELOG_v0_1_3.md`: release notes and validation summary.
- `final_v0_1_1/gold_review_audit_v0_1_3.jsonl`: integration audit.
- `final_v0_1_1/gold_integration_conflicts_v0_1_3.csv`: conflict report.
- `final_v0_1_1/gold_validation_report_v0_1_3.json`: validation report.
- `gold_v0_1_1.schema.json`: unchanged legacy v0.1.1 JSON Schema.
- `gold_v0_1_3.schema.json`: schema for the final v0.1.3 JSONL contract.
- `candidate_pool_strong_v1_3_2.csv`: reviewed Strong candidate pool.
- `candidate_pool_multi_v1_3_2.csv`: reviewed Multi-evidence candidate pool.
- `build_final_gold_dataset.py`: reproducible Gold integration script.
- `screen_strong_single_evidence.py`: Strong candidate screener.
- `screen_multi_evidence.py`: Multi-evidence candidate screener.
- `candidate_screening_common.py`: shared screening and CSV-schema utilities.
- `validate_gold.py`: standalone schema validation, with optional prepared-corpus replay.

## Evidence Semantics

`gold_core_evidence_sets` is an OR-of-ANDs. The outer list contains alternative
sufficient evidence paths; every span inside one inner list must be retrieved
together for that path. For example, `[[span_A, span_B], [span_C]]` means either
`span_A` and `span_B` jointly support the answer, or `span_C` alone supports it.

`partial_evidence` is diagnostic only and never counts as a complete Gold hit.

Each span uses chapter-local coordinates: `char_start`, `char_end`,
`chapter_char_start`, and `chapter_char_end` all refer to offsets inside the
span's `chapter_id`. Normalization is responsible for binding these raw spans
to corpus-global coordinates. Each span carries `block_id`; it does not carry
`content_type`. Consumers should look up the block type from the shared prepared
corpus.

Evidence is restricted by the shared W5 policy to `body`, `equation`, `example`,
`figure_caption`, `glossary`, and `table`. If the best match is only in
`summary`, `learning_objective`, `problem`, or another excluded block type, the
item should be replaced with allowed evidence or moved to unresolved review.

The final release uses Gold annotation version `m3_gold_v0.1.3`, corpus version
`2.0.0-dev.m4-structure-v2-main-3553825`, and parser version `1.3.2` for the
exported records. The final JSONL intentionally retains `annotation_status:
draft` and pending personalisation fields: the completed CSV
`manual_review` decisions are the authoritative source for evidence acceptance,
while those Gold-level fields belong to a later annotation-status contract.

## Validation

Validate the final JSONL without regenerating it:

```sh
python3 m3_gold/validate_gold.py \
  --schema m3_gold/gold_v0_1_3.schema.json \
  m3_gold/final_v0_1_1/gold_v0_1_3.jsonl
```

Validate a legacy v0.1.1 file with the unchanged legacy schema:

```sh
python3 m3_gold/validate_gold.py \
  --schema m3_gold/gold_v0_1_1.schema.json \
  m3_gold/gold_v0_1_1.jsonl
```

To reproduce the final Gold integration, provide the external evidence inputs:

```sh
python3 m3_gold/build_final_gold_dataset.py \
  --strong m3_gold/candidate_pool_strong_v1_3_2.csv \
  --multi m3_gold/candidate_pool_multi_v1_3_2.csv \
  --schema m3_gold/gold_v0_1_3.schema.json \
  --blocks <openstax-m3-evidence>/combined/evidence_source_blocks.jsonl \
  --manifest <openstax-m3-evidence>/combined/corpus_manifest.json \
  --ck12-blocks <ck12-m3-adapter>/evidence_source_blocks.jsonl \
  --ck12-manifest <ck12-m3-adapter>/corpus_manifest.json \
  --output-dir m3_gold/final_v0_1_1
```

OpenStax inputs originate from the OpenStax parser v1.3.2 and must use the
combined evidence-block manifest. CK-12 inputs originate from the CK-12 M3
adapter. In this checkout the available CK-12 manifest identifies
`ck12-people-physics-2016-09-09` / `ck12-1.1.0` and supports the 82 CK-12
spans. The review target
`2.0.0-dev.m4-four-book-main-a1fe99e` is not present in this repository, so
four-book M4 alignment remains an external follow-up and is not claimed as
verified here.

The parser corpora, caches, and local environments are intentionally not
committed. The upstream OpenStax parser and CK-12 adapter outputs must be
available at the paths supplied above when reproducing the integration.
