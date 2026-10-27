# Six-request low evidence confirmation

**Outcome: 3 accepted by validation, 3 unresolved.** This fresh paid check was executed by the user after the quotation repair. The original 20-cell trial remains unchanged.

Execution ID: `gemini-low-evidence-six-20261028-01`. Saved completions: **28 October 2026, 01:09:48–01:10:03 Sydney (AEDT)**; UTC timestamps fall on 27 October. Preparation source: `96626a7f3bd03cd08cc09c970511f94eb2138244`.

Scope: only `evidence_support`, only `low`, six fixed historical contexts, one application attempt each. The configured SDK HTTP retry policy still allows up to five attempts; individual HTTP attempts were not instrumented. No saved cache hit was used. This is not another 20-cell high/low comparison.

| Question / topic | Generator | Target level | Condition | Validation outcome |
| --- | --- | --- | --- | --- |
| sciq-train-01144 / current | gpt-oss | intermediate | P1R1_combined | accepted_by_validation |
| sciq-train-06027 / ultrasound | gpt-oss | advanced | P1R0_prompt_only | unresolved |
| sciq-train-04946 / manometer | gemma | advanced | P1R1_combined | unresolved |
| sciq-train-05989 / nuclei | gemma | beginner | P1R0_prompt_only | unresolved |
| sciq-train-06774 / EMR | gemma | beginner | P1R1_combined | accepted_by_validation |
| sciq-train-09248 / cyclotron control | llama | intermediate | P0R1_reranking_only | accepted_by_validation |

## Remaining issues

- **Ultrasound:** E2 is declared as supporting evidence but has no quotation; both claims are affected.
- **Nuclei:** E2 is declared as supporting evidence but has no quotation; all three claims are affected.
- **Manometer:** claim c2 declares support from E5 and marks citation support as supported, while the answer actually cites E1/E2. No declared supporting ID intersects the actual citations.

These are incomplete or inconsistent fresh judge outputs, not merely an ellipsis/whitespace formatting problem. No evidence ID, quotation or verdict was silently removed or replaced to make them pass. Each remains unresolved. The current runtime and canonical validators were both rerun offline and reproduce all six saved statuses.

The original quotation replay recovered seven old failures by rechecking old outputs. The fresh six-request check generated different outputs and found new failures; the two results answer different questions. The targeted six-case result is not an estimate of full-Dev failure rates. Accepted-by-validation does not prove semantic correctness.

The fresh set intentionally includes five previously affected cases and one control, and
allows only one application attempt per case. The first low evidence trial allowed retries
and logged 28 client attempts for 20 requests. Different case selection and retry policies
prevent a direct comparison of the unresolved percentages; this check does not establish
that low became less reliable.

## Usage and cost limitation

| Measured from the three accepted envelopes only | Value |
| --- | ---: |
| Input tokens | 7,241 |
| Output tokens, including thinking | 1,851 |
| Thinking tokens, already included above | 285 |
| Token-price estimate for that recorded subset | USD 0.00458675 |

**The full six-request token usage and cost are unknown from these saved files.** The unresolved-envelope branch in the existing runner does not copy response usage into the envelope. Its zero fields must not be treated as zero usage or free calls. The figure above is a lower bound using the original trial price assumptions, not the six-call bill. No split of the provider AUD bill is inferred.

## Review and next gate

The later adaptation N/A guard is a separate task and does not change these evidence-support request payloads. Leader decision #212 selects low for all four tasks. Team review should assess these remaining evidence failures before deciding whether another repair or paid check is needed. Full Dev remains on hold pending budget approval. No new paid call was made to package or revalidate these files.
