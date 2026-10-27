# Provider billing observation for the first 20-cell trial

The user supplied an AI Studio dashboard showing **AUD 0.69** in project spending and
identified it as the first 20-cell high/low trial's actual spend. Record it as the provider
dashboard observation; the card is project-level and is not a per-run invoice. Its visible
spending window is 30 September–27 October 2026, with a cost-reporting delay warning.
Screenshots and the private project/billing URL are not published.

| Measurement | Observed value | Scope / precision |
| --- | ---: | --- |
| Provider dashboard spending | AUD 0.69 | Project-level display; user attributes it to the first trial |
| Provider input-token chart | approximately 535.47K | Rounded; 27 October, chart labelled UTC-8 |
| Provider output-token chart | approximately 246.81K | Rounded; same chart date |
| Provider request chart | 204 | Same chart date |
| Local logged client attempts | 204 | Exact first-trial log count |
| Local input tokens | 467,357 | Exact saved first-trial logs |
| Local output tokens, including thinking | 248,830 | Exact saved first-trial logs |
| Local thinking-token subset | 187,150 | Already included in output tokens |
| Local token-price estimate | USD 0.49008425 | Original price assumptions; not an AUD invoice |

These observations are **not fully reconciled**. The rounded provider input/output counters
do not exactly match the local counters. No cause is assumed and no exchange rate is inferred
by dividing the two cost figures. The 204-request match is useful but does not itself prove
run-specific billing attribution. Preserve both measurements without replacing the original
logs, report or USD full-Dev estimate. The provider's final bill is authoritative.

The earlier AUD 0.77 balance movement (AUD 8.00 to AUD 7.23) is not treated as this trial's
bill. AUD 0.69 refers to the first trial observation, **not** the later six-request low
confirmation. That run's full saved token cost remains unknown because unresolved envelopes
omit usage metadata; see [its report](../m8_low_evidence_confirmation_20261028/report.md).

[billing_observation.json](billing_observation.json) records the same values and limitations
in machine-readable form. No new API request or currency conversion was performed.
