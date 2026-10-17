# V2 批量生成运行报告

开发实验，reportable=false。生成产物交给 M8 独立评分。

预定 1944 个实验单元，保存 1944 个。Role 候选覆盖完整：True。

| 条件 | 等级 | 预定 | 回答 | 拒答 | 技术失败 | 输出截断 | 模型调用 |
|---|---|---:|---:|---:|---:|---:|---:|
| P0R0_plain | beginner | 162 | 162 | 0 | 0 | 0 | 162 |
| P0R0_plain | intermediate | 162 | 162 | 0 | 0 | 0 | 162 |
| P0R0_plain | advanced | 162 | 162 | 0 | 0 | 0 | 162 |
| P1R0_prompt_only | beginner | 162 | 162 | 0 | 0 | 0 | 162 |
| P1R0_prompt_only | intermediate | 162 | 162 | 0 | 0 | 0 | 162 |
| P1R0_prompt_only | advanced | 162 | 162 | 0 | 0 | 0 | 163 |
| P0R1_reranking_only | beginner | 162 | 162 | 0 | 0 | 0 | 162 |
| P0R1_reranking_only | intermediate | 162 | 162 | 0 | 0 | 0 | 163 |
| P0R1_reranking_only | advanced | 162 | 162 | 0 | 0 | 0 | 162 |
| P1R1_combined | beginner | 162 | 162 | 0 | 0 | 0 | 163 |
| P1R1_combined | intermediate | 162 | 162 | 0 | 0 | 0 | 162 |
| P1R1_combined | advanced | 162 | 162 | 0 | 0 | 0 | 163 |

耗时、用量及引用数量见 generation_summary.json；完整证据和原始模型输出见 generation_records.jsonl。引用 ID 有效不等于证据语义支持；本报告不测量学生等级适配质量，也不自动批准正式结论。
