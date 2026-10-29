# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 18; eligible: 18.

Full-correct rate: None; bounds: [0.7222222222222222, 0.7777777777777778]; unresolved: 1.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | google/gemma-3-12b-it | 0 / 1 | 0 |
| dev | advanced | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 0 / 2 | 1 |
| dev | advanced | P0R0_plain | openai/gpt-oss-20b | 2 / 2 | 0 |
| dev | advanced | P1R0_prompt_only | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | advanced | P1R1_combined | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | beginner | P0R0_plain | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | beginner | P0R0_plain | openai/gpt-oss-20b | 0 / 1 | 0 |
| dev | beginner | P0R1_reranking_only | openai/gpt-oss-20b | 1 / 1 | 0 |
| dev | beginner | P1R0_prompt_only | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | beginner | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 1 / 1 | 0 |
| dev | beginner | P1R1_combined | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 1 / 1 | 0 |
| dev | beginner | P1R1_combined | openai/gpt-oss-20b | 1 / 1 | 0 |
| dev | intermediate | P0R0_plain | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | intermediate | P0R0_plain | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 0 / 1 | 0 |
| dev | intermediate | P0R0_plain | openai/gpt-oss-20b | 1 / 1 | 0 |
| dev | intermediate | P1R0_prompt_only | meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | 1 / 1 | 0 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
