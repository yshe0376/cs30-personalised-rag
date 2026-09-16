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

Client-readable metric cells retain numerator, denominator, and value. The
combined report also preserves abstention causes, answerability outcomes,
per-citation validity, chunk/source traceability, execution status, and failure
labels from the underlying score artifacts.

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

Formal comparisons require one globally frozen `lambda*`. Every baseline and
frozen pair must contain exactly the same unique question IDs; missing, extra,
or duplicate questions fail before any delta is reported.

## Blinded level-adaptation ratings

Use `prepare-blind-ratings` to build a single-rater CSV sheet from saved run
files. Only normally answered runs enter the sheet; abstentions and technical
failures remain in automated error analysis. The sheet contains the question,
assigned level, answer choice, and explanation, but excludes run, condition,
lambda, retrieval, prompt, and model identifiers. A separate private key maps
the random answer identifiers back to run IDs.

The optional `--ratings` CSV or JSONL contains the completed manual scores. It deliberately has
no run, condition, or lambda field: the rater receives a random blinded answer
identifier. A separate private `--rating-key` file joins that identifier back
to the saved run only after scoring is complete. A third `--rating-rubric`
manifest freezes the rubric version and score range instead of hard-coding an
unapproved scale in the evaluator.

```json
{"schema_version":"0.1","rating_id":"rating-001","question_id":"q-001","blinded_answer_id":"answer-A17","assigned_level":"beginner","score":4,"rubric_version":"level-fit-v1","rater_id":"rater-1"}
```

```json
{"schema_version":"0.1","blinded_answer_id":"answer-A17","run_id":"run-001"}
```

```json
{"schema_version":"0.1","rubric_version":"level-fit-v1","score_min":1,"score_max":5}
```

The team must freeze the rubric and range before formal rating. If no rating
package is supplied, the report marks the section `pending`; it does not infer
adaptation quality from answer accuracy. When a rating package is supplied,
every answer in its private key must have exactly one score; incomplete sheets
fail instead of producing a partial formal aggregate.

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
  "parser_version": "parser-v1",
  "annotation_date": "2026-09-16",
  "annotator_ids": ["primary-annotator"],
  "double_annotated": false,
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

The audit checks the file hash, record count, record schema version, corpus and
parser identities, question IDs, span/chunk references, and the relationship
between each question and evidence reference. It reports the single annotator
and package versions. It explicitly records that Role semantic quality and IAA
were not assessed by M8.

For `reference_universe=corpus_records`, pass M4's final `records.jsonl` through
`--role-records`; the audit then checks every Role reference against the full
frozen chunk universe. Also pass a normalized JSONL of authoritative
`question_id`/`chunk_id` pairs through `--role-question-references`; this is
needed to reject a valid chunk that belongs to a different question.
`gold_mapping` is available only when the Role package is intentionally limited
to chunks in the Gold mapping.

## Command

After the team freezes the rating rubric, create the single-rater material from
the saved model outputs. Keep the key and randomisation seed private until the
sheet has been completed:

```powershell
cs30-evaluate prepare-blind-ratings `
  --runs artifacts/plain/run_results.jsonl artifacts/reranked/run_results.jsonl `
  --gold artifacts/gold_v1.jsonl `
  --contexts artifacts/w6_experiment_contexts.jsonl `
  --seed 5703 `
  --output-dir artifacts/w6_blind_rating
```

First run the existing `score` command for every frozen run and retain each
`answer_citation_scores.jsonl`. Then build the cross-run package:

```powershell
cs30-evaluate report-extension `
  --scores artifacts/plain/answer_citation_scores.jsonl artifacts/reranked/answer_citation_scores.jsonl `
  --contexts artifacts/w6_experiment_contexts.jsonl `
  --ratings artifacts/w6_level_adaptation_ratings.jsonl `
  --rating-key artifacts/w6_blinded_answer_key.jsonl `
  --rating-rubric artifacts/w6_level_adaptation_rubric.json `
  --role-manifest artifacts/role_label_provenance_manifest.json `
  --role-gold artifacts/gold_v1.jsonl `
  --role-mapping artifacts/gold_chunk_mapping_v1.json `
  --role-records artifacts/records.jsonl `
  --role-question-references artifacts/question_chunk_relationships.jsonl `
  --output-dir artifacts/w6_evaluation
```

Ratings and Role inputs may be omitted during development. Their report
sections then remain visibly pending. A metric with no valid denominator is
written as `not_applicable`, including refusal Recall/F1 when the Gold set has
no unanswerable samples. Formal lambda reporting is strict by default: every
observed comparison bucket must contain both `lambda=0` and frozen-`lambda*`
groups. `--allow-incomplete` exists only for development fixtures and partial
diagnostics.
