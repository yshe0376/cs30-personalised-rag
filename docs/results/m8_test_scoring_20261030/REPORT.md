# Test evaluation report — GPT-OSS-20B

Status: completed scoring and local delivery verification; findings for Leader review. The native analysis retains `reportable=false`; completion is not a blanket approval of research claims.

## Findings

The registered prompt-only contrast improves judge-rated beginner adaptation. Advanced adaptation does not show a supported improvement or decline. The registered conservative correctness noninferiority check is not met. These results do not establish improved learner outcomes.

## Registered co-primary comparison

Contrast: P1R0 prompt-only minus P0R0 plain, within question and level. Main eligibility: full plus endpoint_only. Each endpoint has 128 eligible questions. Complete pairs are used, with missing pairs disclosed. Holm adjustment covers the two endpoints; 2,000 question-cluster bootstrap draws, seed 5703. Intervals are descriptive, unadjusted 95% percentile intervals. Effects and noise floors below are percentage points (pp).

| Level | Complete / eligible pairs | Unscored pairs | Difference (pp) | 95% interval (pp) | Holm p | Dev noise floor (pp) | Supported direction |
|---|---:|---:|---:|---|---:|---:|---|
| beginner | 123 / 128 | 5 | +7.66 | [+2.64, +12.33] | 0.00700 | 1.43 | Positive |
| advanced | 126 / 128 | 2 | -3.31 | [-7.08, +0.46] | 0.09845 | 2.12 | Neither |

The advanced point estimate is negative, but its uncertainty includes zero; it is not evidence of a statistically supported decline. This Test evaluates one generator, not a Test comparison between GPT-OSS, Llama and Gemma.

## Correctness

Strict correctness means score 2. The registered noninferiority margin is 3 pp, using the same prompt-only contrast pooled across levels (187 question clusters, 561 paired cells). Nine pairs contain unresolved correctness. The worst-case difference is -1.25 pp (95% interval [-3.74, +1.25]); the best-case difference is +0.36 pp ([-1.96, +2.85]). Both lower bounds must exceed -3 pp. The worst-case lower bound does not meet this requirement. Therefore noninferiority is not established; this does not prove correctness worsened.

| Condition | Cells | Strict correct | Unscored answers | Generation failures | Strict-correct rate bounds |
|---|---:|---:|---:|---:|---|
| P0R0_plain | 561 | 518 | 3 | 0 | 92.34–92.87% |
| P0R1_reranking_only | 561 | 515 | 2 | 1 | 91.80–92.16% |
| P1R0_prompt_only | 561 | 514 | 6 | 0 | 91.62–92.69% |
| P1R1_combined | 561 | 513 | 5 | 0 | 91.44–92.34% |

Across all conditions: 2,060 strict-correct cells; overall bounds 91.80–92.51%. There are 16 unscored answers (14 judge_error and 2 needs_review). The single generation truncation is a separate technical failure and contributes system score zero under the frozen policy. Unknown judge scores remain unknown; they are not silently assigned zero.

## Completion, coverage and costs

All four jobs have completion receipts. Exit code 3 denotes unresolved/review outputs, not a process crash. Request counts differ from cell counts because identical answers share requests and adaptation also evaluates comparison levels.

| Task | API attempts including retries | Resolved answered target cells | Unscored answered target cells | Generation failures |
|---|---:|---:|---:|---:|
| correctness | 1476 | 2227 | 16 | 1 |
| adaptation | 2666 | 2207 | 36 | 1 |
| discrimination | 1431 | 2243 | 0 | 1 |
| evidence_support | 1851 | 2113 | 130 | 1 |

All-target coverage above is distinct from the eligibility-restricted primary analysis. The adaptation and evidence runners retain 36 and 104 unresolved unique requests respectively; those are not interchangeable with target-cell counts. The 48-row companion CSV reports missingness by task, level and condition.

Total: 7,424 API attempts; all have known usage. Input: 17,168,562 tokens. Output including thinking: 3,382,963 tokens. List-price token estimate: USD 9.366585. Planning estimate: AUD 15.015609 using AUD/USD 1.50 and input multiplier 1.15. These amounts are calculated from the recorded token usage and stated pricing assumptions only. Provider billing updates are delayed and the official billing report is not yet available for download. The final billed expense remains unverified.

## Integrity and interpretation limits

- Configuration, prompts, eligibility, rubric set and statistical rules remain frozen. Intermediate main adaptation uses I1/I2; I3, discrimination and citation support remain reference-only.
- Saved JSONL contains valid Unicode line separators inside strings. The legacy reader incorrectly splits these characters. A separate ASCII-escaped export fixes serialization compatibility only. Decoded JSON values are identical, with new hashes recorded in serialization-verification.json. No raw results, cache, ledger, receipt or score was overwritten.
- The native report loaded the correctness score binding and assembled judge provenance successfully. The delivery is separately packaged and its native reading and statistical replay are verified offline. This is software verification, not an independent human review of judge accuracy.
- Reduced validity scope and waived independent human audit/rubric review remain disclosed. Known citation-field limitations remain; no post-Test scoring rule was relaxed. Test questions had retrieval-development exposure; do not claim fully untouched end-to-end evaluation or learner benefits.

## Delivery and review

The scoring archive includes all 2,244 source-bound joined rows, native score inputs,
correctness bindings, judge outputs, frozen configuration and this analysis. The
companion audit archive preserves original generation inputs, results, requests,
caches, usage ledgers and completion receipts. M8 owns aggregation and this report;
M7 may consume the scores for integration or verification without regenerating answers.

The Leader should review the findings and claim boundaries. Pre-release publication
makes the artifacts available for review; it does not change `reportable=false`.
No rule tuning, threshold change or additional paid run was performed after Test.

## Descriptive supporting results

The following tables are descriptive, not additional primary hypothesis tests.
Discrimination and citation support remain reference-only. N/A fractions have
resolved criterion judgments as denominators; missing judgments are not N/A.
The native intermediate main rate uses I1/I2 and retains I3 separately.

### Main adaptation, available answers

| Level | Condition | Resolved / eligible | Mean main criterion pass rate |
|---|---|---:|---:|
| beginner | P0R0_plain | 124 / 128 | 70.56% |
| beginner | P1R0_prompt_only | 127 / 128 | 78.08% |
| beginner | P0R1_reranking_only | 125 / 128 | 70.20% |
| beginner | P1R1_combined | 126 / 128 | 78.17% |
| intermediate | P0R0_plain | 124 / 128 | 95.97% |
| intermediate | P1R0_prompt_only | 127 / 128 | 97.64% |
| intermediate | P0R1_reranking_only | 124 / 128 | 95.16% |
| intermediate | P1R1_combined | 126 / 128 | 96.83% |
| advanced | P0R0_plain | 128 / 128 | 83.72% |
| advanced | P1R0_prompt_only | 126 / 128 | 80.69% |
| advanced | P0R1_reranking_only | 128 / 128 | 84.51% |
| advanced | P1R1_combined | 127 / 128 | 80.18% |

### Reference discrimination

| Condition | Resolved target cells | Correct level guesses | Accuracy among resolved cells |
|---|---:|---:|---:|
| P0R0_plain | 561 | 176 | 31.37% |
| P0R1_reranking_only | 560 | 187 | 33.39% |
| P1R0_prompt_only | 561 | 199 | 35.47% |
| P1R1_combined | 561 | 206 | 36.72% |

### Reference evidence metrics

Available numeric per-answer values are averaged; N/A is excluded and its count
is disclosed. Claim-level and answer-level averages are different quantities.
Citation support retains the known citation-field limitations of the frozen pipeline.

| Condition | Resolved answers | Bundle-evaluable answers | Mean bundle faithfulness | Citation-evaluable answers | Mean citation support |
|---|---:|---:|---:|---:|---:|
| P0R0_plain | 527 | 527 | 95.00% | 523 | 89.53% |
| P0R1_reranking_only | 536 | 534 | 94.45% | 533 | 90.25% |
| P1R0_prompt_only | 525 | 523 | 94.07% | 523 | 85.77% |
| P1R1_combined | 525 | 523 | 93.67% | 522 | 86.53% |

Full matrices, level-by-condition reference means and B3/A2/A3 N/A fractions:
[reference-descriptive-summary.json](reference-descriptive-summary.json).
Registered results: [registered-test-analysis.json](registered-test-analysis.json).
Missingness: [missingness_by_task_level_condition.csv](missingness_by_task_level_condition.csv).
