# Role Labels v2

Evidence Role labels for every chunk of the v2 development corpus
(`2.0.0-dev.m4-structure-v2-main-3553825`, release `v2-m4-structure-v2-dev-v1`).
Member 7's level-aware reranker needs one Role per retrieval candidate, so these
labels cover corpus records, not just Gold chunks. The v1 package in
`m3_role_labels/` covers only the 20 Gold chunks of the old corpus.

- `role_taxonomy_v2.json`: the six Roles, their definitions, cues,
  "not this role" notes and the decision rules for hard cases. The terminal help
  and the LLM prompt both read it. Edit the definitions here, never in the
  script. `revision_note` records what each draft changed. It is frozen as
  `evidence-role-v2`; any edit changes its hash and relabels every chunk.
- `scripts/role_labels_v2.py`: the workflow below. All outputs go to
  `artifacts/v2/role_labels/`, which Git ignores. Back up your
  `human_labels_*.jsonl` files.

## Released package

Pre-release
[`v2-role-labels-v2-dev-v1`](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-role-labels-v2-dev-v1)
holds 5,976 labels under `evidence-role-v2`: 4,519 from `qwen3:8b`, 1,435 from
a review by `claude-opus-5-5` of every advanced-role candidate, and 22 decided
by a person. It has not been checked against an independent human annotation;
the release notes give the sources and agreement figures.

## Workflow

The process follows the A3 plan in `docs/系统架构与文献映射.md` §3.3: pilot a
sample by hand, check balance and agreement, revise the definitions, freeze,
then label the whole corpus with an LLM and check a subset by hand.

Run from the repository root with the project virtual environment active. The
LLM steps need the Ollama app running with `qwen3:8b` (`ollama pull qwen3:8b`).

1. Draw the 150-chunk pilot sample (deterministic):

       python scripts/role_labels_v2.py sample

2. Label it by hand. Type `1`–`6`, add `?` when unsure, and add a note after a
   space (`4? mostly a device`). `h` shows the definitions, `b` goes back, `s`
   skips, `q` quits. Each answer is saved at once; rerun to continue.

       python scripts/role_labels_v2.py annotate --annotator <your-id>

3. Label the same sample with the LLM (about 12 s per chunk):

       python scripts/role_labels_v2.py llm-label --scope artifacts/v2/role_labels/pilot_sample.json

4. Compare. The report gives Cohen's kappa, per-role precision, recall and F1,
   macro-F1, the confusion matrix and the comparison/application confusions, and
   writes the disagreements to a CSV that opens in Excel:

       python scripts/role_labels_v2.py compare artifacts/v2/role_labels/human_labels_<your-id>.jsonl artifacts/v2/role_labels/llm_labels_qwen3-8b.jsonl --scope artifacts/v2/role_labels/pilot_sample.json

   If the agreement is low, revise the definitions and rerun step 3. A changed
   taxonomy file relabels every chunk; unchanged chunks are never paid for twice.

5. Double annotation: a second annotator labels the first 30 chunks (20%), then
   compare the two human files the same way:

       python scripts/role_labels_v2.py annotate --annotator <second-id> --first 30

6. Freeze the taxonomy: set `status` to `frozen` and a final
   `taxonomy_version`. Then label the whole corpus. It takes about 20 hours for
   5,976 chunks; stop it any time and rerun the same command to resume.

       python scripts/role_labels_v2.py llm-label --scope all

7. Review the advanced Roles with a stronger labeller. `qwen3:8b` misses most
   derivations (2 of 7 in the pilot), so candidates are chosen by text cues
   (derivation phrasing with equations, boundary phrasing, many equations;
   worked examples excluded) plus every chunk the LLM labelled derivation or
   boundary:

       python scripts/role_labels_v2.py candidates --llm artifacts/v2/role_labels/llm_labels_qwen3-8b.jsonl

   Label the candidates in `advanced_candidates.txt` with a person (`annotate
   --scope`) or a stronger model. Save model review rows as JSONL with at least
   `chunk_id`, `role`, `model` and `taxonomy_sha256` (the hash the export
   checks), for example `review_labels_<model>.jsonl`.

8. Check by hand: the LLM review queue (errors, confidence below high, or a
   quote not found in the chunk), and a blind spot-check of the review labels.
   Your answer overrides the review and the LLM in the package. Leave out
   `--show-llm` for a blind check, then compare your file with the review file
   on the same scope:

       python scripts/role_labels_v2.py annotate --annotator <your-id> --scope artifacts/v2/role_labels/llm_review_queue_qwen3-8b.txt --show-llm artifacts/v2/role_labels/llm_labels_qwen3-8b.jsonl

9. Export the package for Member 7. It refuses to write an incomplete package
   unless you pass `--allow-incomplete`, and it checks the result with Member 7's
   own loader:

       python scripts/role_labels_v2.py export --llm artifacts/v2/role_labels/llm_labels_qwen3-8b.jsonl --review artifacts/v2/role_labels/review_labels_<model>.jsonl --human artifacts/v2/role_labels/human_labels_<your-id>.jsonl

## Package

`role_labels_v2.jsonl` has one row per chunk:
`{"schema_version": "role-labels-v2", "chunk_id": ..., "role": ..., "label_source": "human" | "review:<model>" | "llm:<model>"}`.
A human label wins over a review label, which wins over an LLM label; review
and LLM labels made under another taxonomy hash are ignored.
`role_labels_v2_provenance_manifest.json` follows `RoleLabelProvenanceManifest`
with `reference_universe: corpus_records`, which Member 7's formal runs require.
Its `annotator_ids` names the one primary annotator the schema requires; use
`label_source` for the provenance of each row.
`role_labels_v2_export_report.json` records the label sources, taxonomy hash,
LLM prompt version and any missing chunks.

## Known gap

Member 8's `audit_role_label_provenance` expects a `question_id` on every row
and a frozen question-to-chunk file for `corpus_records`. Member 7's loader keys
labels by `chunk_id` alone and rejects a repeated `chunk_id`. A chunk-level
package satisfies Member 7 but not that audit; the two contracts need to agree.
