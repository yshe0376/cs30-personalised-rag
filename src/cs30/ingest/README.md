# Member 2 - textbook data engineering

Implement `cs30.ports.DocumentParser`:

    `parse(source: Path) -> TextbookDocument`

`TextbookDocument` is the provider-neutral name for the frozen v1.0 document
contract. `OpenStaxDocument` remains as a compatibility alias. Supported source
profiles are listed by `cs30-list-textbooks`: one OpenStax profile and the five
physics-related CK-12 books cited in the SciQ paper's Appendix A.

The catalogue records provenance but does not download books. Pass a local PDF
to `cs30-build --textbook ...`, or pass an already-normalised contract JSON.
Legacy CK-12 source URLs may have moved; the local file hash remains the build's
authoritative source identity. PDF input is checked against the selected
profile's title markers before parsing, then still requires the per-title parser
QA gate described in `docs/real-build.md`.

Drop the real implementation next to `fixture.py`. The Leader supplies it as the
`parser` field of `BuildDeps`; `run_build_pipeline()` itself does not change.

## Week 1 acceptance

- Same input reproduces byte-identical normalised text.
- Chapters, titles, and body text are not misaligned.
- Record `document_hash` and `parser_version` on every document.
- Any demo chunk can be traced back to the textbook.
- Emit one `TextBlock` per structural unit, with `content_type`, `section_id`,
  and pages preserved.

## Notes

`TextbookDocument.text` is never stripped by the contract layer: it is the
coordinate system every char span refers to. Emit it exactly as the parser
produced it, and never re-normalise it later without bumping
`parser_version` and regenerating chunks and indexes.

`text` is derived from the blocks, not authored separately:

```python
SEP = "

"
parts, offset = [], 0
for block in parsed_blocks:
    block.char_start = offset
    block.char_end = offset + len(block.text)
    parts.append(block.text)
    offset = block.char_end + len(SEP)
text = SEP.join(b.text for b in parsed_blocks)
```

Structure is not flattened by this: every block keeps its `section_id`,
`content_type`, and pages, and gains a position in a shared coordinate system.
That coordinate system is what lets chunking be re-run with different
parameters against fixed evidence annotations.
