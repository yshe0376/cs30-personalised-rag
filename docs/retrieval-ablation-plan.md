# RAG Optimisation Knob Checklist

This document records the retrieval parameters that may affect retrieval quality,
ranking quality, and abstention behaviour. Each parameter must be evaluated
through a controlled ablation rather than selected arbitrarily.

A star (★) marks a high-priority parameter that requires calibration before the
final evaluation.

## Retrieval Ablation Table

| ID | Priority | Parameter | Baseline | Comparison | Applicable Modes | Evaluation Metrics | Status |
|---|---|---|---|---|---|---|---|
| A1 | ★ | `dense_min_similarity` | `None` (disabled) | A threshold calibrated on the validation set | Dense and Hybrid | Recall@K, MRR, abstention precision, abstention recall, abstention F1 | Pending evaluation dataset |
| A2 | High | BM25 query stopword filtering | Disabled | Enabled | BM25 and Hybrid | Recall@K, MRR, out-of-scope abstention accuracy | Configuration available (`retrieval.bm25_stopwords`) |
| A3 | High | Retrieval mode | BM25 | Dense and Hybrid RRF | All modes | Recall@K, Hit@K, MRR | Four-book Dev: BGE-M3 Hybrid reaches 216/273 vs BM25 213/273 complete Hit@5, but MRR is 0.5703 vs 0.5729; BM25 remains the baseline under the replacement rule |
| A4 | Medium | `bm25_min_score` | `0.0` | Validation-set calibrated value | BM25 and Hybrid | Recall@K, MRR, abstention accuracy | Configuration available |
| A5 | Medium | `rrf_k` | `60` | Validation-set alternatives | Hybrid | Recall@K, MRR | Configuration available |
| A6 | Medium | `rrf_input_top_k` | `20` | Validation-set alternatives | Hybrid | Recall@K, MRR and latency | Configuration available |
| A7 | Low | Final returned `top_k` | Configured default | Candidate values such as 3, 5 and 10 | All modes | Hit@K, Recall@K, MRR and latency | Configuration available |
| A8 | Medium | Weighted RRF | BM25 | Dense weights `0.05`, `0.10`, `0.20`, `0.25`, `0.50`, `0.75` | Hybrid | Hit@K, Recall@K and MRR | Six weights evaluated on four-book Dev; BGE-M3 `0.10/0.90` is the diagnostic lexicographic winner but does not replace BM25 because MRR decreases |
| A9 | High | Embedding model | BM25 | Nine pinned dense models, including M5 BGE-M3, GTE-ModernBERT and Qwen3 | Dense and Hybrid | Hit@K, Recall@K, MRR, truncation diagnostics | W6: revisions pinned and propagated through custom loaders; source and copied FAISS hashes validated; Qwen3 query prompt recorded |

## Dense Similarity Threshold

`dense_min_similarity` controls whether a dense retrieval result is sufficiently
similar to the query to be retained.

The default value is `None`, which disables similarity filtering. This is
intentional because a threshold must not be selected before the evaluation set
is available.

The setting is exposed through:

- Configuration field: `RetrievalConfig.dense_min_similarity`
- Environment variable: `CS30_DENSE_MIN_SIMILARITY`
- Dense retriever argument: `FaissDenseRetriever(min_similarity=...)`

The valid range is from `-1.0` to `1.0`. When enabled, a dense hit with a score
below the configured threshold is removed before ranks are assigned.

In Hybrid mode, the threshold applies only to the Dense candidate list before
RRF fusion. The RRF calculation itself remains unchanged.

## Dev and Test separation

The current M6 W6 four-book experiment uses Golden Evidence v0.1.3 with 341
answerable questions. It deterministically derives 273 Dev and 68 stratified
Test questions while keeping questions that share a rebound evidence chunk in
the same split. The split has zero exact-evidence overlap. Model and weight
comparisons use Dev. The notebook's diagnostic lexicographic rule (complete
evidence Hit@5 followed by MRR) identifies BGE-M3 Hybrid with Dense 0.10 / BM25
0.90, and records that candidate on the 68-question Test split.

The baseline replacement rule remains stricter: replace BM25 only if a Dev
candidate improves complete Hit@5, does not reduce MRR, and passes an exact
paired McNemar test at `p < 0.05`. On four-book Dev, BGE-M3 improves complete
Hit@5 from 213/273 to 216/273 but reduces MRR from 0.5729 to 0.5703, so it does
not replace BM25 as the baseline. The all-model Test table is exploratory and
must not be used to retune or override this rule.

The four-book corpus remains `reportable=false`, Golden Evidence annotations
remain `draft`, and the derived 273/68 split is reproducible but not an approved
frozen release split. The earlier 162/26 three-book result remains historical
and is not the current M6 W6 comparison.

## Calibration Procedure

The threshold will be calibrated after the evaluation questions and gold
evidence are available.

1. Divide the labelled questions into validation and test sets.
2. Include both answerable and unanswerable questions.
3. Run Dense retrieval with threshold filtering disabled.
4. Record the similarity scores for relevant, irrelevant and unanswerable
   queries.
5. Compare candidate thresholds using the validation set only.
6. Measure retrieval quality using Hit@K, Recall@K and MRR.
7. Measure refusal behaviour using abstention precision, recall and F1.
8. Select a threshold that improves refusal behaviour without causing an
   unacceptable reduction in recall for answerable questions.
9. Freeze the selected threshold before running the final test set.
10. Report both the unfiltered baseline and calibrated result.

The test set must not be used to select the threshold.

## Current Safeguards

The current retrieval implementation includes:

- BM25 query-side stopword filtering.
- Empty results when a BM25 query contains only stopwords.
- A configurable BM25 minimum score.
- An optional Dense similarity threshold.
- Rejection of unsupported index artifact types.
- Validation of FAISS vector count and embedding dimension.
- Validation of the source and copied FAISS payload against the v2 artifact's
  declared SHA-256.
- Validation of chunk-map positions, identifiers and item counts.
- Propagation of pinned model revisions and `trust_remote_code` through both
  default and injected model loaders.
- Rejection of empty queries and non-positive `top_k` values.
- RRF abstention propagation when both retrieval branches return no evidence.
- Defensive copying of cached retrieval results.

## Reporting Requirement

Every reported ablation result should record:

- Retrieval mode.
- Dataset or corpus version.
- Evaluation-set version.
- Embedding model.
- `top_k`.
- `dense_min_similarity`.
- `bm25_min_score`.
- `rrf_k`.
- `rrf_input_top_k`.
- `rrf_dense_weight` and `rrf_bm25_weight`.
- Hit@K, Recall@K and MRR.
- Abstention precision, recall and F1 where unanswerable questions are included.

No parameter should be described as an improvement unless it is compared with
the corresponding baseline on the same evaluation set.
