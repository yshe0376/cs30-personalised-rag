# M3-to-M4 alignment issues

Status: accepted exclusions in the 2026-09-13 partial delivery.

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
Adding 5,769 `problem` blocks for two provisional spans would materially change
the retrieval corpus and increase textbook-question leakage. M4 therefore keeps
the original filter and does not modify M3's annotations.

`gold_mapping_diagnostic/gold_to_chunk_mapping.json` retains all 20 outcomes.
The M1-compatible `evaluation_mapping_v0_1.json` skips the three uncovered
spans; because each affected question has no other span, the three questions
are omitted from `items`. M1 records them as `mapping_missing`. The companion
`delivery_manifest.json` lists every omitted question, span, content type and
reason so the 17-question evaluation is auditable.
