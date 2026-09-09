# Evaluation contracts v0.1

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

## Run-result semantics

`EvaluationRunResult.status` has five mutually exclusive terminal values:

- `retrieval_error`
- `generation_error`
- `parse_error`
- `abstained`
- `answered`

The first three are technical errors and cannot contain a final answer. An
`abstained` result is a successful run whose parsed final answer explicitly
refused to answer. This prevents evaluator code from scoring infrastructure or
model-call failures as correct refusals.

The run trace stores retrieval output, the exact evidence bundle sent to the
model, raw output, optional repaired output, the final answer, citation
validation, and structured error details. Batch-level reproducibility metadata
belongs to the run manifest implemented by the batch runner.

## Loading the fixtures

```python
from pathlib import Path

from cs30.evaluation import load_gold_samples, load_run_results

fixture_dir = Path("tests/fixtures/evaluation")
gold = load_gold_samples(fixture_dir / "gold_v0_1.jsonl")
runs = load_run_results(fixture_dir / "run_results_v0_1.jsonl")
```

The fixtures are deliberately tiny and hand-computable. They are engineering
fixtures, not reported evaluation results.
