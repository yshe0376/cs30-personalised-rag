# M7 V2 批量生成与 M8 交接

入口为 `python -m cs30.v2.experiment_cli`（安装后为 `cs30-experiment-v2`）。
M7 冻结生成输入、执行三个等级 × 四条件、保存证据和答案。M8 独立维护 rubric、
judge、人工校准和评分报告；修改 rubric 不改变 M7 的输入摘要或已生成答案。

完整 [2026-10-17 Dev 运行（λ=0.2）](results/m7_v2_dev_20261017_lambda02/README.md)
已完成 162 题 × 3 等级 × 4 条件，共 1,944/1,944 条成功答案，零技术失败、零输出截断。
结果目录提供保存答案、报告和逐文件校验；GitHub pre-release 提供冻结输入、完整原始记录和全部检查点。
本轮仅完成生成，正确性与等级适配仍待 M8 独立评分，`reportable=false`。

## 准备输入

获取团队已发布的开发数据并验证摘要：M3 Gold v0.1.3、M4 四本书语料
（`2.0.0-dev.m4-four-book-main-a1fe99e`）和对应的四本书 Role 包。

```bash
python scripts/fetch_v2_experiment_inputs.py --output-dir artifacts/v2-experiment-inputs
python -m cs30.v2.experiment_cli convert-gold \
  --gold artifacts/v2-experiment-inputs/gold_v0_1_3.jsonl \
  --corpus-dir artifacts/v2-experiment-inputs/2.0.0-dev.m4-four-book-main-a1fe99e \
  --split-map docs/examples/v2-m7-provisional-splits.json \
  --output-dir artifacts/v2-experiment-inputs/converted-v0.1.3
```

转换保留参考答案、原始章节坐标和证据注释；只有 chapter/block/原文精确唯一匹配时才绑定。
`pending → dev`、`proposed_test → test` 是开发临时映射，不构成正式划分批准。
v0.1.3 有 311 题 pending、30 题 proposed_test；其中 26 题 Test 已在 M6 诊断中暴露，仍需披露。
82 题的证据来自 CK-12，只能在四本书语料上绑定。Gold 参考答案不会进入模型提示词。

输入已从 Gold v0.1.2 + 三本书语料换成 v0.1.3 + 四本书语料。2026-10-17 的 Dev 运行及其
lambda 选择基于旧输入，不能与新输入的结果直接比较；新输入需要重新做 Dev 选择。

Role 包使用团队 [四本书 V2 Role 开发 Release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-role-labels-v2-four-book-dev-v1)，
下载脚本已核对摘要，`--role-manifest` 传
`artifacts/v2-experiment-inputs/role_labels_v2_provenance_manifest.json`。要求所有候选 chunk
都有匹配标签；只有诊断运行才允许显式 `--allow-missing-roles`。Role 包主要由模型标注，
未完成独立人工验证。

若需新标注，可使用 `role-template` 导出候选及空白 Role，再用 `import-roles` 打包真实填写的
标注。这两个命令不会伪造标注。原生检索候选也可通过 `prepare --retrieval` 提供；
否则复用生产 BM25。候选的内容、来源、版本和摘要必须与语料一致。

## Dev 选择正 lambda

先冻结开发候选：

```bash
python -m cs30.v2.experiment_cli prepare \
  --corpus-dir artifacts/v2-experiment-inputs/2.0.0-dev.m4-four-book-main-a1fe99e \
  --gold artifacts/v2-experiment-inputs/converted-v0.1.3/gold.jsonl \
  --gold-conversion-manifest artifacts/v2-experiment-inputs/converted-v0.1.3/conversion_manifest.json \
  --role-manifest artifacts/v2-experiment-inputs/role_labels_v2_provenance_manifest.json \
  --model gpt-oss:20b --split dev --candidate-k 20 --evidence-k 5 \
  --output-dir artifacts/v2-dev-candidates
python -m cs30.v2.experiment_cli select-lambda \
  --prepared-dir artifacts/v2-dev-candidates \
  --lambdas 0 0.1 0.2 0.35 0.5 --output artifacts/v2-dev-lambda.json
```

完整证据命中采用 Gold 的 OR-of-AND 路径。候选网格必须含 0 基线；只在
`lambda > 0` 且 `complete_hit_rate(lambda) >= complete_hit_rate(0) - 0.01`
的候选中选择最大的 lambda。span 覆盖率作为审计指标记录，不改变该选择规则。
没有合格正值就报错。此处 0.01 是绝对 1 个百分点，不是相对下降 1%。
2026-10-16 的冻结 Dev 网格（旧输入）按新规则应选择 0.2；正式运行以保存的选择文件为准。
Test 禁止调参，只能复用匹配语料、Gold、Role 和参数的 Dev 选择。

使用选择结果重新准备最终输入：

```bash
python -m cs30.v2.experiment_cli prepare \
  --corpus-dir artifacts/v2-experiment-inputs/2.0.0-dev.m4-four-book-main-a1fe99e \
  --gold artifacts/v2-experiment-inputs/converted-v0.1.3/gold.jsonl \
  --gold-conversion-manifest artifacts/v2-experiment-inputs/converted-v0.1.3/conversion_manifest.json \
  --role-manifest artifacts/v2-experiment-inputs/role_labels_v2_provenance_manifest.json \
  --selected-lambda artifacts/v2-dev-lambda.json \
  --model gpt-oss:20b --split dev --output-dir artifacts/v2-dev-final
python -m cs30.v2.experiment_cli check --prepared-dir artifacts/v2-dev-final
```

`prepare` 不接收或读取 rubric，不调用评分器。三个等级 × 四条件均使用同一冻结候选池；
P0 关闭等级提示，R1 在同一候选池上重排后取 top-5。包含 R1 的矩阵禁止以 lambda=0 运行。

## 运行、停机和续跑

```bash
python -m cs30.v2.experiment_cli run \
  --prepared-dir artifacts/v2-dev-final --output-dir artifacts/v2-dev-run \
  --provider ollama --timeout 180 --max-output-tokens 2048 \
  --context-window 32768 --seed 0 --stop-after-errors 3
```

V2 提示词版本为 v3。提示词中的引用使用 E1–En（top-5 为 E1–E5），本地严格校验后映射为
原始 chunk ID；`GeneratedAnswer` 契约保持不变。证据正文、完整身份、原始模型输出和映射
留在生成记录中。错误短编号进入有界修复，不能作为原始 chunk ID 直接通过。

每次调用保存耗时、用量及 `done_reason`。Ollama 返回 `done_reason=length` 时记为
`output_truncated`，包括空内容；它独立于服务失败，不触发服务停机阈值。
Ollama 的 seed、上下文容量和模型 digest 都进入运行清单和恢复校验。

连续停机计数只累计「每次尝试都是 provider_failure」的单元，成功、引用错误、解析错误、
混合失败或输出截断都会重置该计数。达到阈值前已完成的单元均已持久化。
退出码：0 为生成完成，3 为完成但仍含失败/截断，2 为配置、服务停机等错误。

给原运行命令加 `--resume` 续跑。恢复前核验冻结输入、代码实现、模型和参数；
只重试纯服务失败单元，将原检查点原子移动到 `checkpoints/superseded/`，保留审计记录。
成功单元和确定的引用/解析失败不重跑。中断时聚合文件可以不完整，以原子检查点为准重建。
单写者锁避免两个进程同时写同一输出。

macOS/Linux 可启动独立监督进程：

```bash
python scripts/run_v2_batch_job.py start \
  --prepared-dir artifacts/v2-dev-final --job-dir artifacts/v2-dev-job
python scripts/run_v2_batch_job.py status --job-dir artifacts/v2-dev-job
python scripts/run_v2_batch_job.py resume --job-dir artifacts/v2-dev-job
```

监督进程冻结已提交代码和输入，macOS 使用 caffeinate 防止空闲睡眠。
Windows 直接给出说明并退出；Windows 可使用上面的前台 `experiment_cli run`。
监督进程校验全部预定单元、检查点和生成产物摘要，不导入评分器或读取评分报告。

## M7 → M8 数据交接（待 M8 review）

M7 输出 `saved_answers.jsonl`、`generation_records.jsonl`、`expected_experiment.json`，
另有生成运行摘要、运行清单和逐单元检查点。矩阵 schema 为 `0.2`，仅绑定 Gold 摘要、
模型和完整单元集合，不含 `rubrics_sha256`；生成记录保存原始输入和调用审计。
`output_truncated` 是单独的失败状态，不应当成服务中断或普通正确性答案。

M8 自己的评分 manifest 绑定 rubric 摘要、Gold、上述生成产物摘要和评分器版本。
独立的 M8 评分 PR 保留旧评分实现供 M8 接手；适配新矩阵/截断状态、评分分母、技术失败列、
按唯一答案出盲评包与校准、rubric 审查和 judge 选型都由 M8 决定。
M7 CLI 已移除 rubrics、review-packet、import-ratings 和 judge 参数。
新模块 `cs30.v2.io` 提供中立 JSONL/摘要工具；运行器只复用评分侧的数据模型。

本次接口约定已写入交接和 PR，仍需 M8 review，不宣称双方已经确认。
旧 2026-10-15/16 归档保留当时的 rubric/评分状态与代码指纹；复现旧归档应使用其原代码快照，
不要用新版本强行改写旧哈希。新版本准备的输入不受 M8 后续 rubric 修订影响。

所有结果仍为开发实验、`reportable=false`。引用 ID 合法不等于语义支持；
生成成功不等于答案正确。学生等级适配和正确性均需 M8 独立评估。
