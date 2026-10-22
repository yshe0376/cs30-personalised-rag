# M6 W6 four-book retrieval results

These files are from the clean shared-retriever run recorded in
`run_manifest.json` at commit `68521494358b970505ec1f7ab7696d9a4b8abdd7`.
The run uses `cs30.pipeline.build_real_retrieval_deps`, all nine pinned model
revisions, `rrf_input_top_k=20`, and the Qwen3 `query` prompt.

The 64-configuration Dev sweep's metric winner is BGE Base Hybrid with Dense
0.05 / BM25 0.95: 218/273 complete Hit@5 with MRR 0.5696. The team selected
BGE-M3 Hybrid with Dense 0.10 / BM25 0.90 as the provisional retriever for the
downstream generator evaluation. BGE-M3 reaches 217/273 complete Hit@5 and
218/273 ordinary Hit@5 with MRR 0.5459. Against BM25 (215/273 complete Hit@5,
MRR 0.5750), its paired McNemar result is `p=0.7539`; it does not pass the
preregistered replacement rule, so BM25 remains the formal baseline. The
manifest records the distinction between the metric winner and the provisional
team-selected candidate.

The 68-question holdout was exposed to all configurations in a superseded run,
so it is diagnostic rather than a clean final Test. This corrected run evaluates
only BM25 and provisional BGE-M3 there. BM25 reaches 51/68 complete Hit@5 with
MRR 0.4846; BGE-M3 reaches 46/68 complete Hit@5 (47/68 ordinary Hit@5) with MRR
0.4645. These numbers cannot be used to select or retune the model. A final
paper result requires a new, team-approved untouched Test split.

Files:

- `dev_summary.csv` / `dev_overall_ranked.csv`: all 64 Dev configurations.
- `dev_grouped_summary.csv`: Dev results grouped by source and question traits.
- `dev_baseline_comparison.csv`: paired baseline-replacement decision.
- `diagnostic_holdout_summary.csv`: exactly two diagnostic holdout rows.
- `truncation_diagnostics.csv`: tokenizer-length diagnostics for all nine models.
- `evaluation_split_assignments.jsonl`: deterministic 273/68 assignments.
- `gold_span_bindings.jsonl`: 352 verified evidence-to-chunk bindings.
- `run_manifest.json`: hashes, Git state, model revisions, and method provenance.

Large per-question metrics, candidate hits, indexes, and source ZIPs are kept
outside Git. No `proposed_test_all_*` output is generated.
