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
- Records both cited-text and actual embedding-input token counts, plus whether
  embedding context enrichment and duplicate rejection were enabled.
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

`include_types` can restrict a run to parser-assigned evidence roles. Excluded
blocks create hard boundaries: their text is never absorbed through a character
span between two included blocks.

```python
from cs30.contracts import ContentType

strategy = BlockChunkingStrategy(
    include_types=(ContentType.BODY, ContentType.EXAMPLE),
)
```

## Split-ready candidates S1-S6

`CHUNKING_CANDIDATES` freezes six reproducible engineering configurations.
They share the same size constraints (`min=100`, `target=500`, `max=600`) and
vary only parser content-type inclusion, optional `embed_text` context, and
section versus chapter isolation. The target guides whole-block grouping; it
does not promise that every emitted chunk will be close to 500 tokens.

| ID | Included content | Embed context | Isolation |
| --- | --- | --- | --- |
| S1 | All parser types | No | Section |
| S2 | Body, example, figure caption, glossary | No | Section |
| S3 | S2 plus table and equation | No | Section |
| S4 | S2 plus objective, sidebar and summary | No | Section |
| S5 | S2 | Yes | Section |
| S6 | S2 | Yes | Chapter |

These are candidates for a later controlled split or evaluation; their names
do not imply retrieval quality rankings.

```python
from cs30.chunking import BlockAwareChunker, get_chunking_candidate

candidate = get_chunking_candidate("S3")
chunks = BlockAwareChunker(strategy=candidate.strategy).chunk(document)
```

The Team Lead supplies the instance through `BuildDeps.chunker`; shared
contracts, ports, and pipeline orchestration do not change.

## Tokenizer hand-off

`UnicodeWordPunctTokenCounter` is a deterministic provisional counter for
fixture development. Member 5's merged `FaissIndexBuilder` now exposes its
actual embedding-model tokenizer, which should be injected before a real index
is built:

```python
from cs30.chunking import BlockAwareChunker
from cs30.indexing import FaissIndexBuilder

index_builder = FaissIndexBuilder()
chunker = BlockAwareChunker(token_counter=index_builder.token_counter())
chunks = chunker.chunk(document)
artifact = index_builder.build(chunks)
```

The tokenizer name and `embedding_input_token_count` are recorded in every
chunk. The latter counts `chunk.embedding_input`, so context added through
`embed_text` remains visible to the index hand-off. Before a production build,
set the strategy limits to fit the selected model's sequence limit; an
individual oversized parser block remains intact and is still reported rather
than silently truncated by the chunker.

## Engineering reports

`build_chunk_statistics()` reports chunk counts, chapter distribution, length
distribution, empty/duplicate/short/oversized checks, and explicitly states
that these are engineering statistics rather than retrieval evaluation.

`build_traceability_samples()` selects up to ten deterministic chunks and
checks each character span against `OpenStaxDocument.text`.

`resolve_small_to_big()` verifies a retrieved chunk's text hash and exact
document span, then returns the complete parser section that contains it. If a
chunk spans multiple or unlabelled sections, its chapter is the parent scope.

`export_retrieval_corpus()` writes one deterministic, validated `records.jsonl`
plus `manifest.json`, schema, statistics, sample records, and trace-back
evidence. The manifest points both Dense and BM25 consumers at the same
`records.jsonl`; retrievers must not maintain repaired or divergent copies.

```python
from pathlib import Path

from cs30.chunking import export_retrieval_corpus

manifest = export_retrieval_corpus(
    documents,
    chunks,
    Path("artifacts/retrieval_corpus"),
    rebuild_command=(
        "python scripts/build_retrieval_corpus.py "
        "--document src/cs30/fixtures/openstax_document.json "
        "--output-dir artifacts/retrieval_corpus"
    ),
)
```

The repository includes that script. A runnable fixture rebuild is:

```bash
python scripts/build_retrieval_corpus.py \
  --document src/cs30/fixtures/openstax_document.json \
  --output-dir artifacts/retrieval_corpus
```

## Chunker version

Version `0.4.0` is intentional. Version `0.3.0` added embedding-input and
duplicate-rejection provenance during the M5 hand-off; `0.4.0` adds candidate,
content-filter, parent-span and unified-corpus semantics. Both revisions are
contained in the still-unmerged M4 feature branch.

## Current integration status

The implementation and unit tests do not wait for Member 2. Provisional
multi-chapter evidence may be generated through a documented adapter, but a
production corpus must be rebuilt from Member 2's frozen, contract-valid
`OpenStaxDocument` export. The manifest's document hashes and parser versions
make that replacement observable.
