# Evaluation contracts and offline scoring

This package is the M1-owned boundary between M3 Gold data, the M1 batch
runner, and M8 answer and citation scoring.

## Gold sample semantics

`GoldSample.gold_core_evidence_sets` uses an outer OR and inner AND structure.
For `[[A, B], [C]]`, retrieving both A and B or retrieving C is sufficient.
Retrieving A alone is partial coverage. `partial_evidence` is retained for
diagnostics and never counts as a complete Gold hit.

Every evidence span uses the half-open interval `[char_start, char_end)` over
canonical `document.text`. Pass a `document_id -> text` mapping to
`load_gold_samples` to verify that every `verbatim_text` replays exactly.

`answerable` is relative to the frozen corpus. It is `null` while an item is
disputed or unresolved; unresolved items must not be silently converted to
unanswerable examples.

### M3 Gold v0.1 input

`load_gold_samples` accepts the M3 W5 v0.1 JSONL shape and retains its option
provenance, source record, and evidence annotation metadata.  M3 spans
carry `chapter_id` and use offsets relative to that chapter's canonical text.
When validating spans, pass both the merged document mapping and a chapter
mapping keyed by `(document_id, chapter_id)`:

```python
from cs30.evaluation import load_gold_samples, load_openstax_document

document = load_openstax_document(
    "data/processed/openstax-w5-v2/openstax_document.json"
)
chapter_documents = {
    (document.document_id, chapter.chapter_id): document.text[
        chapter.char_start : chapter.char_end
    ]
    for chapter in document.chapters
}
gold = load_gold_samples(
    "m3_gold/gold_v0_1.jsonl",
    documents={document.document_id: document.text},
    chapter_documents=chapter_documents,
)
```

The old string-option fixtures remain readable for engineering tests.  M3's
`m3_initial` records are provisional; the v0.1 package itself documents that
all 20 answers are currently `D` and that it contains no unanswerable records,
so it must not be used as a final answer-accuracy or abstention benchmark.

### M1-normalized Gold v0.2 output

`GoldSample` v0.2 is M1's normalized representation of an M3 input. It retains
the raw M3 `char_start` and `char_end` fields as chapter-local offsets and
copies them to `chapter_char_start` and `chapter_char_end`; generic offsets
never become corpus-global coordinates. A span records its normalization
outcome as `resolved`, `stale`, or `ambiguous`. Resolved spans must also carry
`corpus_char_start` and `corpus_char_end`, plus optional `resolved_block_id`
and the method (`block_id`, `chapter_offset`, or `verbatim_unique`) when
available. If a source has no `block_id`, a chapter-local coordinate that
replays its `verbatim_text` is resolved directly with `chapter_offset`; a
non-empty but stale block ID still goes through the guarded unique-text
fallback.

Normalized samples may record `source_corpus_version` and `normalizer_version`
to make the provenance of the M1 transformation explicit. M3 v0.1 remains
loadable without any of these derived fields.

Formal (reportable) run and scoring paths are fail-closed: every Gold span must
be resolved and carry corpus-global coordinates, and every sample must have
`annotation_status=reviewed`. Development and fixture scoring may still use raw
v0.1 Gold for contract and pipeline checks.

## M4 mapping handoff and artifact versions

M3's raw JSONL is immutable. Its `char_start`/`char_end` values are chapter
coordinates, while M1's normalized v0.2 artifact adds explicit
`chapter_char_start`/`chapter_char_end` and derives
`corpus_char_start`/`corpus_char_end` from the prepared merged corpus. M4 can
continue to build mappings from `span_id`, chapter/block identity, and
`verbatim_text`; it does not need to switch to global coordinates.

The regeneration rules are:

| Change | Normalized Gold | M4 mapping |
|---|---|---|
| Chunker or chunk configuration only | Keep it | Regenerate with a new `chunk_config_hash` and `mapping_version` |
| Chapter order, separator, parser, or source text | Normalize the unchanged raw M3 JSONL again for the new `corpus_version` | Regenerate for the new corpus and mapping versions |
| Block split/merge or changed block text | M1 reports stale/ambiguous spans by `span_id`; M3 reviews failed migrations | Regenerate only after the reviewed Gold is normalized |

Never overwrite an old Gold, corpus, manifest, or mapping artifact. Formal
compatibility checks require the same full `corpus_version` in normalized Gold,
mapping, and run manifest, and the same `chunk_config_hash` in mapping and
manifest. The detailed M4 handoff example and checklist are in
[`docs/m4-gold-mapping-handoff.md`](../../../docs/m4-gold-mapping-handoff.md).

## Run-result semantics (v0.2)

`GoldSample` is version `0.1` for raw M3 input and version `0.2` for
M1-normalized output; the per-question run trace is schema version `0.2`.
`EvaluationRunResult.status` has six mutually exclusive
terminal values:

- `retrieval_error`
- `generation_error`
- `parse_error`
- `retrieved`
- `abstained`
- `answered`

The first three are technical errors and cannot contain a final answer. The
`retrieved` state is the successful terminal state for `retrieval_only` runs.
An `abstained` result records an explicit `abstention_cause`: either the
retriever returned no hits (the model was not called), or the model abstained
after receiving evidence. Infrastructure failures are never scored as correct
refusals.

Answer/citation scoring reports abstention at two explicit levels. The existing
`abstention_accuracy`, `abstention_precision`, `abstention_recall`, and
`abstention_f1` metrics are system-level: both `no_retrieval_hits` and
`model_abstained_with_evidence` count as predicted system abstentions. The
`model_abstention_*` metrics evaluate only successful decisions made after the
model received evidence and Gold answerability is resolved, so no-hit runs,
unresolved Gold, and technical failures are excluded.
Per-question records retain `abstention_cause`, and aggregate JSON, CSV, and
Markdown reports break correct, wrong, and unresolved abstentions down by that
cause. Metric definitions are stored once in the top-level
`metric_definitions`; overall and grouped metric values contain only numerator,
denominator, value, and excluded counts.
F1 rows use the count form `2TP / (2TP + FP + FN)` so their reported numerator
and denominator remain interpretable as counts. Markdown and CSV label the
cross-group result as an overall diagnostic aggregate and also emit complete
group-specific metrics and cause breakdowns; formal comparisons use the latter.

The run trace stores retrieval output, evidence used by the generation seam,
raw output, optional repaired output, model-call count, the final answer,
citation validation, and structured error details. GenerationTrace can also
record the prompt evidence IDs and a prompt hash. Batch-level reproducibility
metadata belongs to `RunManifest`.

Prompt provenance is optional diagnostic metadata: malformed IDs or hashes are
discarded without turning an otherwise validated answer into a technical error.

## Retrieval metrics

The official report metric is `first_hit_mrr`, the reciprocal rank of the first
chunk mapped to a core gold span. `complete_evidence_mrr` is an additional
diagnostic: for each OR path, all required spans must be covered and the path's
completion rank is the latest required span rank; the question takes the
earliest complete path.

At each requested K the scorer also reports complete-evidence Hit@K, evidence
recall, core precision, context noise rate, no-relevant-hit rate, partial
evidence count, returned count, and empty-retrieval rate. Precision, noise,
and no-relevant-hit are undefined (`null`) for an empty top-K result; their
defined-sample counts are reported separately instead of treating an empty
context as zero precision or zero noise. Partial mappings are required to
compute the noise and partial diagnostics.

The aggregate also contains `retrieval_scores`, one row per saved question.
Each row states whether it entered the retrieval denominator and, when it did,
stores the two MRR values and the requested per-K metrics. Excluded rows carry
an explicit reason such as `unanswerable`, `unresolved`, `retrieval_error`, or
`mapping_missing`. The aggregate `excluded_runs.total` is the authoritative
number of excluded questions; the reason counters are mutually exclusive and
sum to that total. A reportable manifest uses strict mapping validation;
development scoring may retain excluded rows for diagnosis.

`RunManifest` version `0.2` records dataset, parser, Gold annotation, and
mapping identities. A reportable run cannot use dirty worktrees, fixture data,
or synthetic generation traces. An interrupted batch keeps an
`.inprogress` manifest sidecar; if a torn final JSONL record is recovered, a
`*.recovery.json` marker records the discarded line and byte count.

## Loading the fixtures

```python
from pathlib import Path

from cs30.evaluation import load_gold_samples, load_run_results

fixture_dir = Path("tests/fixtures/evaluation")
gold = load_gold_samples(fixture_dir / "gold_v0_1.jsonl")
runs = load_run_results(fixture_dir / "run_results_v0_2.jsonl")
```

`run_results_v0_2.jsonl` is a lifecycle fixture: it intentionally contains
multiple terminal states for one question and is not a valid batch for
aggregate scoring. The one-row-per-question companion can be scored end to
end without invoking a model:

```text
cs30-evaluate score \
  --gold tests/fixtures/evaluation/gold_v0_1.jsonl \
  --runs tests/fixtures/evaluation/run_results_scorable_v0_2.jsonl \
  --mapping tests/fixtures/evaluation/mapping_v0_1.json \
  --k-values 1 3
```

The fixtures are deliberately tiny and hand-computable. They are engineering
fixtures, not reported evaluation results.

## Preparing the OpenStax archive

The M2 handoff may contain one `openstax_document.json` per chapter inside a
zip archive.  Before M4 builds chunks, merge and validate that handoff into one
document-wide character coordinate system:

```text
cs30-evaluate prepare-corpus \
  --archive D:/path/to/data.zip \
  --output-dir data/processed/openstax-w5-v2
```

The command writes `openstax_document.json` and `corpus_manifest.json`.  It
checks that every chapter has the same OpenStax document identity, preserves
all chapter/block spans after adding a deterministic separator, and records a
compact corpus version derived from the source identity, selected chapters, and
separator.  It
does not create Gold samples or gold-to-chunk mappings; M3 and M4 still supply
those artifacts before a formal retrieval score can be reported.

Normalize M3's immutable chapter-local Gold into a separate, corpus-bound
artifact before a formal run. The prepared manifest is required because its
separator is part of the full corpus identity:

```text
cs30-evaluate normalize-gold \
  --gold m3_gold/gold_v0_1.jsonl \
  --document data/processed/openstax-w5-v2/openstax_document.json \
  --corpus-manifest data/processed/openstax-w5-v2/corpus_manifest.json \
  --output gold/gold_normalized_corpus_v1.jsonl
```

Formal `run` and `score` commands require this schema-0.2 artifact together
with `--document` and the matching `--corpus-manifest`; their Gold, run
manifest, and M4 mapping must all use the same full `corpus_version`. M3's
short document ID is never used as a formal corpus identity. Engineering
fixture/development flows may continue using the small raw fixtures, but their
manifests remain non-reportable.

The batch commands are available through `cs30-evaluate` (or
`python -m cs30.evaluation.cli`):

```text
cs30-evaluate run --gold gold_normalized_corpus_v1.jsonl --output run.jsonl \
  --document data/processed/openstax-w5-v2/openstax_document.json \
  --corpus-manifest data/processed/openstax-w5-v2/corpus_manifest.json \
  --execution-mode retrieval_only --retrieval-mode bm25 --top-k 5 --k-values 1 3 5
cs30-evaluate score --gold gold_normalized_corpus_v1.jsonl --runs run.jsonl --mapping mapping.json \
  --document data/processed/openstax-w5-v2/openstax_document.json \
  --corpus-manifest data/processed/openstax-w5-v2/corpus_manifest.json \
  --k-values 1 3 5 --scores-output retrieval_scores.jsonl
```

`run` checkpoints to `run.jsonl.inprogress` and only promotes it after all
records validate. Synthetic traces are allowed only for explicit fixture runs
and are never reportable. `score` reads saved results and never invokes a
generator; `--scores-output` writes the per-question retrieval rows as JSONL.

## Answer, abstention, format, and citation extension

The score command registers `AnswerCitationScorer` through the shared
`ScoringExtension` seam. It consumes the same `GoldSample`,
`EvaluationRunResult`, and span-to-chunk mapping objects as retrieval scoring;
it does not define a competing run schema or invoke retrieval or generation.

The extension reports answer accuracy for explicit denominators, abstention
accuracy/precision/recall/F1, raw and repaired JSON/schema validity, citation
validity against `evidence_sent_to_model`, per-citation validity, complete Gold
evidence-path citation coverage, failure labels, and comparable experiment
groups. `retrieval_error`, `generation_error`, and `parse_error` are attributed
separately as retrieval failure, generation failure, and invalid output;
technical failures remain separate from model abstentions. Scorer-resolved
citation chunk IDs must exactly match the ordered
`citation_validation.resolved_citations` sequence.
Gold questions missing from the saved run file are listed explicitly rather
than silently disappearing from the report.

The scoring mode is determined once from the manifest. A manifest with
`reportable=true` uses `reportable` mode; all other scoring uses `development`
mode. In development mode, split, retrieval-mode, and condition mismatches are
excluded with mutually exclusive counters and scoring continues. Reportable
mode fails on those mismatches and on missing expected runs. A saved run with no
matching Gold is excluded as `missing_gold` in both modes. Excluded runs enter
no records, groups, answer metrics, abstention metrics, or citation metrics.
Duplicate run or Gold IDs and invalid JSON/schema remain hard failures.

Gold with unresolved answerability (`answerable=null`) remains visible in the
per-question diagnostics and failure queue but is excluded from every formal
answer-accuracy and abstention denominator. Retrieval-only batches report
`applicability: not_applicable`, an empty answer `metrics` object, and a
`not_applicable` outcome count instead of null answer, format, and citation
metrics.

Pass `--answer-citation-output-dir` to write the review artifacts:

```text
cs30-evaluate score \
  --gold tests/fixtures/evaluation/gold_v0_1.jsonl \
  --runs tests/fixtures/evaluation/run_results_scorable_v0_2.jsonl \
  --mapping tests/fixtures/evaluation/mapping_v0_1.json \
  --k-values 1 3 \
  --output artifacts/evaluation/scores.json \
  --answer-citation-output-dir artifacts/evaluation
```

The generic `--output` file contains retrieval and extension aggregates but
omits answer/citation `records`. `--answer-citation-output-dir` writes the
answer/citation aggregate JSON, per-question JSONL, summary CSV, Markdown report,
and focused failure-review JSONL. Fixture outputs validate the implementation
only and must not be reported as final model quality.

## Personalisation evaluation reporting

The `report-extension` command combines existing offline answer/citation scores
with textbook, learner-level, condition, and lambda metadata. It does not rerun
retrieval or generation, and its M8-owned sidecars do not change
`EvaluationRunResult`, `RunManifest`, Gold, mapping, retrieval, generation, or
Role-label contracts.

The report keeps three evidence sources separate:

1. automated per-question answer and citation scores;
2. single-rater blinded level-adaptation scores;
3. an identity and reference audit of the M3 Role-label package.

M8 reports Role-label provenance but does not assess Role semantics or compute
Evidence Role IAA.

### Experiment context

`--contexts` is a JSONL sidecar with exactly one row for every scored `run_id`.
It supplies the reporting dimensions that are intentionally absent from the
shared run-result contract:

```json
{"schema_version":"0.1","run_id":"run-001","question_id":"q-001","condition_id":"plain","comparison_id":"prompt-controlled-reranking","textbook_id":"openstax_college_physics_2e","student_level":"beginner","execution_mode":"retrieval_and_generation","chunk_version":"chunks-v1","mapping_version":"mapping-v1","index_version":"hybrid-index-v1","lambda_weight":0.0,"lambda_status":"baseline"}
```

`comparison_id` pairs the two conditions being compared. Baseline rows must use
`lambda_weight=0`; frozen rows use the one global `lambda*` selected on Dev.
Formal reporting requires both sides of every declared comparison, identical
unique question sets, and one globally frozen lambda value. Partial development
reports must opt in with `--allow-incomplete`.

Formal reporting also binds every score artifact to the real `RunManifest`
written by its runner invocation. The report verifies the manifest is
reportable and non-fixture, then checks condition, execution mode, retrieval
mode, dataset, split, corpus, chunk, mapping, and index identities against the
score records and contexts. Score and manifest SHA-256 values are retained in
the aggregate report. A development report may omit these bindings only with
`--allow-incomplete`; the aggregate JSON and Markdown then label the binding
state as `pending` or `incomplete` rather than claiming a formal binding.

The report rejects a context whose `execution_mode` disagrees with its score
record or manifest, and rejects lambda comparisons that mix incompatible run
manifests or artifact versions. `retrieval_only` records must not contain model
calls, answers, repairs, citations, abstention causes, or generation metrics;
valid retrieval-only records remain traceable with those metrics marked
`not_applicable`. Retrieval, generation, and parsing failures remain separate
technical outcomes and do not enter answer or abstention accuracy denominators.

### Formal experiment coverage

`--expected-experiments` supplies the frozen acceptance matrix rather than
hard-coding M7 condition names in M8. Each cell identifies one required
textbook, learner level, split, condition, comparison, retrieval mode, lambda
status and exact question set. Formal reporting fails on missing, extra, or
partially covered cells.

```json
{
  "schema_version": "0.1",
  "matrix_version": "formal-matrix-v1",
  "cells": [
    {
      "schema_version": "0.1",
      "mode": "hybrid",
      "execution_mode": "retrieval_and_generation",
      "data_version": "gold-v1",
      "split": "dev",
      "corpus_version": "openstax-cp2e-v1",
      "chunk_version": "chunks-v1",
      "mapping_version": "mapping-v1",
      "index_version": "hybrid-index-v1",
      "textbook_id": "openstax_college_physics_2e",
      "student_level": "beginner",
      "comparison_id": "prompt-controlled-reranking",
      "condition_id": "P0R0_plain",
      "lambda_weight": 0.0,
      "lambda_status": "baseline",
      "expected_question_ids": ["q-001"]
    }
  ]
}
```

### Single-rater blind assessment

Create the blind sheet from saved run files after the team freezes the rating
rubric. Only normally answered runs enter the sheet; abstentions and technical
failures remain in automated error analysis.

```powershell
cs30-evaluate prepare-blind-ratings `
  --runs artifacts/plain/run_results.jsonl artifacts/reranked/run_results.jsonl `
  --gold artifacts/gold_v1.jsonl `
  --contexts artifacts/experiment_contexts.jsonl `
  --seed 5703 `
  --output-dir artifacts/blind_rating
```

The command writes:

- `blind_rating_sheet.csv`, containing the question, assigned level, answer
  choice, and explanation but no run, condition, lambda, prompt, retrieval, or
  model identifiers;
- `blinded_answer_key.jsonl`, the private post-rating mapping to run IDs;
- `blind_rating_manifest.json`, with expected/excluded counts and hashes.

Keep the key and randomisation seed private until the sheet is complete. The
filled CSV supplies `score`, `rubric_version`, and `rater_id`. The corresponding
rubric manifest records the agreed version and score range:

```json
{"schema_version":"0.1","rubric_version":"level-fit-v1","score_min":1,"score_max":5}
```

Every answer in the private key must receive exactly one score. Missing ratings,
duplicate ratings, level/question mismatches, unknown blind IDs, and scores
outside the frozen range fail before aggregation.

After the single rater completes the sheet, seal the final files:

```powershell
cs30-evaluate seal-blind-ratings `
  --ratings artifacts/blind_rating/blind_rating_sheet.csv `
  --rating-key artifacts/blind_rating/blinded_answer_key.jsonl `
  --rating-rubric artifacts/level_adaptation_rubric.json `
  --output artifacts/blind_rating/blind_rating_submission.json
```

The sealed manifest binds the completed rating file, private key, rubric, and
expected row count by SHA-256. A supplied empty file fails rather than becoming
`pending`, and more than one `rater_id` is rejected. Only a completely omitted
rating package is reported as `pending`; partial coverage is allowed solely in
development with `--allow-incomplete` and is labelled `incomplete`.

### Role-label provenance

Pass `--role-manifest`, `--role-gold`, and `--role-mapping` together. The
M8-owned manifest records the Role schema/taxonomy/annotation versions, corpus
and parser identities, annotation date, the single annotator, label-file hash,
record count, configured field names, and whether references target Gold
mapping spans or the full frozen chunk universe.

For full chunk-universe validation, also pass M4's final `records.jsonl` through
`--role-records` and authoritative candidate `question_id`/`chunk_id` pairs
through `--role-question-references`. The audit checks identities, hashes,
counts, schema versions, valid IDs, and question-to-evidence relationships
without judging Role-label quality.

In formal mode, any failed Role provenance check stops report generation. A
development run may retain the failed audit only with `--allow-incomplete`.
The current repository does not yet contain a frozen machine-readable Role
schema or Role-label package, so M8 does not hard-code the six design-time Role
names or claim a completed allowed-value audit. Once that upstream package is
available, allowed values must be validated from its own frozen schema rather
than redefined in evaluation code. Supplying `--role-records` or
`--role-question-references` without the three core Role inputs is an error.

### Combined report

First retain the `answer_citation_scores.jsonl` output for every frozen run,
then build the combined package:

```powershell
cs30-evaluate report-extension `
  --scores artifacts/plain/answer_citation_scores.jsonl artifacts/reranked/answer_citation_scores.jsonl `
  --score-manifest artifacts/plain/answer_citation_scores.jsonl artifacts/plain/run_results.manifest.json `
  --score-manifest artifacts/reranked/answer_citation_scores.jsonl artifacts/reranked/run_results.manifest.json `
  --contexts artifacts/experiment_contexts.jsonl `
  --expected-experiments artifacts/expected_experiments.json `
  --ratings artifacts/blind_rating/blind_rating_sheet.csv `
  --rating-key artifacts/blind_rating/blinded_answer_key.jsonl `
  --rating-rubric artifacts/level_adaptation_rubric.json `
  --rating-submission-manifest artifacts/blind_rating/blind_rating_submission.json `
  --role-manifest artifacts/role_label_provenance_manifest.json `
  --role-gold artifacts/gold_v1.jsonl `
  --role-mapping artifacts/gold_chunk_mapping_v1.json `
  --role-records artifacts/records.jsonl `
  --role-question-references artifacts/question_chunk_relationships.jsonl `
  --output-dir artifacts/evaluation_report
```

The original five answer/citation artifacts remain unchanged. The combined
package adds aggregate JSON, experiment and lambda CSVs, grouped failure
analysis, level-adaptation scores, Role provenance, and a client-readable
Markdown report. Automated metrics, human ratings, and provenance findings stay
separate. Metric cells retain numerator, denominator, and value; empty valid
denominators are `not_applicable`, including refusal Recall/F1 when the Gold set
has no unanswerable samples. Ratings and Role inputs may be omitted during
development, in which case their report sections remain explicitly `pending`.
