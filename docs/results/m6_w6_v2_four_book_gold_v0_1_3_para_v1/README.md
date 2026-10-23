# M6 W6 para-v1 retrieval robustness results

This directory contains the lightweight outputs from the para-v1 query rerun.
The run changes only the question wording: the four-book corpus, 341 question
IDs, evidence bindings, models, pinned revisions, shared BM25/RRF retriever,
six Hybrid weights, and deterministic 273/68 assignment remain unchanged.

The para-v1 Gold file is pinned to SHA-256
`57ca94918912df01d8d66e6e9e7fed95b3faf4e6dd4254428b349823a3623696`.
It changes 336 question strings and leaves all non-question Gold fields aligned
with the original query set.

The joint ranking uses combined original-plus-para-v1 Dev Complete Hit@5, with
question-count-weighted mean MRR as a tie-breaker. Qwen3 Hybrid Dense 0.10 /
BM25 0.90 ranks first with 400/546 Complete Hit@5 and is therefore the system
retriever exported for the M7 handoff. BM25 remains the historical reference;
no statistical-superiority claim is made from the exposed holdout.

The 68-question split is already exposed and is therefore a diagnostic holdout,
not a clean final Test. Only BM25 and the selected Qwen3 system retriever are
evaluated on it.

Files:

- `dev_summary.csv` / `dev_overall_ranked.csv`: all 64 para-v1 Dev configurations.
- `dev_grouped_summary.csv`: grouped para-v1 Dev results.
- `dev_rule1_selection.csv`: joint original/para-v1 ranking for all 64 configurations.
- `dev_paired_bm25_vs_qwen3_summary.csv`: paired significance and MRR intervals.
- `dev_paired_bm25_vs_qwen3_questions.csv`: 1,092 supporting paired rows.
- `diagnostic_holdout_summary.csv`: BM25 and Qwen3 only on the exposed holdout.
- `evaluation_split_assignments.jsonl`: deterministic assignments.
- `gold_span_bindings.jsonl`: verified evidence bindings.
- `run_manifest.json`: hashes, clean Git state, model revisions, and method provenance.

Large candidate lists, indexes, and source archives remain outside Git.
