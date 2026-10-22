# M6 W6 four-book retrieval results

These files are from the clean shared-retriever run recorded in
`run_manifest.json` at commit `8bf226c1876ed1ae0bc7463e553cda93938f4686`.
The run uses `cs30.pipeline.build_real_retrieval_deps`, all nine pinned model
revisions, `rrf_input_top_k=20`, and the Qwen3 `query` prompt.

The 64-configuration Dev sweep selected BGE Base Hybrid with Dense 0.05 / BM25
0.95 by complete-evidence Hit@5 followed by MRR. It reaches 218/273 complete
Hit@5 with MRR 0.5696, compared with BM25 at 215/273 and MRR 0.5750. The paired
McNemar result is `p=0.25`, so the candidate fails the preregistered replacement
rule and BM25 remains the baseline.

The 68-question holdout was exposed to all configurations in a superseded run,
so it is diagnostic rather than a clean final Test. This corrected run evaluates
only BM25 and the Dev-selected Hybrid there; both reach 51/68 complete Hit@5,
while BM25 has MRR 0.4846 and the Hybrid has MRR 0.4656. These numbers cannot be
used to select or retune the model. A final paper result requires a new,
team-approved untouched Test split.

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
