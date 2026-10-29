# Dev diagnostics supplement and perturbation review draft

## What is completed

Five offline computations are complete: P0R0 level-bias observations; within-level length/formula associations; paired generation noise; existing task/model/level/condition missingness; and B3/A2/A3 not-applicable proportions. No API or Test data was used. These are descriptive measurements, not a blanket validity pass. Source scoring files and the published core handoff remain unchanged.

## P0R0 level-bias observations

| Generator | Answered control cells | Available | Observed match to hidden target | Absolute deviation from 1/3 |
|---|---:|---:|---:|---:|
| gpt-oss | 462 | 462 | 32.90% | 0.43% |
| llama | 462 | 462 | 33.77% | 0.43% |
| gemma | 462 | 462 | 32.47% | 0.87% |

All three target levels have154cellspergenerator. The target is hidden from the discrimination judge. The1/3comparison follows the repository's P0R0 diagnostic. Label guesses are not uniform: most plain answers are classified beginner. Chance-like agreement with the hidden target does not prove balanced predictions, fairness or judge accuracy. Repeated/identical answers are not independent subjects. No acceptance threshold has been supplied, so passed=null.

## Length and formula associations

| Generator | Target level | Valid target-level answers | Word-count/rate correlation | Formula minus no-formula mean rate |
|---|---|---:|---:|---:|
| gpt-oss | beginner | 596 | -0.081 | -0.238 |
| gpt-oss | intermediate | 610 | 0.085 | 0.016 |
| gpt-oss | advanced | 614 | -0.284 | -0.218 |
| llama | beginner | 586 | -0.036 | -0.196 |
| llama | intermediate | 574 | -0.131 | 0.068 |
| llama | advanced | 602 | -0.441 | -0.078 |
| gemma | beginner | 596 | 0.067 | -0.152 |
| gemma | intermediate | 608 | 0.087 | 0.003 |
| gemma | advanced | 615 | -0.178 | -0.060 |

The outcome above is the continuous criterion_pass_rate, not an invented aggregate pass/fail cutoff. The supplement also contains within-level/condition results and criterion-specific binary-pass correlations/gaps. Overall adaptation pass and validity thresholds are unfrozen; this does not claim the frozen binary surface-bias gate passed. Negative or positive associations can reflect legitimate content requirements or question difficulty, not necessarily judge bias. Advanced A1 explicitly discourages unnecessary introductory teaching; beginner B4 evaluates whether notation is explained. Do not turn these associations into causal findings.

## Optional-criterion not_applicable proportions

Denominator: resolved unique Dev adaptation requests that include the criterion. It is not every generated cell and not all criteria pooled together. Unresolved cases are documented in missingness tables; they are not converted into N/A.

| Generator | Criterion | N/A | Available criterion judgements | N/A proportion |
|---|---|---:|---:|---:|
| gemma | A2 | 377 | 417 | 90.41% |
| gemma | A3 | 297 | 417 | 71.22% |
| gemma | B3 | 248 | 489 | 50.72% |
| gpt-oss | A2 | 492 | 551 | 89.29% |
| gpt-oss | A3 | 416 | 551 | 75.50% |
| gpt-oss | B3 | 322 | 578 | 55.71% |
| llama | A2 | 415 | 461 | 90.02% |
| llama | A3 | 345 | 461 | 74.84% |
| llama | B3 | 243 | 481 | 50.52% |

The user confirmed the warning threshold X is not yet decided. Warning fields stay null. A2 is about89–90%N/A in these resolved requests; this merits contextual review but is not automatically a rule violation. Recognition questions can legitimately require no additional assumptions or quantitative relationship. No always-assessed criterion returned N/A in this validated view.

## Paired generation noise

Each generator has30repeatedDevquestions ×12cells=360pairs. Native saved report results were independently checked against paired source rows. Correctness missing pairs stay in the360denominator as bounds.

| Generator | Known strict-correct flips | Missing pairs | Flip-rate bounds | Observed adaptation mean absolute rate difference |
|---|---:|---:|---|---:|
| gpt-oss | 8 | 5 | 2.22%–3.61% | 0.0674 |
| llama | 22 | 1 | 6.11%–6.39% | 0.0735 |
| gemma | 6 | 7 | 1.67%–3.61% | 0.0292 |

Native noise-floor bounds and by-condition/level details are in generation_noise.json and generation_noise_summary.csv. The registered primary contrast and delta are not supplied, so a noise-floor comparison against delta is not claimed. Adaptation score differences use available pairs and record excluded/N/A/unresolved counts separately. Generation noise is not an independent repeat of the judge on identical answers.

## Missingness

The existing full task × generator × target-level × condition tables are copied byte-for-byte. Dev and generation-repeat cohorts remain separate; adaptation additionally has an all-checklist-level table. Scored system-zero generation failures stay distinguished from null judge outcomes. Evidence missingness differs between generators; use the detailed tables rather than assume complete-case model comparisons are unbiased.

## Small perturbation: prepared for review, not run

There are18single-edit drafts: B1,B4,A1,I3,correctness,evidence-support ×3generators, seed5703. All base answers were scored2and each adaptation target originally passed. The proposed A1/I3 redundancy cases are an alternative to deleting requested reasoning, which could also damage correctness completeness. They do not test A4/I2, and require Leader approval of the target selection. Appended tutorials and true-but-unprovided evidence claims retain the original answer text. Correctness replaces the required answer velocity with acceleration for displacement/time; it does not merely change a figure number.

Read perturbation-draft/REVIEW_PENDING.md for every question, original, modified answer, exact frozen criterion, single edit and pending decision. No claim of semantic isolation or human confirmation is made yet. The six target clauses,18cases and proposed80%detection-plus-at-least-one-per-target rule must be recorded/frozen before judging these perturbations or inspecting Test results. With18cases,80%requires at least15detected cases, and at least1of3in each target group. Unresolved judge outputs must not disappear from the audit denominator.

The code can verify byte-level single-edit isolation; only the human review can confirm that a changed answer really violates exactly the intended criterion while preserving other requirements. No live requests or runnable paid commands are included. After review and budget agreement, use the frozen production configuration, fresh IDs, new caches/results/attempt logs, and keep synthetic audit scores out of primary Dev/Test scores. The future report must state authoring method, reviewer, counts, target/other-criterion changes and limits; this is a small sensitivity audit, not population judge accuracy.

## Parallel work and Test order

M7 may read current saved scores, validate file integration and prepare the generation interface while these diagnostics and human reviews proceed. Any choices that change final model selection, thresholds, exclusion/reference-only criteria or scoring policy need a versioned team decision before formal Test generation/scoring as applicable. Do not tune choices after seeing Test outcomes. Completing this descriptive supplement does not satisfy other outstanding reportable gates. The scoring handoff remains usable for engineering integration with its existing caveats.
