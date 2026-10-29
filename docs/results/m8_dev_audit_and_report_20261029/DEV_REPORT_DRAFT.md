# Dev evaluation report draft and human-audit handoff

**Draft; reportable=false.** No completed independent human audit is claimed. Dev-only preparation; no Test answers were read and no API was called.

## Start here

Leader/M3: read [the audit guide](audit/AUDIT_GUIDE.md), confirm the draft audit rubric, optionally inspect calibration_review.md, then review the 20 cases in [independent_review.md](audit/independent_review.md). Fill actual decisions in the pending lines in the review sheet; M8 transcribes them to ratings.pending.jsonl and later checks the ratings with the private binding key and native load_bound_human_audit. Preparing this packet does not complete an audit.

Selected scope: GPT-OSS only, with ten orientation/calibration cases and 20 independent audit cases. Llama and Gemma remain unaudited. The orientation cases are not proof of completed historical calibration or permission to tune the frozen judge. This branch includes the merged #223 follow-up; no new PR or Release update is implied.

## Scope and sources

154 Dev questions x three levels x four conditions = 1,848 cells per generator; 5,544 primary Dev cells. A separate 30-question generation-repeat cohort contributes 360 cells per generator (1,080 total). Combined handoff coverage is 6,624 cells; repeat cells do not enlarge the primary Dev denominator.

Arms: P0R0 plain, P1R0 prompt-only, P0R1 reranking-only, P1R1 combined. All four tasks were scored. Lambda=0.1; gemini-3.1-flash-lite, thinking low, temperature 1; frozen profile 1888c3b7. Its independent physics review was waived, not completed.

Source: [existing Dev Release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m8-full-dev-low-20261028), scoring archive SHA-256 da1b860a1204bb16a79026c5433614fa0d1b6202dfdbf9502d725e871969d07e. All original scores, caches and logs remain unchanged.

## Correctness coverage (primary Dev only)

| Generator | Cells | Strict-correct | Unresolved | Strict-correct bounds |
|---|---:|---:|---:|---|
| gpt-oss | 1848 | 1774 | 11 | 96.00% - 96.59% |
| llama | 1848 | 1609 | 3 | 87.07% - 87.23% |
| gemma | 1848 | 1724 | 6 | 93.29% - 93.61% |

Unresolved judgements remain unknown in the denominator; no complete-case point accuracy is substituted. Mean score/2 is not accuracy. Generation failures and unresolved judge outputs are distinct.

## Saved exploratory contrasts (legacy I3-inclusive basis)

Adaptation below is a continuous mean criterion pass rate, not a thresholded answer pass rate. The saved contrasts include I3 and are not the final revised primary analysis. Intervals are the saved question-cluster bootstrap intervals. No primary contrast, multiplicity correction or non-inferiority margin is invented.

| Generator | Metric | Contrast | Difference (pp) | Interval (pp) | Resolved pairs | Question clusters | Missing pairs |
|---|---|---|---:|---|---:|---:|---:|
| gpt-oss | strict_correct | prompt_without_reranking | -0.66 | [-1.99, +0.44] | 455 | 154 | 7 |
| gpt-oss | strict_correct | prompt_with_reranking | +0.22 | [-1.09, +1.53] | 459 | 154 | 3 |
| gpt-oss | strict_correct | reranking_without_prompt | -0.87 | [-1.97, +0.00] | 458 | 153 | 4 |
| gpt-oss | strict_correct | reranking_with_prompt | +0.00 | [-1.33, +1.53] | 455 | 154 | 7 |
| gpt-oss | adaptation_criterion_pass_rate | prompt_without_reranking | -0.76 | [-3.12, +1.56] | 309 | 106 | 9 |
| gpt-oss | adaptation_criterion_pass_rate | prompt_with_reranking | +1.22 | [-1.03, +3.61] | 313 | 106 | 5 |
| gpt-oss | adaptation_criterion_pass_rate | reranking_without_prompt | -0.35 | [-2.58, +1.96] | 312 | 106 | 6 |
| gpt-oss | adaptation_criterion_pass_rate | reranking_with_prompt | +1.82 | [+0.03, +3.64] | 312 | 106 | 6 |
| llama | strict_correct | prompt_without_reranking | -8.48 | [-12.94, -4.33] | 460 | 154 | 2 |
| llama | strict_correct | prompt_with_reranking | -9.11 | [-12.34, -5.86] | 461 | 154 | 1 |
| llama | strict_correct | reranking_without_prompt | +0.87 | [-1.30, +3.26] | 460 | 154 | 2 |
| llama | strict_correct | reranking_with_prompt | +0.43 | [-3.46, +4.55] | 462 | 154 | 0 |
| llama | adaptation_criterion_pass_rate | prompt_without_reranking | -1.17 | [-4.14, +1.74] | 291 | 105 | 3 |
| llama | adaptation_criterion_pass_rate | prompt_with_reranking | -0.54 | [-3.72, +2.58] | 292 | 106 | 4 |
| llama | adaptation_criterion_pass_rate | reranking_without_prompt | -0.24 | [-2.18, +1.60] | 313 | 106 | 5 |
| llama | adaptation_criterion_pass_rate | reranking_with_prompt | -0.15 | [-2.95, +2.76] | 282 | 105 | 2 |
| gemma | strict_correct | prompt_without_reranking | +1.96 | [-0.65, +5.00] | 460 | 154 | 2 |
| gemma | strict_correct | prompt_with_reranking | +1.09 | [-1.52, +3.94] | 458 | 154 | 4 |
| gemma | strict_correct | reranking_without_prompt | +0.43 | [-0.44, +1.52] | 461 | 154 | 1 |
| gemma | strict_correct | reranking_with_prompt | -0.44 | [-1.75, +0.87] | 458 | 154 | 4 |
| gemma | adaptation_criterion_pass_rate | prompt_without_reranking | +6.26 | [+2.81, +10.02] | 310 | 106 | 8 |
| gemma | adaptation_criterion_pass_rate | prompt_with_reranking | +7.20 | [+4.19, +10.68] | 310 | 106 | 8 |
| gemma | adaptation_criterion_pass_rate | reranking_without_prompt | -0.64 | [-1.96, +0.77] | 311 | 106 | 7 |
| gemma | adaptation_criterion_pass_rate | reranking_with_prompt | +0.16 | [-1.47, +1.88] | 310 | 106 | 8 |

### Llama prompt contrasts: resolved-count warning

The Leader's final #223 review requires resolved counts beside Llama prompt contrasts. Above, resolved pairs and question clusters describe each exact contrast's available paired sample, not independent answer counts. Below is the separate intermediate-level coverage context. In the all-target view, each prompt arm has 134/154 resolved, versus 153/154 in each no-prompt arm. This imbalance can affect available-case comparisons. The main-eligible subset has a different denominator; do not substitute one scope for another.

| Scope | Condition | Resolved / expected | Unresolved |
|---|---|---:|---:|
| all_target_intermediate | P0R0_plain | 153 / 154 | 1 |
| all_target_intermediate | P0R1_reranking_only | 153 / 154 | 1 |
| all_target_intermediate | P1R0_prompt_only | 134 / 154 | 20 |
| all_target_intermediate | P1R1_combined | 134 / 154 | 20 |
| main_eligible_intermediate | P0R0_plain | 106 / 106 | 0 |
| main_eligible_intermediate | P0R1_reranking_only | 106 / 106 | 0 |
| main_eligible_intermediate | P1R0_prompt_only | 96 / 106 | 10 |
| main_eligible_intermediate | P1R1_combined | 93 / 106 | 13 |

Reranking effects are not clearly demonstrated in these exploratory comparisons; this is not proof of no effect. These are judge evaluations, not learner outcomes.

## I3 and supporting diagnostics

The Leader confirmed intermediate-i3-reference-only-v1: main intermediate rates use I1/I2 and report I3 separately, without changing the checklist or prompts. The [Dev I3 comparison](../m8_dev_validity_diagnostics_20261029/perturbation-results/DEV_I3_SENSITIVITY.md) gives paired available-cell changes of 0.00 pp for GPT-OSS, -0.44 pp for Gemma and -1.66 pp for Llama in the native main intermediate scope. The original handoff retains legacy aggregates. Final reporting must explicitly apply the new policy and recompute the selected contrasts consistently.

[Existing diagnostics](../m8_dev_validity_diagnostics_20261029/REPORT.md) provide P0R0 observations, within-level length/formula associations, generation-plus-judge noise, optional N/A proportions and task/model/level/condition missingness. They are descriptive, not a blanket validity pass.

## Human audit status and limits

The native sampler uses fixed seed 5703/5704, normalized-answer deduplication, disjoint calibration/audit sets and coverage of all three levels and four conditions. Known trial, evidence-confirmation and perturbation exposures are excluded by question and answer. The frame requires resolved adaptation, discrimination and evidence outputs; it cannot validate unresolved cases. Unrecorded prior exposure cannot be ruled out. Metadata is hidden in reviewer packets, but public answers may still be recognizable. No completed review or reviewer identity is fabricated.

The native audit detects obvious errors in three judge dimensions; it is not an accuracy or inter-rater-agreement estimate. Correctness observations are optional context and need Gold/rubric material for substantive review. Never tune the judge on independent audit cases. Pending ratings must fail native import until filled.

## Validity findings and claim limits

The perturbation audit detected 15/18 with I3 0/3; the original rule failed. The Leader accepted the reduced section 6 scope with I3 reference-only. No should-pass controls were run, so false-fail rate is unmeasured; evidence-llama is one observed correctness false fail. Non-target changes may include randomness. There was no independent same-answer retest, position-order check or second-family judge. Repeat measurements combine generation and judge noise; Test differences below the applicable metric-specific noise floor must not be reported as differences. Gemma/Gemini share a vendor; any Gemma advantage needs this caveat. Citation support is reference-only because of the structured citation_ids issue noted by the Leader.

## Pending decisions and next steps

| Item | Owner / next step | State |
|---|---|---|
| Primary-model human audit | Leader/M3 reviews; M8 validates ratings | prepared, not completed |
| Comparator human audits | outside the selected scope | not completed |
| Primary metric/contrast, delta, adaptation pass threshold, multiplicity | team registers decisions | pending confirmation |
| I3/reduced validity scope | Leader registers #223 decisions | confirmed in review; verify registration |
| Profile/eligibility and report provenance | owners freeze/review; M8 binds actual records | not cleared here |
| Test models, sample size, seeded sample | Leader/M7 | separate prerequisite |
| 187 Test correctness rubrics | designated reviewers | separate prerequisite |

Saved native report blockers also include unresolved scores and unbound decision fields. Preserve those blockers; do not set reportable=true because a packet or PR exists. After actual review and decisions, update the narrative and versioned analysis. The original reports remain immutable evidence of the earlier state.

Until all five #222 gates are recorded, no reading, sampling, summarizing or scoring of Test answers is allowed. Test scoring and budget are later tasks; this packet does not authorize any provider call.

## Primary Dev task coverage

Cell-level counts from the saved missingness table, not unique API requests. Repeat batches are excluded. Evidence coverage differs by generator; missing judgements are not zero or automatically N/A.

| Generator | Task | Applicable cells | Scored | Missing | Missing rate |
|---|---|---:|---:|---:|---:|
| gemma | adaptation | 1848 | 1819 | 29 | 1.57% |
| gemma | correctness | 1848 | 1842 | 6 | 0.32% |
| gemma | discrimination | 1848 | 1845 | 3 | 0.16% |
| gemma | evidence_support | 1848 | 1723 | 125 | 6.76% |
| gpt-oss | adaptation | 1848 | 1820 | 28 | 1.52% |
| gpt-oss | correctness | 1848 | 1837 | 11 | 0.60% |
| gpt-oss | discrimination | 1848 | 1847 | 1 | 0.05% |
| gpt-oss | evidence_support | 1848 | 1773 | 75 | 4.06% |
| llama | adaptation | 1773 | 1762 | 11 | 0.62% |
| llama | correctness | 1848 | 1845 | 3 | 0.16% |
| llama | discrimination | 1773 | 1773 | 0 | 0.00% |
| llama | evidence_support | 1773 | 1727 | 46 | 2.59% |

For full level/condition breakdowns use the unchanged source missingness tables. No threshold-based adaptation pass rate is inferred.
