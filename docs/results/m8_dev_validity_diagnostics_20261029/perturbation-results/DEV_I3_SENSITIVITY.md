# Dev intermediate adaptation: I3 reporting sensitivity

Leader decision: [PR #223 review](https://github.com/yshe0376/cs30-personalised-rag/pull/223#issuecomment-6490707658).

Policy: `intermediate-i3-reference-only-v1`, bound to the reviewed frozen profile.
For Test reporting, use I1 and I2 for the main intermediate adaptation rate and report I3 separately as reference-only. Keep all three judge verdicts and the unchanged checklist/prompt. The saved handoff contains the original three-criterion rates; consumers must explicitly apply this reporting policy rather than silently reuse those legacy aggregates.

These Dev comparisons are offline recomputations from existing verdicts, not new judge calls. Every row averages answer-level rates over exactly the same resolved cells in both versions. Missing cells remain missing. The main scope follows the repository eligible_levels function: full and endpoint_only, including intermediate observations; none is excluded. Cross-level evaluations are excluded.

| Generator | Scope | Condition | Resolved / expected | With I3 | Without I3 | Change (pp) | I3 pass rate (reference) |
|---|---|---|---:|---:|---:|---:|---:|
| dev-gemma | all_target_intermediate | all_conditions | 608 / 616 | 94.02% | 93.59% | -0.44 | 94.90% |
| dev-gemma | all_target_intermediate | P0R0_plain | 153 / 154 | 91.50% | 91.18% | -0.33 | 92.16% |
| dev-gemma | all_target_intermediate | P0R1_reranking_only | 154 / 154 | 92.64% | 92.53% | -0.11 | 92.86% |
| dev-gemma | all_target_intermediate | P1R0_prompt_only | 151 / 154 | 96.03% | 95.36% | -0.66 | 97.35% |
| dev-gemma | all_target_intermediate | P1R1_combined | 150 / 154 | 96.00% | 95.33% | -0.67 | 97.33% |
| dev-gemma | main_eligible_intermediate | all_conditions | 419 / 424 | 95.54% | 95.11% | -0.44 | 96.42% |
| dev-gemma | main_eligible_intermediate | P0R0_plain | 105 / 106 | 93.65% | 93.33% | -0.32 | 94.29% |
| dev-gemma | main_eligible_intermediate | P0R1_reranking_only | 106 / 106 | 94.34% | 93.87% | -0.47 | 95.28% |
| dev-gemma | main_eligible_intermediate | P1R0_prompt_only | 105 / 106 | 96.83% | 96.19% | -0.63 | 98.10% |
| dev-gemma | main_eligible_intermediate | P1R1_combined | 103 / 106 | 97.41% | 97.09% | -0.32 | 98.06% |
| dev-gpt-oss | all_target_intermediate | all_conditions | 610 / 616 | 97.49% | 97.21% | -0.27 | 98.03% |
| dev-gpt-oss | all_target_intermediate | P0R0_plain | 153 / 154 | 97.39% | 97.06% | -0.33 | 98.04% |
| dev-gpt-oss | all_target_intermediate | P0R1_reranking_only | 153 / 154 | 96.51% | 96.08% | -0.44 | 97.39% |
| dev-gpt-oss | all_target_intermediate | P1R0_prompt_only | 152 / 154 | 97.59% | 97.37% | -0.22 | 98.03% |
| dev-gpt-oss | all_target_intermediate | P1R1_combined | 152 / 154 | 98.46% | 98.36% | -0.11 | 98.68% |
| dev-gpt-oss | main_eligible_intermediate | all_conditions | 422 / 424 | 98.10% | 98.10% | +0.00 | 98.10% |
| dev-gpt-oss | main_eligible_intermediate | P0R0_plain | 106 / 106 | 98.11% | 98.11% | +0.00 | 98.11% |
| dev-gpt-oss | main_eligible_intermediate | P0R1_reranking_only | 106 / 106 | 96.86% | 96.70% | -0.16 | 97.17% |
| dev-gpt-oss | main_eligible_intermediate | P1R0_prompt_only | 105 / 106 | 98.10% | 98.10% | +0.00 | 98.10% |
| dev-gpt-oss | main_eligible_intermediate | P1R1_combined | 105 / 106 | 99.37% | 99.52% | +0.16 | 99.05% |
| dev-llama | all_target_intermediate | all_conditions | 574 / 616 | 91.23% | 89.63% | -1.60 | 94.43% |
| dev-llama | all_target_intermediate | P0R0_plain | 153 / 154 | 91.29% | 89.54% | -1.74 | 94.77% |
| dev-llama | all_target_intermediate | P0R1_reranking_only | 153 / 154 | 89.76% | 88.24% | -1.53 | 92.81% |
| dev-llama | all_target_intermediate | P1R0_prompt_only | 134 / 154 | 92.29% | 90.67% | -1.62 | 95.52% |
| dev-llama | all_target_intermediate | P1R1_combined | 134 / 154 | 91.79% | 90.30% | -1.49 | 94.78% |
| dev-llama | main_eligible_intermediate | all_conditions | 401 / 424 | 91.69% | 90.02% | -1.66 | 95.01% |
| dev-llama | main_eligible_intermediate | P0R0_plain | 106 / 106 | 90.88% | 89.15% | -1.73 | 94.34% |
| dev-llama | main_eligible_intermediate | P0R1_reranking_only | 106 / 106 | 91.19% | 89.62% | -1.57 | 94.34% |
| dev-llama | main_eligible_intermediate | P1R0_prompt_only | 96 / 106 | 92.01% | 90.10% | -1.91 | 95.83% |
| dev-llama | main_eligible_intermediate | P1R1_combined | 93 / 106 | 92.83% | 91.40% | -1.43 | 95.70% |

The measure is a continuous criterion pass rate, not a thresholded answer pass rate. No new aggregate pass threshold, confidence interval, delta, or formal model comparison is inferred. These tables remain exploratory (`reportable=false`). The original development reports and scores are preserved.

Reproduce from the repository root with the current checkout installed or its src directory on PYTHONPATH:

```powershell
python scripts/summarize_dev_i3_sensitivity.py --package PATH_TO_DEV_SCORING_HANDOFF --out NEW_OUTPUT_DIRECTORY
```

The script checks consumed source hashes, frozen-profile binding, metadata alignment and complete I1/I2/I3 verdicts before writing. It refuses existing output folders and never writes inside the source package. It accepts only the reviewed Dev bundle, not Test data.
