# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 1848; eligible: 1848.

Full-correct rate: None; bounds: [0.8695887445887446, 0.8728354978354979]; unresolved: 6.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 143 / 154 | 1 |
| dev | advanced | P0R1_reranking_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 141 / 154 | 0 |
| dev | advanced | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 134 / 154 | 0 |
| dev | advanced | P1R1_combined | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 133 / 154 | 0 |
| dev | beginner | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 140 / 154 | 0 |
| dev | beginner | P0R1_reranking_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 145 / 154 | 0 |
| dev | beginner | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 125 / 154 | 0 |
| dev | beginner | P1R1_combined | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 130 / 154 | 0 |
| dev | intermediate | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 137 / 154 | 1 |
| dev | intermediate | P0R1_reranking_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 139 / 154 | 1 |
| dev | intermediate | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 121 / 154 | 2 |
| dev | intermediate | P1R1_combined | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 119 / 154 | 1 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
