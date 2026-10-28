# Open-answer correctness report

DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION

Expected runs: 1848; eligible: 1848.

Full-correct rate: None; bounds: [0.928030303030303, 0.9377705627705628]; unresolved: 18.

Partial credit is reported separately and is not strict correctness.

| Split | Level | Condition | Model | Correct / eligible | Pending |
|---|---|---|---|---:|---:|
| dev | advanced | P0R0_plain | google/gemma-3-12b-it | 143 / 154 | 0 |
| dev | advanced | P0R1_reranking_only | google/gemma-3-12b-it | 142 / 154 | 2 |
| dev | advanced | P1R0_prompt_only | google/gemma-3-12b-it | 141 / 154 | 2 |
| dev | advanced | P1R1_combined | google/gemma-3-12b-it | 144 / 154 | 0 |
| dev | beginner | P0R0_plain | google/gemma-3-12b-it | 142 / 154 | 1 |
| dev | beginner | P0R1_reranking_only | google/gemma-3-12b-it | 143 / 154 | 2 |
| dev | beginner | P1R0_prompt_only | google/gemma-3-12b-it | 145 / 154 | 1 |
| dev | beginner | P1R1_combined | google/gemma-3-12b-it | 146 / 154 | 1 |
| dev | intermediate | P0R0_plain | google/gemma-3-12b-it | 142 / 154 | 0 |
| dev | intermediate | P0R1_reranking_only | google/gemma-3-12b-it | 142 / 154 | 0 |
| dev | intermediate | P1R0_prompt_only | google/gemma-3-12b-it | 145 / 154 | 3 |
| dev | intermediate | P1R1_combined | google/gemma-3-12b-it | 140 / 154 | 6 |

## Limitations

- Automatic scores are reference-based assessments, not human ground truth.
- No formal evaluation approval is inferred from a successful run or review record ID.
- Unresolved assessments keep their expected denominator and suppress point estimates.
- Factual correctness, citation support and level adaptation remain separate metrics.
- Human-subset calibration statistics do not establish population-level accuracy.
