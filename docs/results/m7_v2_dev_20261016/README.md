# M7 V2 完整 Dev 实验结果：2026-10-16

本目录交付已经完成的 **162 题 × 3 个等级 × 4 个条件 = 1,944 个单元**。
1,930 条成功生成，14 条生成失败，原始失败记录全部保留。
这是开发实验，`reportable=false`；1,930 条答案的正确性仍待评分，正确率点估计为 null。
没有配置独立 judge，也没有实际人工评分。生成成功不等于答案正确。

## 直接查看

- [生成运行报告](generation_report.md)：按条件、等级汇总回答、失败和调用次数。
- [全部保存答案](saved_answers.jsonl)：1,944 条，包括 14 条技术失败。
- [失败详情](generation_failures.jsonl)：14 条失败的原始响应、每次尝试和允许引用的编号。
- [评分状态报告](scoring/open_answer_report.md) / [汇总 CSV](scoring/open_answer_summary.csv)。
- [运行清单](run_manifest.json) / [执行摘要](execution_metadata.json)：代码、输入、模型和输出指纹。
- [运行结束核查](verification.json) / [交付包核查](delivery_verification.json)。
- [完整压缩包](m7_v2_dev_20261016.tar.gz)：约 13 MiB，解压后包含冻结输入、完整原始
  生成记录、1,944 个断点文件、全部评分状态文件和四轮执行日志。
- [压缩包内文件清单](archive_inventory.json) / [交付文件 SHA-256](SHA256SUMS)。

评分器将 14 条生成失败按技术失败规则处理，因而汇总中有 `scored=14`；
它们不是已经完成真人评审的答案。其余 `needs_review=1930` 保持未决，不能把报告里的
`0 / eligible` 解读为整批模型的正确率为 0%。

## 实际运行配置

| 项目 | 本次值 |
|---|---|
| 运行代码 | `55e3f341b8b1a35a330911a2f3bdd7862dbca2e3` |
| 生成模型 | 本机 Ollama `gpt-oss:20b` |
| 模型权重摘要 | `17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7` |
| 上下文 / 最大输出 | 32,768 / 2,048 token |
| 温度 / 超时 | 0 / 180 秒 |
| 单元修复重试 | 最多 1 次；已保存失败不会在续跑时偷偷重试 |
| 候选 / 证据 | 同一冻结 BM25 top-20 候选，每个单元取 top-5 |
| Role 覆盖 | 2,242 个唯一 Dev 候选全部有标签，无缺项回退 |
| lambda / confidence | Dev 选择的 lambda=0 / 控制输入 confidence=1 |
| 模型调用 | 1,980 次，包括失败与修复尝试 |
| 开始 / 完成 | 2026-10-16 11:21:22 / 15:54:20，Australia/Sydney（UTC+11） |
| 断点恢复 | 3 次；已保存单元保留原值，未完成单元继续执行 |

四个条件分别为 `P0R0_plain`、`P1R0_prompt_only`、`P0R1_reranking_only`、
`P1R1_combined`，三个等级为 beginner / intermediate / advanced。
Dev 的证据命中目标选择了 lambda=0，因此 R0/R1 使用相同的检索顺序；
本结果不能支持重排带来改善的结论。Role 包主要由模型标注，未完成独立人工验证。
Rubric 仍为参考答案生成的草稿，尚未通过真人校准或团队冻结。

## 14 条失败

| 题目 ID | 失败单元数 |
|---|---:|
| `sciq-train-00953` | 1 |
| `sciq-train-02858` | 1 |
| `sciq-train-07169` | 2 |
| `sciq-train-10613` | 10 |

按最后一次尝试分类，8 条是引用不属于输入证据，6 条是 provider 返回空内容。
其中 `sciq-train-10613` 多次将长 chunk ID 缩短为不存在的 ID。
连续三条生成失败触发暂停后，检查原始响应，再使用相同代码、输入和模型参数续跑。
未改写或手动修补答案来使其通过。每次尝试的原文和错误均在完整记录与断点中。

## 获取与验证

在本目录运行（macOS/Linux）：

```bash
shasum -a 256 -c SHA256SUMS
```

在仓库根目录解压并检查冻结输入，不会调用模型：

```bash
mkdir -p artifacts/m7-v2-dev-20261016-delivery
tar -xzf docs/results/m7_v2_dev_20261016/m7_v2_dev_20261016.tar.gz \
  -C artifacts/m7-v2-dev-20261016-delivery
python -m cs30.v2.experiment_cli check \
  --prepared-dir artifacts/m7-v2-dev-20261016-delivery/inputs
```

压缩包结构为 `inputs/`、`output/`、`logs/`、`verification.json`、
`execution_metadata.json`。`archive_inventory.json` 逐文件记录解压字节数与 SHA-256。
交付时重新验证了冻结输入摘要、全部单元 ID 和断点摘要、答案及详细记录与断点的一致性、
运行输出摘要、评分分母，以及压缩后逐文件解压摘要。
输入与输出文件保留原始字节；日志中的本机任务目录前缀替换为 `${RUN_DIR}`。
个人工作目录、进程状态、`.git` 和模型权重不属于该数据包。

直接浏览的答案、清单与汇总文件和压缩包中的对应输出保持字节一致。
`generation_failures.jsonl`、执行摘要及交付核查是基于原始文件整理的附加说明。
Windows 时区依赖的后续修复在 `a9e756c`，未修改本次冻结的生成实现或实验结果。

## 输入来源与使用边界

Gold 来源为 M3 v0.1.2，原始参考文件公开发布于团队已有交付。
冻结 Gold 快照保留完整 188 题及来源信息，含临时映射后的 162 Dev / 26 Test；
本次矩阵和模型调用仅覆盖 Dev，不包含 Test 生成结果，也不构成正式划分批准。
`pending → dev`、`proposed_test → test` 的显式映射保存在 `inputs/gold_conversion.json`。
参考答案和 Gold 标注不进入生成提示词。

原生证据来自
[M4 V2 开发语料](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m4-structure-v2-dev-v1)，
版本 `2.0.0-dev.m4-structure-v2-main-3553825`；
Role 来源为
[V2 Role 开发包](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-role-labels-v2-dev-v1)。
具体语料、Gold、标签、lambda 选择及实现摘要见输入和运行清单。

检索原文保留用于证据追溯，其来源与许可遵循 `inputs/corpus_manifest.json` 和
M4 Release 的声明（CC BY 4.0）。教材来自 OpenStax：
[College Physics 2e](https://openstax.org/details/books/college-physics-2e)、
[College Physics for AP Courses 2e](https://openstax.org/details/books/college-physics-ap-courses-2e)、
[Physics](https://openstax.org/details/books/physics)。
本次保留的教材引文未改写，原作者和出版方的署名及其他许可条件仍适用。

后续评分和复核操作见 [M7 V2 实验说明](../../v2-member7-experiments.md) 与
[开放题评分说明](../../open-answer-scoring.md)。本次交付没有新增评分。
