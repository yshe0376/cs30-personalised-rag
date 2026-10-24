# 题目适用范围 `personalisation_eligibility` v1

日期：2026-10-24。对应评估方案 §3.2。

**状态：标注草稿。** 用到的等级画像包 `level-profile-v1`（`2c61590c…`）仍是 `frozen=false`，所以这批标签只能用于开发阶段，不能用于 `--reportable` 运行。画像冻结后，要用冻结版本重新渲染规则、重新运行。人工校准和复核也还没做，见文末"待完成"。

## 取值的定义

每题先写一个**中级参照答案**：能通过中级清单 I1–I3 全部适用条目的最短正确答案。再把这个答案原样拿去按初学者清单（B1–B4）和高级清单（A1–A4）评，看有没有适用条目不通过：

| 初学者侧有不通过 | 高级侧有不通过 | 取值 |
|---|---|---|
| 是 | 是 | `full` |
| 是 | 否 | `endpoint_only` |
| 否 | 是 | `endpoint_only` |
| 否 | 否 | `none` |

- 没有不通过、但有 `uncertain` 的，也归为 `endpoint_only`：拿不准的题留在主结果里，但不进入 `full`。
- 取值由程序 `map_label` 计算。标注模型只判断各条目，看不到这三个取值名。
- 条目的含义以 `docs/evaluation/level-profile-v1/` 的清单原文为准。A3 按原文执行：答案中已有的定性标度或极限论证算作满足。

## 标注方式

- 标注者：Codex CLI，模型 `gpt-6.1-sol`，reasoning effort `high`。共 341 题，分 18 批，每批开一个新会话，批次顺序用种子 `20261024` 打乱。
- 每个会话只拿到本批题目（题号、题干、参考答案、Gold 证据）、规则和 schema，文件内容直接拼在提示词里。拿不到题型、难度、split、M3 备注，也拿不到任何生成答案。
- 每个会话的事件日志都核查过：只运行了一次 JSON 语法检查，只写了指定的输出文件。中途有两次尝试因账户额度中断，没有计入结果。原始会话日志（约 5 MB）未入库。
- Codex 与生成模型 gpt-oss 同属 OpenAI 家族。标注时看不到任何生成答案，因此风险小，但在此注明。

## 文件

| 文件 | 内容 |
|---|---|
| `personalisation_eligibility_v1.jsonl` | 交给 M8 的附加文件，`EligibilityRecord` 格式，341 行 |
| `annotations_v1.jsonl` | 每题的完整判断：中级参照答案、I/B/A 各条目的说明与结论、参考答案疑点、理由 |
| `needs_review.jsonl` / `review_details.json` | 48 道待复核题（46 道参考答案疑点、2 道不确定判断） |
| `run_manifest.json` | 规则、提示词、schema、术语约定、画像和 Gold 的哈希，批次顺序，模型设置 |
| `summary.json` / `source_provenance.json` | 汇总计数；输入文件的来源提交 |
| `prompt/` | `RULES.template.md`、`TASK_PROMPT.md`、`output_schema.json`、`term_convention.proposed.txt`，与运行时使用的版本逐字节相同 |

脚本 `scripts/eligibility_codex_batches.py` 负责准备批次（`prepare`）和汇总输出（`collect`）。它与运行时的版本相比，只改了模板路径和格式。用它对运行输出重新 `collect`，得到的附加文件与本目录中的逐字节相同。

## 结果

| 集 | `full` | `endpoint_only` | `none` | 合计 |
|---|---:|---:|---:|---:|
| Dev | 2 | 104 | 48 | 154 |
| Test | 0 | 128 | 59 | 187 |
| 合计 | 2 | 232 | 107 | 341 |

- 模型判断的题目要求：334 题只问名称或事实，6 题问为什么或怎样，1 题要求计算。Gold v0.1.3 里没有真正需要计算的题，标为 `calculation` 的 6 题都是让学生说出一个量的名称，所以不要按 `question_type` 单独报告"计算题"的结果。
- 不通过的条目几乎全在初学者侧：B1 219 次，B3 158 次，B2 6 次。高级侧只有 A4 3 次、A2 1 次。也就是说，取值基本由"答案术语是否需要向初学者解释"决定。主结果衡量的主要就是这一点，报告里应如实说明。

## 已知问题

1. 两道 `full`（`sciq-train-00056`、`sciq-train-09086`）的高级侧不通过，都源于参考答案本身的错误：前者题目问的是角，后者题目前提有物理错误。复核后大概率会变成 `endpoint_only`，因此不宜单独报告 `full` 子集。
2. B1 的判断受参照答案措辞影响。参照答案如果顺手带了一句较易懂的解释，B1 就可能被判通过：例如 `sciq-train-05331` capacitors、`sciq-train-06209` diverging 都被标为 `none`，而 `sciq-train-00058` kinetic energy 没有解释，被标为 `endpoint_only`。107 道 `none` 中，有 35 道的参照答案超过 4 个词，应优先复核。
3. 参考答案疑点的报告偏保守。例如 `sciq-train-09321` 脱离语境后答案并不唯一，但没有被标出。

## 待完成

- 画像冻结，并把术语约定写进冻结画像；之后用冻结版本重新运行。
- 人工校准：Leader 与 M3 对 15–20 题各自独立标注（`calibration_question_count` 要求 15–20），形成校准记录和标注来源记录，二者都是 M8 `validate-inputs` 的必需输入。若复核发现规则需要修改，修改规则后全部重跑，不逐题手改。
- 复核：48 道待复核题、35 道带解释的 `none`、两道 `full`。
- 校准集和盲抽集不能包含讨论中用过的示例题：`sciq-train-00963`、`sciq-train-01031`、`sciq-train-02858`、`sciq-train-04256`、`sciq-train-09387`。
- M8 接入（见方案 §12.1）：`adapt` 现在要求附加文件与本次运行的题目集合完全一致，这份 341 题的文件直接用于 154 题的 Dev 运行会报 coverage mismatch；条件对照尚未按适用范围分层；`none` 层的适切度在汇总里被置空。
