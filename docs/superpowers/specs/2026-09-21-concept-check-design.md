# Concept Check — first design specification

> Status: decided (finalised 2026-09-22, recorded in the decided table of `docs/构思与待定.md`)
>
> Date: drafted 2026-09-21, finalised 2026-09-22
>
> Owner: M1 (contracts, integration, versioning, experiment management)
>
> Implementers: M7 (authoring, validation, grading, state updates), M3 (question and evidence review), M8 (UI, logging, evaluation)

## 1. Goal

A Concept Check is an optional micro-test offered after an answer. It is not a second question-answering system and not part of the formal Dev/Test evaluation set. Its job is to:

1. check a student's understanding of the current Topic with one short, textbook-grounded question;
2. grade the attempt automatically and record it as a learning event;
3. update Topic mastery, attempt coverage and attempt counts transparently;
4. let the next personalised answer read the updated dynamic state;
5. shut off safely — rather than showing an unvalidated question — whenever question quality, evidence support, or data isolation is not satisfied.

The first version supports four-option multiple choice only. Short answers, richer knowledge tracing, and full KG paths belong to later versions.

## 2. Scope and non-goals

### 2.1 In scope for the first version

- a `practice_only` question pool;
- three question sources: human-authored, aligned SciQ, and LLM candidates;
- structural validation, evidence-reference checks, and a human review state;
- a provider-neutral Topic registry maintained by M3, plus a deterministic Topic resolver;
- stable evidence anchors, with bindings that resolve to current chunks per corpus version;
- automatic four-option grading;
- skipped questions leave state unchanged;
- a LearnerState obtained by replaying the event log;
- a transparent TopicState update function and a static StudentProfile snapshot adapter;
- an end-to-end fixture-mode demonstration;
- a Concept Check feature flag that is off by default;
- serialisable contracts for questions, attempts and LearnerState.

### 2.2 Explicitly out of scope for this stage

- letting unreviewed LLM questions enter the official pool;
- treating the SciQ `support` field directly as online RAG evidence;
- putting Concept Check questions into the formal Dev/Test sets;
- changing the type or semantics of the existing `StudentProfile.topic_levels`;
- wiring the Restricted KG into the first version of Concept Check;
- automatic short-answer scoring, BERT-KT, or elaborate psychometrics;
- changing the input path of the v1 static personalisation main experiment;
- letting dynamic question confidence override the existing static profile confidence.

## 3. Design principles

### 3.1 Mixed authoring, but publication only after review

Questions are neither all hand-written nor all machine-generated. Sources are mixed and staged:

```text
hand-written fixture / human-authored / aligned SciQ
              ↓
        LLM candidate questions
              ↓
  automatic structure and evidence-reference checks
              ↓
             M3 review
              ↓
     published practice question
```

An LLM may draft candidates but may not decide on its own whether a question is publishable. In staging and production the official Concept Check reads `published` questions only. In development, unreviewed candidates may be shown only when `allow_unreviewed_questions` is explicitly on; they must be marked as development output and must not enter the official trace or the question pool. Online generation fallback is off by default.

### 3.1.1 Question sources and the publication gate

This is the single rule for the question pool. The validator, the M3 review process, and the M8 display logic must all reuse it rather than each interpreting it their own way:

- **Human-authored.** Questions written or maintained by M3/M1 still go through automatic structural validation and M3 review. "Human-authored" does not exempt a question from evidence binding or feedback review.
- **Textbook-aligned SciQ.** Questions may be drawn only from the SciQ `train` or `validation` split and must then be bound to current textbook evidence. The original `source_question_id` must be preserved; rewriting the stem, the options, or the Concept Check `question_id` must not be a way around the checks.
- **Offline LLM candidates.** Generation is allowed only as an offline batch in the development environment, producing `draft` candidates that then enter the validator and M3 review. They may not be generated online at answer-submission time, and a successful generation must not publish anything by itself.

Every source passes through the same state transition:

```text
draft
  → auto_validated
  → reviewed (M3)
  → published
```

A question reaching `published` must satisfy three conditions, none of which substitutes for another:

1. an M3 `review_record_id` recording the review conclusion on the unique answer, the difficulty, the Topic, the distractors, and the evidence support;
2. a static feedback explanation, `rationale`, that M3 has reviewed — no LLM is called to produce feedback at submission time;
3. a stable evidence anchor with a `resolved` binding already generated for the current corpus version.

A question missing any of these stays in `draft`, `auto_validated`, or `rejected`, and must not enter the official pool.

SciQ provenance uses a bidirectional leakage gate. A practice question's `source_question_id` must not appear in any frozen Gold provenance; and when Gold is frozen or updated, the new Gold's source IDs must not collide with the published practice pool. Neither order — practice question first, or Gold first — can reuse the same SciQ item.

Gold leakage checking is not limited to SciQ provenance. All three sources must pass two automatic checks:

- after a question's anchor is bound to the current corpus, reject the question outright if its textbook, chapter, and half-open character span overlap Gold Dev/Test evidence, or if its `text_hash` equals that of Gold evidence;
- when the stem and options reach a frozen text/semantic similarity threshold against a Gold Dev/Test question, the validator emits a `gold_leakage_suspected` flag. Such a question cannot move to `auto_validated` or `published` automatically; M3 must either clear the flag explicitly in the review record or reject the question.

These two checks matter most for offline LLM candidates, because rewriting a stem or changing a question ID does not get past evidence-overlap and stem-similarity gates. The checker version, the thresholds, the matched Gold IDs, and the outcomes must be written into the validator trace.

### 3.2 Where the validator stops

The automatic validator enforces constraints that can be decided mechanically:

- JSON fields and types are correct;
- the option set is exactly A, B, C, D;
- `correct_answer` belongs to the option set;
- `evidence_anchors` is non-empty and resolves to evidence through the binding for the current corpus version;
- `split_guard` is `practice_only`;
- the question ID is unique;
- when `source_question_id` is present it is traceable in the Gold/SciQ provenance registry;
- the question does not reference a formal Test question ID and does not use the SciQ test split;
- the question's anchor does not overlap Gold Dev/Test evidence by span or text hash;
- the stem/option Gold similarity check produced no `gold_leakage_suspected`, or the flag was explicitly cleared by M3 in `review_record_id`;
- the difficulty and Topic fields are present and legal.

The following still require M3's human review:

- whether there is exactly one defensible correct answer;
- whether the correct answer is genuinely supported by the textbook evidence;
- whether the distractors are plausible;
- whether the difficulty matches the intended student level;
- whether the question depends on knowledge outside the textbook;
- whether it leaks semantically into a formal Test question or answer.

An LLM judge may serve as a hint for the human reviewer, but its verdict cannot mark a question `published`.

### 3.3 Topic must never be guessed at run time

Nothing at run time infers a Topic freely from question text or from an LLM answer. Starting from Gold's `concept_group`, M3 maintains a provider-neutral, versioned Topic registry:

```text
concept_group → topic_id
textbook/chapter/section/evidence anchor → topic_id
```

A `topic_id` denotes a concept reusable across textbooks and carries no specific textbook ID. A chapter may be an input to a deterministic mapping, but `chapter_id` must never be used directly as a Topic. If one chapter corresponds to several Topics, M3 must supply section- or evidence-anchor-level mappings.

Topic is not an embedded field of the v2 Chunk. The resolver reads only a sidecar `chunk_topic_map` whose `corpus_hash` matches the current retrieval manifest and that carries a `topic_registry_version`. A chunk absent from the map simply has no Topic; it must not be guessed from a chapter title or from question text.

Two situations must be kept apart:

- **Normal.** The map is valid but a particular retrieved chunk has no entry. That chunk contributes no Topic weight.
- **Misconfiguration.** The map is missing, or `validate_chunk_topic_map()` reports that `corpus_version`/`corpus_hash` disagrees with the current manifest, or that it references a `chunk_id` absent from the corpus. The resolver must catch this, record the error code in the trace (`TOPIC_MAP_UNAVAILABLE` or `TOPIC_MAP_MISMATCH`), return `no_topic_available` for the round, and let M8 count it separately. Treating it silently as "no Topic" would let the whole Concept Check fail unnoticed.

`chunk_topic_map` is validated once, at load time, against the current manifest and a single read of the corpus `chunk_id` set. A failed load stays in the corresponding unavailable/mismatch state for the lifetime of that resolver; `records.jsonl` must not be rescanned on every query. Retrieval results must carry the same `corpus_version`/`corpus_hash` provenance as the validated sidecar; missing provenance also returns `TOPIC_MAP_UNAVAILABLE`, with no exception for any run mode.

The MVP does not depend on the v3 Conversation Context. Instead the resolver is split into two operations that happen at different points in the round:

1. `resolve_retrieval_topic(retrieval_hits)` — called after retrieval completes and before the reranker runs. It reads the `topic_ids` of the retrieved chunks from the `chunk_topic_map` sidecar to choose the round's candidate Topic for building the `LearnerContextSnapshot`. Hits absent from the map contribute no Topic weight.
2. `resolve_cited_topic(cited_chunks)` — called after the answer passes citation validation. It reads only the evidence actually cited by a non-abstained answer, and is used to select the Concept Check question. When the answer abstains or cites nothing it returns `no_topic_available` and no question is asked.

Both operations use the same deterministic scoring rule. They use the rank returned by the initial retrieval — not the reranked position. A chunk at rank `r` contributes `1/r`; if that chunk carries `n` Topics, each Topic receives `1/(r*n)`, so a chunk mapped to several Topics splits its evidence weight evenly. Compute `support(topic) = topic_weight / total_topic_weight`; a Topic is determined only when it is the unique maximum and `support >= min_topic_support`. Ties, a missing Topic, or insufficient support return `no_topic_available`.

When the retrieval stage cannot determine a unique Topic, the v1 main pipeline may still build a snapshot from the static global level for compatibility, but the Concept Check must be off for that round: an unsupported Topic must never update LearnerState. A one-to-one chapter-to-Topic mapping is admissible only as a fixture or as a fallback that M3 has explicitly registered.

The Topic registry must carry a `topic_registry_version`, and that version flows into questions, state, and the run trace. Cross-textbook mappings of the same concept are reviewed by M3; they are never created ad hoc by M7 or at run time.

## 4. Question lifecycle and sources

### 4.1 Source enumeration

```text
human_authored   written by a person
sciq_aligned     a SciQ question aligned to textbook evidence (OpenStax or CK-12)
llm_generated    an LLM candidate generated from evidence
```

A `sciq_aligned` question must additionally record:

```text
source_dataset = "SciQ"
source_question_id = the original SciQ ID
source_split = train | validation
```

The Concept Check practice pool admits SciQ `train` or `validation` only. A `test` item may not enter the pool even if its question text was rewritten or its `question_id` replaced.

### 4.2 Status enumeration

```text
draft            an initial question or an LLM candidate
auto_validated   passed automatic structure/reference checks, awaiting human review
reviewed         reviewed by M3
published        may enter the practice pool
rejected         failed automatic checking or human review
```

`split_guard` and `status` are two different fields. `split_guard=practice_only` says the question may not enter a formal evaluation set; `status=published` says the question has passed the quality bar.

A `published` question must also have an M3 `review_record_id`, a reviewed feedback explanation `rationale`, and at least one resolved binding for a current or rebuildable corpus version. `auto_validated` must never be treated at run time as if it were `published`. For `source_type=sciq_aligned`, `source_dataset`, `source_question_id` and `source_split` must all be present; for `human_authored`, those SciQ fields must be empty or absent.

### 4.3 Minimal question data structure

The first version should use the fields below. Multi-textbook identity fields come from M1's shared v2 contracts; M7 must not invent a second set. A persisted question never treats `chunk_id` as the identity of its evidence.

```json
{
  "schema_version": "0.1",
  "question_id": "cc_physics_0001",
  "question": "If an object moves with constant velocity, what is its acceleration?",
  "options": {
    "A": "It is zero",
    "B": "It doubles",
    "C": "It is constant but non-zero",
    "D": "It is undefined"
  },
  "correct_answer": "A",
  "topic_id": "constant_velocity_and_acceleration",
  "topic_registry_version": "topics-0.1",
  "difficulty": "beginner",
  "evidence_anchors": [
    {
      "schema_version": "2.0",
      "span_id": "cc:cc_physics_0001:1",
      "textbook_id": "openstax_college_physics_2e",
      "chapter_id": "2",
      "chapter_char_start": 1200,
      "chapter_char_end": 1260,
      "verbatim_text": "An object moving at constant velocity has zero acceleration.",
      "text_hash": "sha256:00161e370e00cb6b6a975348449ed1a812a9ba715d9251880eac9d9ee50bb24c",
      "origin_corpus_version": "2.0.0-dev.1"
    }
  ],
  "source_type": "human_authored",
  "split_guard": "practice_only",
  "rationale": "Constant velocity means velocity does not change, so acceleration is zero.",
  "review_record_id": "m3_review_cc_0001",
  "status": "published"
}
```

The question and evidence above are a synthetic fixture example and must not be used as Gold or as real practice content. Each item of `evidence_anchors` is the v2 contract's `EvidenceSpan` (`cs30.v2.contracts`), the same type as v2 Gold evidence: the offsets form a **chapter-local** half-open interval, the length of `verbatim_text` must equal the interval length, and `text_hash` is its SHA-256 (computed by the contract when omitted, and required to agree when supplied). The hash in the example is the real value for that example text. A `span_id` must be unique across Gold and Concept Check; prefixes `gold:` and `cc:` are recommended. An anchor stores no `document_id`, global offset, `chunk_id`, or `source_locator` — all of those change when the corpus is rebuilt and appear only in the binding described in §4.4. The example is human-authored and therefore carries no SciQ provenance; a `sciq_aligned` question must additionally carry the SciQ fields defined below. `rationale` is M3-reviewed static feedback; no LLM is called at submission time. It must be reviewed together with the same set of evidence anchors, and must not explain something the question's evidence does not support.

### 4.4 Evidence anchors and corpus binding

`evidence_anchors` is the question's stable source-of-truth. Each anchor's `origin_corpus_version` records the corpus version it was first aligned against; the `chunk_id` used by the current index is only a runtime resolution result. Each target corpus version produces one `EvidenceSpanBinding` (`cs30.v2.contracts`) per anchor, and Gold evidence uses the same type:

```text
(span_id, corpus_version, corpus_hash)
    → resolution_status = resolved | stale | ambiguous
    → resolution_method = block_id | chapter_offset | verbatim_unique   # required when resolved
    → document_id + document-global interval + chunk_ids               # present only when resolved
```

Resolution follows the Gold mapping rules: within the same textbook/chapter, try block_id, then chapter-local offset with a `text_hash` check, then a unique verbatim-text match. A corpus rebuild therefore does not invalidate the question pool merely because chunk IDs changed. When a source needs to be displayed, the chunk resolved by the binding supplies the `source_locator`, produced by the v2 `ids.source_locator` builder in the form `source=<source_name>|textbook=…|chapter=…|location=…|span=start:end`. `source_name` is the `textbook_id` itself (or `textbook_id/<part>` if a book is later split across several source files) and carries no file extension; v2 catalog validation rejects any other form. When a PDF page number exists, `location` is `p<page>`. Nobody may hand-write a locator or keep using the v1 `#chapter=...&char=...` format.

A question anchor and a v2 Gold evidence span use **one and the same** evidence-interval type defined by M1, `EvidenceSpan` (textbook, chapter, chapter-local half-open character interval, verbatim text and `text_hash`; `document_id`, global offsets and `chunk_id` are resolution results and live in `EvidenceSpanBinding`). There is **exactly one implementation** of "text interval → chunk", provided by M4 as part of the Gold mapping; Concept Check's `anchors.py` is only a thin adapter over it and writes no matching logic of its own. This is what lets the Gold-overlap gate in §4.5 compare like with like, instead of two implementations giving different coordinates for the same passage and missing an overlap.

An anchor may only fall on content types that the current evidence policy retains and that enter the retrieval corpus (for W5: body, example, figure_caption, glossary, table, equation). An anchor on excluded content — problem, summary, conceptual_question and the like — can never bind, so the question cannot be published. M3 observes the same restriction when marking seed passages.

When resolution fails, goes stale, or matches several places, the question must not be marked `published` and must not be shown online. Note what this binding does and does not require: it requires the reviewed evidence to resolve against the current corpus. It does **not** require the resolved evidence to be a subset of this round's top-k retrieval. An answer's citations still obey the v1 constraint — they may come only from chunks this round's retrieval actually returned. These are two different contracts.

`resolved_chunk_ids` may appear only in per-corpus-version bindings and in the run trace; it never overwrites a question's stable anchor. Rebuilding the corpus rebuilds bindings; it does not permanently rewrite every question to new chunk IDs.

Gold already has typed `GoldSource`/`SourceSplit` and a `GoldSample.source` field. Concept Check reuses them directly rather than inventing a second provenance type in Phase 1. Two namespaces must be kept apart:

- `GoldSample.split` is the project's evaluation split (`dev`, `test`, plus any proposed marker the current process uses);
- `GoldSample.source_split` is SciQ's own source split (`train`, `validation`, `test`).

SciQ's `source_split` must not be normalised into the project's `dev`/`test`, and the project split must not stand in for the SciQ source split. The practice registry indexes every Gold `source_question_id` and reports Dev/Test hits separately at minimum. Once an ID has entered frozen Gold provenance it may not be used as a practice-question source.

This document assumes the target v2 baseline already exports these typed classes. Before implementation, confirm where they actually live on the chosen v2 branch; if the checkout still carries the older models, sync that baseline first rather than growing a second provenance type with the same name or similar meaning under Concept Check.

### 4.5 SciQ provenance and the general Gold leakage gate

For `source_type=sciq_aligned`, all of the following are mandatory:

```text
source_dataset = "SciQ"
source_question_id
source_split ∈ {train, validation}
```

The validator must check all of:

1. `source_split` is not `test`;
2. `source_question_id` is not in Gold's Dev/Test provenance set;
3. `source_question_id` is not in any frozen Gold provenance set;
4. rewriting the stem, the options, or the Concept Check `question_id` does not bypass the checks above.

For every source — and especially for `llm_generated` — a Gold content-leakage check is also required:

1. Normalise the question's anchor binding and the Gold Dev/Test evidence to the same current-corpus coordinates. Reject the question if the textbook, chapter and half-open interval overlap, or if the anchor's `text_hash` equals that of Gold evidence. Both sides must be resolved by the same M4 resolver from §4.4. While Gold has not yet been migrated and resolved to the current corpus version, this check counts as **failed**, not skipped, and the question cannot reach `auto_validated`.
   **Cross-book duplicates are compared by duplicate group.** In the v2 corpus roughly 94% of the AP edition's retrievable text is verbatim identical to College Physics 2e. Every build emits `duplicate_blocks.json` (bound to the corpus hash) listing blocks with identical body text that belong to different textbooks. Before the overlap check, expand the blocks covered by the anchor and by the Gold evidence into their respective duplicate groups; any intersection of groups counts as an overlap. A **partially** overlapping copy living in another book is therefore rejected too, rather than passing because its `text_hash` is not exactly equal.
2. Run a version-pinned text/semantic similarity check over the stem and the options. On reaching the frozen threshold, flag `gold_leakage_suspected`; the question must not pass `auto_validated` automatically and must be explicitly cleared or rejected by M3 in the review record.
3. The validator trace records the checker version, the thresholds, the matched Gold IDs, the evidence-overlap result and the similarity result.

The leakage check runs in both directions. When Gold is frozen or updated, every `source.source_question_id` of the new Gold must also be compared back against the provenance of the published Concept Check practice pool. A collision in either direction blocks publication. Checking only when a practice question enters Gold is not enough, because M3 may later select SciQ train/validation items into a new Gold.

Consequently, questions carrying `sciq-test-*` in the current fixtures may not go straight into a Concept Check fixture or provider; a separate practice fixture containing only SciQ train/validation or human-authored questions is required.

## 5. Run-time flow

### 5.0 When Concept Check is off

When `concept_check.enabled=false`, the pipeline calls no Topic resolver, question provider, binding resolver, or LearnerState event store. The snapshot comes straight from the static StudentProfile, and the run manifest and trace record `profile_source="static_profile"`. This mode appends no Concept Check events and shows no questions.

The formal four-condition Dev/Test experiments must all run in this off mode, so that the comparison is between static profiles and retrieval/generation conditions rather than being contaminated by dynamic attempt state. Only a standalone Concept Check demonstration or a dynamic experiment may turn `concept_check.enabled` on.

### 5.1 Presenting a question

After an answer completes, the UI may offer: "Would you like a short question to check your understanding?" If the student does not choose the Concept Check, no question is created and no state changes.

Question selection proceeds in this order:

1. if `resolve_retrieval_topic` did not determine a unique Topic at the retrieval stage, return `no_topic_available` for the round, do not call the post-answer cited-topic resolver, and ask no question;
2. only a non-abstained answer that passed citation validation proceeds to a Concept Check; with no citations, or on abstention, return `no_question_available`;
3. call `resolve_cited_topic` with the evidence the answer actually cited, independent of the not-yet-implemented v3 Conversation Context; ask nothing when the Topic is not uniquely determined;
4. filter to `published` practice questions under that Topic whose bindings resolve against the current corpus version, and exclude any `question_id` this student has already submitted (including attempts later revoked — those are not shown again);
5. order the candidates as follows. Normally prefer the difficulty equal to the current Topic level, then adjacent difficulties. But when `mastery_score >= promotion_threshold` and the current level is not `advanced`, enter upward-probe mode: prefer unanswered questions one level up (the target level), falling back to same-level questions. If the pool has no usable question one level up, fall back to the ordinary difficulty order — never fabricate evidence of promotion. Add a soft bonus when at least one resolved chunk overlaps the evidence cited by this round's answer. Overlap is a ranking bonus only; it is never a hard validator or display gate;
6. a `sciq_aligned` question must additionally have a train/validation source split and pass the bidirectional leakage gate;
7. LLM candidate generation is permitted only when the experimental fallback is explicitly on;
8. with no binding or no usable question, return `no_question_available` and keep the original answer.

The official first-version demonstration uses only the TopicResolver, published practice/SciQ questions, and successful bindings; it does not use the online LLM fallback. LLM candidates are generated in offline batches; one successful online call never publishes anything automatically.

### 5.2 Submitting an answer

The submission path calls no LLM:

```text
ConceptCheckQuestion + selected_choice
        ↓
        Grader
        ↓
ConceptCheckGrade(correct / incorrect / skipped)
        ↓
LearnerStateUpdater
```

`selected_choice=null` is permitted only in the `skipped` state. Resubmitting the same `attempt_id` must be idempotent and must not accumulate attempts twice.

Post-submission feedback reads only the published question's `rationale`, the correct answer, and the textbook evidence resolved by the current binding. The MVP calls no LLM and generates no ad-hoc feedback from the student's answer. If per-distractor corrective hints are wanted later, add a v2 `misconception_feedback` mapping that M3 has reviewed — do not let it become an implicit online generation capability.

### 5.3 Failure semantics

- Structural failure: the question moves to `rejected`.
- An evidence anchor cannot resolve against the current corpus: do not show the question, and mark the binding `stale` or `ambiguous`.
- The binding is missing, stale, or ambiguous: do not show the question; return `no_question_available`. This round's retrieval failing to return the chunk an anchor points at is **not** a failure — it only loses the evidence-overlap ranking bonus.
- A SciQ `source_question_id` appears in Gold Dev/Test or in the SciQ test split: the question moves to `rejected`.
- The Topic cannot be determined: do not show a question; return `no_topic_available`.
- `chunk_topic_map` is missing or disagrees with the current manifest: also return `no_topic_available`, but record the configuration error `TOPIC_MAP_UNAVAILABLE`/`TOPIC_MAP_MISMATCH` in the trace, counted separately by M8.
- LLM/API/JSON failure: record the single-question failure; do not interrupt the batch.
- State-update failure: keep the attempt record and report the error; never fabricate a new LearnerState.
- No failure may ever let the system produce feedback without evidence.

## 6. First-version LearnerState rules

### 6.1 State fields

```text
state_id
profile_id
topics[topic_id]
  mastery_score       0.0–1.0
  level               beginner/intermediate/advanced
  attempt_coverage    0.0–1.0
  total_attempts
  attempts_since_level_change
  correct_attempts
  misconceptions
```

The event log is the single source of truth for dynamic learning state. `LearnerState` is the current result of replaying that log, not a second fact written independently. `attempt_coverage` expresses how much attempt evidence has accumulated for the current level estimate; it is not the profile confidence the reranker consumes.

The ordering within one round is fixed:

```text
retrieval
  → resolve_retrieval_topic(retrieval hits)
  → build LearnerContextSnapshot
  → rerank / generation
  → citation validation
  → resolve_cited_topic(answer citations)
  → select Concept Check question
```

So the snapshot is not built "at the start of each round" but after retrieval completes and before the reranker runs:

- `profile.level`: if `resolve_retrieval_topic` determined a unique Topic, take that Topic's current `level`. If it could not, fall back to the static StudentProfile's global level — but then no Concept Check state update is allowed that round.
- `profile.confidence`: keep the static profile's original confidence; do not let `attempt_coverage` override it.
- `profile.topic_levels`: a compatibility snapshot for older prompts and interfaces only, produced on the fly by the LearnerState adapter, never a second persisted state.
- the snapshot additionally carries `topic_id`, `attempt_coverage`, `state_version` and TopicState;
- the same snapshot is given to reranking and to generation. The post-answer `resolve_cited_topic` only decides the Concept Check question's Topic; it never writes back to, or replaces, the snapshot already used for this round's answer.

This is why a cold start with `attempt_coverage=0` does not quietly drive `effective_lambda = lambda × profile.confidence` to zero: the reranker's confidence semantics are unchanged.

`profile_source` has exactly two values: `learner_state_replay` when Concept Check is on and state comes from replaying the event log, and `static_profile` when Concept Check is off. It must be written into both the run manifest and the trace — which profile source a round actually used must not have to be inferred from a config file.

### 6.2 Update rules

```text
correct answer   current_performance = 1.0
wrong answer     current_performance = 0.0
partial answer   current_performance = 0.5  # unused in the first version

level_relation = below | same | above
  # compare question.difficulty with the current Topic level before updating it
correct_weight = correct_difficulty_weights[level_relation]
wrong_weight = wrong_difficulty_weights[level_relation]
alpha_eff = 0.2 × (correct_weight if correct else wrong_weight)
new_score = previous_score + alpha_eff × (current_performance - previous_score)
```

The MVP defaults to asymmetric weights, with the array order fixed as `[below, same, above]`:

```toml
correct_difficulty_weights = [0.5, 1.0, 1.0]
wrong_difficulty_weights = [1.0, 1.0, 0.5]
```

That is: answering a question above the current level correctly is as informative as answering at level, while getting it wrong counts at half weight; answering below the current level correctly counts at half weight, while getting it wrong still counts in full. This avoids discounting informative observations by symmetric distance, and avoids producing only a tiny demotion signal when an advanced student keeps failing beginner questions.

Recommended for the first version:

- a new Topic starts at `mastery_score=0.5`, `total_attempts=0`;
- the student's self-selected global level is that Topic's initial level;
- `level_change_window=3` is the single minimum-sample count and window length for level changes; there is no separate minimum-attempts parameter. Replay keeps a bounded sliding window of the most recent 3 valid submissions within the current level epoch; each time it reaches 3, those 3 may be re-evaluated for a level change. Skipped or revoked attempts do not enter the window, while `attempts_since_level_change` may accumulate every valid submission in the epoch;
- `attempt_coverage = min(1.0, attempts_since_level_change / attempt_coverage_window)`, where `attempt_coverage_window=5` only controls how quickly the displayed coverage saturates — it is not an additional level-change gate;
- a question below the current Topic level cannot by itself justify promotion; getting a question above the current Topic level wrong cannot by itself trigger demotion;
- no level change before at least one full `level_change_window` has accumulated;
- promotion requires `mastery_score >= 0.75` and at least two questions in the recent window whose difficulty is not below the target level and which were answered correctly;
- demotion requires `mastery_score <= 0.25` and at least two questions in the recent window at or below the current level answered incorrectly;
- at most one level of change at a time. If the window qualifies, change one level, then clear the window and the counters for that level epoch — never jump several levels over the same batch of history;
- after a level change, reset `mastery_score` to `0.5` and reset `attempts_since_level_change` and `attempt_coverage` to `0`;
- `total_attempts` and historical events are never deleted; they remain for long-term audit;
- `skipped` does not update state;
- in the first version `misconceptions` may be written only by reviewed rules or human labels, never produced freely by an LLM.

After each submission event is written and replayed, the selector reads that Topic's **latest** TopicState. On the next selection, whenever `mastery_score >= promotion_threshold` and the current level is below `advanced`, it enters upward-probe mode targeting the next level up. It never uses pre-update state, and it does not require this to be the "first" time the threshold was reached. Starting from `mastery_score=0.5`, four correct same-level answers give `0.7952` (the first three give only `0.744`, below the threshold); two subsequent correct answers at the target level then satisfy the promotion condition of at least two correct target-level questions in the recent window, so the earliest promotion is around the sixth valid attempt. Three consecutive wrong answers give `0.256`, still above the `0.25` demotion threshold. These worked examples assume consecutive same-level questions; tests must not assume a level change occurs on the third question.

These thresholds, difficulty weights and the level-change window are configurable MVP defaults written into the run manifest. They must not be presented as validated psychometric findings.

## 7. Event sourcing and student control

An attempt never overwrites LearnerState directly. The system appends immutable events, and LearnerState is obtained by replaying them:

```text
ConceptCheckEvent
  attempt_submitted | attempt_skipped | attempt_revoked | topic_level_overridden
        ↓ replay
LearnerStateSnapshot
```

Submitted and skipped events carry at least `event_id`, `attempt_id`, `question_id`, `topic_id`, `question_difficulty`, `selected_choice`, `performance`, `event_type`, `state_version_before`, `stream_version` and `created_at`. A revocation event points at its target attempt through a separate `revoked_attempt_id` rather than reusing the target's `attempt_id`. A Topic level override event records `topic_id`, `topic_registry_version`, `new_level`, `actor` and `reason`, and does not require `attempt_id`, `question_id` or `question_difficulty`. `stream_version` is assigned monotonically per student stream by the event store, and replay orders by it; `created_at` is for audit only and never determines state order. For submitted and skipped events, `attempt_id` is the attempt idempotency key; for overrides and revocations, the retrying caller must reuse the same `event_id`. The same event identifier carrying a different payload must raise a conflict rather than silently overwrite.

The MVP event store is a **single-writer append-only JSONL** under a single-user demo assumption (one stream per student, writes protected by an in-process lock or equivalent). The MVP does not require cross-process concurrency control with an expected stream version. If the deployment shape stops satisfying the single-writer assumption, v3 must upgrade to a persistent event store with expected stream versions rather than continuing to overwrite silently.

`LearnerStateSnapshot` is an optional cache, not a source of truth, and must carry `derived_from_event_version`. Replaying the same event log must yield the same state.

Student control maps onto events:

- **Turning Concept Check off**: no attempt events are appended.
- **Revoking an attempt**: the MVP allows revoking only the most recent valid submission for the target Topic within that student's **single** stream. It appends an `attempt_revoked` event, and replay excludes the revoked attempt. Revoking an older record, revoking twice, or revoking a non-existent attempt must be rejected. M8 reports the revocation rate so that mastery cannot be inflated by repeatedly revoking wrong answers. General revocation of an arbitrary historical attempt is left to v3.
- **Correcting a Topic level**: append `topic_level_overridden`, recording actor=`student` and a reason, and reset that Topic's mastery and window to the initial state for the new level.
- **Viewing evidence**: read the question anchor's current binding and display only resolved textbook evidence.
- **Deleting the dynamic profile**: v3 must actually delete that student's event log and snapshots from storage. Appending a `deleted` marker to pretend the deletion happened is not acceptable.

The event log is append-only; user deletion is a controlled storage operation, not an ordinary state update.

## 8. Suggested code boundaries

### 8.1 M1 owns

- shared v2 contracts in `src/cs30/v2/contracts/`: Concept Check, LearnerState, Topic, provenance/binding and `LearnerContextSnapshot`, plus the evidence-interval type shared by question anchors and v2 Gold evidence (§4.4);
- reuse of the existing `src/cs30/v2/ids.py`, catalog, corpus version and source-locator builder — no second set of textbook-identity or locator rules inside the Concept Check module;
- v2 Protocols in `src/cs30/v2/ports.py`, covering the Topic resolver, validator, grader, event store and state replay;
- v2 configuration still managed by `src/cs30/v2/config.py`, but **without** wiring Concept Check into `src/cs30/v2/pipeline.py`: that file is currently the `run_build_pipeline` corpus-build entry point, not the question-answering flow;
- snapshot construction implemented as a side-effect-free pure function, e.g. `src/cs30/concept_check/snapshot.py`, taking an explicit LearnerState, static StudentProfile and Topic result, and returning an immutable `LearnerContextSnapshot`;
- Concept Check implemented as a standalone post-answer component, e.g. `src/cs30/concept_check/service.py`, responsible for post-answer selection, submission, grading and event appending. It receives retrieval/citation/state dependencies through Protocols and is not called from the current build pipeline;
- integration through a separate adapter once the v2 question-answering pipeline exists — without changing v1's `src/cs30/contracts/`, `src/cs30/ports.py`, `src/cs30/config.py`, `src/cs30/pipeline.py`, or the corpus-build-only `src/cs30/v2/pipeline.py` at this stage;
- schema/version, practice/Test isolation, anchor binding, manifest and integration tests;
- failure codes, run traces, and forward compatibility with later v2 identity fields.

### 8.2 M7 owns

- the pure-function implementation in `src/cs30/concept_check/snapshot.py`;
- the standalone post-answer component in `src/cs30/concept_check/service.py`, with no direct dependency on the current v2 build pipeline;
- `src/cs30/concept_check/generator.py`;
- `src/cs30/concept_check/validator.py`;
- `src/cs30/concept_check/grader.py`;
- the pure replay/update logic in `src/cs30/concept_check/learner_state.py`;
- the two resolver adapters in `src/cs30/concept_check/topics.py`;
- `src/cs30/concept_check/anchors.py`: a thin adapter calling M4's shared span resolver, with no matching logic of its own;
- the fixture question provider and the LLM candidate adapter;
- single-question failure isolation and JSON parsing.

### 8.3 M3 owns

- Topic and difficulty annotation rules;
- the provider-neutral Topic registry, the `concept_group → topic_id` mapping, and its version;
- `reviewed` / `rejected` decisions;
- review of evidence-anchor support, answer uniqueness, and Test/SciQ split leakage;
- physical isolation between the practice pool and the formal Dev/Test sets.

### 8.4 M4 owns

- the shared "text interval → chunk" resolver: Gold mapping and Concept Check anchor binding use the same implementation, locating by `textbook_id` + chapter rather than by a `document_id` that changes on re-parsing;
- generating the Gold mapping and question anchor bindings for each corpus version, recording each entry's resolution method and its `resolved`/`stale`/`ambiguous` status;
- generating the `chunk_topic_map` for each corpus version according to M3's Topic mapping rules, calling `validate_chunk_topic_map()` before publication;
- migrating v1 Gold onto the v2 corpus — the precondition for the §4.5 Gold-overlap gate to run at all.

### 8.5 M8 owns

- the Quiz me entry point, submission, skip and feedback UI;
- attempt event logging, revocation, opt-out, evidence viewing, and the LearnerState display/correction UI;
- analysis of question validation rate, answer accuracy, skip rate, generation failure rate and state updates.

## 9. First-version test requirements

### 9.1 Contract tests

- missing fields, unknown fields and wrong types are rejected;
- an option set that is not exactly A/B/C/D is rejected;
- a correct answer outside the option set is rejected;
- a question whose binding is empty, unresolvable, or stale/ambiguous for the current corpus version is rejected;
- a separate test asserts that v1 answer citations must be a subset of the chunks this round's retrieval returned — that rule must not be misapplied to a Concept Check question's resolved evidence;
- an evidence anchor that cannot be resolved for the current corpus version is rejected;
- a question that is not `practice_only` cannot be published;
- a `sciq_aligned` question missing `source_question_id`, using the test split, or hitting a Gold Dev/Test source ID is rejected;
- an anchor from any source that overlaps Gold Dev/Test evidence by span or text hash is rejected;
- a stem/option pair reaching the Gold similarity threshold is flagged `gold_leakage_suspected`, cannot publish automatically, and M3's clearance must appear in the review record;
- no question is asked when the Topic registry is missing, the vote ties, or Topic support is insufficient;
- a chunk mapped to several Topics splits its weight as `1/len(topic_ids)`;
- when `chunk_topic_map` is missing or disagrees with the retrieval manifest, the round returns `no_topic_available` and the trace records `TOPIC_MAP_UNAVAILABLE`/`TOPIC_MAP_MISMATCH`; when the map is valid but a chunk has no entry, that chunk merely contributes no Topic and no error is recorded;
- anchors and Gold evidence are resolved by the same resolver; while Gold has not been migrated to the current corpus, the overlap gate counts as failed;
- an anchor on a content type excluded by the evidence policy fails to bind and the question cannot be published;
- a catalog `source_name` carrying a file extension or differing from `textbook_id` is rejected;
- the ordering of the post-retrieval snapshot and the post-answer cited-topic step is correct, and no question is asked on abstention or with no citations;
- already-answered questions are excluded; evidence overlap is a ranking bonus with no hard gate;
- duplicate question IDs and attempt IDs have well-defined behaviour.

### 9.2 Grading tests

- a correct answer returns `correct` with performance 1.0;
- a wrong answer returns `incorrect` with performance 0.0;
- a skip returns `skipped` and leaves LearnerState unchanged;
- grading calls no LLM.

### 9.3 State tests

- exponential-smoothing values are correct;
- questions above, at, and below the current level each exercise the asymmetric weights for both correct and incorrect answers;
- no level change while the level-change window is short, and the window is the most recent N valid submissions rather than unbounded history;
- starting from `0.5`, neither three consecutive correct nor three consecutive incorrect answers changes the level; after the promotion threshold is reached, a target-level probe question is offered first, and promotion is allowed only after two correct target-level answers;
- after a level change, mastery, coverage and the window counter reset while total history is retained;
- an advanced level never drops straight to beginner on a single wrong answer;
- a duplicate attempt stays idempotent through event replay;
- revocation and student level override replay correctly;
- revoking anything other than the most recent attempt is rejected, and M8 can measure the revocation rate;
- the snapshot keeps the static profile confidence and uses the current Topic's level;
- when `enabled=false`, resolvers and the event store are never called, the snapshot uses the static profile, and `profile_source="static_profile"` is recorded — the formal four-condition experiments verify this mode;
- the single-writer JSONL event store is idempotent and replays stably;
- every `[concept_check]` configuration key passes a three-part reachability test: the value is read, injected, and changes behaviour;
- `allow_llm_generation` or `allow_unreviewed_questions` is rejected outside development, and the run trace records both the switches and what was actually called;
- `src/cs30/v2/pipeline.py` is never called by the Concept Check runtime; the pure snapshot builder and the post-answer service are independently testable;
- bidirectional leakage tests pass, both new Gold against the published practice pool and the practice pool against all frozen Gold provenance;
- the fixture end-to-end path runs.

## 10. Feature flag and acceptance gate

Initial configuration:

```toml
[concept_check]
enabled = false
allow_llm_generation = false
allow_unreviewed_questions = false
promotion_threshold = 0.75
demotion_threshold = 0.25
level_change_window = 3
attempt_coverage_window = 5
correct_difficulty_weights = [0.5, 1.0, 1.0] # below, same, above
wrong_difficulty_weights = [1.0, 1.0, 0.5]   # below, same, above
min_topic_support = 0.5
```

That is exactly ten Concept Check configuration keys. `level_change_window` defines both the minimum sample count for a level change and the bounded window length; there is no separate minimum-attempts key. All ten must be covered by configuration reachability tests, which verify not only that the TOML is readable but that dependency injection actually changes the corresponding behaviour.

The v2 run configuration separately provides an environment field, `environment ∈ {development, staging, production}`; it does not count towards the ten `[concept_check]` keys. Configuration loading must enforce:

```text
if environment != "development" and (
    allow_unreviewed_questions or allow_llm_generation
):
    reject configuration
```

Silently flipping `true` to `false` in staging or production is not acceptable. `allow_llm_generation=true` permits candidate generation in development only; `allow_unreviewed_questions=true` permits explicitly displaying unreviewed candidates in development only. Neither may mark a question `published`. Every run's manifest and trace must record `environment`, both switches, `enabled`, `profile_source` and `resolver_called`, so that configuration and actual behaviour are auditable.

Before the official feature flag may be turned on:

- questions have stable evidence anchors bound to the current corpus version;
- question status is `published`;
- questions have an M3-reviewed `rationale`, and the submission path does not depend on an LLM;
- there is no Gold Dev/Test or SciQ test-split leakage;
- the reverse source-ID check between newly frozen Gold and the published practice pool has been completed;
- the Topic registry, the resolver and the Topic support check pass;
- the snapshot is created after retrieval and before reranking, and no Concept Check is produced when the answer abstains or cites nothing;
- a question may have zero overlap with this round's evidence; overlap is only a ranking bonus;
- answer uniqueness and difficulty have been spot-checked by a person;
- generation failure has an explicit degradation path;
- fixture, contract, grading and state-update tests pass;
- the UI, logs and reports can distinguish question source, question status, and official versus practice split.

## 11. Phased implementation

### Phase 1: M1 contracts and fixtures

- freeze the models, enumerations and Protocols;
- freeze the **structure, version field and resolver algorithm** of the Topic registry, and supply a synthetic registry fixture for testing only. Production Topic content and cross-textbook mappings are M3's Phase 3 output; Phase 1 must not claim the content is frozen;
- reuse the existing typed `GoldSource`, `SourceSplit` and `GoldSample.source`, adding only the Gold provenance registry and the bidirectional leakage gate — no parallel source types, and no rewriting the source split into the project's dev/test;
- use the `EvidenceSpan` and `EvidenceSpanBinding` already present in the v2 contracts for stable evidence anchors and corpus-version bindings (added to `cs30.v2.contracts` on 2026-09-23). They are also the types used by v2 Gold evidence; the two are not defined separately;
- represent fixture question anchors with `EvidenceSpan`, and produce any locator that needs displaying only through the v2 `ids.source_locator` builder. Use textbook ID `openstax_college_physics_2e` and a corpus version of the form `2.0.0-dev.1`;
- add the feature flag;
- add 3–5 hand-written fixture questions with M3-reviewed `rationale`;
- build the single-writer JSONL event store, the most-recent-only revocation rule, and a replay fixture;
- add reachability tests for the ten `[concept_check]` configuration keys;
- keep the snapshot builder a pure function, and offer Concept Check first as a standalone post-answer component with fixture/API tests;
- do not wire Concept Check into the current `src/cs30/v2/pipeline.py` corpus-build entry point;
- complete the contract and integration tests;
- call no real LLM.

### Phase 2: M7 core logic

- implement the question validator, the grader, the Topic resolver adapters, and event replay/update;
- wire in the fixture provider;
- implement difficulty weighting and the mastery/window reset after a level change;
- implement JSON parsing and failure isolation for candidate questions;
- emit attempt/grade traces for M8 to consume.

### Phase 3: M3/M2/M4 data integration

- wait for the chunks, Topics and splits of the v2 textbooks (three OpenStax books plus one CK-12) to be frozen;
- M4 migrates v1 Gold onto the v2 corpus and provides the shared span resolver. Until this is done, the §4.5 Gold-overlap gate cannot pass and no question may be published;
- M3 completes the `concept_group → topic_id` mapping, the textbook/chapter/section-to-Topic mapping, and the easy/medium ↔ beginner/intermediate/advanced difficulty correspondence;
- following M3's mapping, M4 generates a `chunk_topic_map` sidecar bound to `corpus_hash` for each corpus manifest and passes `validate_chunk_topic_map()`. Chunks with no mapping are treated at run time as having no Topic;
- while producing v2 Gold, M3 also marks seed passages (passages that explain one concept on their own, annotated with `topic_id` and a suggested difficulty). These may only come from content types retained by the evidence policy and must not overlap the core evidence of Test Gold. Seed passages are the input for offline LLM authoring;
- build the aligned practice pool;
- M4 generates evidence anchor bindings for each corpus version using the shared resolver;
- generate candidates from SciQ train/validation and run the bidirectional leakage check against all Gold source IDs; also check back against the published practice pool when freezing new Gold;
- generate LLM candidate questions;
- M3 marks them `published` after review.

### Phase 4: M8 UI and a standalone dynamic experiment

- wire up Quiz me, feedback and skip;
- once the v2 question-answering pipeline has a stable post-answer seam, connect the standalone Concept Check component through an integration adapter — do not push question-answering wiring back into the corpus-build pipeline;
- record before-and-after state snapshots;
- evaluate state updates, remediation direction and learning effect over 30–60 multi-turn scenarios;
- keep the feature flag off whenever Concept Check quality is below the bar.

## 12. Definition of done

When the first version is complete, M1 should be able to demonstrate:

```text
fixture answer
  → published practice question
  → automatic validation
  → student submit
  → deterministic grading
  → LearnerState update
  → traceable result
```

together with all of:

1. the default behaviour of the v1 static main pipeline is unchanged;
2. Concept Check is off by default;
3. unreviewed LLM questions cannot be read by any official path;
4. after retrieval, a Topic snapshot can be built for reranking/generation; after the answer, the Concept Check Topic can be determined again from cited evidence, and the system refuses safely when it cannot be determined or the answer abstained;
5. questions bind to the current corpus through stable anchors rather than depending permanently on chunk IDs;
6. SciQ source IDs, Gold Dev/Test, and SciQ split leakage all have automatic gates;
7. the snapshot does not override the static profile confidence, and the reranker and generation use the same snapshot;
8. questions, evidence, events and state updates all have stable IDs;
9. a single-question failure does not interrupt a batch;
10. a question's evidence binding need not belong to this round's top-k; the citation-subset constraint still applies to answers only;
11. difficulty updates use asymmetric weights, level changes use a bounded window, a change moves exactly one level and resets the epoch;
12. `enabled=false` bypasses Concept Check completely, the formal four-condition experiments use the static profile and record `profile_source`, and the two dangerous switches are rejected outside development;
13. all ten configuration keys, the contracts, replay, and the state-update rules have automated tests;
14. the three question sources share one state transition, and a published question has an M3 review record, a reviewed `rationale`, and a resolved binding for the current corpus;
15. the snapshot builder is a pure function and Concept Check is a standalone post-answer component; the current v2 corpus-build pipeline carries no question-answering runtime wiring, and integration later happens through an adapter on the v2 question-answering pipeline;
16. question anchors and v2 Gold evidence use the same evidence-interval type and the same M4 resolver, and a `chunk_topic_map` misconfiguration is recorded and counted rather than silently treated as "no Topic";
17. M7, M3 and M8 can continue implementing without redefining any schema.
