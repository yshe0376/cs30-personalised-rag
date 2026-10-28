# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 360; eligible: 360.

Full-correct rate: None; bounds: [0.8638888888888889, 0.8805555555555555]; unresolved: 6.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | google/gemma-3-12b-it | 26 / 30 | 0 |
| dev | advanced | P0R1_reranking_only | google/gemma-3-12b-it | 26 / 30 | 1 |
| dev | advanced | P1R0_prompt_only | google/gemma-3-12b-it | 28 / 30 | 0 |
| dev | advanced | P1R1_combined | google/gemma-3-12b-it | 28 / 30 | 0 |
| dev | beginner | P0R0_plain | google/gemma-3-12b-it | 25 / 30 | 1 |
| dev | beginner | P0R1_reranking_only | google/gemma-3-12b-it | 26 / 30 | 0 |
| dev | beginner | P1R0_prompt_only | google/gemma-3-12b-it | 27 / 30 | 0 |
| dev | beginner | P1R1_combined | google/gemma-3-12b-it | 26 / 30 | 0 |
| dev | intermediate | P0R0_plain | google/gemma-3-12b-it | 25 / 30 | 1 |
| dev | intermediate | P0R1_reranking_only | google/gemma-3-12b-it | 25 / 30 | 1 |
| dev | intermediate | P1R0_prompt_only | google/gemma-3-12b-it | 24 / 30 | 1 |
| dev | intermediate | P1R1_combined | google/gemma-3-12b-it | 25 / 30 | 1 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
