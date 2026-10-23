# Topic registry review guide

## Current status

The frozen registry is `topics-0.2` in `artifacts/v2/topics/topic_registry_v0.2.json`; its source draft remains `topics-0.2-draft`. All 309 section-title candidate groups have a recorded disposition: 220 matched an existing Topic, 9 were mapped to multiple existing Topics, 2 were retained as standalone Topics already present in the registry, 2 new standalone Topics were added, and 76 composite or instructional headings were excluded. No section-title candidates remain unresolved.

The registry contains 2520 Topics: 2518 model-concept groups plus 2 new Topics from user-confirmed section titles. The Microscopy and Kinetic Theory section titles were attached to existing independent Topic IDs and their source references and draft definition candidates were added; this avoids duplicate Topics.

The registry was frozen on 2026-10-13 for development-corpus labeling. All 2518 model-concept definitions have a recorded assistant high-confidence resolution; 29 cases have explicit assistant adjudication records, including source-based corrections. The user confirmed definitions for “Motion of an Object in a Viscous Fluid” and “Planck and Quantum Nature of Light.” No Topics remain flagged for definition review or M3 confirmation. The source corpus is development-only (`reportable=false`), and generated labels still require M1 review and M3 spot-checking before release.

## CK-12 extension (2026-10-14)

The frozen `topics-0.2` registry and its 309 title decisions are based on the
three-OpenStax corpus only. They remain available as that version; they do not
yet include CK-12. A separate development corpus now includes the approved
CK-12 *People's Physics Concepts (With Answers)* source:
`2.0.0-dev.topic-ck12-2026-10-14` (`sha256:1af6489539026b115db6d9d2e8bc143161e0cd3832d01fe0c9706fc53b77d205`).

The four-book section inventory has 1,045 sections (925 OpenStax and 120
CK-12), 388 title candidate groups, and 111 sections without a title. Of the
95 title groups with CK-12 sources, 16 are shared with other textbooks and 79
are CK-12-only. The separate local Qwen run completed all 120 CK-12 section
proposals successfully, reusing the existing 925 OpenStax proposals. The
combined aggregate contains 7,527 concept mentions and 2,751 exact concept
groups after applying the current merge map; 23 new near-duplicate pairs
involving CK-12 await human review. The local
`artifacts/v2/topics-ck12-2026-10-14/topic_ck12_review_packet.json` contains
the CK-12 title groups, concept groups, and new near-duplicate review queue.

The title groups and CK-12 proposals still need human reconciliation against
the existing Topics; they must not be added to or used to replace the frozen
registry until a new registry version is reviewed and frozen. M2's ten manual
parser-QA samples also remain pending, so this corpus is for development review
only.

To reproduce the CK-12 addendum from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\install_v2_sources.py --format parsed
.\.venv\Scripts\python.exe scripts\build_v2_corpus.py --config real-development `
  --output-dir artifacts/v2/textbooks/2.0.0-dev.topic-ck12-2026-10-14 `
  --corpus-version 2.0.0-dev.topic-ck12-2026-10-14 --embedding-model ""
.\.venv\Scripts\python.exe scripts\build_topic_section_review.py `
  --corpus-dir artifacts/v2/textbooks/2.0.0-dev.topic-ck12-2026-10-14 `
  --output-dir artifacts/v2/topics-ck12-2026-10-14
.\.venv\Scripts\python.exe scripts\run_topic_section_proposals.py `
  --output-dir artifacts/v2/topics-ck12-2026-10-14 prepare `
  --corpus-dir artifacts/v2/textbooks/2.0.0-dev.topic-ck12-2026-10-14 `
  --textbook-id ck12_peoples_physics_concepts
.\.venv\Scripts\python.exe scripts\run_topic_section_proposals.py `
  --output-dir artifacts/v2/topics-ck12-2026-10-14 run --provider ollama `
  --ollama-model qwen3:8b --ollama-context 32768 --ollama-output-tokens 1024 `
  --ollama-timeout-seconds 1800 --confirm-run
.\.venv\Scripts\python.exe scripts\run_topic_section_proposals.py `
  --output-dir artifacts/v2/topics-ck12-2026-10-14 aggregate `
  --include-proposals artifacts/v2/topics/topic_section_proposals.jsonl
```

## Recorded decisions

- `artifacts/v2/topics/topic_title_seed_decisions_v0.json` is the reproducible source of the 75 title decisions (62 prior high-confidence decisions and 13 user-confirmed decisions dated 2026-10-13). Multi-Topic mappings are contextual associations; they do not merge aliases or change Topic identity.
- `artifacts/v2/topics/topic_registry_review_packet_v0.json` includes each disposition, per-Topic mapping, source-section references, the new Topics, and alternate definitions.
- `artifacts/v2/topics/topic_definition_decisions_v0.json` records the two user-confirmed definitions and the resolution of `MC-section-0843`.
- `artifacts/v2/topics/topic_definition_reconciliation_v0.json` records the local offline review of all 2518 non-user-confirmed definitions, including 1181 multi-candidate Topics and 1337 single-candidate Topics. It records 2507 high-confidence model selections and 11 model review flags; all 11 flags were resolved and recorded in `artifacts/v2/topics/topic_definition_manual_adjudications_v0.json`. That file contains 29 assistant adjudications, including source-context refinements for incomplete or inaccurate glossary definitions. No definition-review flags remain.
- The 13 final title decisions include 4 standalone Topic outcomes (2 existing independent Topics retained and 2 new Topics), 9 mappings to existing Topics, and 0 unresolved candidates. Composite headings such as “Electromotive Force: Terminal Voltage” are associated with their component or relationship Topics without being treated as synonyms.
- `MC-section-0843` is resolved by user decision: Chapter 20 “Induction” remains routed to Electromagnetic Induction by context, while its duplicated definition stays with the separate “EMF” candidate and is excluded from Electromagnetic Induction’s definition candidates.

## Review rule and next phase

A Topic should be a concept a student can be quizzed on by itself, usually no larger than a section. Merge synonyms only when they name the same concept. A section title that covers several concepts should map to those Topics without becoming a new Topic. See `docs/superpowers/specs/2026-09-21-concept-check-design.md` §3.3 and Phase 3.

The definition review phase is complete: 2518 assistant-resolved definitions and 2 user-confirmed definitions are recorded, with 0 M3 definition confirmations outstanding. The frozen registry and its provenance are recorded in `artifacts/v2/topics/topic_registry_freeze_manifest_v0.2.json`. Phase 3 is underway on the three-OpenStax development corpus; the pilot labels and review queue are separate from any production map.

## Earlier concept-disposition work

- All 108 lexical near-duplicate pairs (ND-001 through ND-108) have user-confirmed decisions: 77 merges and 31 keep-separate decisions. Merge mappings are in `docs/topic-registry/topic_merge_map_v1.json`.
- All 887 multi-concept sections have recorded concept dispositions; 0 concept dispositions are pending. The earlier Coulomb Interaction, Hall emf, Induction, and Tagged cases have recorded dispositions, including source-context handling for Induction.
- There are 925 source sections (925 successful, 0 failed), 6981 model-concept mentions, and 2638 initial exact-title groups. The merged aggregate used for this registry has 2518 concept groups.

## Rebuilding the draft

From the repository root, run:

```powershell
python scripts/build_topic_registry_draft.py
```

Inputs include `artifacts/v2/topics/topic_section_concept_aggregate_merged_v23.json`, `artifacts/v2/topics/topic_title_candidates.json`, `artifacts/v2/topics/topic_title_seed_decisions_v0.json`, `artifacts/v2/topics/topic_definition_decisions_v0.json`, the full proposal JSONL, the versioned merge map, and the corpus manifest. Outputs are `artifacts/v2/topics/topic_registry_draft_v0.json` and `artifacts/v2/topics/topic_registry_review_packet_v0.json`.
