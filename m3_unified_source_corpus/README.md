# M3 unified source-corpus handoff

Delivery date: 2026-09-13

The prepared OpenStax corpus is intentionally not committed in this repository.
M3 validates against the shared M4 prepared corpus through `load_prepared_corpus()`
from `cs30.evaluation`; do not add a duplicate `openstax_document.json` here.

Expected prepared directory shape:

```text
source_corpus/
  openstax_document.json
  corpus_manifest.json
  evidence_source_blocks.jsonl
```

After the M1 `write_prepared_corpus()` byte-output fix is merged to `main`,
rebuild the local handoff from the M4 chapter archive:

```sh
cs30-evaluate prepare-corpus \
  --archive <data.zip> \
  --output-dir m3_unified_source_corpus/source_corpus
```

Regenerate `SHA256SUMS` from the two content artifacts.  The manifest is kept
as provenance metadata for the prepared-corpus loader, but it is not an archive
content checksum: fields such as `archive_sha256` and `chapter_entries` depend
on the particular source ZIP container.

```sh
sha256sum m3_unified_source_corpus/source_corpus/openstax_document.json \
  m3_unified_source_corpus/source_corpus/evidence_source_blocks.jsonl \
  > m3_unified_source_corpus/SHA256SUMS
```

Verify the rebuilt content artifacts before using them for M3 span checks or
M4 mapping work:

```sh
sha256sum -c m3_unified_source_corpus/SHA256SUMS
```

- Corpus version: `openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864`
- Coordinate owner: M3 records chapter-local spans; normalization binds them to
  the unified prepared corpus.
