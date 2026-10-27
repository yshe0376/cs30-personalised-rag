# Historical offline evidence-quotation repair verification

**Superseded policy and replay:** the fragment-length/order policy below describes the first
implementation. For the current three-word, ordered, nonoverlapping rule and the updated
5/8 recovery count, use [the strict-policy replay](../m8_quote_fragment_revalidation_20261028/README.md).
The original data and historical counts below are preserved; they are not the current policy.

This follow-up revalidates the saved #210 outputs. It makes no Gemini calls and spends no new money. Original trial artifacts are unchanged.

| Setting | Originally unresolved | Recovered from saved output | Still unresolved | Previously accepted regressions |
| --- | ---: | ---: | ---: | ---: |
| high | 3 | 2 | 1 | 0 |
| low | 5 | 5 | 0 | 0 |

Both the request-level validator and the canonical evidence-task validator were exercised. The remaining high request for sciq-train-04946 declares a supporting E2 without its quotation; the saved record also contains ungrounded wording. Missing ID/quote coverage and invented fragments are still rejected.

## Policy and scope

- Repeated quote rows for the same evidence ID are preserved as multiple excerpts in the existing ID-to-string mapping. No external schema field/type changes are needed.
- Ellipses delimit independent excerpts. Every nonempty fragment must appear in the same evidence ID, after NFC, whitespace and limited typographic quote/hyphen normalization. Fragment order is not treated as a continuous sentence; no claim of contiguous quotation is made.
- Case, numbers, mathematical operators, superscripts and other wording are not rewritten. No fuzzy/paraphrase matching is performed.
- Unknown IDs, absent quotations, altered claim text and unsupported citation bindings remain invalid. Frozen profiles, Gold and shared cs30.contracts are unchanged.
- The high/low semantics were not rescored. This does not establish that low is accurate, equal to high, or stable on fresh calls. Human review of 23 existing criterion differences and 5 level predictions remains pending.

## Files

- [revalidation.json](revalidation.json): per-request results, saved source hashes and original token-cost audit.
- [report.md](report.md): short offline summary.
- [human_review.md](human_review.md): existing disagreements with their answer context and both explanations; decisions remain pending.

## Reproduce without spending

Use an installed project environment and a local copy of the #210 report package (its folder is the trial root):

```powershell
python scripts/revalidate_judge_trial.py --trial-root PATH_TO_ORIGINAL_TRIAL --out NEW_OFFLINE_OUTPUT
```

This script has no API client construction or paid option, checks both validation layers, audits recorded token costs, and refuses an output directory inside the original trial. The original 204 logged attempts recompute to USD 0.49008425. This is not reconciliation with the provider invoice.

The now-versioned scripts/judge_trial.py reproduces sample selection, task request counting and budget extrapolation from the generation handoff. It is disabled for paid calls by default: use --offline for free pipeline checks. Any paid execution requires a human to supply --allow-paid explicitly. No paid execution was performed for this change.

Offline simulation intentionally creates unresolved judge results and zero cost; it is input/pipeline verification, not measured judge performance. The original list-price cost projection is still a small-sample estimate and excludes additional validity work.

The success caches and original report are not rewritten. Do not substitute this validation-only report for a new independently executed paid trial.

## Verification

- Focused quote/runner tests: 45 passed. Related Evaluation regression selection: 147 passed.
- Full suite: 1,287 passed, 2 skipped. The full Windows run used normal local execution after the sandbox blocked native Faiss loading.
- Ruff and git diff whitespace checks passed.
- The versioned trial script completed a separate --offline pipeline check and reproduced the 20-cell selection and full-Dev request counts (3,611 / 5,485 / 3,611 / 4,169), with zero API calls.
- The saved paid trial source hashes are recorded in revalidation.json; originals were preserved.
- Paid low confirmation and human judgment review have not been performed.
