# M3-to-M4 alignment issues

Status: blocked handoff identified by the 2026-09-12 fail-closed mapping run.

M1 normalization resolved all 20 M3 Gold v0.1 spans against the prepared
34-chapter M2 corpus: 20 resolved, 0 stale and 0 ambiguous. The fixed M4 corpus
filter then fully covered 17 spans. The following three spans are outside that
filter:

| Question ID | Span ID | Parser content type | Reason |
| --- | --- | --- | --- |
| `sciq-test-00614` | `openstax-cp2e-a052d9fae2a90e13_ch08_p0374_b003_gold_0013` | `problem` | M3 selected evidence from Problems & Exercises. |
| `sciq-test-00620` | `openstax-cp2e-a052d9fae2a90e13_ch07_p0336_b013_gold_0016` | `problem` | M3 selected evidence from Problems & Exercises. |
| `sciq-test-00955` | `openstax-cp2e-a052d9fae2a90e13_ch13_p0592_b036_gold_0020` | `summary` | M3 selected evidence from the section summary. |

The M4 filter intentionally excludes assessment-like material and summaries.
Adding 5,769 `problem` blocks to satisfy two provisional spans would materially
change the retrieval corpus and make the affected SciQ questions close to
verbatim textbook-question matches. M4 therefore does not silently expand the
filter or modify M3's annotations.

One of the following versioned decisions is required:

1. M3 supplies independently reviewed replacement evidence inside the current
   body/example/figure-caption/glossary/table/equation filter; or
2. the team approves a new corpus-filter version and accepts the evaluation
   leakage implications.

Until then, `gold_mapping_diagnostic/gold_to_chunk_mapping.json` records all 20
outcomes, while the M1-compatible evaluation mapping is deliberately withheld.
