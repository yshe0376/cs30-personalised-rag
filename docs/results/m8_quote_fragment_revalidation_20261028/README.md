# Strict quote-fragment policy and offline replay

Implements the [Leader's quotation review](https://github.com/yshe0376/cs30-personalised-rag/pull/210#issuecomment-6445628620)
and its [earlier two counterexamples](https://github.com/yshe0376/cs30-personalised-rag/pull/210#issuecomment-6443930536).
The accepted always-assessed adaptation rule is unchanged. No new API call or paid retry was made.

## Current quotation policy

1. Normalize NFC, whitespace and the existing limited typographic quotes/hyphens. Case,
   numbers, mathematical operators, superscripts and other wording remain unchanged.
2. Split each individual quote row on ellipses (`...` or `…`), ignoring empty omission margins.
   Every nonempty fragment must have **at least three words after normalization**. A word is
   a whitespace-delimited token containing a Unicode letter or digit; punctuation-only tokens
   do not count. The minimum also applies to a row without ellipses.
3. Within a row, match each fragment in the **same evidence text**, from left to right,
   starting at or after the previous fragment's end. Fragments cannot overlap or be reordered.
   When text repeats, the earliest available nonoverlapping occurrence is used.
4. Separate rows for the same ID remain independent. The existing ID-to-string representation
   stores their boundaries using the reserved separator `\n[quote-row]\n`, rather than an
   ellipsis. Row order and overlap across separate rows do not constrain one another.
   Online rows containing that reserved separator are rejected; the separator is inserted
   only when the normalizer merges rows. Boundaries survive model/JSON round trips.
5. Missing/unknown supporting IDs, absent quotations and inconsistent citation support still
   fail closed. No missing quote is filled in and no verdict is changed to force acceptance.

The online schema and shared contracts retain their existing fields/types. This is an
Evaluation-owned normalization/validation behavior change. Old saved strings that joined
rows with ellipses no longer retain row provenance; they are treated as one row rather than
having row boundaries guessed. Existing trial caches/results are not rewritten. A new live
confirmation must use a fresh output/cache folder, as already required by the Leader.

## Offline replay of all 40 original evidence outputs

| Setting | Originally unresolved | Recovered under strict policy | Still unresolved | Previously accepted regressions |
| --- | ---: | ---: | ---: | ---: |
| high | 3 | 2 | 1 | 0 |
| low | 5 | 3 | 2 | 0 |

**Five of the original eight unresolved outputs are recovered.** All 32 originally accepted
outputs remain accepted. Compared with the earlier loose-policy replay (7/8 recovered),
two low outputs are rejected again:

- **Ultrasound / sciq-train-06027:** claim 2 includes the two-word fragment `are received`
  for E1/E2. It exists in the source, but fails the three-word minimum.
- **Manometer / sciq-train-04946, low:** claim c2's E5 fragments are individually present
  and long enough, but the density definition precedes the gauge-pressure passage in the
  source. The row quotes them in reverse order, so it fails the source-order rule.
- **Manometer / sciq-train-04946, high:** remains unresolved for the original missing
  supporting-ID quotation; its saved content also contains ungrounded wording.

Both runtime and canonical task validation are exercised by the versioned replay script.
The original outputs/verdicts/caches are unchanged. These results concern output validity,
not semantic accuracy or a new model run. The original 204-call usage audit still totals
USD 0.49008425; this replay costs zero.

## Reproduce without payment

From the repository root, choose a new output directory:

```powershell
python scripts/revalidate_judge_trial.py --trial-root docs/results/m8_judge_trial_20261027 --out ../W8/judge-trial/strict-quote-replay-new
```

- [revalidation.json](revalidation.json): all 40 checks, source hashes and original cost audit.
- [report.md](report.md): generated concise replay result.
- [fragment_diagnostics.json](fragment_diagnostics.json): failing saved fragments, word counts
  and whether an occurrence exists after the previous fragment's end.
- [SHA256SUMS.json](SHA256SUMS.json): package file hashes, excluding itself.

## Existing six-request check and next gate

The [archived six-request low check](../m8_low_evidence_confirmation_20261028/README.md)
was executed before this stricter quote-fragment change. It remains historical evidence
and **does not satisfy the requested post-change confirmation**. It is not relabelled as a
new run. Another paid six-request confirmation has not been executed in this task; the user
must initiate it only after this code change, using a fresh directory and recorded limits.
The scope remains five affected contexts plus one control, evidence_support only, low only.

Leader decision #212 selects low for all four tasks. Full Dev still awaits budget approval.

## Verification

- Both exact Leader counterexamples are rejected: `a ... e` and
  `damaged ... Healthy cells are not` against the supplied cancer-cell source.
- Three-word fragments in reverse order, overlap, reused occurrences, independent reversed
  rows, row-boundary JSON round trips and both validator entry points are covered.
- Focused quotation/runner suite: **60 passed**. Full offline suite: **1,322 passed, 2 skipped**.
- Ruff, source/artifact hashes, Markdown links and diff checks are validated before publication.
