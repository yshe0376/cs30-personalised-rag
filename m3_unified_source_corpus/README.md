# M3 unified source-corpus handoff

Delivery date: 2026-09-13

Use `source_corpus/openstax_document.json` as the single 34-chapter source
document. Do not load the 34 per-chapter documents as separate documents: they
share one document identity and can overwrite one another downstream.

The companion manifest records the chapter order, separator, source identity,
and corpus version. Verify every file against `SHA256SUMS` before use.

- Corpus version: `openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864`
- Coordinate owner: M3 retains semantic annotations; normalization binds the
  original chapter-local spans to this unified corpus.
