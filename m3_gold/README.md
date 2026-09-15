# M3 Gold Evidence v0.1.1

This directory contains the W5 M3 Gold Evidence handoff. It supersedes the
removed v0.1 draft files.

## Files

- `gold_v0_1_1.jsonl`: final M3 Gold v0.1.1 JSONL for this W5 package.
- `gold_v0_1_1.schema.json`: JSON Schema for one JSONL record.
- `candidate_pool_v0_1_1.review_labeled.csv`: M3 manual review record for accepted candidates.
- `dev_test_split_plan_v0_1_1.md`: deterministic proposed Dev/Test split plan.
- `personalisation_candidate_list_v0_1_1.csv`: provisional M3 personalisation candidate screen.
- `personalisation_candidate_list_v0_1_1.md`: narrative summary of the personalisation screen.
- `validate_gold.py`: validator that uses the shared main evaluation loader and, when supplied, the shared prepared corpus loader.

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

`annotation_status` is `m3_initial` for this package.
`personalisation_eligibility` remains `pending` until M1 finalises the A3
taxonomy.

## Validation

Schema and contract validation without the large corpus:

```sh
python3 m3_gold/validate_gold.py m3_gold/gold_v0_1_1.jsonl
```

Full span replay requires the shared M4 prepared corpus directory and uses
`load_prepared_corpus()` from the main evaluation package:

```sh
python3 m3_gold/validate_gold.py \
  --prepared-corpus-root m3_unified_source_corpus/source_corpus \
  m3_gold/gold_v0_1_1.jsonl
```

The prepared corpus itself is not committed. Rebuild it with
`cs30-evaluate prepare-corpus` as documented in `m3_unified_source_corpus/README.md`.
