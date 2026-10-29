> Status update: see [perturbation results](perturbation-results/README.md) and [Dev I3 comparison](perturbation-results/DEV_I3_SENSITIVITY.md). Planning sections below retain the pre-run snapshot. Current policy excludes I3 from the main intermediate rate and reports it separately. Original offline tables below retain their original three-criterion basis.

# Dev diagnostics supplement and perturbation review draft

## What is completed

Five offline computations are complete: P0R0 level-bias observations; within-level length/formula associations; paired generation noise; existing task/model/level/condition missingness; and B3/A2/A3 not-applicable proportions. No new API calls were made, and no Test data was used. These are descriptive measurements, not a blanket validity pass. Source scoring files and the published core handoff remain unchanged.

## P0R0 level-bias observations

| Generator | Answered control cells | Available | Observed match to hidden target | Absolute deviation from 1/3 |
|---|---:|---:|---:|---:|
| gpt-oss | 462 | 462 | 32.90% | 0.43% |
| llama | 462 | 462 | 33.77% | 0.43% |
| gemma | 462 | 462 | 32.47% | 0.87% |

All three target levels have 154 cells per generator. The target is hidden from the discrimination judge. The 1/3 comparison follows the repository's P0R0 diagnostic. Label guesses are not uniform: most plain answers are classified beginner. Chance-like agreement with the hidden target does not prove balanced predictions, fairness or judge accuracy. Repeated/identical answers are not independent subjects. M8 proposes a 5-percentage-point screening tolerance in THRESHOLD_PROPOSAL.md. This remains unapproved, so saved passed flags stay null.

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

M8 proposes an N/A coverage warning at 80%, subject to Leader approval (see THRESHOLD_PROPOSAL.md). Saved warning fields remain null until approval. A2 is about 89–90% N/A in these resolved requests; this merits contextual review but is not automatically a rule violation. Recognition questions can legitimately require no additional assumptions or quantitative relationship. No always-assessed criterion returned N/A in this validated view.

## Paired generation noise

Each generator has 30 repeated Dev questions × 12 cells = 360 pairs. Native saved report results were independently checked against paired source rows. Correctness missing pairs stay in the 360-pair denominator as bounds.

| Generator | Known strict-correct flips | Missing pairs | Flip-rate bounds | Observed adaptation mean absolute rate difference |
|---|---:|---:|---|---:|
| gpt-oss | 8 | 5 | 2.22%–3.61% | 0.0674 |
| llama | 22 | 1 | 6.11%–6.39% | 0.0735 |
| gemma | 6 | 7 | 1.67%–3.61% | 0.0292 |

Native noise-floor bounds and by-condition/level details are in generation_noise.json and generation_noise_summary.csv. The registered primary contrast and delta are not supplied, so a noise-floor comparison against delta is not claimed. Adaptation score differences use available pairs and record excluded/N/A/unresolved counts separately. Generation noise is not an independent repeat of the judge on identical answers.

## Missingness

The existing full task × generator × target-level × condition tables are copied byte-for-byte. Dev and generation-repeat cohorts remain separate; adaptation additionally has an all-checklist-level table. Scored system-zero generation failures stay distinguished from null judge outcomes. Evidence missingness differs between generators; use the detailed tables rather than assume complete-case model comparisons are unbiased.

## Small perturbation v2: redesigned for review, not run

The v1 stock-template design has been replaced. The v2 draft uses 18 different Dev
questions, with one case for each target/generator pair (six per generator), and
covers all four experimental conditions. Selection is purposeful and constrained
by coverage; it is not a representative random sample. Exact IDs, source hashes,
controlled edits and reasons are tracked in curated_edits.v2.json. Approval of the
revised selection approach remains pending. Source scoring records are unchanged.

| Target | Three subject-specific changes |
|---|---|
| B1 | Sap-transport wording compressed into hydraulic jargon; accessible inertia wording replaced by formal language; equipotential definition removed |
| B4 | Local pressure derivative without notation explanations; ideal-mixture pressure sum written with unexplained indices; sound-level logarithm without symbol definitions |
| A1 | Elementary vector preface to a magnetic-force answer; circuit definitions interrupting a loop-law answer; repeated velocity-difference walkthrough in a falling-ball answer |
| I3 | Quantum-color explanation removed; plain lensing description replaced by unexplained general-relativistic concepts; mastered frequency/period definitions repeated in an atomic-clock answer |
| Correctness | Carbon proton-count error updated consistently in both mentions; positive-current direction reversed; dispersion confused with diffraction |
| Evidence support | A temperature-specific sound speed not given in the bundle; an unprovided delayed-neutron mechanism; an unprovided parallel-voltmeter procedure |

Each target has proposed clear, moderate and subtle cases, six of each overall.
Every difficulty label has a case-specific reason recorded before scoring; these
are design judgements, not measured difficulty. The Leader must confirm or revise
labels before freezing and must reject a case if the intended failure is not real.
The correct answer is not retained elsewhere as an artificial contradiction cue.
For correctness, repeated mentions of one wrong fact are changed consistently.

The proposed detection rule remains at least 15 of 18 cases and at least one
per target. An unresolved output remains in the denominator as not detected and is
reported separately. An evidence detection must address the added subclaim as
unsupported by the supplied bundle; factual truth established in an external
review reference does not establish bundle support. Omitting the subclaim is not
a successful detection. These rules are pending approval, not observed results.

Read perturbation-draft/REVIEW_PENDING.md for originals, changed answers, frozen
clauses, edit spans, difficulty rationales and review-only physics references.
Every case has pending checks for the target violation, other-criterion effects,
full-answer consistency and final approval. Source/boundary checks are mechanical;
no semantic isolation or human approval is claimed. The saved baseline pass is a
selection filter, not independent physics validation. External reference pages
must never be added to the scoring evidence. This small audit does not estimate
population judge accuracy and does not test A4/I2 reasoning-depth requirements.

All perturbation model calls are still unrun. Approve the sample, difficulty labels,
detection rule and budget before scoring, and record Test-scoring decisions before
viewing Test quality scores. Re-estimate cost from the approved v2 requests;
the older v1 average estimate is not a cap or execution approval. Use the unchanged
production judge configuration with separate IDs, results, caches and call logs.

## Parallel work and Test order

M7 may read current saved scores, validate file integration and prepare the generation interface while these diagnostics and human reviews proceed. M7 has already published Test generation in PR #221. Decisions affecting remaining Test quality scoring, thresholds and reporting treatment require a versioned team record before scoring and before viewing any Test quality scores. Record the actual timing and any earlier Test access; do not backdate a freeze or tune choices to Test outcomes. Completing this descriptive supplement does not satisfy other outstanding reportable gates. The scoring handoff remains usable for engineering integration with its existing caveats.
