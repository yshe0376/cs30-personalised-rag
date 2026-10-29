# Six-step perturbation audit: ownership and actual status

This is the small synthetic-answer sensitivity test described in the Leader's plan.
It is separate from the five existing-output computations.
No perturbed-answer model call, human approval or detection result exists yet.

| Step | Work | Responsible role | Current status |
|---|---|---|---|
| 1 | Approve exact criteria, expected reactions, detection rule, sample scope and decision record before Test quality scoring | Leader decides; M8 prepares the proposal | Proposed only; not approved or frozen |
| 2 | Select eligible passed/correct Dev originals with fixed seed and provenance | M8 prepares; Leader confirms scope | 18 candidate originals selected; seed 5703 and identities recorded |
| 3 | Draft one controlled change per answer, with before/after spans | M8 prepares programmatic draft edits for Leader review | 18 programmatic candidate edits prepared; Leader review pending |
| 4 | Review EVERY edit for intended violation, unchanged factual content and other-criterion effects; reject/rewrite unsuitable cases, then freeze hashes | **Leader** | **Pending; M8 has not confirmed on the Leader's behalf** |
| 5 | Re-score approved frozen perturbations with the same model, prompt, low thinking, rubric/profile and runtime settings; write separate results/cache/attempt logs | **M8**, after review and budget confirmation | **Not started; zero new model calls** |
| 6 | Report target detection, missing outcomes and changes on non-target criteria; describe authorship, reviewer, sample size and limits | **M8** prepares; Leader reviews the conclusion | **Not started; requires step 5 outputs** |

M8's next execution stage is step 5, followed by step 6. Preparing and packaging
inputs and the offline Dev summaries does not transfer the Leader's step 4 review
to M8. The release and this branch are materials to review, not review approval.

## Proposed target selection needs explicit confirmation

The 18 candidates cover B1, B4, A1, I3, correctness and evidence support, with three
generators for each target. This target choice is NOT frozen. The Leader's plan
groups several possible clauses. The proposal chooses redundancy additions for A1
and I3, because deleting a required derivation can also change correctness completeness.
It therefore does not test A4/I2 reasoning depth. The Leader may accept this choice,
choose the original suggested reasoning deletions instead, or reject/rewrite cases.

A1 must not be described as requiring advanced derivation: the frozen clause concerns
needless introductory teaching. Short recognition answers must not fail solely for
having no derivation. B4 does not require every answer to contain a formula.

## Review handoff

Open perturbation-draft/REVIEW_PENDING.md. Each entry links its question, original,
changed text, target rule, single edit, baseline verdict and pending decision. Review
status, reviewer identity/time and semantic-isolation confirmation remain unset.
The 80% overall / at-least-one-per-target rule is proposed, not an approved threshold.
M8 proposes an 80% N/A coverage warning in THRESHOLD_PROPOSAL.md; the approved threshold remains unset.

The first 18 edits are drafts. Fixed-seed selection and string/hash checks prove
reproducibility and byte-level isolation; they do not prove pedagogical validity or
that the target really fails. Human confirmation must precede any model scoring.

## Parallel work with M7

M7 can download/read existing saved scores and develop integration in parallel.
Test generation is already published in PR #221. The team must record the approved
criteria, thresholds and scoring policy before remaining Test quality scoring and
before viewing any Test quality scores. Disclose actual timing and earlier data
access; do not backdate approval or adjust decisions to Test outcomes.
Descriptive statistics and a small sensitivity sample do not automatically clear other formal reportability requirements.
