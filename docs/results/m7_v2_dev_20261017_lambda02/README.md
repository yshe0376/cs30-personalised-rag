# M7 V2 完整 Dev 实验结果：2026-10-17，λ=0.2

**162 题 × 3 个等级 × 4 个条件 = 1,944 个单元全部成功回答**，零技术失败、零输出截断。
本次完整生成已于悉尼时间 2026-10-17 17:06:19 结束，`reportable=false`。
答案正确性、证据语义支持和学生等级适配仍待 M8 独立评分；生成成功率不等于正确率。

## 查看和下载

- [生成报告](generation_report.md) / [运行摘要](generation_summary.json)。
- [全部保存答案](saved_answers.jsonl)：1,944 条，保留原始字节。
- [预定矩阵](expected_experiment.json) / [运行清单](run_manifest.json)。
- [Dev 参数选择](lambda_selection.json) / [执行摘要](execution_metadata.json)。
- [运行核查](verification.json) / [交付核查](delivery_verification.json)。
- [完整归档（GitHub pre-release）](https://github.com/yshe0376/cs30-personalised-rag/releases/download/v2-m7-dev-20261017-lambda02/m7_v2_dev_20261017_lambda02.tar.gz)：约 13.2 MiB，
  包含冻结输入、全部原始生成记录、1,944 个逐单元检查点及执行日志。
- [归档文件清单](archive_inventory.json) / [下载摘要](release_asset.json) / [交付文件 SHA-256](SHA256SUMS)。

## 实际运行

| 项目 | 本次值 |
|---|---|
| 冻结代码 | `78d73902ba8cce82dc29d34eb12a46ac69fc0cca` |
| 生成模型 | 本机 Ollama `gpt-oss:20b` |
| 模型权重 SHA-256 | `17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7` |
| 开始 / 完成 | 2026-10-17 13:47:12 / 17:06:19，Australia/Sydney（UTC+11） |
| 总耗时 / 续跑 | 约 3 小时 19 分钟 / 0 次 |
| 上下文 / 最大输出 | 32,768 / 2,048 token |
| 温度 / seed / 超时 | 0 / 0 / 180 秒 |
| 单元修复重试 | 最多 1 次 |
| 检索候选 / 证据 | 同一冻结 BM25 top-20 / top-5 |
| λ / profile confidence | Dev 选择的 0.2 / 控制输入 1.0 |
| Role 覆盖 | 2,242 个唯一 Dev 候选全部有标签 |
| 模型调用 | 1948 次，包含重试；所有原始尝试均保留 |
| 最终状态 | answered=1944；technical_failures=0；output_truncated=0 |

四条件为 `P0R0_plain`、`P1R0_prompt_only`、`P0R1_reranking_only`、`P1R1_combined`；
三个等级为 beginner、intermediate、advanced。12 个分组各有 162 条成功答案。
V3 提示词使用 E1–E5 短引用，保存记录包含短编号到完整 chunk ID 的映射。
四次首次输出因 token 预算截断，修复重试后全部成功；原始截断尝试保存在完整生成记录中。
表中的零输出截断指最终单元状态，并不抹去中间尝试。

λ 只在 Dev 选择：取完整证据命中率不低于零基线减 1 个百分点的最大正候选。
λ=0.2 的选择指标为 0.820988，零基线为 0.827160；这是检索证据命中指标。
完整运行使用此前冻结的同一输入，没有根据本轮生成答案重新调参，没有新增 Test 生成。

## 完整性与复现

原始输入、输出及检查点保持原字节，未手动修补答案。交付前逐项检查了输入/输出摘要、
冻结代码与提交的对应关系、全部矩阵 ID、检查点 payload 摘要、答案和完整记录的一致性、
引用集合以及压缩包内每个文件的 SHA-256。日志中的本机任务目录前缀替换为 `${RUN_DIR}`。
归档不含代码检出目录、`.git`、模型权重或本机进程状态。

在本目录检查可浏览文件：

```bash
shasum -a 256 -c SHA256SUMS
```

完整归档 SHA-256：`2302abaa1452050e576c8aa368e66874c25cc9535b08a55096069dc003800ef2`。下载链接及字节数见 `release_asset.json`。
解压后结构为 `inputs/`、`output/`、`logs/`、`verification.json`、`execution_metadata.json`。
复现时检出上述代码提交，使用相同模型权重和冻结参数，按 [M7 生成说明](../../v2-member7-experiments.md)
执行 `check` 与 `run`；本轮代码已经与评分解耦，M8 可以直接接收保存答案和完整记录。

## 来源与适用范围

Gold 来源为团队 M3 v0.1.2；冻结快照保留 188 题和来源信息，本次矩阵仅使用暂定 Dev 的 162 题。
`pending → dev`、`proposed_test → test` 的显式转换保存在归档 `inputs/gold_conversion.json`。
参考答案与 Gold 标注不进入生成提示词；暂定划分不构成正式 Gold/Test 批准。
Role 包主要由模型标注，未完成独立人工验证。

证据来自 [M4 V2 开发语料](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m4-structure-v2-dev-v1)，
版本 `2.0.0-dev.m4-structure-v2-main-3553825`；Role 来源为
[V2 Role 开发包](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-role-labels-v2-dev-v1)。
教材引文遵循原 corpus manifest 和 M4 声明的 CC BY 4.0 许可，原作者及出版方署名继续适用。
教材由 OpenStax 发布：[College Physics 2e](https://openstax.org/details/books/college-physics-2e)、
[College Physics for AP Courses 2e](https://openstax.org/details/books/college-physics-ap-courses-2e)、
[Physics](https://openstax.org/details/books/physics)。教材引文未改写。

[前一轮 λ=0 结果](../m7_v2_dev_20261016/README.md)和
[12 格接线验收](../m7_v2_readiness_20261017/README.md)保留为历史记录；本目录是后续完整 λ=0.2 运行。
独立评分实现交由 [M8 PR #191](https://github.com/yshe0376/cs30-personalised-rag/pull/191) review，本交付没有运行 judge 或人工评分。
