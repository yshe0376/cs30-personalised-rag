# Proposed pre-Test small perturbation audit (review required)

Status: draft, not registered, no perturbed judge outcomes observed.

Concrete candidate screening limits are in THRESHOLD_PROPOSAL.md. They were
proposed after inspecting Dev summaries and are not retrospective preregistration
or a complete production validity configuration. Approval remains pending.

- Scope: Dev-only synthetic audit; no Test inputs or primary score replacement.
- Candidate targets: B1, B4, A1, I3, correctness, evidence supportedness. Three base
  generators per target, one case per generator, total 18. Seed 5703 and case IDs/hash
  in selection_manifest.json. A1/I3 use redundant-tutorial additions as a proposed
  alternative to derivation deletion; the Leader must approve this choice first.
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
