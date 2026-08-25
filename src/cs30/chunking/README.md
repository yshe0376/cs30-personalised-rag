# Member 4 - chunking and metadata

Implement `cs30.ports.Chunker`:

    `chunk(document: OpenStaxDocument) -> list[Chunk]`

Drop the real implementation next to `fixture.py`. The Leader supplies it as the
`chunker` field of `BuildDeps`; `run_build_pipeline()` itself does not change.

## Week 1 acceptance

- Every chunk has a unique id and a chapter source.
- Chunk text can be located back in the normalised document.
- No empty chunks and no cross-chapter mixing.
- Output feeds member 5 directly.

## Notes

The contract enforces `len(text) == char_end - char_start`, so a wrong span
fails at construction instead of at demo time. `Chunk.metadata` accepts
string values only: use `{"section": "1"}`, not `{"section": 1}`.

Do not re-derive structure from raw text. `document.blocks` already carries
`section_id`, `content_type`, and pages; carry them into `Chunk.metadata`
instead of parsing the text a second time.

Chunk boundaries follow block structure, but chunk offsets still address
`document.text`. Keep one ~500-token size target so chunk lengths stay
comparable: blocks range from a few tokens to several hundred, and mixing those
lengths in a single index distorts similarity scores.

Emit offsets into `document.text` even when a chunk is a union of whole blocks.
Gold evidence spans live in that coordinate system, so retrieval metrics can
only be computed when chunks are addressed the same way.

Set `Chunk.embed_text` when applying context enrichment: keep `text` verbatim
and put the enriched form, such as `"From chapter 1, section 1.2 (Physical
Quantities and Units): <text>"`, in `embed_text`. The section titles come from
`document.blocks`. The contract requires `embed_text` to contain `text`
verbatim, so the citation never drifts from the evidence.
