# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 1944; eligible: 1944.

Full-correct rate: None; bounds: [0.0, 0.992798353909465]; unresolved: 1930.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | gpt-oss:20b | 0 / 162 | 161 |
| dev | advanced | P0R1_reranking_only | gpt-oss:20b | 0 / 162 | 161 |
| dev | advanced | P1R0_prompt_only | gpt-oss:20b | 0 / 162 | 162 |
| dev | advanced | P1R1_combined | gpt-oss:20b | 0 / 162 | 161 |
| dev | beginner | P0R0_plain | gpt-oss:20b | 0 / 162 | 161 |
| dev | beginner | P0R1_reranking_only | gpt-oss:20b | 0 / 162 | 161 |
| dev | beginner | P1R0_prompt_only | gpt-oss:20b | 0 / 162 | 159 |
| dev | beginner | P1R1_combined | gpt-oss:20b | 0 / 162 | 160 |
| dev | intermediate | P0R0_plain | gpt-oss:20b | 0 / 162 | 161 |
| dev | intermediate | P0R1_reranking_only | gpt-oss:20b | 0 / 162 | 161 |
| dev | intermediate | P1R0_prompt_only | gpt-oss:20b | 0 / 162 | 161 |
| dev | intermediate | P1R1_combined | gpt-oss:20b | 0 / 162 | 161 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
