# Small perturbation audit: results (steps 5–6)

Run date: 2026-10-29 (06:02–06:07 UTC). Dev-only synthetic answers; no Test data was used.
This completes steps 5 and 6 of the audit planned in
[WORKFLOW_AND_OWNERSHIP.md](../WORKFLOW_AND_OWNERSHIP.md), using the 18 cases merged in #220
(`curated_edits.v2.json`, sha256 `89799c12…`) after the Leader's OK.

## Result

**15 of 18 perturbations detected (83.3%). The pre-set rule is not met**: the rule requires
at least 80% overall *and* at least one detection in every target, and I3 detected 0 of 3.

| Target | Detected | Unresolved |
|---|---:|---:|
| B1 (beginner: explain unfamiliar terms) | 3/3 | 0 |
| B4 (beginner: explain notation) | 3/3 | 0 |
| A1 (advanced: no redundant introductory teaching) | 3/3 | 0 |
| **I3 (intermediate: accurate terms, explain specialist ideas, no redundant core definitions)** | **0/3** | 0 |
| Correctness (score below 2) | 3/3 | 0 |
| Evidence support (added subclaim unsupported) | 3/3 | 0 |

By proposed difficulty: clear 5/6, moderate 5/6, subtle 5/6 (each miss is one of the I3 cases).

**I3:** all three I3 edits were judged *pass*:
- a removed explanation of "color" (quark property);
- general-relativity jargon ("null geodesics") replacing a plain explanation;
- redundant frequency/period definitions in a clock answer.

In the judge's rationales, the terminology was "used appropriately" and the definitions were "not redundant". On this small sample, I3 does not respond to the kinds of change it is meant to catch.

**Proposed treatment, for Leader confirmation:** following the agreed fallback, report I3 on Test as reference-only and state this in the report. Do not change the I3 wording or the judge prompt in response to this result.

## Per-case results

Target verdict is the judge's verdict on the target criterion (adaptation), the
correctness score (0–2), or the support verdict of the claim covering the inserted
subclaim (evidence).

The last column compares each perturbed answer with the **original full-Dev scores of the same answer**, across all four scoring tasks. P0R0 answers are assessed at all three levels.

| Case | Target | Difficulty | Target verdict | Detected | Non-target changes vs original Dev scores |
|---|---|---|---|---|---|
| b1-gpt-oss | B1 | moderate | fail | yes | beginner:B3 pass→fail |
| b1-llama | B1 | subtle | fail | yes | — |
| b1-gemma | B1 | clear | fail | yes | beginner:B3 N/A→fail; citation-unsupported claims 0→1 |
| b4-gpt-oss | B4 | clear | fail | yes | predicted level beginner→intermediate; unsupported claims 0→1 |
| b4-llama | B4 | moderate | fail | yes | beginner:B3 N/A→pass; predicted level beginner→intermediate |
| b4-gemma | B4 | subtle | fail | yes | beginner:B1 fail→pass, advanced:A1 pass→fail, advanced:A3 fail→pass; predicted level beginner→intermediate; citation-unsupported 0→4 |
| a1-gpt-oss | A1 | clear | fail | yes | beginner:B1 fail→pass, B3 fail→pass; advanced:A3 pass→N/A; predicted level intermediate→beginner |
| a1-llama | A1 | moderate | fail | yes | correctness 2→judge error; beginner/intermediate adaptation unresolved |
| a1-gemma | A1 | subtle | fail | yes | unsupported claims 0→3 |
| i3-gpt-oss | I3 | clear | pass | **no** | citation-unsupported 1→0 |
| i3-llama | I3 | subtle | pass | **no** | predicted level intermediate→advanced; bundle-unsupported 0→1, citation-unsupported 1→2 |
| i3-gemma | I3 | moderate | pass | **no** | beginner:B3 N/A→pass; evidence support unresolved |
| correctness-gpt-oss | correctness | clear | score 0 | yes | B2, I1, I2, A4 pass→fail; A1 fail→pass; unsupported 0→2 |
| correctness-llama | correctness | moderate | score 0 | yes | B2, I2, A4 pass→fail; B3 N/A→fail; unsupported 0→1 |
| correctness-gemma | correctness | subtle | score 0 | yes | B1, B2, I1, I2, I3, A4 pass→fail; predicted level beginner→uncertain; unsupported 0→1 |
| evidence-gpt-oss | evidence | moderate | unsupported | yes | — |
| evidence-llama | evidence | subtle | unsupported | yes | **correctness 2→0** (judge read the inserted delayed-neutron sentence as a factual error) |
| evidence-gemma | evidence | clear | unsupported | yes | — |

**Reading the non-target column**
- **Some changes are expected.** A wrong core answer also fails the reasoning criteria (B2/I2/A4). Advanced notation shifting the predicted level to intermediate is likewise expected.
- **Some changes show the edit was not fully isolated.** The clearest case is evidence-llama, where the correctness judge read the inserted delayed-neutron sentence as a factual error and scored it 0 (*critical error*).
- **This run cannot separate edit effects from judge randomness.** The judge runs at temperature 1, and this audit has no same-answer rescoring. That is the separate repeat-retest check of plan §6, which has not run yet.

## Execution record

| Item | Value |
|---|---|
| Requests | 92 (adaptation 38, discrimination 18, evidence support 18, correctness 18) |
| Provider attempts | 115: 87 accepted, 28 invalid outputs retried or left unresolved |
| Usage reported | All attempts; 264,197 input and 65,450 output tokens |
| Estimated cost | ≈ USD 0.16 list price, ≈ AUD 0.26 adjusted (provider bill is authoritative) |
| AI Studio balance (operator observation) | AUD 6.14 before, AUD 6.05 after (−0.09); charges may post with a delay, so this is not a reconciled invoice |

**Judge settings and isolation**
- The judge settings are identical to full Dev:
  - model gemini-3.1-flash-lite, thinking low;
  - the same prompts, frozen profile `1888c3b7…`, Dev correctness rubrics `acd5ae48…` and Gold `235c92a1…`;
  - evaluation source tree `c1fc3254…` (unchanged since #218).
- Rebuilding the requests for the 18 **unperturbed** originals with the same pipeline reproduces their full-Dev request IDs exactly (74/74). The perturbed requests share no ID with any Dev request.
- Every perturbed answer has a new evaluation/run ID and was scored with fresh caches and separate result and ledger files. No perturbation score enters any primary Dev or Test result.
- Every judge output was re-validated with the repository's canonical `assemble_judge_results` before analysis.

## Files

| File | Contents |
|---|---|
| `perturbation_summary.json` | Totals, rule outcome, usage, input hashes |
| `perturbation_cases.jsonl` | Per-case detection, judge reasons, non-target changes |
| `run/` | `case_map.json`, `BUILD_MANIFEST.json`, perturbed inputs, judge configuration and frozen profile, judge results, correctness reports, attempt ledgers, run status |
| `tools/build_perturbation_run.py` | Offline builder for the step-5 inputs and requests |
| `tools/analyze_perturbation_run.py` | Offline step-6 analysis; reproduces the two output files from `run/` and the published scoring handoff |

**Limits**
- These are 18 purposefully written cases, reviewed before scoring. They are not a random sample and do not estimate population judge accuracy.
- The cases were not revised after any score was seen.
- Scope agreed with the Leader during the #220 review: the free offline checks plus this perturbation audit. The paid repeat-answer retest and order-reversal checks, and the second-family judge, were not run by that decision. Judge run-to-run variation and checklist-position effects are therefore not measured directly.
