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

Member 4 publishes the following `Chunk.metadata` keys for indexing,
retrieval and citation trace-back. These keys are a documented module seam;
they do not add fields to the shared `Chunk` contract.

| Key | Meaning |
|---|---|
| `source_locator` | Source URI plus chapter and half-open character span |
| `source_chapter_ids` | Comma-separated source chapter IDs used by anomaly reporting |
| `parent_scope` | `section` or `chapter` for small-to-big expansion |
| `parent_char_start`, `parent_char_end` | Half-open parent span in `OpenStaxDocument.text` |
| `parent_source_block_ids` | Parser block IDs covered by the parent span |
| `candidate_id` | Stable candidate name such as `main` or `S1`–`S6` |
| `include_types` | Canonical comma-separated content filter, or `*` for all types |
| `embedding_input_token_count` | Token count of `Chunk.embedding_input` |

`strategy` also encodes the canonical `include_types` filter. This ensures
Member 5's configuration provenance distinguishes two custom `main` runs that
use different content filters, even before M5 explicitly adds `include_types`
to its own configuration-key list.

## Evaluation contracts v0.2

`src/cs30/evaluation/` freezes the W5 boundary shared by M1, M3, and M8.
`GoldSample.gold_core_evidence_sets` is an outer-OR, inner-AND structure: every
span in one inner set must be retrieved for that path to be complete, while
any complete inner set is an acceptable alternative path. `partial_evidence`
is diagnostic only and never counts as a complete Gold hit.

Gold spans use the repository-wide half-open `[char_start, char_end)` rule over
their canonical text. The Gold loader can receive a `document_id -> text`
mapping for whole-document fixtures and rejects missing documents, out-of-range
spans, and any `verbatim_text` that does not replay exactly. `answerable` is
relative to the frozen corpus; disputed or unresolved items use `null`, not
`false`.

`GoldSample` uses schema version `0.1` for raw M3 input and `0.2` for
M1-normalized output; the per-question `EvaluationRunResult` is version `0.2`.
It records six distinct terminal
states: `retrieval_error`, `generation_error`, `parse_error`, `retrieved`,
`abstained`, and `answered`. `retrieved` is the successful terminal state for
`execution_mode=retrieval_only`. Technical errors cannot carry a final answer
or citation result.

The M3 W5 Gold v0.1 artifact is the source JSON contract consumed by the
evaluation loader. Its options retain `text` and `source_field`, and its Gold
spans retain `chapter_id`, `block_id`, `sufficiency`, and `annotation_note`.
M3 character offsets are chapter-local, so span replay must use a
`(document_id, chapter_id) -> chapter text` mapping rather than the merged
document text alone. The loader keeps the legacy string-option fixture shape
for engineering tests, but does not silently discard M3 metadata.

M1's normalized Gold v0.2 representation preserves raw M3 `char_start` and
`char_end` as chapter-local coordinates. It must copy them to
`chapter_char_start` and `chapter_char_end`; the generic fields are never
repurposed as corpus-global offsets. Each normalized span reports
`resolution_status` as `resolved`, `stale`, or `ambiguous`, and can record a
`resolution_method` of `block_id`, `chapter_offset`, or `verbatim_unique`. A
span without a block ID may use `chapter_offset` after its chapter-local text
replays exactly; a non-empty stale block ID still requires the guarded unique
verbatim fallback. A resolved span must provide `corpus_char_start` and
`corpus_char_end`, and may retain a `resolved_block_id`. Normalized samples may
include `source_corpus_version` and `normalizer_version` provenance. Raw v0.1
M3 records remain valid with all normalization-derived fields absent.

Reportable run and scoring paths are fail-closed: every Gold span must be
`resolved` with non-null corpus-global coordinates. Raw v0.1 and stale or
ambiguous normalized Gold may be used only for non-reportable development or
fixture checks.
Every reportable Gold sample must also have `annotation_status=reviewed`.

### Coordinate ownership and M4 mapping regeneration

M3 owns the immutable semantic annotation. In the raw v0.1 artifact,
`char_start`/`char_end` are chapter-local half-open offsets and are interpreted
with `(document_id, chapter_id, block_id, verbatim_text)`. M1 owns the derived
normalization: `chapter_char_start`/`chapter_char_end` make the local coordinate
explicit, while `corpus_char_start`/`corpus_char_end` are calculated only from
the selected frozen merged corpus. The generic `char_start`/`char_end` fields
are never repurposed as global offsets.

M4 consumes the normalized Gold together with the prepared corpus manifest to
build its block-to-chunk mapping. M4 does not need to replace block-based
mapping with global character coordinates: `span_id`, `chapter_id`,
`resolved_block_id` (or the reviewed original `block_id`), and
`verbatim_text` are sufficient inputs. The output mapping remains keyed by
`span_id` and records `corpus_version`, `chunk_config_hash`, and
`mapping_version`.

Mapping regeneration follows the artifact dependency boundary:

- A chunker or chunk configuration change keeps the normalized Gold and
  `corpus_version`, but requires a new M4 mapping and `chunk_config_hash`.
- A chapter-order, separator, parser, or source-text change creates a new
  `corpus_version`; M1 must normalize the unchanged raw M3 Gold again and M4
  must produce a new mapping.
- A block split/merge or changed block text is resolved block-first by M1.
  Stale, ambiguous, or cross-block matches are listed by `span_id` for M3
  review; they are never silently migrated into a formal report.

Raw Gold, normalized Gold, corpus manifests, and mapping artifacts are
append-only versioned outputs. A new version is written beside the old one so
historical scores remain bound to the corpus and mapping that produced them.

`abstained` requires an `abstention_cause`: `no_retrieval_hits` means the
retriever returned an empty result and no model call was attempted;
`model_abstained_with_evidence` means the model received evidence and returned
an explicit refusal. `model_call_count` is the source of truth for the derived
`model_invoked` convenience flag. The trace separately stores retrieval
output, generation evidence, raw output, optional repaired output, final
answer, citation validation, and structured errors.

If profile preparation or evidence assembly fails after retrieval, the runner
saves a `generation_error` with the retrieval result and leaves prompt/model
fields empty. This keeps one bad question checkpointable and prevents a
technical failure from being interpreted as a correct abstention.

If the answer and citation validation succeed but optional prompt provenance is
malformed, the runner keeps the normal `answered`/`abstained` outcome and drops
only the invalid diagnostic fields. A valid parse-error trace retains its raw
output, prompt chunk IDs, and prompt hash.

Until the bundle-consumer seam is approved, M7's prompt builder consumes the
same `RetrievalResult` as the citation bundle builder. `GenerationTrace` records
the prompt evidence chunk IDs and prompt hash so a later prompt/bundle change
cannot silently invalidate citation scoring.

The W5 `RunManifest` is version `0.2`. It records dataset, parser, Gold
annotation, and M4 mapping identities in addition to corpus/chunk and backend
versions. Reportable manifests must use a clean, non-fixture run with a real
generation trace. Batch resume compares the complete manifest sidecar rather
than only the condition ID. A torn trailing JSONL write may be recovered once,
but the recovery is recorded in a `*.recovery.json` audit marker.

Offline retrieval scoring emits one `retrieval_scores` row per saved question.
Rows explicitly state whether they enter the answerable-and-gold denominator;
unanswerable, unresolved, disputed, technical-error, and missing-mapping rows
remain visible with exclusion reasons. Empty retrieval makes precision/noise
and no-relevant-hit undefined, with defined counts reported separately. The
aggregate `excluded_runs.total` is authoritative; its reason counters are
mutually exclusive and sum to that total.

The hand-computable JSONL fixtures under `tests/fixtures/evaluation/` exercise
joint evidence, alternative evidence, partial evidence, unresolved Gold, and
all six run states. They validate the interface and must not be reported as
formal evaluation results.

## Ownership

| Contract | Producer | Primary consumers |
|---|---|---|
| `OpenStaxDocument` | Member 2 | Member 4, Leader |
| `TextBlock` (inside `OpenStaxDocument`) | Member 2 | Member 4, Member 5 |
| `Chunk` | Member 4 | Members 5 and 6 |
| `IndexArtifact` | Member 5 | Member 6 |
| `SciQQuestion` | Member 3 | Members 6 and 7 |
| `RetrievalResult` | Member 6 | Member 8 EvidenceContextBuilder |
| `EvidenceBundle` | Member 8 | Member 7 (downstream integration), citation resolver, UI |
| `StudentProfile` | Member 7 / UI | Prompt builder |
| `GeneratedAnswer` | Member 7 | Member 8 citation resolver, UI |
| `PipelineRun` | Leader | Member 8, ablation table |
| `GoldSample` | Member 3 | Leader/M1 retrieval evaluator, Member 8 answer evaluator |
| `EvaluationRunResult` | Leader/M1 runner | Member 8 scorers, report pipeline |

Member numbers follow the week 1 division of labour held in the team Drive.

## Module seams

Computational modules implement Protocols from `src/cs30/ports.py`. Members 2,
4, and 5 are orchestrated by `BuildDeps` / `run_build_pipeline()`; members 6 and
7 are orchestrated by `PipelineDeps` / `run_pipeline()`. Member 3 supplies
validated questions through `QuestionProvider`. Member 8 prepares the
`EvidenceBundle` from the selected retrieval results and consumes `PipelineRun`
for the UI. The bundle is the M8 delivery fixture for downstream M7
integration; the current legacy `AnswerGenerator` still receives
`RetrievalResult`, and M7 remains responsible for its own prompt and LLM
implementation. See each module package's `README.md` for its acceptance
criteria.

`IndexArtifact` is the explicit hand-off between index building and retrieval.
It records the index type, stable location, chunk count, and implementation
metadata. A retriever must accept it through `load_index()` before querying the
corresponding real index. The fixture implementation uses a process-local
`memory://` location; real adapters must use a persistent location that another
process can reopen.

`CitationResolver` validates the generator's chunk IDs against the evidence
items in the `EvidenceBundle`. E-style IDs, when retained, are M8 display labels
and are not part of the generator's citation interface.
Unknown citations raise `CitationIntegrityError`; abstention is recorded as
`skipped` because there is no citation to validate.

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
