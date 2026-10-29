# Candidate diagnostic limits for Leader review

Proposal version: dev-diagnostic-limits-v1-draft, 2026-10-29.

Status: proposed by M8 for M7 and Leader review; not approved, frozen or active.
These are project-specific screening choices, not published universal standards or
a powered statistical validation design. No threshold is applied to production
scores, no existing result is relabelled as passed, and no model call is authorised.

## Ownership and timing

The Leader's plan proposes a detection rule and assigns approval of rules
and every answer edit to the Leader. M8 can submit a concrete candidate; the
repository currently assigns formal threshold proposal to M7 and confirmation to
the Leader. This document is input to that joint decision, not M7 endorsement or
Leader approval. Please accept, amend or point to an already authoritative version.

These candidates were written after the Dev diagnostics were inspected. They are
therefore exploratory, Dev-informed proposals, not thresholds preregistered before
the Dev run. Test generation has already been published in PR #221; that PR
explicitly leaves Test quality scoring and judge validity pending. This proposal
does not establish that Test content/results have never been inspected by anyone.
Record the actual approval and data-access dates, and distinguish retrospective
Dev checks from any later prospective assessment. Do not backdate approval or tune
these values after inspecting Test scores.

## Proposed values and meanings

| Check | Candidate value | Minimum data / denominator | Action and reason |
|---|---|---|---|
| P0R0 target matching | Absolute distance from 1/3 <= 0.05 (5 percentage points; approximately 28.33%-38.33% matching) | At least 90 answered cells, all three target levels equally represented and at least 30 per target; disclose unique questions/answers and uncertain guesses | Outside this interval requires investigation. A round 5-point tolerance limits the allowed shift; it is not a significance test or evidence of fair prediction distributions. Correlated/repeated cells are not independent subjects. |
| Within-level length association | Review when absolute Pearson r > 0.30 | At least 30 usable observations per generator/target-level stratum, with variation in both length and outcome | A deliberately interpretable screening limit for a noticeable association; not a causal-bias verdict. Report condition-specific details and question/content confounding. Do not pool levels to claim a pass. |
| Formula versus no-formula difference | Review when absolute rate difference > 0.10 (10 percentage points) | At least 30 usable observations per generator/target level, including at least 10 with and 10 without a formula | A 10-point shift is a practical review trigger. If either subgroup is too small, report insufficient evidence for that comparison rather than passing it. |
| Optional-criterion N/A warning X | Warn at N/A proportion >= 0.80 (80%) | At least 30 resolved unique Dev adaptation requests for the individual criterion/generator; B3, A2 and A3 separately; unresolved requests stay separate | Four out of five available judgements not assessing a criterion warrants checking its opportunity/applicability. This is a coverage warning, not a failed judgement or automatic criterion rejection. |
| Small perturbation detection | At least 80% overall and at least one detection in every target group | 18 Leader-approved cases, three per target and one per generator, with targets/edits frozen before scoring; at least 15/18 detections | Retains the Leader's suggested rule. Missing/unresolved outputs count as not detected in the overall denominator and are also reported separately. No target group may have zero detections. The small targeted sample does not estimate population judge accuracy. |

The sample-count choices above are practical screening safeguards, not a power
calculation. If the Leader rejects a draft case, replace and approve it before
judging so the proposed 18-case denominator is retained, or record a revised plan
before any perturbed outcomes are observed.

## Important surface-check boundary

The current supplement reports continuous criterion_pass_rate associations and
criterion-specific binary verdicts. The production surface_bias_check instead
expects an aggregate binary adaptation pass outcome. Its adaptation_pass_threshold
must be separately approved before that formal binary check can be assembled.

The 0.30 / 0.10 values above are candidate review triggers for the current
descriptive summaries, not evidence that the production binary gate ran or passed.
If adopted as production ValidityThresholds values, recompute the correct binary
outcomes and record the agreed reporting treatment for a failed check first. The
formula subgroup safeguard is an additional proposed interpretation rule; it is
not silently implemented by changing the existing validator in this PR.

## What these proposals would highlight in the observed Dev summaries

- P0R0 deviations are approximately 0.43, 0.43 and 0.87 percentage points for the
  three generators, within the proposed 5-point interval. Predictions are still
  mostly beginner: the target-matching result alone does not establish fairness
  or useful level discrimination.
- Llama's advanced length/rate correlation is approximately -0.441, beyond the
  proposed absolute 0.30 review line. GPT-OSS beginner formula/no-formula mean
  rates differ by approximately 23.8 percentage points, beyond the proposed
  10-point line. Other strata and subgroup counts must also be reviewed; this is
  not a complete list of flagged comparisons or a causal conclusion.
- A2 N/A proportions are approximately 89%-90% across generators. They would all
  receive the proposed coverage warning. Identification questions can legitimately
  make A2 inapplicable; this warning does not prove the judge or checklist is wrong.
- Perturbation scoring has not run. No detection pass/fail result exists.

These observations illustrate consequences of the proposed limits; they do not
retroactively turn an exploratory Dev analysis into confirmatory validation.
Retain all observed problems and missing outcomes regardless of the final choice.

## Decisions outside this proposal

Do not invent a new acceptance cutoff for generation noise or missingness here.
Keep their measured values and bounds. The registered primary metric/contrast,
correctness non-inferiority margin delta and adaptation pass threshold remain team
decisions to obtain from M7 and the Leader. Generation-noise comparison with delta
needs the registered paired sample definition. Repeat-judge, order and second-family
judge checks are outside the completed work in this PR and remain unrun unless
separately documented; this small proposal is not a complete ValidityThresholds
configuration.

This file changes no scoring rules, frozen profile text, original records, Release
assets, reportability flags or execution budget.

## Requested review response

Please record accept/amend/existing-decision-link for each row, plus the approved
version, scope, owner and date. Confirm target selection and every answer edit
separately. M8 will only apply the approved configuration after that review; paid
perturbation execution remains a separate, user-initiated action.

Leader decision: pending.
M7 confirmation or authoritative decision link: pending.
Approved threshold version and decision date: pending.

## Method references and attribution

The numerical cutoffs in this document are this project's proposals. The sources
below support transparent timing and interpretation, not these numerical values.

- [Center for Open Science: Preregistration](https://www.cos.io/initiatives/prereg):
  distinguish exploratory work from analyses specified before the relevant outcomes
  were inspected.
- [NIST: Scatter Plot](https://itl.nist.gov/div898/handbook/eda/section3/eda33q.htm):
  association alone does not demonstrate causality.
