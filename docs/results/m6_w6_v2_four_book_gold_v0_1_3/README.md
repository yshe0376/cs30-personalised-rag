# M6 W6 four-book retrieval results

These lightweight files come from the completed nine-model run recorded in
`run_manifest.json`:

- `dev_summary.csv`: all 64 Dev configurations.
- `dev_grouped_summary.csv`: Dev results grouped by source and question traits.
- `proposed_holdout_summary.csv`: the Dev-selected frozen configuration on Test.
- `proposed_test_all_summary.csv`: exploratory all-model Test comparison.
- `evaluation_split_assignments.jsonl`: deterministic 273/68 assignment.
- `gold_span_bindings.jsonl`: all 352 verified evidence-to-chunk bindings.

The notebook's diagnostic ranking rule was complete evidence Hit@5 followed by
MRR. It identified BGE-M3 with Dense 0.10 / BM25 0.90 on Dev. The diagnostic
68-question Test result has MRR 0.4715, Hit@1 27.9%, Hit@3 64.7%, Hit@5 70.6%,
and Hit@10 80.9%.

This does not replace the repository's BM25 baseline. BGE-M3 improves Dev
complete Hit@5 from 213/273 to 216/273 but reduces Dev MRR from 0.5729 to
0.5703, so it fails the stricter baseline-replacement gate.

The `proposed_test_all_*` files are exploratory audit outputs and must not be
used to replace the Dev-selected frozen configuration. Large per-question model
metrics, candidate hits, indexes, and source ZIPs are intentionally excluded
from Git.

This experiment is diagnostic (`reportable=false`); see `run_manifest.json` for
the exact corpus, Gold, model, split, index, and method provenance.
