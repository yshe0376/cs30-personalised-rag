# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 12; eligible: 12.

Full-correct rate: None; bounds: [0.0, 1.0]; unresolved: 12.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | gpt-oss:20b | 0 / 1 | 1 |
| dev | advanced | P0R1_reranking_only | gpt-oss:20b | 0 / 1 | 1 |
| dev | advanced | P1R0_prompt_only | gpt-oss:20b | 0 / 1 | 1 |
| dev | advanced | P1R1_combined | gpt-oss:20b | 0 / 1 | 1 |
| dev | beginner | P0R0_plain | gpt-oss:20b | 0 / 1 | 1 |
| dev | beginner | P0R1_reranking_only | gpt-oss:20b | 0 / 1 | 1 |
| dev | beginner | P1R0_prompt_only | gpt-oss:20b | 0 / 1 | 1 |
| dev | beginner | P1R1_combined | gpt-oss:20b | 0 / 1 | 1 |
| dev | intermediate | P0R0_plain | gpt-oss:20b | 0 / 1 | 1 |
| dev | intermediate | P0R1_reranking_only | gpt-oss:20b | 0 / 1 | 1 |
| dev | intermediate | P1R0_prompt_only | gpt-oss:20b | 0 / 1 | 1 |
| dev | intermediate | P1R1_combined | gpt-oss:20b | 0 / 1 | 1 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
