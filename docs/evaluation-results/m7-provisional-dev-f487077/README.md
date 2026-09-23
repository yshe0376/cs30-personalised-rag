# M7 provisional four-condition reporting snapshot

## Status and permitted use

**Technical reporting-pipeline acceptance is complete. Formal model-quality and
personalisation-effect acceptance is not complete.**

This snapshot may be used to verify the engineering flow from M7's saved
four-condition outputs through M8's adapter and offline evaluator. It must not
be used for formal research claims, final model-quality conclusions, or a
personalisation/lambda conclusion.

The generated report retains the source manifest's
`DEVELOPMENT / NOT FOR FORMAL CLAIMS` status. The files are checked in as a
reproducible integration snapshot, not as a promoted V1 acceptance result.

## What this snapshot verifies

The reporting command successfully:

- loaded M7's immutable cases, result rows, and run manifest;
- joined all 144 result rows to 36 cases and the four expected conditions;
- rejected identity drift and incomplete or duplicate condition cells;
- reconstructed the ordered evidence and exact prompt for every row;
- verified each reconstructed prompt against M7's saved SHA-256;
- adapted the rows to `EvaluationRunResult` v0.2;
- ran the offline answer/citation evaluator; and
- generated JSON, JSONL, CSV, Markdown, LaTeX, SVG, and failure-review outputs.

This establishes that the M7-to-M8 adapter and reporting pipeline work against
the currently published M7 delivery.

## Why this is not a formal evaluation result

The upstream experiment has material limitations:

1. M7's `run_manifest.json` explicitly sets `reportable` to `false` and marks
   the input as `provisional`.
2. The batch covers provisional Dev cases only; it is not a frozen Dev/Test
   acceptance run.
3. The saved generation cases contain the question text but omit the MCQ A-D
   options. Consequently, the reported answer-choice accuracy is not a
   meaningful estimate of model quality. The zero values must not be presented
   as a valid comparison of the four conditions.
4. The selected lambda is provisional and its source artifact marks the result
   as non-reportable/not interpretable because Role-label coverage is
   incomplete for the candidate universe.
5. Some reconstructed prompts exceed the provisional 1,500-token
   whitespace-estimate target. The adapter preserves and reports those inputs;
   it does not alter the upstream experiment.
6. No completed blinded human level-adaptation assessment is attached. Human
   ratings require a frozen rubric and real independent rating activity; they
   cannot be inferred by the evaluator.

Citation and pipeline-integrity metrics remain useful for engineering checks,
but they do not remove these limitations.

## Source provenance

- Upstream M7 publication commit: `f487077`
- Source run ID: `member7-four-condition-861e54acc967c869`
- Provider/model recorded by the manifest: Ollama / `gpt-oss:20b`
- Cases: `artifacts/task7-week5/provisional_dev_cases.jsonl`
- Results:
  `artifacts/task7-week5/provisional_dev_four_condition_run/four_condition_results.jsonl`
- Run manifest:
  `artifacts/task7-week5/provisional_dev_four_condition_run/run_manifest.json`
- Gold: `eval_inputs/gold_v0_2_from_m3_v0_1_1.jsonl`
- Mapping: `eval_inputs/evaluation_mapping_v0_1.json`

## Generated files

- `evaluation_run_results_v0_2.jsonl`: adapted and verified per-run records;
- `four_condition_summary.json`: aggregate metrics and audit details;
- `four_condition_comparison.csv`: long-form four-condition comparison;
- `four_condition_report.md`: readable development report;
- `four_condition_report.tex`: LaTeX version of the development report;
- `four_condition_comparison.svg`: deterministic comparison chart; and
- `four_condition_failures.jsonl`: focused failure-review queue.

## Reproduction

From the repository root:

```powershell
cs30-evaluate report-four-conditions `
  --gold eval_inputs/gold_v0_2_from_m3_v0_1_1.jsonl `
  --mapping eval_inputs/evaluation_mapping_v0_1.json `
  --cases artifacts/task7-week5/provisional_dev_cases.jsonl `
  --results artifacts/task7-week5/provisional_dev_four_condition_run/four_condition_results.jsonl `
  --run-manifest artifacts/task7-week5/provisional_dev_four_condition_run/run_manifest.json `
  --output-dir docs/evaluation-results/m7-provisional-dev-f487077
```

## Remaining work for formal acceptance

A formal result requires the team to freeze the intended V2 experiment scope,
provider/model and rubric; include the complete MCQ options in generation
inputs; publish reportable Dev/Test manifests with sufficient Role-label
coverage; rerun the four conditions; and complete any required blinded human
assessment. The same adapter and evaluator can then regenerate a formally
reportable package from those replacement inputs.
