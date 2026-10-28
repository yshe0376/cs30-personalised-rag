# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 1848; eligible: 1848.

Full-correct rate: None; bounds: [0.9415584415584416, 0.9664502164502164]; unresolved: 46.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | openai/gpt-oss-20b | 146 / 154 | 5 |
| dev | advanced | P0R1_reranking_only | openai/gpt-oss-20b | 145 / 154 | 3 |
| dev | advanced | P1R0_prompt_only | openai/gpt-oss-20b | 145 / 154 | 3 |
| dev | advanced | P1R1_combined | openai/gpt-oss-20b | 144 / 154 | 6 |
| dev | beginner | P0R0_plain | openai/gpt-oss-20b | 146 / 154 | 2 |
| dev | beginner | P0R1_reranking_only | openai/gpt-oss-20b | 143 / 154 | 4 |
| dev | beginner | P1R0_prompt_only | openai/gpt-oss-20b | 145 / 154 | 4 |
| dev | beginner | P1R1_combined | openai/gpt-oss-20b | 143 / 154 | 5 |
| dev | intermediate | P0R0_plain | openai/gpt-oss-20b | 147 / 154 | 3 |
| dev | intermediate | P0R1_reranking_only | openai/gpt-oss-20b | 146 / 154 | 4 |
| dev | intermediate | P1R0_prompt_only | openai/gpt-oss-20b | 144 / 154 | 5 |
| dev | intermediate | P1R1_combined | openai/gpt-oss-20b | 146 / 154 | 2 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
