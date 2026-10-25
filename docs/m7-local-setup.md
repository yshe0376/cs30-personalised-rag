# M7 本地配置与运行（2026-10-26）

代码已同步至 `17cb2f3`。本地原有 `IndexArtifact._version` 修改已备份至
`artifacts/m7-readiness-20261026/backups/original-contract-change.patch`，字段恢复为
`schema_version`，索引加载恢复。三模型 Dev 和独立重复生成已完成；未生成 Test 答案。
完整结果与 M8 交接入口见 [2026-10-26 API Dev 结果](results/m7_api_dev_20261026/README.md)。

## 当前运行方案

用户已批准 M7 生成总预算 USD15，并于本聊天确认替换持续限流的 Qwen。
当前活动模型为 DeepInfra 的 gpt-oss-20b、Gemma 3 12B、Llama 3.1 8B Instruct。
Qwen 已停止续跑，原始结果和费用保留为历史探索，不能并入 Llama。

- GPT：`openai/gpt-oss-20b`，`.env.m7.gpt-oss20b`，JSON Object。
- Gemma：`google/gemma-3-12b-it`，`.env.m7.gemma3-12b-schema`，JSON Schema。
  原 JSON Object 测试的字符串 `"null"` 类型失败保留在原目录。
- Llama：`meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`，`.env.m7.llama31-8b-json`，JSON Object。
  提供方不支持此模型的 JSON Schema；独立 JSON Object 首轮 12/12 通过。
  10题测试中117/120成功，3个引用字段类型错误严格保留为失败。完整 Dev 已完成，
  沿用相同提示词与解析器；失败仍留在分母中，不做静默转换或挑选重跑。
  本机接续参数为 `--model llama31-8b --retain-smoke-format-failures`，
  决策记录见本地 `llama31-8b-smoke-review.json`；这不是正式质量接受阈值。

密钥保存在仅所有者可读写、被 Git 忽略的 `.env.m7.credentials`，各模型配置引用
`DEEPINFRA_API_KEY`。DeepInfra 已充值 USD10，账户和实验密钥月度限额均为 USD10。
SiliconFlow 预付 USD5，停用 Qwen 后不再发起该平台的生成调用；没有启用自动充值。

GPT 和 Gemma 各 1,848 个 Dev 与 360 个重复单元全部成功；Llama Dev 1,773/1,848、
重复 351/360 成功，84 个格式失败保留。全部 6,624 个单元执行完毕，最终无截断，
输入/输出哈希、矩阵、检查点和引用成员关系验证通过。累计已报告 token 费用约 USD0.807，
含历史探索与重试，以平台账单为准。完成后的状态见 `final-generation-summary.json`；
原始运行由 `.codex_work/run_m7_sequence.py` 接续完成，定时监控 `m7-30` 已删除。
不要重跑成功单元或将诊断失败挑选重跑成成功。

公开 API 模型 ID 不代表已核实不可变权重版本；manifest 如实记录该限制。
所有结果均为开发结果，答案正确性和适配度仍待 M8 独立评分。

## 已完成的本地准备

- 固定下载并校验 Gold v0.1.3、四教材语料、6,184 个 chunk 的 Role，以及 M6 Qwen3
  Dense 0.10 / BM25 0.90、全部 341 题的 top-20 原生候选。
- 重新转换 341 题、352 条证据绑定；生成侧划分为 154 Dev / 187 Test。
- 在 154 × 3 = 462 个 Dev case 上重选 λ：**0.1**。
  λ=0 完整证据命中率为 81.82%，λ=0.1 为 80.95%，下降 0.87 个百分点；
  λ=0.2 为 79.00%，不满足最多下降 1 个百分点的规则。
- 已准备并检查 10 题冒烟（120 单元）、154 题 Dev（1,848 单元）、
  30 题独立重复（360 单元）。这些目录的模型名为 `readiness-no-api`，仅供准备检查；
  填写实际模型后，启动器会为该模型创建独立目录。
- 离线模拟生成：120/120 单元成功；完成后续跑新增 0 次调用。模拟答案仅用于工程检查，
  不是真实模型输出或效果证据，不能交作正式生成结果。

上述文件保存在忽略的 `artifacts/m7-readiness-20261026/`；全部为 `reportable=false`。

## GitHub 历史决定与本机后续选择

[PR #202](https://github.com/yshe0376/cs30-personalised-rag/pull/202) 确定：
主模型为托管 gpt-oss-20b；对比为 Qwen3 8B 加 Llama 3.1 8B / Gemma 3 12B 二选一；
均走 API，评分归 M8。该 PR 明确预算、第三模型及对比规模仍待定。
[PR #203](https://github.com/yshe0376/cs30-personalised-rag/pull/203) 明确实际托管平台、
根地址、模型部署版本和预算未指定；仓库里的 Groq/Qwen 参数只是示例。

本聊天随后由用户批准了提供方、USD15 预算和以 Llama 替换 Qwen。
使用上面列出的模型专用配置；通用 `.env.m7` 仍为空模板，不能用于实际批次。
本机的用户授权不等于团队的 Test 冻结或正式评估批准。

## 配置与运行

在项目根目录执行。macOS 可直接使用 `./start_m7.sh`；其他平台或终端可用
`.venv/bin/python scripts/run_m7_local.py` 替代启动器。

```bash
./start_m7.sh status
```

本机已创建被 Git 忽略的 `.env.m7`（仅文件所有者可读写）。填写提供方、根地址、模型 ID、
真实部署版本及密钥。新机器先复制 `docs/examples/m7-api.env` 到 `.env.m7`。
文件使用简单 `KEY=VALUE` 格式，shell 中已有的同名变量优先；JSON 参数写在一行。
请不要把密钥发到聊天、放进命令参数或提交 Git。

填入批准的冒烟请求上限、输出 token 上限与平台参数后：

```bash
# 仅准备与检查，不调用模型；缺少 API 信息也可以执行。
./start_m7.sh prepare --batch smoke
# 检查 API 设置与输入，不发出 API 请求；仍需填写非密钥配置与预算。
./start_m7.sh run --batch smoke --dry-run
# 显式启动真实 API 冒烟，可能产生费用。
./start_m7.sh run --batch smoke
```

冒烟为 10 题 × 3 档 × 4 条件，共 120 个单元；HTTP 尝试数还可能包含格式探测与重试。
先检查该批次的日志、截断率、格式/引用错误和实测 token，再冻结 `M7_OUTPUT_FORMAT`
为 `json_schema` / `json_object` / `text` 之一，以及 token 上限和模型平台参数。
`M7_EXTRA_BODY` 中不能放密钥，也不能覆盖 model/messages 等受控字段。

全量 Dev 与独立重复批次分别设置批准的 `M7_DEV_REQUEST_CAP` / `M7_REPEAT_REQUEST_CAP`，
并在提供方设置金额上限，然后执行：

```bash
./start_m7.sh prepare --batch dev
./start_m7.sh run --batch dev --dry-run
./start_m7.sh run --batch dev
./start_m7.sh prepare --batch repeat
./start_m7.sh run --batch repeat
```

每次启动器都会核验固定下载文件。每个模型、批次有独立 prepared/run 目录；
重复批次与基线不共用生成缓存。已有运行目录不会被覆盖。中断恢复使用相同配置：

```bash
./start_m7.sh run --batch dev --resume
```

模型、提供方、输出格式、token 或平台参数变更时不能续跑旧批次；用 `--root` 指定新目录，
启动器会重新准备固定输入。累计请求上限不等同费用上限，失败与重试也计入请求预算。
实际 API 的可用性、参数支持、输出质量和用量仍须真实冒烟确认。

本启动器只处理 Dev。Test 须等 M8 冻结 judge，Leader 登记 δ、主要比较和抽样方案后，
再按 [M7 实验说明](v2-member7-experiments.md) 执行一次。画像与清单当前仍是待审核草稿。

## 验证记录

此前全仓测试：**1,212 passed / 3 skipped**；当时本地启动器新增 5 项测试，覆盖
预算未配置、正式批次误用 auto、密钥不进入参数、受控平台字段和默认不调用 API。
随后增加共享凭据变量名相关检查；发布前启动器专项测试 **7 passed**，
最终全仓回归 **1,214 passed / 3 skipped**，静态检查通过。
离线交接核验使用 `python scripts/verify_m7_handoff.py --root artifacts/m7-readiness-20261026`，
不会调用 API。日志和模拟验证摘要位于本地 artifacts 目录。
