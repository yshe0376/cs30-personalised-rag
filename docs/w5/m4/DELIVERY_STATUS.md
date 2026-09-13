# Week 5 Member 4 delivery status

Date: 2026-09-13

## Outcome

The M4 corpus configuration was versioned to include `problem` and `summary`,
matching the evidence scope used by M3. The 34-chapter corpus and Gold mapping
were rebuilt from the same frozen M2 document. A clean second run reproduced
both identities.

## Verified results

- Source corpus: 34 chapters, 35,905 parser blocks and 4,981,016 characters.
- Chunk corpus: 3,979 stable chunks covering 30,394 included blocks.
- Structural QA: 0 empty chunks, 0 duplicate chunk IDs and 0 cross-chapter chunks.
- Filter QA: 0 excluded-content leaks and 0 omitted included blocks.
- Trace-back QA: 20 fail-fast samples covering chapter starts and ends,
  formulas/equations, short source blocks and cross-block chunks.
- Duplicate text: 11 source-distinct groups were preserved and recorded rather
  than collapsed across different locations.
- Embedding QA: the selected model has a 256-token sequence limit and a
  254-content-token ceiling after two special tokens; 1,911 inputs are listed
  for M5 truncation or reconfiguration review.
- Gold normalization: 20 resolved, 0 stale and 0 ambiguous.
- Gold mapping: 20 fully covered and 0 incomplete; the M1-compatible mapping
  was emitted.
- Verification: Ruff and the complete repository test suite passed.

## Identities

- Source corpus version:
  `openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864`
- Chunk corpus ID:
  `sha256:f9cd500ed16ec9866ecd3acaae179a6d845f003b8a8e0de1afc855f14a6c663c`
- Chunk configuration ID:
  `sha256:18f6f63e1fd1b7523fc4a49901ee944fd8702e029408c89821b1c8986e345bc9`
- Gold mapping ID:
  `sha256:f4743820217944edb32389c2499e6cf678db243a090c4b1af8ff8096864084c0`

## Remaining handoffs

M5 can build dense and BM25 indexes from the v2 `corpus/records.jsonl` and
`corpus/manifest.json`. M5 must record the disposition of the 1,911 embedding
inputs above the real model ceiling. M2's supplied manual QA samples and M3's
independent review status remain pending.

Including textbook problems aligns M4 with M3's evidence annotations but may
increase evaluation leakage for questions derived from the same exercises.
Evaluation reports must retain this limitation.
