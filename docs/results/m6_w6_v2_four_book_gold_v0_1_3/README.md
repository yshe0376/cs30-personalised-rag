# M6 W6 four-book retrieval results

These files are from the clean shared-retriever run recorded in
`run_manifest.json`.
The run uses `cs30.pipeline.build_real_retrieval_deps`, all nine pinned model
revisions, `rrf_input_top_k=20`, and the Qwen3 `query` prompt.

The original-query 64-configuration Dev sweep's metric winner is reported
separately from the system retriever. The clean joint rerun ranks Qwen3 Hybrid
Dense 0.10 / BM25 0.90 first with 400/546 Complete Hit@5. BGE-M3 Hybrid Dense
0.10 / BM25 0.90 ranks second with 399/546 and remains the team-selected system
retriever for the M7 handoff. This is a documented operational choice, not a
claim of metric or statistical superiority.

The earlier per-query-set baseline-replacement check remains as a descriptive
comparison. Against original-query BM25 (215/273 complete Hit@5, MRR 0.5750),
BGE Base has exact paired McNemar `p=0.25` and lower MRR. The separate BGE-M3
comparison has `p=0.7539`. Neither establishes statistical superiority; system
selection is controlled by the joint robustness table instead. Both descriptive
rows remain in `dev_baseline_comparison.csv`.

With `rrf_k=60` and `rrf_input_top_k=20`, all tested Hybrid configurations with
Dense weight at most 0.25 satisfy `dense_weight / 61 < bm25_weight / 80`. When
BM25 returns 20 candidates, a Dense-only chunk therefore cannot enter the fused
top 10. These low-Dense configurations mainly use Dense overlap to rerank the
BM25 top-20 candidate set rather than introduce new Dense-only chunks.

The 68-question holdout was exposed to all configurations in a superseded run,
so it is diagnostic rather than a clean final Test. This corrected run evaluates
only BM25 and the BGE-M3 system retriever there. BM25 reaches 51/68 complete
Hit@5 with MRR 0.4846; BGE-M3 reaches 46/68 complete Hit@5 (47/68 ordinary
Hit@5) with MRR 0.4645. These numbers cannot be used to select or retune the
model. A final paper result requires a new, team-approved untouched Test split.

Files:

- `dev_summary.csv` / `dev_overall_ranked.csv`: all 64 Dev configurations.
- `dev_grouped_summary.csv`: Dev results grouped by textbook, provider and
  evidence scope.
- `dev_baseline_comparison.csv`: separate paired comparisons for the per-set Dev
  metric winner and the jointly selected system retriever.
- `dev_rule1_selection.csv`: all 64 configurations ranked on combined original
  and para-v1 Dev Complete Hit@5, with mean MRR as the tie-breaker.
- `dev_paired_bm25_vs_bge_m3_summary.csv`: exact McNemar and bootstrap MRR
  comparisons for BM25 versus BGE-M3 0.10/0.90 on both query sets.
- `dev_paired_bm25_vs_bge_m3_questions.csv`: the 1,092 paired
  question/configuration rows underlying those comparisons.
- `diagnostic_holdout_summary.csv`: exactly two diagnostic holdout rows.
- `truncation_diagnostics.csv`: tokenizer-length diagnostics for all nine models.
- `evaluation_split_assignments.jsonl`: deterministic 273/68 assignments.
- `gold_span_bindings.jsonl`: 352 verified evidence-to-chunk bindings.
- `run_manifest.json`: hashes, Git state, model revisions, and method provenance.

Large per-question metrics, candidate hits, indexes, and source ZIPs are kept
outside Git. No `proposed_test_all_*` output is generated.
