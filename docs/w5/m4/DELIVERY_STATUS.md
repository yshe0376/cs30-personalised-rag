# Week 5 Member 4 delivery status

Date: 2026-09-12

## Outcome

The 34-chapter M2 archive was prepared into one deterministic source corpus,
M3 Gold v0.1 was normalized against that corpus, and the fixed M4 chunk corpus
was built with M5's real tokenizer. A second clean run reproduced the source
document, manifest, normalized Gold, chunk corpus identity and mapping identity.

## Verified results

- Source corpus: 34 chapters, 35,905 parser blocks and 4,981,016 characters.
- Chunk corpus: 3,684 stable chunks.
- Structural QA: 0 empty chunks, 0 duplicate chunk IDs and 0 cross-chapter chunks.
- Filter QA: 0 excluded-content leaks and 0 omitted included blocks.
- Trace-back QA: 20 fail-fast samples covering chapter starts and ends,
  formulas/equations, short source blocks and cross-block chunks.
- Duplicate text: 17 source-distinct groups were preserved and recorded rather
  than collapsed across different locations.
- Embedding QA: the selected model has a 256-token sequence limit and a
  254-content-token ceiling after two special tokens; 1,446 inputs are listed
  for M5 truncation or reconfiguration review.
- Gold normalization: 20 resolved, 0 stale and 0 ambiguous.
- Gold mapping: 17 fully covered and 3 blocked by the fixed content filter.
- Verification: Ruff passed, M3's validator accepted all 20 records, and the
  complete repository test suite passed all 307 collected tests.

## Identities

- Source corpus version:
  `openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864`
- Chunk corpus ID:
  `sha256:896432aa0db5ce84f52971369f40b605115de44fe5d3c6e203af5923d9535fbf`
- Chunk configuration ID:
  `sha256:4c3c35e13eec2dc04a5fea85ebd912704846d04f31dd2d9006eb36f0db264b61`
- Diagnostic mapping ID:
  `sha256:8b41c6fca540bf3008315fbfe3793db6cce94e7ac1baa0fbb16598d6bc08dff7`

## Remaining handoffs

M3 must replace or independently review the three evidence spans listed in
`M3_ALIGNMENT_ISSUES.md`, or the team must approve a new filter version. M5
must decide the disposition of the 1,446 embedding inputs above the real model
ceiling. M2's manual QA samples also remain pending in the supplied archive.

The M1-compatible evaluation mapping is intentionally not emitted while any
Gold span is uncovered. This prevents a partial mapping from silently changing
retrieval Recall.
