## M8 judge trial

Model `gemini-3.1-flash-lite`, temperature 1.0, 20 Dev cells (gpt-oss: 7, llama: 7, gemma: 6) across levels and conditions, main-scope eligibility. Same cells for every task and thinking level. Price: US$0.25/M input, US$1.5/M output including thinking (Google list price). Every API call is logged, including retries.

### thinking `high`

| Task | Requests | API calls | Extra attempts | API errors | Unresolved | Mean input | Mean output (incl. thinking) | Mean thinking | Truncated | Spent | Per request | Full-Dev requests | Projected full Dev |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| correctness | 20 | 21 | 1 | 0 | 1 | 656 | 1,026 | 782 | 0 | US$0.0357 | US$0.0018 | 3,611 | US$6.4541 |
| adaptation | 30 | 30 | 0 | 0 | 0 | 1,960 | 2,173 | 1,882 | 0 | US$0.1125 | US$0.0037 | 5,485 | US$20.5639 |
| discrimination | 20 | 20 | 0 | 0 | 0 | 3,505 | 1,193 | 1,080 | 0 | US$0.0533 | US$0.0027 | 3,611 | US$9.6271 |
| evidence_support | 20 | 32 | 12 | 0 | 3 | 2,924 | 2,900 | 2,437 | 0 | US$0.1626 | US$0.0081 | 4,169 | US$33.8966 |

Spent at `high`: **US$0.3642**. Projected full Dev scoring at `high` (all six batches, four tasks): **US$70.5416**.

### thinking `low`

| Task | Requests | API calls | Extra attempts | API errors | Unresolved | Mean input | Mean output (incl. thinking) | Mean thinking | Truncated | Spent | Per request | Full-Dev requests | Projected full Dev |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| correctness | 20 | 20 | 0 | 0 | 0 | 647 | 349 | 106 | 0 | US$0.0137 | US$0.0007 | 3,611 | US$2.4734 |
| adaptation | 30 | 33 | 3 | 0 | 0 | 1,992 | 440 | 132 | 0 | US$0.0382 | US$0.0013 | 5,485 | US$6.9856 |
| discrimination | 20 | 20 | 0 | 0 | 0 | 3,505 | 293 | 176 | 0 | US$0.0263 | US$0.0013 | 3,611 | US$4.7506 |
| evidence_support | 20 | 28 | 8 | 0 | 5 | 2,941 | 646 | 167 | 0 | US$0.0477 | US$0.0024 | 4,169 | US$9.9456 |

Spent at `low`: **US$0.1259**. Projected full Dev scoring at `low` (all six batches, four tasks): **US$24.1552**.

Notes:
- Full-Dev request counts are exact: identical answers share one request, as in the real run; correctness excludes cells scored by deterministic rules and non-answers.
- The projection scales the measured cost per request and already includes observed retries. Validity checks (repeat and order-reversed runs) cost about the adaptation per-request price times the size of each comparison subset, which the Leader has not fixed yet; a second judge from another family is not priced here.
- Calls that failed without usage are counted as zero; the provider bill is authoritative.
- This is a runtime and cost trial, not judge calibration.
