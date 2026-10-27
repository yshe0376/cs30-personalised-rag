# Detailed trial analysis — 2026-10-27

This analysis uses the saved request/result JSONL files, not the truncated previews in spotcheck.md. It is an automated comparison plus a targeted reading of selected explanations. It is not an independent human audit, accuracy estimate, or calibration result.

### Runtime and cost

- All four tasks ran for both configurations on the same 20 cells. Adaptation contains 30 requests because some answers are checked against additional profiles.
- 204 logged client attempts: 103 high and 101 low; no wrapper-level API exceptions or truncations. SDK internal HTTP attempts are not independently observed.
- Estimated token cost: high US$0.3641535; low US$0.12593075; total US$0.49008425. Low is 65.4% cheaper in this trial. Invoice reconciliation remains pending.
- Sum of logged call durations: high 613.4 seconds; low 221.7 seconds. These are not exact end-to-end wall-clock durations. Serial execution and thinking explain much of the wait.
- Base full-Dev projection: high US$70.54; low US$24.16. These exclude additional judge validity checks, a second judge family, future fixes/re-runs, taxes and currency conversion. Selection excludes none scope. Projection uncertainty is not quantified by 20 cells.

### Correctness

- High: 19 scored, 1 needs_review; low: 20 scored. All 19 mutually scored results have the same score. High has 17 scores of 2 and 2 scores of 0; low has 18 scores of 2 and 2 scores of 0. Scores are rubric outcomes, not proof of real-world correctness.
- The difference is sciq-train-05989: high requests review because an extra A=60 claim is not verified by supplied reference evidence; low accepts the core answer and treats the extra detail as factual but extraneous. This exposes a boundary between checking the requested answer and checking additional statements. Inspect the frozen rubric before choosing an interpretation.
- The two full-eligibility questions are already documented as Gold/reference concerns in docs/v2-generation-evaluation-plan.md, section 3.2. Reference-matching scores cannot independently certify those references.

### Adaptation

- Both configurations returned 30 resolved outputs. Resolution means output/schema/quotation validation passed, not that the judgments are educationally correct.
- Exact criterion-verdict matches: 88/111; differences: 23/111. All criterion verdicts match in 17/30 request pairs. These counts include pass/fail/not_applicable differences and correlated observations on the same answers. They are not a validity or human-agreement estimate.
- A targeted example is the radiotherapy identification answer, sciq-train-01931. At the advanced profile, high fails A2/A3/A4 while low returns not_applicable/not_applicable/pass. At the beginner profile, high demands additional causal explanation and concrete support; low accepts a direct identification answer.
- This suggests inconsistent application of task-relative requirements: a simple identification answer should not automatically be required to become a derivation merely because an advanced profile is supplied. This is a suspected interpretation issue requiring review against the existing frozen identification-question guidance, not permission to alter the profiles.

### Discrimination

- Both configurations returned 20 resolved outputs. Predictions match in 15/20 pairs and differ in 5/20 pairs.
- High predicts beginner/intermediate/advanced/uncertain = 13/5/0/2. Low predicts 17/1/1/1. The generation targets were beginner/intermediate/advanced = 8/5/7.
- Low tends to call several concise answers beginner where high calls them intermediate (longitudinal waves, black-hole tidal forces, and cyclotron magnetic fields). This could reflect poor separation in generated answer styles, judge bias, or overlapping profiles. The hidden generation target is not a human-verified true writing level, so target mismatch alone is not judge error.

### Evidence support

- Final resolved requests: high 17/20, low 15/20. The same 15 requests resolve under both configurations.
- Application-level extra attempts: high 12, low 8. Failure categories include evidence quotation text not being an exact substring, repeated evidence IDs, and mismatch between supporting IDs and quotation coverage.
- Fail-closed validation is working: invalid outputs remain unresolved instead of receiving silently accepted scores. That is desirable protection, but the remaining 15%/25% unresolved workload makes this path unsuitable for blind full-scale scoring. Do not interpret an unresolved judge result as an incorrect generator answer.
- High produces 38 claims across its 17 resolved outputs; low produces 31 across its 15. These totals have different denominators and claim segmentation, so their supported-claim percentages cannot be directly used to rank high versus low.
- Evidence scoring is the most expensive task in this run and the largest projected cost component, making validation repair a priority.

## Recommended next steps

1. Give the Leader the runtime/cost evidence, with the unresolved results and projection exclusions disclosed. The initial summary is already posted on #209.
2. Inspect full request/result records for the evidence failures and selected semantic disagreements. A user/Leader human review remains pending; do not invent a completed audit.
3. Diagnose prompt/schema/quotation behavior and check the existing identification-question rules before proposing code changes. Preserve the frozen profiles, Gold and shared contracts.
4. After approval of any repair, run a small separately identified verification sample; keep original trial evidence intact and record any new spend.
5. Use low as a cheaper candidate, not a proven equivalent replacement. Do not start full Dev without explicit budget approval and the required validity/calibration decisions.

## Source locations

- Selection: selection.json
- Cost evidence: summary.json and calls.csv
- Full judgments: thinking-high/ and thinking-low/, task request/result JSONL files
- Validation: src/cs30/evaluation/judge_runtime.py, validate_judge_output (evidence checks around lines 291–315)
- Duplicate evidence ID schema check: src/cs30/evaluation/v2_generation_models.py (around line 468)
- Cost token accounting and SDK retry policy: src/cs30/evaluation/gemini_judge_client.py (around lines 82–85 and 130–146)

Result paths are relative to this directory. Code paths refer to source commit 7068dae27e44c4ad316e4ce3bed7cb64dd2daf2a in this repository.
