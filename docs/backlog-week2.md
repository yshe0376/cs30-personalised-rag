# Week 2 Retrieval Backlog

This backlog records the remaining retrieval tasks that depend on the labelled
evaluation set or additional CI fixtures.

## Current Status

The following work has already been completed:

- Real BM25, Dense and Hybrid RRF retrieval implementations.
- Query-side BM25 stopword filtering.
- Configurable BM25 and Dense score thresholds.
- Mode-aware real retrieval service.
- Index artifact, chunk-map and FAISS consistency validation.
- Unit tests for BM25 abstention, Dense filtering, RRF fusion, caching and
  pipeline mode selection.
- A real-mode BM25 CI assertion for an out-of-scope question.

The current retrieval regression test file contains 22 tests. The complete
repository test suite currently contains 125 passing tests.

## RET-01: Calibrate the Dense Abstention Threshold

**Priority:** High  
**Owner:** Member 6  
**Status:** Blocked until the labelled evaluation set is available

### Objective

Calibrate `dense_min_similarity` using answerable and unanswerable evaluation
questions. The threshold must improve refusal behaviour without causing an
unacceptable reduction in retrieval recall.

### Dependencies

- Final or provisional educational corpus.
- Gold evidence labels.
- Answerable and unanswerable questions.
- A validation/test split.
- Confirmed embedding model and index version.

### Tasks

- [ ] Confirm the evaluation-set format and version.
- [ ] Separate the questions into validation and test sets.
- [ ] Run Dense retrieval with `dense_min_similarity=None`.
- [ ] Record similarity scores for relevant and irrelevant results.
- [ ] Sweep candidate thresholds on the validation set.
- [ ] Calculate Hit@K, Recall@K and MRR for answerable questions.
- [ ] Calculate abstention precision, recall and F1.
- [ ] Select and freeze the threshold before final testing.
- [ ] Run the frozen configuration on the test set.
- [ ] Add the selected value and results to `RAG优化旋钮清单.md`.
- [ ] Record the final configuration in the project report.

### Acceptance Criteria

- The threshold is selected using the validation set only.
- Both answerable and unanswerable questions are represented.
- The unfiltered Dense baseline is reported.
- Retrieval and abstention metrics are reported separately.
- The selected threshold and evaluation-set version are reproducible.
- No fixed accuracy target is claimed without literature or experimental
  support.

## RET-02: Extend Real-Mode CI Abstention Coverage

**Priority:** High  
**Owner:** Member 6  
**Status:** Pending

### Objective

Extend the existing real-mode BM25 abstention assertion to Dense and Hybrid
retrieval so that all retrieval modes preserve the no-evidence refusal
behaviour.

### Tasks

- [ ] Add a deterministic Dense test fixture that requires no network access,
  external API or model download.
- [ ] Add a real-mode Dense test in which all candidate scores fall below the
  configured threshold.
- [ ] Assert that the Dense retrieval result contains no hits.
- [ ] Assert that the generated answer has `abstained=True`.
- [ ] Add a Hybrid test in which both BM25 and Dense return no evidence.
- [ ] Assert that the Hybrid RRF result contains no hits.
- [ ] Assert that abstention is preserved through the complete pipeline.
- [ ] Add the Dense and Hybrid assertions to the CI smoke job.
- [ ] Confirm that the CI tests remain deterministic and offline.

### Acceptance Criteria

The Dense CI assertion must verify:

```python
assert result["mode"] == "real"
assert result["retrieval"]["mode"] == "dense"
assert result["retrieval"]["hits"] == []
assert result["answer"]["abstained"] is True
assert result["answer"]["citations"] == []
```

The Hybrid CI assertion must verify:

```python
assert result["mode"] == "real"
assert result["retrieval"]["mode"] == "hybrid"
assert result["retrieval"]["hits"] == []
assert result["answer"]["abstained"] is True
assert result["answer"]["citations"] == []
```

## RET-03: Record Final Retrieval Ablation Results

**Priority:** Medium  
**Owner:** Member 6  
**Status:** Pending completion of RET-01

### Tasks

- [ ] Compare BM25, Dense and Hybrid RRF on the same evaluation set.
- [ ] Keep the corpus, question set and `top_k` fixed during comparison.
- [ ] Report Hit@K, Recall@K and MRR separately.
- [ ] Report answerable and unanswerable results separately.
- [ ] Record all retrieval configuration values.
- [ ] Add limitations and error examples to the Overleaf report.

## Deferred Decisions

The following decisions must not be finalised until evaluation evidence is
available:

- The production value of `dense_min_similarity`.
- Whether Hybrid RRF performs better than both individual retrievers.
- Whether BM25 or Dense should be the default retrieval mode.
- Whether additional reranking is necessary.
- Whether Dense and Hybrid CI should use a packaged FAISS artifact or injected
  deterministic test doubles.