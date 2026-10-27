# Package-bound adaptation applicability validation

This package addresses the [Leader request on #210](https://github.com/yshe0376/cs30-personalised-rag/pull/210#issuecomment-6444017837).
It checks the original saved trial outputs offline. No API calls, retry calls or new charges
were incurred. The original verdicts, scores, requests and caches remain historical records.

## Rule and scope

For substantive answers under frozen package
`1888c3b7fb6f2f0fd52dbe06455c40cef88ff8839ab47383a76d7c29a1088238`,
**B1, B2, B4, I1, I2, I3, A1 and A4 must be assessed**. Their verdict must be pass or fail.
Only B3, A2 and A3 may be `not_applicable`. This implements the existing frozen text;
it does not change the checklist or the physics-review waiver.

The Evaluation-owned helper binds this rule to the verified package hash and the exact
profile/checklist content. It checks content fingerprints, including when criterion order
is reversed for validity testing. Another package requires its own reviewed policy; it
does not silently inherit these eight IDs. Legacy synthetic checklists without the
always-assessed wording keep their previous behavior and are not production-profile evidence.

The normal CLI prepares requests with the policy in the hashed payload. Existing unbound
requests with always-assessed criteria fail preflight before an API client is constructed.
Rebuild adaptation requests with `prepare-judge-requests` before a future authorised live run;
old adaptation cache identities are intentionally not reused for the new policy.
Both runtime and canonical adaptation validation reject illegal N/A outputs. The existing
application-level retry receives the error; exhausted retries stay unresolved with no score.
The validator never substitutes a pass/fail verdict. Non-answer routing is unchanged.

## Offline findings

| Historical thinking setting | Saved requests | Always-assessed verdicts | Requests now rejected | Invalid criterion |
| --- | ---: | ---: | ---: | --- |
| high | 30 | 80 | 6 | B4: 6 |
| low | 30 | 80 | 5 | B4: 5 |

The 60 outputs belong to the original 20-cell cost trial; they are not 60 new answer samples.
These are counterfactual validation results, not new judge judgments or an accuracy estimate.
The in-memory replay gives each saved output the new policy-bound request ID solely to test
its original verdicts against the corresponding new request. It verifies the rest of the
payload is identical and records both IDs. It does not write back to the saved trial.

- [report.md](report.md): concise generated result.
- [replay.json](replay.json): per-request results, source hashes and exact package identity.
- [Original trial](../m8_judge_trial_20261027/README.md): unchanged paid-run evidence.
- [Quotation replay](../m8_judge_quote_revalidation_20261027/README.md): separate evidence-quotation repair.

## Reproduce without payment

Run from the repository root, using a new output folder outside the original trial:

```powershell
python scripts/revalidate_adaptation_trial.py --trial-root docs/results/m8_judge_trial_20261027 --profiles docs/evaluation/level-profile-v1/profile_checklist.frozen.json --out ../W8/judge-trial/adaptation-policy-replay-new
```

The script reads local files only and has no paid execution mode. The tests cover all eight
illegal-N/A criteria, all three optional criteria, retry recovery, exhausted retries,
package/content mismatch, reordered checklists, CLI preflight and the real saved-output counts.

Verification on 2026-10-28: full offline suite **1,307 passed, 2 skipped**;
related Evaluation selection **85 passed** (overlapping tests); `ruff check .` and
`git diff --check` passed. API-client construction is forbidden in the offline replay tests.

## Execution decision

The Leader selected **thinking low for all four tasks**, for Dev and later Test, in [#212](https://github.com/yshe0376/cs30-personalised-rag/pull/212).
High remains here only as historical comparison data. The six-request low evidence check is
a separate exercise and is not repeated by this replay. **Full Dev remains on hold until
the Leader approves its budget.** No human-review decision is inferred from validation success.
