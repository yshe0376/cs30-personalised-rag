# Topic map release 2.0.0-rc.1

This package publishes Topic Registry `topics-0.2` and a combined chunk-to-topic
map for the official, reportable four-book corpus `2.0.0-rc.1`.

## Files

- `chunk_topic_map_topics-0.2.json` is the runtime sidecar. It contains 4,486
  chunk assignments and 8,378 topic links.
- `topic_registry_v0.2.json` defines the 2,520 topic IDs used by the map.
- `topic_registry_freeze_manifest_v0.2.json` records the frozen registry
  provenance.
- `corpus_manifest_2.0.0-rc.1.json` binds the map to the official corpus hash.
- `topic_map_release_build_report.json` records source hashes, counts, and
  validation results.
- `topic_map_release_attestation.json` records the release decision and review
  scope.
- `sources/` contains the two source maps, the CK-12 M1 decisions, and the
  OpenStax labeling run report used to build the combined map.

The map is valid only for a corpus with the exact version and hash in the
manifest. No embedding index is included; the Topic map is a separately
versioned sidecar and does not change corpus or index identity.

## Rebuild and validate

From the repository root, with the matching official corpus available locally:

```powershell
python scripts/build_topic_map_release.py `
  --corpus-dir artifacts/v2/textbooks/2.0.0-rc.1 `
  --registry artifacts/v2/topics/releases/2.0.0-rc.1/topic_registry_v0.2.json `
  --source-map artifacts/v2/topics/releases/2.0.0-rc.1/sources/chunk_topic_map_openstax_source_v0.2.json `
  --source-map artifacts/v2/topics/releases/2.0.0-rc.1/sources/chunk_topic_map_ck12_m1_source_v0.2.json `
  --output-map artifacts/v2/topics/releases/2.0.0-rc.1/chunk_topic_map_topics-0.2.json `
  --report artifacts/v2/topics/releases/2.0.0-rc.1/topic_map_release_build_report.json
```

The builder requires an official, reportable corpus manifest, checks every
source chunk ID and topic ID, rejects overlapping chunk assignments, and
validates the resulting map against the corpus.
