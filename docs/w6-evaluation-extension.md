# W6 Evaluation Extension

## Purpose and boundary

The W6 extension combines the existing offline answer and citation scores with
the experiment metadata needed for the six-textbook personalisation report. It
does not change `EvaluationRunResult`, `RunManifest`, Gold, mapping, retrieval,
generation, or Role-label contracts. It does not rerun retrieval or generation.

The extension keeps three evidence sources separate:

1. automated per-question scores produced by the existing M8 scorer;
2. blinded manual level-adaptation ratings;
3. an identity and reference audit of the M3 Role-label package.

M8 does not assess Role-label semantics and does not compute Evidence Role IAA.

## Report structure

The original five answer/citation artifacts remain unchanged. The extension
adds one client-readable Markdown report and six machine-readable artifacts:

- `w6_evaluation_summary.json`
- `w6_experiment_groups.csv`
- `w6_lambda_comparison.csv`
- `w6_failure_analysis.csv`
- `w6_level_adaptation_scores.json`
- `role_label_provenance_report.json`
- `w6_evaluation_report.md`

The Markdown report presents the combined result. The separate files preserve
the origin of automated metrics, human ratings, and provenance checks so they
cannot be mistaken for one another.

## Experiment context input

`--contexts` is an M8-owned JSONL sidecar with one row for every `run_id` in the
input score files. It annotates existing scores without changing the shared run
schema.

```json
{"schema_version":"0.1","run_id":"run-001","question_id":"q-001","condition_id":"plain","comparison_id":"prompt-controlled-reranking","textbook_id":"openstax_college_physics_2e","student_level":"beginner","lambda_weight":0.0,"lambda_status":"baseline"}
```

`comparison_id` explicitly pairs the two conditions being compared. This
prevents plain/prompt-only and reranking-only/combined runs from being combined
accidentally. A baseline row must use `lambda_weight=0`. The extension also
retains mode, data version, split, and corpus version from the source score
record, so Dev and Test or different corpora cannot be mixed.

## Blinded level-adaptation ratings

The optional `--ratings` JSONL contains the manual scores. It deliberately has
no run, condition, or lambda field: the rater receives a random blinded answer
identifier. A separate private `--rating-key` file joins that identifier back
to the saved run only after scoring is complete.

```json
{"schema_version":"0.1","rating_id":"rating-001","question_id":"q-001","blinded_answer_id":"answer-A17","assigned_level":"beginner","score":4,"rubric_version":"level-fit-v1","rater_id":"rater-1"}
```

```json
{"schema_version":"0.1","blinded_answer_id":"answer-A17","run_id":"run-001"}
```

Scores use a 1-5 scale. The team must freeze the rubric before formal rating.
If no rating file is supplied, the report marks the section `pending`; it does
not infer adaptation quality from answer accuracy.

## Role-label provenance audit

The optional Role audit requires `--role-manifest`, `--role-gold`, and
`--role-mapping` together. The M8 sidecar records package identity, checksum,
annotation date, annotator count, and the field names used by M3's JSONL. This
adapts the final M3 file without redefining its schema.

```json
{
  "schema_version": "0.1",
  "role_schema_version": "role-schema-v1",
  "role_taxonomy_version": "role-taxonomy-v1",
  "annotation_version": "role-labels-v1",
  "corpus_version": "six-textbooks-v1",
  "annotation_date": "2026-09-16",
  "annotator_ids": ["primary-annotator"],
  "labels_file": "evidence_role_labels_v1.jsonl",
  "labels_sha256": "<64 lowercase hexadecimal characters>",
  "declared_record_count": 240,
  "question_id_field": "question_id",
  "reference_id_field": "chunk_id",
  "reference_type": "chunk",
  "reference_universe": "corpus_records",
  "role_field": "role",
  "record_schema_version_field": "schema_version"
}
```

The audit checks the file hash, record count, record schema version, corpus
identity, question IDs, and span/chunk references. It reports the single
annotator and package versions. It explicitly records that Role semantic
quality and IAA were not assessed by M8.

For `reference_universe=corpus_records`, pass M4's final `records.jsonl` through
`--role-records`; the audit then checks every Role reference against the full
frozen chunk universe. `gold_mapping` is available only when the Role package
is intentionally limited to chunks in the Gold mapping.

## Command

First run the existing `score` command for every frozen run and retain each
`answer_citation_scores.jsonl`. Then build the cross-run package:

```powershell
cs30-evaluate report-extension `
  --scores artifacts/plain/answer_citation_scores.jsonl artifacts/reranked/answer_citation_scores.jsonl `
  --contexts artifacts/w6_experiment_contexts.jsonl `
  --ratings artifacts/w6_level_adaptation_ratings.jsonl `
  --rating-key artifacts/w6_blinded_answer_key.jsonl `
  --role-manifest artifacts/role_label_provenance_manifest.json `
  --role-gold artifacts/gold_v1.jsonl `
  --role-mapping artifacts/gold_chunk_mapping_v1.json `
  --role-records artifacts/records.jsonl `
  --output-dir artifacts/w6_evaluation
```

Ratings and Role inputs may be omitted during development. Their report
sections then remain visibly pending. A metric with no valid denominator is
written as `not_applicable`, including refusal Recall/F1 when the Gold set has
no unanswerable samples.
