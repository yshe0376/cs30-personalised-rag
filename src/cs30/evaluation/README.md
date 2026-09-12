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
cause. Each metric's `definition` states its precise denominator and exclusions.
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
groups. Technical failures remain separate from model abstentions.
Gold questions missing from the saved run file are listed explicitly rather
than silently disappearing from the report.

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

The output directory contains aggregate JSON, per-question JSONL, summary CSV,
a Markdown report, and a focused failure-review JSONL. Fixture outputs validate
the implementation only and must not be reported as final model quality.
