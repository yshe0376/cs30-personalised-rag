# Member 4 — structure-aware chunking and metadata

`BlockAwareChunker` implements the existing `cs30.ports.Chunker` interface:

```python
chunk(document: OpenStaxDocument) -> list[Chunk]
```

## Revised Week 1 strategy

The chunker groups complete `document.blocks`. It does **not** scan the text
with fixed 500-token windows and does not implement a fixed-window comparison
experiment. The default strategy has one approximate size target:

```text
target_tokens = 500
min_tokens = 100
max_tokens = 600
respect_section_boundaries = true
```

The target guides greedy grouping. Every emitted boundary remains a parser
block boundary. A single block above the maximum is emitted intact and marked
`oversized_chunk=true`; it is never split in the middle merely to satisfy a
numeric limit. A short final group is merged or rebalanced using whole blocks
where possible.

## Contract guarantees

- Accepts `OpenStaxDocument`, including parser-provided `TextBlock` structure.
- Never re-derives sections, content types, pages, or chapter membership from text.
- Never mixes chapters; sections are also isolated by default.
- Stores document-wide half-open character offsets.
- Keeps `Chunk.text` as an exact substring of `document.text`.
- Carries section IDs, section titles, content types, block IDs, pages, parser
  version, document hash, strategy, tokenizer, and size flags in string-only metadata.
- Generates deterministic unique chunk IDs.
- Rejects empty chunks and exact duplicate chunk text by default.
- Optionally adds context through `embed_text` while keeping evidence text verbatim.

For every emitted chunk:

```python
assert document.text[chunk.char_start:chunk.char_end] == chunk.text
```

## Usage

```python
from cs30.chunking import BlockAwareChunker, BlockChunkingStrategy

strategy = BlockChunkingStrategy(
    target_tokens=500,
    min_tokens=100,
    max_tokens=600,
    respect_section_boundaries=True,
    enrich_embed_text=False,
)
chunker = BlockAwareChunker(strategy=strategy)
chunks = chunker.chunk(document)
```

The Team Lead supplies the instance through `BuildDeps.chunker`; shared
contracts, ports, and pipeline orchestration do not change.

## Tokenizer hand-off

`UnicodeWordPunctTokenCounter` is a deterministic provisional counter for
fixture development. Member 5 should confirm the final embedding model and
inject its tokenizer through the `token_counter` constructor parameter before
building the production index. The tokenizer name is recorded in every chunk.

## Engineering reports

`build_chunk_statistics()` reports chunk counts, chapter distribution, length
distribution, empty/duplicate/short/oversized checks, and explicitly states
that these are engineering statistics rather than retrieval evaluation.

`build_traceability_samples()` selects up to ten deterministic chunks and
checks each character span against `OpenStaxDocument.text`.

## Current integration status

The real implementation and its tests run against the repository's packaged
`OpenStaxDocument` fixture, so Member 4 development does not wait for Member 2.
Complete 2–3 chapter outputs and the joint ten-chunk source review remain
pending until Member 2 supplies contract-valid real documents.
