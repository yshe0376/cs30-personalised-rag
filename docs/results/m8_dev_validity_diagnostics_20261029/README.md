# Supplemental Dev diagnostics and perturbation review draft

Start with REPORT.md. It includes the English report.
Read THRESHOLD_PROPOSAL.md for concrete Dev-informed candidate limits awaiting
M7/Leader review. Approved thresholds remain unset; no current pass flag changes.
This supplement adds five offline computations without replacing the original scores:
P0R0 observations, length/formula associations, generation noise, missingness, and
optional-criterion N/A proportions. The numeric warning threshold X is still unset.

perturbation-draft/ contains 18 single-edit candidate cases, not judged results.
Read REVIEW_PENDING.md and PLAN_DRAFT.json. Leader confirmation of target choice,
semantic isolation, thresholds and sample freeze is required before paid scoring.
A1/I3 redundancy cases are proposed alternatives to reasoning deletion; they do not
validate A4/I2. No live command or fabricated human decision is included.

The primary score handoff remains m8_scoring_handoff_20261029.tar.gz on the existing
release. This is its companion report, not a replacement scoring interface. M7
may read and integrate current saved scores in parallel. Choices affecting
remaining formal Test quality scoring must be agreed and recorded before scoring and
before viewing any Test quality scores. Test generation is already published in
PR #221; record actual decision timing and any prior data access. This supplement
does not set reportable=true.

Reproduce offline (source package and repository are explicit inputs):
python scripts/build_dev_diagnostics.py --package PATH_TO_EXTRACTED_SCORE_PACKAGE --repo PATH_TO_REPOSITORY --out NEW_EMPTY_OUTPUT_DIRECTORY --seed 5703

The script constructs no provider client, uses Dev-only inputs and refuses to
replace an existing output directory. See SOURCE_HASHES.json and verification.json.

## Review scope and current ownership

Read WORKFLOW_AND_OWNERSHIP.md for the six-step perturbation plan. The Leader must
confirm each changed answer; M8 must not record a decision on the Leader's behalf.
Perturbation scoring and detection statistics have not run. The completed offline
Dev statistics are separate from the future perturbation detection report.

The branch keeps compact tables, summaries and 18 review candidates. Per-cell
feature observations remain in the downloadable supplemental asset and are also
reproducible by the script; full source scoring/caches/ledgers are not copied here.
The source score bundle is an attachment on the existing release:
https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m8-full-dev-low-20261028
Its SHA-256 is da1b860a1204bb16a79026c5433614fa0d1b6202dfdbf9502d725e871969d07e.

The script intentionally does not construct a judge client or emit paid commands.
Numerical policy thresholds remain unset or proposed. This branch is a review
proposal and must not be described as an approved Test-scoring freeze record.
