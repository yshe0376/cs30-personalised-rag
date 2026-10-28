# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 360; eligible: 360.

Full-correct rate: None; bounds: [0.9222222222222223, 0.9472222222222222]; unresolved: 9.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | openai/gpt-oss-20b | 29 / 30 | 0 |
| dev | advanced | P0R1_reranking_only | openai/gpt-oss-20b | 28 / 30 | 1 |
| dev | advanced | P1R0_prompt_only | openai/gpt-oss-20b | 28 / 30 | 1 |
| dev | advanced | P1R1_combined | openai/gpt-oss-20b | 28 / 30 | 0 |
| dev | beginner | P0R0_plain | openai/gpt-oss-20b | 27 / 30 | 2 |
| dev | beginner | P0R1_reranking_only | openai/gpt-oss-20b | 27 / 30 | 1 |
| dev | beginner | P1R0_prompt_only | openai/gpt-oss-20b | 29 / 30 | 0 |
| dev | beginner | P1R1_combined | openai/gpt-oss-20b | 26 / 30 | 1 |
| dev | intermediate | P0R0_plain | openai/gpt-oss-20b | 29 / 30 | 0 |
| dev | intermediate | P0R1_reranking_only | openai/gpt-oss-20b | 27 / 30 | 1 |
| dev | intermediate | P1R0_prompt_only | openai/gpt-oss-20b | 28 / 30 | 1 |
| dev | intermediate | P1R1_combined | openai/gpt-oss-20b | 26 / 30 | 1 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
