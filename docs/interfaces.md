# Week 1 core interface contract

Contract version: `1.0` (revised 2026-08-24 and 2026-08-25 before module
development began — see [ADR-0001](adr/0001-week1-thin-slice.md))

All cross-module payloads must be validated by the Pydantic models in
`src/cs30/contracts`. Unknown fields are rejected to expose interface drift.

## Character-span convention

`char_start` is inclusive and `char_end` is exclusive, matching Python slicing:

```python
assert document.text[chunk.char_start:chunk.char_end] == chunk.text
```

Spans refer to the normalised document text produced by the frozen parser
version. Changing normalisation requires a new `parser_version` and document
hash, followed by chunk and index regeneration.

`Chunk` enforces `len(text) == char_end - char_start` at construction, so a
mismatched span fails immediately instead of surfacing during a demo.

## Document structure: blocks

`OpenStaxDocument` carries two things: `text`, the coordinate system every span
refers to, and `blocks`, the structure the parser recovered.

A `TextBlock` holds **offsets only, never its own copy of the text**. Two copies
of the same string can drift apart; one string plus a span cannot. Read a
block's text through the document:

```python
for block in document.blocks:
    print(block.content_type, document.block_text(block))
```

Blocks must be ordered, non-overlapping, inside the document text, and inside
the chapter they claim. That last rule catches mislabelled sections at
construction rather than during retrieval.

`content_type` records what a block *is*, because explanatory prose and a
question about that prose are different kinds of text. An exercise retrieved as
supporting evidence produces an answer that looks grounded but rests on the
wrong material, and `validate_citations` cannot detect that: it checks where a
citation came from, not what kind of text it is.

Indexing policy is configuration, not contract. The agreed Week 2 default is to
index `body`, `example`, `figure_caption`, and `glossary`; to keep
`conceptual_question` and `problem` in a separate index; and to attach `heading`
to its following block rather than indexing it alone.

Blocks exist so structure survives the module seam. Without them a chunker
receives undifferentiated text and has to re-derive section, page, and role
information the parser already established.

## What is embedded, and what is cited

`Chunk` holds two texts. `text` is verbatim corpus text bound to a span: it is
what gets cited and shown to a student. `embed_text` is optional and is what
the embedder sees, carrying whatever context enrichment retrieval benefits
from — typically the chapter and section a passage came from.

```python
chunk.embedding_input   # embed_text when set, otherwise text
```

`embed_text` must contain `text` verbatim. Enrichment may add context around
the evidence but never replace it, so a chunk cannot be retrieved on the
strength of wording that is absent from what it cites.

Producer is member 4, which has the section titles through `document.blocks`.
Member 5 embeds `chunk.embedding_input`; member 6 returns `chunk.text` in a
`RetrievalHit`, because that is the text a citation points at.

## String handling: two kinds of field

The contract layer **never rewrites text that a span points at**.

| Kind | Fields | Behaviour |
|---|---|---|
| `SpanText` | `OpenStaxDocument.text`, `Chunk.text`, `Chunk.embed_text`, `RetrievalHit.text` | Kept verbatim. Never stripped — stripping would move the text without moving the offsets |
| `Identifier` | all `*_id`, `source`, `version`, `document_hash`, `parser_version`, citation entries | Surrounding whitespace removed, so `"ch01 "` and `"ch01"` cannot become two chapters |
| `NonEmptyText` | `question`, `support`, `explanation`, `title` | Stripped; no span semantics |

This distinction is about whether a pair of offsets points at the string. It is
not about content type: figures and formulas are a separate question, tracked as
R3 in the team planning materials maintained outside GitHub.

## No evidence, and refusal

Both are first-class outcomes, not errors:

- `RetrievalResult.hits` may be empty. Retrieval ran and found nothing relevant.
  Reserve exceptions (`IndexUnavailableError`, `EmptyQueryError`) for genuine
  failures.
- `GeneratedAnswer` may set `abstained=True`, which requires no `final_choice`
  and no citations. Conversely a non-abstained answer **must** cite at least one
  chunk, so an ungrounded claim cannot be constructed.

`cs30.citation.validate_citations` then rejects any citation that retrieval did
not return.

## Metadata fields

`Chunk.metadata` and `PipelineRun.metadata` are `dict[str, str]`: **string
values only**. Use `{"section": "1"}`, not `{"section": 1}`.

## Ownership

| Contract | Producer | Primary consumers |
|---|---|---|
| `OpenStaxDocument` | Member 2 | Member 4, Leader |
| `TextBlock` (inside `OpenStaxDocument`) | Member 2 | Member 4, Member 5 |
| `Chunk` | Member 4 | Members 5 and 6 |
| `IndexArtifact` | Member 5 | Member 6 |
| `SciQQuestion` | Member 3 | Members 6 and 7 |
| `RetrievalResult` | Member 6 | Member 7, Leader |
| `StudentProfile` | Member 7 / UI | Prompt builder |
| `GeneratedAnswer` | Member 7 | UI, citation checker |
| `PipelineRun` | Leader | Member 8, ablation table |

Member numbers follow the week 1 division of labour held in the team Drive.

## Module seams

Computational modules implement Protocols from `src/cs30/ports.py`. Members 2,
4, and 5 are orchestrated by `BuildDeps` / `run_build_pipeline()`; members 6 and
7 are orchestrated by `PipelineDeps` / `run_pipeline()`. Member 3 supplies
validated questions through `QuestionProvider`. Member 8 consumes `PipelineRun`
directly. See each module package's `README.md` for its acceptance criteria.

`IndexArtifact` is the explicit hand-off between index building and retrieval.
It records the index type, stable location, chunk count, and implementation
metadata. A retriever must accept it through `load_index()` before querying the
corresponding real index. The fixture implementation uses a process-local
`memory://` location; real adapters must use a persistent location that another
process can reopen.

`validate_citations()` raises `CitationIntegrityError` when generated citations
are not present in the retrieval result. Because it derives from `CS30Error`,
the command-line boundary reports the problem cleanly instead of leaking a
traceback.

## Integration gate

Every Pull Request crossing a module boundary must include:

1. A payload that validates against the relevant contract.
2. A small fixture or test covering the new behaviour.
3. Explicit errors for missing inputs rather than process termination.
4. A successful run of the end-to-end pipeline.

## Changing a contract

1. Raise it with the Leader; `CODEOWNERS` routes `src/cs30/contracts/` changes.
2. If any module already produces stored data in the old shape, bump
   `schema_version` and state the migration. Before that point, revise in place
   and record the revision in the ADR.
3. Update the packaged fixtures and this document in the same Pull Request.
