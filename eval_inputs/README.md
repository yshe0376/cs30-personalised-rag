# Evaluation inputs for the frozen W5 corpus

The normalized Gold and the Gold-to-chunk mapping that `cs30-evaluate` reads.
Both are derived from the frozen corpus, and both must be regenerated together
whenever that corpus changes, so they are kept in one directory rather than
next to their separate producers.

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

`cs30.evaluation.metrics.validate_artifact_compatibility` rejects a scoring run
whose Gold, mapping and run manifest disagree on these, so a stale file fails
loudly instead of producing wrong metrics.

Coverage: 20 questions, 21 evidence spans, 0 excluded. Every core span in
`m3_gold_v0.1.1` is mapped, so no question is dropped as
`retrieval.excluded_runs.mapping_missing`.

## Usage

```bash
cs30-evaluate score \
  --gold eval_inputs/gold_v0_2_from_m3_v0_1_1.jsonl \
  --mapping eval_inputs/evaluation_mapping_v0_1.json \
  --runs <saved run results>
```

## Known gap: formal runs are still blocked

Every record here carries `annotation_status: m3_initial`, inherited unchanged
from the M3 source. `assert_reportable_gold` requires
`annotation_status: reviewed`, and it is enforced both in `run_batch` and in
`score_saved_run`, so a manifest with `reportable=True` fails with:

    reportable Gold requires annotation_status=reviewed

Development-mode runs and scoring are unaffected and work today. Marking these
records reviewed is an M3 annotation decision, not a code change; the review
record exists at `m3_gold/candidate_pool_v0_1_1.review_labeled.csv` but has not
been reflected into the field.

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
