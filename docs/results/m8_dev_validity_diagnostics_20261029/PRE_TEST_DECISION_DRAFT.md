# Proposed small perturbation audit before Test scoring (review required)

Status: draft, not approved or frozen; no perturbed judge outcomes observed.
Test generation is already published in PR #221. Approval must precede perturbation
scoring and remaining Test quality scoring, before any Test quality scores are viewed.

Concrete candidate screening limits are in THRESHOLD_PROPOSAL.md. They were
proposed after inspecting Dev summaries and are not retrospective preregistration
or a complete production validity configuration. Approval remains pending.

- Scope: Dev-only synthetic audit; no Test inputs or primary score replacement.
- Candidate targets: B1, B4, A1, I3, correctness and evidence support. The v2
  sample has 18 distinct Dev questions, three cases per target and six per generator.
  Selection is purposeful under explicit coverage constraints, not random. Exact
  originals/edits are in curated_edits.v2.json; case IDs/hashes are in selection_manifest.json.
  A1 tests topic-specific redundancy. I3 includes both specialist-language gaps and
  redundant course-core definitions. This does not test A4/I2 reasoning depth.
- Difficulty proposals: one clear, moderate and subtle case per target, each with a
  case-specific rationale. Confirm/freeze these labels before scoring; do not revise
  labels in response to judge outcomes. All labels and cases remain review-pending.
- The original full answers remain preserved; code verifies one contiguous edit.
  Leader review is still needed for semantic isolation and factual preservation.
- Proposed detection rule: >=80% overall (at least 15/18), at least one case in each target
  detected. Missing outputs remain in the denominator. Record every other-criterion
  change separately. Thresholds are proposals until approved in this decision record.
- Review and freeze the approved cases/checksum BEFORE any synthetic judge call.
- Runtime after separate authorisation: same production prompt/rubric/frozen profile,
  model, temperature and thinking low. Fresh IDs/cache/output/attempt log; no score
  enters primary Dev/Test. Request count 18; up to two application attempts would mean
  up to 36 attempts, not an assured 18 billable calls. Estimate cost before launch.
- If a selected criterion fails this limited audit, record the agreed Test reporting
  treatment explicitly; do not silently change the criterion or tune on Test scores.
- N/A warning X remains undefined: counts/rates only, no invented warning decision.
- This audit does not establish population accuracy, complete human calibration or
  automatically clear the repository's other reportability gates.

Leader decision: pending.
Reviewer identity/time: pending.
Approved targets/cases/final checksum: pending.
Approved thresholds/runtime/budget: pending.
