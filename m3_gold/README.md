# M3 Gold Dataset v0.1.3

This directory contains the final M3 Gold v0.1.3 delivery: reviewed Strong and
Multi candidate pools, the integrated Gold JSONL, its schema, and the scripts
used to build and screen the dataset.

## Files

- `final_v0_1_1/gold_v0_1_3.jsonl`: authoritative final Gold JSONL.
- `final_v0_1_1/CHANGELOG_v0_1_3.md`: release notes and validation summary.
- `gold_v0_1_1.schema.json`: JSON Schema for one JSONL record.
- `candidate_pool_strong_v1_3_2.csv`: reviewed Strong candidate pool.
- `candidate_pool_multi_v1_3_2.csv`: reviewed Multi-evidence candidate pool.
- `build_final_gold_dataset.py`: reproducible Gold integration script.
- `screen_strong_single_evidence.py`: Strong candidate screener.
- `screen_multi_evidence.py`: Multi-evidence candidate screener.
- `candidate_screening_common.py`: shared screening and CSV-schema utilities.
- `test_build_final_gold_dataset.py`: integration validation tests.

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
`2.0.0-dev.m4-structure-v2-main-3553825`, and parser version `1.3.2`.

## Validation

Schema and contract validation:

```sh
python3 m3_gold/test_build_final_gold_dataset.py
```

The parser corpora are kept outside this delivery branch. Screening and
integration commands must be given the appropriate local evidence-corpus and
manifest paths; the expected parser version is `1.3.2`.
