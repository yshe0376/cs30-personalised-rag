# M6 W6 four-book retrieval results

The prior files in this directory were produced from a dirty worktree by a
notebook-local BM25/RRF implementation and are withdrawn. A replacement run
must use `cs30.pipeline.build_real_retrieval_deps`, all nine pinned model
revisions, `rrf_input_top_k=20`, and the Qwen3 `query` prompt from a clean
committed worktree.

Only Dev may be swept across models and Hybrid weights. The 68-question
holdout was exposed to all configurations in the superseded run, so it is
diagnostic rather than a clean final Test. Replacement outputs will contain
only BM25 and the Dev-selected Hybrid on that holdout; no
`proposed_test_all_*` files are permitted.
