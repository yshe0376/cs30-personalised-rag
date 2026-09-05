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

## Revision, 2026-09-05: an evidence bundle between retrieval and generation

Citation integrity was checked by `validate_citations(answer, retrieval)`,
which tested membership against whatever retrieval happened to return. Nothing
recorded which evidence was actually offered to the model, how much context it
amounted to, or which index artifact produced it. The ablation table needs all
three, and a run cannot be reproduced from a set-membership test.

`EvidenceItem`, `EvidenceBundle`, and `ValidatedAnswer` were added, with three
optional fields on `PipelineRun`: `evidence_bundle`, `validated_answer`, and
`trace`. `RetrievedEvidence` gained an optional `source_locator`, left `None`
until the retrieval seam can supply a real corpus locator. It is deliberately
not filled with the document source: a traceability field that silently
duplicates `source` is worse than an absent one, because it reads as span-level
provenance the system does not have.

**Citations stay chunk-based.** The bundle assigns `E1`, `E2` identifiers and
keeps a `citation_map`, but the prompt shows chunk IDs and the resolver accepts
only chunk IDs. Switching namespace means changing the prompt, which changes
model behaviour. W5 opens with Level-Aware Reranking; two simultaneous changes
would make the generation results unattributable, which the one-knob rule
exists to prevent. E numbers stay display labels until a prompt-format
comparison is worth its own ablation row.

**The token budget observes, it does not filter.** An earlier revision dropped
evidence past the budget while the prompt still listed every retrieved chunk as
citable, so a model obeying the prompt could be judged to have hallucinated a
citation — measured at two of five hits. The budget is now recorded and warned
about, never enforced by removal. Its unit is whitespace-separated words, not
model tokens; the warning message says so, and a real tokenizer replaces it
before any budget claim is made.

`schema_version` stays `1.0`. Every new field is optional with a default, so
records written before this revision still validate. The reverse does not hold:
`ContractModel` forbids extra keys, so older code rejects newer records. That
asymmetry is acceptable while nothing outside this repository consumes a
`PipelineRun`.

Member 8 builds the bundle and owns citation resolution. Member 7's
`AnswerGenerator` keeps receiving a `RetrievalResult`; no bundle-consuming port
is added to `ports.py` until Member 7 accepts one.

Left deliberately empty: `evidence_role` (A3, pending the taxonomy freeze in
#16), the normalised score and the `lambda`/`confidence` inputs C4 needs (#17),
and `source_locator` until retrieval supplies it.

`prompt_context` and `citation_map` are both read, but not by the generator.
`prompt_context` is hashed into `trace.context_hash`; since the generator
receives a `RetrievalResult` and builds its own prompt, that hash records the
context the bundle assembled rather than the text the model saw. The resolver
validates citations against `citation_map.values()` and resolves through it,
so the map's chunk IDs are load-bearing; only its `E` keys are unused, because
the generator cites chunk IDs. Both become fully used when Member 7 accepts a
bundle-consuming port.

## Consequences

The team can develop in parallel against fixtures and replace adapters without
changing public payloads. The Week 1 demo cannot be used to claim that a model,
embedding, or retrieval method performs better.

