# Evaluation inputs for the frozen W5 corpus

The normalized Gold, the Gold-to-chunk mapping and the Dev/Test split manifest
that `cs30-evaluate` and the Member 7 lambda search read. All three are bound to
the frozen corpus, and they must be regenerated together whenever that corpus
or the Gold changes, so they are kept in one directory rather than next to
their separate producers.

They are committed rather than distributed as release assets because they total
about 100 KB, `cs30-evaluate score` requires them on every run, and a change to
either must be visible in a diff. The corpus they are bound to is 30 MB and is
a release asset instead; see the repository README for how to fetch it.

## Files

- `gold_v0_2_from_m3_v0_1_1.jsonl`: M1-normalized Gold v0.2, produced by
  `cs30-evaluate normalize-gold` from `m3_gold/gold_v0_1_1.jsonl`. It carries
  the same questions and evidence as the M3 source, with each span resolved to
  corpus-global coordinates. All 21 spans are `resolution_status: resolved` via
  `resolution_method: block_id`.
- `evaluation_mapping_v0_1.json`: the M1-compatible Gold-to-chunk mapping.
  This is the file `--mapping` takes. It loads as
  `cs30.evaluation.mapping.GoldChunkMapping`.
- `gold_to_chunk_mapping.json`: the detailed mapping, which additionally
  records every overlapping chunk and each span's `coverage_status`. Use it to
  audit a mapping decision; it is not the scoring input.
- `matching_rule.json`: the rule that decided chunk relevance, with `rule_id`,
  `rule_version` and `rule_hash`. The report cites this rather than describing
  the overlap predicate in prose.
- `split_manifest.json`: the final Dev/Test split, 12 Dev and 8 Test questions,
  with the question IDs and evidence chapters of each side. The lambda search
  reads `expected_question_count` from it to prove no Dev question is missing.
  The split isolates by chapter (Dev uses chapters 2-16, Test 18-33), so no
  chapter and no `concept_group` appears on both sides.

The delivery manifest for the mapping is committed separately at
`docs/w5/m4/delivery_manifest.json`. Its content is identical to the copy that
ships inside M4's output directory, so it is not duplicated here. If M4
regenerates the mapping, update that one file rather than adding a second copy.

## Identity

Every file here is valid only against the exact corpus and Gold it was derived
from. These values must agree with the artifacts being scored:

| Field | Value |
|---|---|
| `corpus_version` | `openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864` |
| `chunk_config_hash` | `sha256:4c3c35e13eec2dc04a5fea85ebd912704846d04f31dd2d9006eb36f0db264b61` |
| `mapping_version` | `mapping-5f8f4ef9976b4440` |
| `gold_annotation_version` | `m3_gold_v0.1.1` |
| `normalizer_version` | `gold-normalizer-0.1` |
| `split_version` | `split-v1` |

`cs30.evaluation.metrics.validate_artifact_compatibility` rejects a scoring run
whose Gold, mapping and run manifest disagree on these, so a stale file fails
loudly instead of producing wrong metrics.

Coverage: 20 questions, 21 evidence spans, 0 excluded. Every core span in
`m3_gold_v0.1.1` is mapped, so no question is dropped as
`retrieval.excluded_runs.mapping_missing`.

## Usage

A reportable Dev run, then its score. The run must start from a clean Git
worktree, and `--mapping-version` is what makes it reportable. Point
`CS30_INDEX_DIR` at an index built from the frozen corpus.

`--chunk-version` takes the mapping's `chunk_config_hash`, not the configuration
name `w5-m4-official-v1`; scoring rejects the run otherwise.

```bash
cs30-evaluate run \
  --gold eval_inputs/gold_v0_2_from_m3_v0_1_1.jsonl \
  --document artifacts/w5/m4-v3/prepared_corpus/openstax_document.json \
  --corpus-manifest artifacts/w5/m4-v3/prepared_corpus/corpus_manifest.json \
  --output runs_dev.jsonl --manifest runs_dev.manifest.json \
  --execution-mode retrieval_only --retrieval-mode hybrid --top-k 5 --split dev \
  --dataset-version m3_gold_v0.1.1 \
  --corpus-version openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864 \
  --chunk-version sha256:4c3c35e13eec2dc04a5fea85ebd912704846d04f31dd2d9006eb36f0db264b61 \
  --gold-annotation-version m3_gold_v0.1.1 \
  --embedding-version <embedding model> --index-version <index version> \
  --mapping-version mapping-5f8f4ef9976b4440

cs30-evaluate score \
  --gold eval_inputs/gold_v0_2_from_m3_v0_1_1.jsonl \
  --document artifacts/w5/m4-v3/prepared_corpus/openstax_document.json \
  --corpus-manifest artifacts/w5/m4-v3/prepared_corpus/corpus_manifest.json \
  --runs runs_dev.jsonl --manifest runs_dev.manifest.json \
  --mapping eval_inputs/evaluation_mapping_v0_1.json --output score_dev.json
```

The same run feeds the Member 7 workflow:

```bash
python -m cs30.generation.prepare_cases \
  --retrieval-runs runs_dev.jsonl --retrieval-manifest runs_dev.manifest.json \
  --gold-mapping eval_inputs/gold_to_chunk_mapping.json \
  --split-manifest eval_inputs/split_manifest.json \
  --target-split dev --input-status formal \
  --output-cases cases_dev.jsonl --output-manifest cases_dev.manifest.json

python -m cs30.generation.lambda_search \
  --cases cases_dev.jsonl \
  --role-label-manifest m3_role_labels/role_labels_v1_provenance_manifest.json \
  --split-manifest eval_inputs/split_manifest.json \
  --input-status provisional --metric-k 3 --output lambda_dev.json
```

## Review status

Every record carries `annotation_status: reviewed`. This reflects a review that
had already happened: `m3_gold/candidate_pool_v0_1_1.review_labeled.csv`
records `m3_decision: accept` for all 20 questions, but the field had been left
at `m3_initial`. The change was made in the source M3 file and this file was
regenerated with `normalize-gold`; only `annotation_status` and `split` differ
from the previous version, and the mapping is unaffected because no evidence
span moved.

With reviewed Gold, `assert_reportable_gold` passes and reportable retrieval
and answer runs work.

## Known limits of the lambda search on this data

Two limits remain and are deliberate for v1.0; neither blocks a run.

- The M3 Role labels cover the Gold chunks only (`reference_universe:
  gold_mapping`), while a formal lambda search needs a label for every
  candidate. Formal mode therefore refuses the package. Provisional mode runs
  and marks its output `not_interpretable`.
- The search requires a candidate pool larger than `metric_k`. The W5 retrieval
  runs return `top_k=5`, so pass `--metric-k` below 5 (for example 3) or supply
  a larger pool.

## Rebuild

These are derived files and are never hand-edited. Regenerating needs the
prepared corpus and the frozen chunk corpus, both release assets.

```bash
cs30-evaluate normalize-gold \
  --gold m3_gold/gold_v0_1_1.jsonl \
  --document artifacts/w5/m4-v3/prepared_corpus/openstax_document.json \
  --corpus-manifest artifacts/w5/m4-v3/prepared_corpus/corpus_manifest.json \
  --output artifacts/w5/m4-v3/gold_normalized/gold_v0_2_from_m3_v0_1_1.jsonl

python scripts/map_gold_spans.py \
  --gold artifacts/w5/m4-v3/gold_normalized/gold_v0_2_from_m3_v0_1_1.jsonl \
  --corpus-dir artifacts/w5/m4-v3/retrieval_corpus \
  --prepared-corpus-dir artifacts/w5/m4-v3/prepared_corpus \
  --output-dir artifacts/w5/m4-v3/gold_mapping
```

`artifacts/` is the Git-ignored regeneration workspace. Copy the results here
only when the corpus they are bound to has actually changed, and commit them in
the same pull request as that change so the pair stays reviewable together. A
new corpus produces a new `mapping_version`.
