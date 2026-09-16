# M5 Official FAISS Index Comparison

All models were indexed using the latest frozen M4 retrieval corpus containing 3,684 chunks.

| Model | Dimension | Build Time (s) | Effective Content Limit | Over-limit Chunks | Reload |
|---|---:|---:|---:|---:|---|
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 94.19 | 254 | 1446 | Passed |
| sentence-transformers/all-mpnet-base-v2 | 768 | 726.93 | 382 | 1056 | Passed |
| intfloat/e5-base-v2 | 768 | 783.20 | 510 | 314 | Passed |
| BAAI/bge-base-en-v1.5 | 768 | 782.31 | 510 | 314 | Passed |
| BAAI/bge-m3 | 1024 | 3143.49 | Long-context | 0 over-limit warning observed | Passed |

All indexes use FAISS Flat Inner Product with L2-normalised embeddings.

The latest retrieval corpus contains 3,684 chunks. The maximum recorded chunk length is 688 tokens, with a mean of 237.54 tokens and a median of 179 tokens.

MiniLM and MPNet have shorter effective input limits and therefore truncate a larger number of long chunks. E5 and BGE-base reduce the truncation risk, but 314 chunks still exceed their effective 510-token content limit.

BGE-M3 was added as a long-context candidate. It successfully indexed and reloaded all 3,684 chunks without an over-limit warning. However, it required substantially more build time and local compute resources than the other models.

Final model selection should be based on retrieval effectiveness using the latest Gold Evidence, including Hit@K, Recall@K, and MRR, rather than build time or truncation alone.