# Supplemental Dev diagnostics and perturbation results

Start with [perturbation-results/README.md](perturbation-results/README.md) for the completed audit and Leader review response. The run detected 15/18 changes, but I3 was 0/3, so the original detection rule was not met. The Leader accepted the reduced plan section 6 scope and confirmed I3 as reference-only; this is not a blanket validity pass.

[DEV_I3_SENSITIVITY.md](perturbation-results/DEV_I3_SENSITIVITY.md) compares Dev intermediate rates with and without I3. For future Test reporting, use I1/I2 for the main intermediate score and retain I3 separately. The immutable original scoring handoff still contains the original I1/I2/I3 aggregates; apply the versioned reporting policy explicitly.

REPORT.md and diagnostics/ contain the offline P0R0, length/formula, combined generation-plus-judge noise, missingness and optional N/A measurements. THRESHOLD_PROPOSAL.md contains Dev-informed proposals, not newly approved numerical gates. The warning threshold X and other pending decisions are not inferred from these results. Citation support remains reference-only.

perturbation-draft/, PRE_TEST_DECISION_DRAFT.md, WORKFLOW_AND_OWNERSHIP.md, summary.json and verification.json preserve the pre-run planning/build snapshot. Their pending or unrun fields describe that earlier snapshot. The completed run and subsequent Leader decisions are reported in perturbation-results/; do not interpret historical planning fields as current run status or as permission to run again.

## Source and reproduction

The original score handoff remains m8_scoring_handoff_20261029.tar.gz, SHA-256 da1b860a1204bb16a79026c5433614fa0d1b6202dfdbf9502d725e871969d07e, on the [existing Dev Release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m8-full-dev-low-20261028). This supplement is a companion, not a replacement interface for M7 or a replacement of original scores.

From the repository root, with the current src installed or on PYTHONPATH:

```powershell
python scripts/build_dev_diagnostics.py --package PATH_TO_EXTRACTED_SCORE_PACKAGE --repo PATH_TO_REPOSITORY --out NEW_OUTPUT_DIRECTORY
python scripts/summarize_dev_i3_sensitivity.py --package PATH_TO_EXTRACTED_SCORE_PACKAGE --out ANOTHER_NEW_OUTPUT_DIRECTORY
```

The first command rebuilds offline diagnostics and the preserved pre-run case specification, not the later review prose. The second reproduces the I3 sensitivity JSON. perturbation-results/tools/analyze_perturbation_run.py independently reproduces the saved audit analysis. All are offline; no provider client is constructed.

The replacement v2 diagnostic archive on the same Release includes the current report, approved v2 case specification, completed perturbation run, analysis tools and checksums. The original scoring, generation and retry archives are preserved. Opening or merging this PR does not by itself publish an asset: the Release update is verified separately.

## Remaining limits and Test boundary

The false-fail rate and checklist-position effects are unmeasured, no independent same-answer retest or second-family judge was run, and Gemma/Gemini share a vendor. Preserve these caveats in Test reporting. All development outputs remain reportable=false. Until all five #222 gates are recorded, nobody reads, samples, summarises or scores Test answers; hash/count/status-only integrity checks remain allowed. No Test answers were read for this supplement.
