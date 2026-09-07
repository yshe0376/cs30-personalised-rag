# Member 8 Offline Evaluation

This package scores saved pipeline and batch outputs. It never invokes a retriever or model.

## Current input boundary

The scorer adapts existing repository fields instead of changing the frozen shared contracts:

- `SciQQuestion.correct_choice` becomes `gold_choice`.
- `SciQQuestion.support` remains source support; it is not treated as aligned gold evidence.
- `SciQQuestion.in_scope` is not treated as corpus-relative answerability.
- Existing `PipelineRun.answer`, `retrieval`, `citation_integrity`, and `validated_answer` fields
  provide the prediction and citation inputs.

Until M1 and M3 freeze the W6 sample schema, answerability defaults to `unresolved` and gold
evidence defaults to an empty list. Such records are explicitly excluded from metrics that need
those labels.

## Run it

Score a combined hand-checkable fixture:

```powershell
python -m cs30.evaluation.cli `
  --runs tests/fixtures/evaluation/hand_checked_runs.jsonl `
  --output-dir artifacts/m8-evaluation
```

To join current M3 question data to saved M1 runs, add `--gold path/to/questions.json`. The join
key is `question_id`.

The command writes `scores.json`, `scores.csv`, `report.md`, and `failures.jsonl`. Every reported
metric contains its numerator, denominator, excluded count, and definition.
