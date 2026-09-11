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
and the method (`block_id` or `verbatim_unique`) when available.

Normalized samples may record `source_corpus_version` and `normalizer_version`
to make the provenance of the M1 transformation explicit. M3 v0.1 remains
loadable without any of these derived fields.

Formal (reportable) scoring is fail-closed: every Gold span must be resolved
and carry corpus-global coordinates. Development and fixture scoring may still
use raw v0.1 Gold for contract and pipeline checks.

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

The batch commands are available through `cs30-evaluate` (or
`python -m cs30.evaluation.cli`):

```text
cs30-evaluate run --gold gold.jsonl --output run.jsonl \
  --document data/processed/openstax-w5-v2/openstax_document.json \
  --execution-mode retrieval_only --retrieval-mode bm25 --top-k 5 --k-values 1 3 5
cs30-evaluate score --gold gold.jsonl --runs run.jsonl --mapping mapping.json \
  --document data/processed/openstax-w5-v2/openstax_document.json \
  --k-values 1 3 5 --scores-output retrieval_scores.jsonl
```

`run` checkpoints to `run.jsonl.inprogress` and only promotes it after all
records validate. Synthetic traces are allowed only for explicit fixture runs
and are never reportable. `score` reads saved results and never invokes a
generator; `--scores-output` writes the per-question retrieval rows as JSONL.
