# M6 W6 four-book retrieval results

These files are from the clean shared-retriever run recorded in
`run_manifest.json`.
The run uses `cs30.pipeline.build_real_retrieval_deps`, all nine pinned model
revisions, `rrf_input_top_k=20`, and the Qwen3 `query` prompt.

The clean joint rerun ranks Qwen3 Hybrid Dense 0.10 / BM25 0.90 first with
400/546 Complete Hit@5. The preregistered joint Dev rule therefore selects that
same Qwen3 configuration as the system retriever for the M7 handoff. This is a
Dev selection, not a claim of statistical superiority on a clean final Test.

The earlier per-query-set baseline-replacement check remains as a descriptive
comparison. Against original-query BM25 (215/273 complete Hit@5, MRR 0.5750),
BGE Base has exact paired McNemar `p=0.25` and lower MRR. The separate Qwen3
comparison is descriptive: Qwen3 records 216/273 complete Hit@5 versus BM25's
215/273, with MRR 0.5565 versus 0.5750 and exact McNemar `p=1.0`. System
selection is controlled by the joint Dev robustness table. Both descriptive
rows remain in `dev_baseline_comparison.csv`.

With `rrf_k=60` and `rrf_input_top_k=20`, all tested Hybrid configurations with
Dense weight at most 0.25 satisfy `dense_weight / 61 < bm25_weight / 80`. When
BM25 returns 20 candidates, a Dense-only chunk therefore cannot enter the fused
top 10. These low-Dense configurations mainly use Dense overlap to rerank the
BM25 top-20 candidate set rather than introduce new Dense-only chunks.

The 68-question holdout was exposed to all configurations in a superseded run,
so it is diagnostic rather than a clean final Test. This corrected run evaluates
only BM25 and the Qwen3 system retriever there. The exact rerun values are in
`diagnostic_holdout_summary.csv`: BM25 reaches 51/68 complete Hit@5 with MRR
0.4846; Qwen3 reaches 49/68 with MRR 0.4673. They cannot be used to select or
retune the model. A final paper result requires a new, team-approved untouched
Test split.

Files:

- `dev_summary.csv` / `dev_overall_ranked.csv`: all 64 Dev configurations.
- `dev_grouped_summary.csv`: Dev results grouped by textbook, provider and
  evidence scope.
- `dev_baseline_comparison.csv`: separate paired comparisons for the per-set Dev
  metric winner and the jointly selected system retriever.
- `dev_rule1_selection.csv`: all 64 configurations ranked on combined original
  and para-v1 Dev Complete Hit@5, with mean MRR as the tie-breaker.
- `dev_paired_bm25_vs_qwen3_summary.csv`: exact McNemar and bootstrap MRR
  comparisons for BM25 versus Qwen3 0.10/0.90 on both query sets.
- `dev_paired_bm25_vs_qwen3_questions.csv`: the 1,092 paired
  question/configuration rows underlying those comparisons.
- `diagnostic_holdout_summary.csv`: exactly two diagnostic holdout rows.
- `truncation_diagnostics.csv`: tokenizer-length diagnostics for all nine models.
- `evaluation_split_assignments.jsonl`: deterministic 273/68 assignments.
- `gold_span_bindings.jsonl`: 352 verified evidence-to-chunk bindings.
- `m7_qwen3_d0.10_b0.90_original_top20_manifest.json`: manifest and hashes for
  the strict v2 M7 candidate-file release asset.
- `run_manifest.json`: hashes, Git state, model revisions, and method provenance.

Large per-question metrics, candidate hits, indexes, and source ZIPs are kept
outside Git. The strict Qwen3 Top-20 candidate JSONL, its manifest, and the M5
index ZIP are published in the development prerelease
[`m6-w6-qwen3-hybrid-dev-v1`](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/m6-w6-qwen3-hybrid-dev-v1).
No `proposed_test_all_*` output is generated.
