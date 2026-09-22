# Role Labels v1

This directory contains the first role-label draft derived from the reviewed
`m3_gold/gold_v0_1_1.jsonl` records.

The allowed role taxonomy is:

```text
definition / example / comparison / application / derivation / boundary
```

Each JSONL record has the required key `(question_id, chunk_id)` plus one
role. `chunk_id` values come from the official M4
`eval_inputs/gold_to_chunk_mapping.json`; the Gold `block_id` is used only to
look up that mapping.

Regenerate it with:

```sh
python3 m3_gold/build_role_labels_v1.py
```

The manifest uses the role-label contract: `schema_version` `0.1`, raw
64-character `labels_sha256`, `reference_universe` `gold_mapping`, and the
declared role taxonomy. The script refuses any missing mapping instead of
inventing an identifier.
