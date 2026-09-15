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

Rebuild the local handoff from the M4 chapter archive when needed:

```sh
cs30-evaluate prepare-corpus \
  --archive artifacts/w5/m4/source_corpus/data.zip \
  --output-dir m3_unified_source_corpus/source_corpus
```

Verify the rebuilt files against `SHA256SUMS` before using them for M3 span
checks or M4 mapping work.

- Corpus version: `openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864`
- Coordinate owner: M3 records chapter-local spans; normalization binds them to
  the unified prepared corpus.
