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
| A2 | High | BM25 query stopword filtering | Disabled | Enabled | BM25 and Hybrid | Recall@K, MRR, out-of-scope abstention accuracy | Not configurable yet |
| A3 | High | Retrieval mode | BM25 | Dense and Hybrid RRF | All modes | Recall@K, Hit@K, MRR | Implemented |
| A4 | Medium | `bm25_min_score` | `0.0` | Validation-set calibrated value | BM25 and Hybrid | Recall@K, MRR, abstention accuracy | Configuration available |
| A5 | Medium | `rrf_k` | `60` | Validation-set alternatives | Hybrid | Recall@K, MRR | Configuration available |
| A6 | Medium | `rrf_input_top_k` | `20` | Validation-set alternatives | Hybrid | Recall@K, MRR and latency | Configuration available |
| A7 | Low | Final returned `top_k` | Configured default | Candidate values such as 3, 5 and 10 | All modes | Hit@K, Recall@K, MRR and latency | Configuration available |

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
- Validation of chunk-map positions, identifiers and item counts.
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
- Hit@K, Recall@K and MRR.
- Abstention precision, recall and F1 where unanswerable questions are included.

No parameter should be described as an improvement unless it is compared with
the corresponding baseline on the same evaluation set.