# Answer-quote v2 offline revalidation

Policy: `answer-quote-v2`. API calls: 0. Original files verified unchanged.
Mode: prepared.

Row counts are result rows; *retry requests* are the unique API requests a rerun
would make (identical correctness answers share one request).

| Task | Unresolved rows | Recovered offline | Covered by existing cache | Still unresolved | Accepted, now invalid | Retry requests |
|---|---:|---:|---:|---:|---:|---:|
| correctness | 76 | 32 | 8 | 36 | 0 | 32 |
| adaptation | 107 | 21 | 0 | 86 | 0 | 86 |
| discrimination | 8 | 5 | 0 | 3 | 0 | 3 |
| evidence_support | 230 | 29 | 0 | 201 | 7 | 208 |
| **total** | 421 | 87 | 8 | 326 | 7 | 329 |

Per job: summary.json. Per record: records.csv.
