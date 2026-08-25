# ADR-0001: Week 1 thin-slice architecture

- Status: Accepted for Week 1
- Target version: `v0.1-thin-slice`
- Scope: Engineering path validation only

## Context

The team needs a runnable client demonstration while GPU, model access, and the
final supervisor-provided dataset remain unresolved. Waiting for those decisions
would block interface, parsing, chunking, integration, and UI work.

## Decision

1. Use one small OpenStax Physics chapter as a temporary technical fixture.
2. Freeze version 1.0 cross-module contracts before full module development.
3. Use 500-token chunking, one future embedding model, and FAISS `IndexFlatIP`.
4. Provide mock retrieval and generation adapters until real services are ready.
5. Support beginner, intermediate, and advanced profile levels from the start.
6. Require generated citations to be a subset of retrieved chunk IDs.
7. Keep the main branch runnable throughout the week.

## Explicitly out of scope

- Formal Evidence Alignment and gold-span annotation
- Hit@K, Recall@K, MRR, or answer-accuracy conclusions
- Formal Dev/Test splits
- BM25/RRF comparisons
- Abstention calibration, restricted KG, and multi-model comparison

## Revision, 2026-08-24 (before module development began)

Version 1.0 was revised in place rather than superseded, because no module yet
produced data in the old shape. Three defects made the original shape unusable:

1. **Contract-level whitespace stripping broke the character-span invariant.**
   The base model normalised every string, so a chunk whose text began or ended
   with whitespace was silently shortened while its offsets were not, and
   validation still passed. Text bound to a span is now kept verbatim; only
   identifiers and span-free free text are normalised, and `Chunk` asserts
   `len(text) == char_end - char_start`.

2. **The contract could not express "no evidence" or "cannot answer".**
   `RetrievalResult.hits` and `GeneratedAnswer.citations` both required at least
   one entry, so retrieval could not report an empty result and the generator
   could not refuse. Refusal is a stated goal of the project, so both lists may
   now be empty, and `GeneratedAnswer.abstained` distinguishes a refusal from an
   ungrounded answer. A non-abstained answer must still cite evidence.

3. **The index builder had no explicit hand-off to retrieval.** `build()` and
   `load()` returned nothing, so members 5 and 6 could not agree on which index,
   chunk map, or configuration was being used. Both now return an
   `IndexArtifact`, and `Retriever.load_index()` accepts that manifest.

`PipelineRun` was added at the same time to carry run metadata, so a later
ablation-table row can be traced back to the configuration that produced it.

Freezing exists to stop churn during development, not to preserve a defect
discovered before development started.

## Revision, 2026-08-25 (before module development began)

Revised in place for the same reason as the previous revision: no module yet
produces data in the old shape.

The first real parser output exposed a gap. `OpenStaxDocument` held only text
and chapter spans, so the parser's per-paragraph structure — section, page, and
what each passage *is* — had nowhere to live and was discarded at the module
seam. A chunker would then have to re-derive that structure from raw text,
duplicating work the parser had already done and guaranteeing the two
derivations would disagree.

`TextBlock` and `ContentType` were added, and `OpenStaxDocument.blocks` is now
required. Blocks store offsets rather than their own text, so the document text
remains the single source of truth. Validation rejects blocks that overlap, run
backwards, exceed the document, or fall outside the chapter they claim; that
last check catches mislabelled sections at construction.

`ContentType` exists because the citation check cannot see it. An exercise
retrieved as supporting evidence yields an answer that is formally grounded and
substantively wrong, and no downstream check distinguishes that case. Only the
parser knows which passages are exercises, so the distinction has to cross the
seam as data.

This revision was prompted by a member's objection that flattening a parsed
document into one string discards structure. The objection was correct. The
document text and the block structure are complementary: the text supplies the
coordinate system that gold evidence spans are expressed in, so one
annotation set serves every chunking strategy; the blocks preserve everything
the parser learned.

## Revision, 2026-08-26: structure-aware chunking supersedes Decision 3

Decision 3 specified 500-token chunking. The ablation now compares
**structure-aware** chunking strategies — per block, per section, section with
a heading prefix, and filtering by `ContentType` — instead of sweeping a fixed
window size. A single ~500-token target is kept as a size constraint, because
blocks range from a few tokens to several hundred and mixing those lengths in
one index distorts similarity scores. It is no longer a swept parameter.

The reason for the change is that the parser recovers structure that flat text
cannot express, and comparing structural strategies tests something no prior
work on this corpus publishes. A window-size sweep tests a parameter whose
behaviour is already well understood, and the project's own knob list ranks
metadata extraction and contextual enrichment above it. Both depend on blocks.

**Character spans remain required, and their justification never depended on
the window sweep.** Evidence alignment maps SciQ support sentences to character
spans; the evaluation set stores a gold support span per question; and
retrieval metrics are computed against those spans. One annotation set
therefore serves every chunking strategy. A span also survives re-parsing,
because it can be relocated from its recorded snippet, whereas a block
identifier cannot: after a realistic re-parse of chapter 1, 24 of 30 sampled
block identifiers no longer existed and 5 silently pointed at different text.

Consequence, and a limit on what may be claimed: **no fixed-window baseline
will be reported.** Results must be stated as relative rankings among
structural strategies. They do not establish that structure-aware chunking
outperforms naive chunking, because that comparison is not being run.

## Revision, 2026-08-26: separating embedded text from cited text

Context enrichment — prefixing a passage with the chapter and section it came
from before embedding it — is one of the higher-value retrieval knobs on the
project's list. It was impossible to express: `Chunk.text` is bound to a
character span and the contract asserts `len(text) == char_end - char_start`,
so prefixing anything to it fails construction.

`Chunk.embed_text` was added, with `Chunk.embedding_input` returning it when
set and `text` otherwise. `embed_text` must contain `text` verbatim. That rule
is the point of the split: enrichment may add context around the evidence but
never replace it, so a chunk cannot be retrieved on the strength of wording
absent from what it cites. Without the rule, an answer could be formally
grounded in a chunk that matched the query only through text the student never
sees.

Member 4 produces it, since section titles arrive through `document.blocks`.
Member 5 embeds `embedding_input`. Member 6 keeps returning `text` in a
`RetrievalHit`, because that is what a citation points at.

## Consequences

The team can develop in parallel against fixtures and replace adapters without
changing public payloads. The Week 1 demo cannot be used to claim that a model,
embedding, or retrieval method performs better.

