# Role Labels v1

This directory contains the first role-label draft derived from the reviewed
`m3_gold/gold_v0_1_1.jsonl` records.

The allowed role taxonomy is:

```text
definition / example / application / derivation / boundary
```

Each JSONL record has the required key `(question_id, chunk_id)` plus one
role. The current prepared corpus does not contain a separate official M4
block-to-chunk mapping file, so this draft uses the existing Gold
`block_id` as the reference value and records that limitation in the
provenance manifest. Do not present this draft as the final M4-compatible
handoff until the official mapping is available.

Regenerate it with:

```sh
python3 m3_gold/build_role_labels_v1.py
```

When M4 supplies a JSON mapping of `block_id` to `chunk_id`, regenerate with
`--chunk-map path/to/block_to_chunk.json`. The script then refuses any missing
mapping instead of inventing an identifier.
