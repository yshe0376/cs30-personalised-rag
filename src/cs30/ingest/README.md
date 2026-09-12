# Member 2 - textbook catalogue and parsing boundary

The ingestion boundary implements `cs30.ports.DocumentParser`:

```python
parse(source: Path) -> TextbookDocument
```

`TextbookDocument` is the provider-neutral public name for the frozen v1.0
contract. `OpenStaxDocument` remains available as a compatibility name, so the
alias does not change the payload schema or the character-span convention.
The aliases provide naming compatibility only: they do not discriminate
providers or add provider-specific validation. A future provider discriminator
or provider-specific payload field requires a separately reviewed contract
revision and migration.

`src/cs30/ingest/textbooks.py` is the source catalogue. It records the stable
textbook ID, display title, provider, source reference, subject, licence, and
identity markers needed by a later source adapter. The catalogue contains the
OpenStax College Physics 2e profile and the five physics-related CK-12 books
listed in SciQ Appendix A. It does not download or redistribute source files.

Textbook selection is configuration of a parser adapter. It is not an extra
argument to `DocumentParser.parse()`, which keeps the existing `BuildDeps` and
`run_build_pipeline()` seam stable. A later M2 build adapter can be configured
with a `textbook_id` and resolve its `TextbookSpec` through `get_textbook()`.

## Parser output contract

The parser must produce one shared coordinate system for the complete
`TextbookDocument.text` string. `TextBlock` stores offsets and structure, not a
second copy of the block text. The following is the parser-side construction
pattern; `parsed_records` are provider-specific intermediate records that still
carry their text:

```python
SEPARATOR = "\n\n"
parts, blocks, chapter_ranges, offset = [], [], {}, 0
for record in parsed_records:
    char_start = offset
    char_end = char_start + len(record.text)
    parts.append(record.text)
    blocks.append(
        TextBlock(
            block_id=record.record_id,
            chapter_id=record.chapter_id,
            section_id=record.section_id,
            section_title=record.section_title,
            content_type=content_type_for_record(record),
            char_start=char_start,
            char_end=char_end,
            page_start=record.pdf_page,
            page_end=record.pdf_page,
            metadata=_block_metadata(record),
        )
    )
    chapter = chapter_ranges.setdefault(
        record.chapter_id,
        {
            "title": record.chapter_title,
            "char_start": char_start,
            "char_end": char_end,
            "page_start": record.pdf_page,
            "page_end": record.pdf_page,
        },
    )
    # A chapter spans its first block through its last block.
    chapter["char_end"] = char_end
    chapter["page_start"] = min(chapter["page_start"], record.pdf_page)
    chapter["page_end"] = max(chapter["page_end"], record.pdf_page)
    offset = char_end + len(SEPARATOR)
document_text = SEPARATOR.join(parts)
chapters = [
    TextbookChapter(
        chapter_id=chapter_id,
        title=chapter["title"],
        char_start=chapter["char_start"],
        char_end=chapter["char_end"],
        page_start=chapter["page_start"],
        page_end=chapter["page_end"],
    )
    for chapter_id, chapter in chapter_ranges.items()
]
```

`parsed_records` must be in document order and grouped by chapter. Each chapter
must have at least one block. Its `char_start` is the first block's start and its
`char_end` is the last block's end; this keeps every block inside the chapter
span required by `TextbookDocument.validate_block_spans()`.
In the current OpenStax adapter, `record_id` becomes `block_id`, `pdf_page`
becomes the block page span, and `content_type_for_record()` plus
`_block_metadata()` perform the provider-specific mappings shown above. A CK-12
adapter must provide equivalent mappings for its own intermediate records.

The parser must preserve chapter order, titles, body text, content type,
section IDs, and page information while assigning spans. The contract layer
must never strip or otherwise re-normalise `TextbookDocument.text`; changing
normalisation requires a new `parser_version`, a new document hash, and fresh
chunks and indexes.

## Week 1 parser acceptance

- The same input produces byte-identical normalised text on repeated parses.
- Chapters, titles, and body text remain aligned with their recorded spans.
- Every document records `document_hash` and `parser_version`.
- Every demo chunk can be traced back to its textbook source span.
- Each structural unit emits a `TextBlock` with `content_type`, `section_id`,
  and page information when the source provides it.

The exact local source file remains part of reproducibility. A real parser/build
PR must record its SHA-256, parser version, selected chapters, source URL,
and per-title QA results before the source is admitted to a frozen corpus.

## Interface acceptance

- Existing `OpenStaxDocument` fixtures continue to validate unchanged.
- Every catalogue entry has a stable ID, title, provider, source URL, subject,
  version label, licence, and non-empty identity markers.
- `TextbookDocument` and `TextbookChapter` remain runtime-compatible aliases.
- `cs30-list-textbooks` prints the catalogue as deterministic JSON.
- No source PDF, full corpus, model, or index is committed to the repository.

The provider-specific PDF parser and the offline `cs30-build` command belong to
a follow-up implementation PR. This PR establishes the names and metadata that
those adapters consume.
