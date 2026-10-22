# M3 Gold v0.1.3

## Release

- Final file: `gold_v0_1_3.jsonl`
- Gold annotation version: `m3_gold_v0.1.3`
- Previous final record count: 344
- Current final record count: 341
- Evidence span count: 352

## Deterministic exclusions

The following accepted candidates were excluded from the release:

- `sciq-validation-00752`: The accepted evidence comes from an AP edition Chapter 9 figure annotation, associated with a block ID ending in `_ch09_p0434_b002`. This evidence block is unavailable in the M4 corpus.
- `sciq-train-01792`: The accepted evidence comes from the CK-12 "Problem Solving 1" subsection, associated with a block ID ending in `_p0092_b800`. The M4 corpus does not include this exercise subsection.
- `sciq-train-07669`: The accepted evidence also comes from the CK-12 "Problem Solving 1" subsection, associated with a block ID ending in `_p0092_b800`. The M4 corpus does not include this exercise subsection.

The source candidate CSV files were not modified.

## CK-12 offset correction

- CK-12 evidence spans inspected: 82
- CK-12 offset pairs changed: 81
- CK-12 offset pairs already correct: 1
- Every remaining CK-12 span now has `char_start == chapter_char_start` and `char_end == chapter_char_end`.
- Evidence text, block IDs, document IDs, chapter IDs, and provenance were preserved.
- OpenStax evidence offsets changed: 0

## Validation

- JSONL parsing: passed
- Gold schema validation: passed
- Evidence provenance validation: passed
- Unique question IDs: passed
- Unique span IDs: passed
- Regression comparison: passed; only the three exclusions, CK-12 offset corrections, and version update changed the release.
- Corpus versions and parser versions: preserved.

## Audit artifacts

- `gold_review_audit_v0_1_3.jsonl`
- `gold_integration_conflicts_v0_1_3.csv`
- `gold_validation_report_v0_1_3.json`
