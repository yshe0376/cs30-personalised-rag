# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 6; eligible: 6.

Full-correct rate: 0.8333333333333334; bounds: [0.8333333333333334, 0.8333333333333334]; unresolved: 0.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | advanced | P0R1_reranking_only | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | advanced | P1R1_combined | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | beginner | P1R0_prompt_only | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | beginner | P1R1_combined | google/gemma-3-12b-it | 1 / 1 | 0 |
| dev | intermediate | P0R0_plain | google/gemma-3-12b-it | 0 / 1 | 0 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
