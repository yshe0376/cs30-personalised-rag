# M3-to-M4 alignment decision

Status: resolved by the versioned M4 configuration on 2026-09-13.

M1 normalization resolved all 20 M3 Gold v0.1 spans against the prepared
34-chapter M2 corpus: 20 resolved, 0 stale and 0 ambiguous. The original M4 v1
filter covered 17 spans. The remaining three spans established that M3's Gold
evidence universe includes `problem` and `summary`:

| Question ID | Span ID | Parser content type | Reason |
| --- | --- | --- | --- |
| `sciq-test-00614` | `openstax-cp2e-a052d9fae2a90e13_ch08_p0374_b003_gold_0013` | `problem` | M3 selected evidence from Problems & Exercises. |
| `sciq-test-00620` | `openstax-cp2e-a052d9fae2a90e13_ch07_p0336_b013_gold_0016` | `problem` | M3 selected evidence from Problems & Exercises. |
| `sciq-test-00955` | `openstax-cp2e-a052d9fae2a90e13_ch13_p0592_b036_gold_0020` | `summary` | M3 selected evidence from the section summary. |

M4 v2 now includes both content types. The rebuilt corpus contains 3,979 chunks,
and the mapping covers all 20 Gold spans with 0 incomplete spans. The formal
`evaluation_mapping_v0_1.json` is emitted for M1, and M5 can index the same v2
corpus.

This decision preserves consistency with M3 without changing M3's annotations.
It also introduces a known evaluation limitation: SciQ questions derived from
the same textbook problems may retrieve near-verbatim problem text. Reports
must disclose this risk and must not compare v1 and v2 results as if they used
the same retrieval corpus.
