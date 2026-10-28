# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 360; eligible: 360.

Full-correct rate: None; bounds: [0.8277777777777777, 0.8361111111111111]; unresolved: 3.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 26 / 30 | 0 |
| dev | advanced | P0R1_reranking_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 27 / 30 | 0 |
| dev | advanced | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 26 / 30 | 0 |
| dev | advanced | P1R1_combined | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 26 / 30 | 0 |
| dev | beginner | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 26 / 30 | 0 |
| dev | beginner | P0R1_reranking_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 27 / 30 | 0 |
| dev | beginner | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 23 / 30 | 2 |
| dev | beginner | P1R1_combined | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 24 / 30 | 0 |
| dev | intermediate | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 25 / 30 | 0 |
| dev | intermediate | P0R1_reranking_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 27 / 30 | 0 |
| dev | intermediate | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 19 / 30 | 1 |
| dev | intermediate | P1R1_combined | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 22 / 30 | 0 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
