# M7 V2 修复验收：2026-10-17

本目录记录生成与评分解耦后的开发验收，`reportable=false`。

- 隔离完整测试：916 项通过，2 项可选依赖检查跳过；排除了工作区原有的 v1 contract 本地修改。
- M8 独立评分代码：65 项测试通过，代码另交 M8 review。
- Ruff、差异空白检查、生成专用 wheel 构建及 wheel 内 CLI 导入通过。
- Dev 结果目录的 Markdown 在 `core.autocrlf=true` 下保持原始字节，SHA256SUMS 全部通过。
- 旧结果复核：每个 P 设置下 R0/R1 prompt 摘要相同 486/486；14 个失败单元的第一次尝试
  全部是引用错误。旧生成文件不改写，归档已移到同仓库 pre-release。

## 正 lambda 选择

使用同一冻结 Gold、语料、候选与完整 Role 包重新准备输入，只在 Dev 选择参数。
在正 lambda 中选取满足命中率不低于零基线减 1 个百分点的最大 lambda。

| lambda | 完整证据命中率 | 是否满足限制 |
|---|---:|---|
| 0 | 0.827160 | 基线 |
| 0.1 | 0.823045 | 是 |
| 0.2 | 0.820988 | 是，选中 |
| 0.35 | 0.796296 | 否 |
| 0.5 | 0.635802 | 否 |

[完整选择记录](lambda_selection.json) 保留每个 Dev 题/等级的指标和来源摘要。
已冻结 162 题 × 3 等级 × 4 条件 = 1,944 格、lambda=0.2 的下一轮输入，Role 覆盖完整。
本目录的实测仅为下面 12 格接线验收，未把完整 1,944 格重跑标为完成。

## 本机真实模型验收

使用现有 Ollama `gpt-oss:20b`，模型 digest 为
`17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7`。
同一 Dev 题、三个等级、四条件，lambda=0.2，seed=0，温度0，
上下文32,768，最大输出2,048 token，超时180秒。

**12/12 格全部回答成功，12 次调用，零技术失败、零输出截断**；本地调用累计约72.82秒。
V3 提示词只使用 E1–E5 引用，逐条校验原始输出短编号与保存答案完整 chunk ID 的映射。
生成报告不包含答案正确性或等级适配的评分。

[保存答案](smoke/saved_answers.jsonl)、[完整生成记录](smoke/generation_records.jsonl)、
[预定矩阵](smoke/expected_experiment.json)、[运行清单](smoke/run_manifest.json)、
[生成报告](smoke/generation_report.md)、[验收摘要](verification.json)。

引文来源为团队发布的 M4 OpenStax 开发语料，来源和 CC BY 4.0 许可遵循原 corpus manifest。
教材及出版方署名见 [原始 Dev 交付](../m7_v2_dev_20261016/README.md)。
