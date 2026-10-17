# V2 开放题离线评分

代码入口：`python -m cs30.evaluation.open_answer_cli`。安装当前版本后也可使用
`cs30-score-open-answers`。该工具读取已保存的答案；不会调用生成模型重答，
不会修改原始答案，也不会将 Gold 答案加入生成提示词。

量表设计见 `docs/superpowers/specs/2026-10-15-v2-open-ended-answer-scoring-proposal.md`。
当前输出明确标为 development、`reportable=false`；实际人工校准和团队冻结不能用
测试通过、文件名或一个 review ID 代替。初版实现正确性评分、人工复核和校准统计。
新增语义级证据支持指标、水平适配及正式实验批准仍保持独立。

## 输入文件

所有 JSON/JSONL 文件使用 UTF-8。摘要是文件原始字节的 SHA-256；空白、换行改变也需要
重新生成摘要。输入会一次读取为快照，输出记录的是实际使用快照的哈希。

1. `gold.jsonl`：显式 schema `2.0` 的 `GoldQuestion`，或现有 schema `0.1`/`0.2` 的
   `GoldSample`。保留原始标注与证据；不猜测或自动迁移未知格式。
2. `open_answer_rubrics.jsonl`：每题一个 `OpenAnswerRubric`，记录下述题目要点。
3. `saved_answers.jsonl`：每个已运行实验单元一个 `OpenAnswerRun`，保存原始生成答案。
4. `expected_experiment.json`：`OpenAnswerExperiment`，列出所有预定单元、Gold 与量表文件哈希。
   不能从成功运行记录反推预定数量，否则失败或遗漏的记录会消失。

原始 V2 批量生成结果可导出为评分输入：

```python
from cs30.evaluation.open_answer_models import ExpectedAnswer, OpenAnswerRun

cell = ExpectedAnswer(
    run_id="run-001", question_id="question-001", condition_id="P0R0_plain",
    student_level="beginner", generator_model=batch_result.trace.model,
)
record = OpenAnswerRun.from_v2_result(cell, batch_result)
line = record.model_dump_json() + "\n"
```

此适配器不改答案，分别保留回答、拒答、技术错误，并核对生成模型身份。
V2 的证据与原始 trace 仍应保存在生成实验自己的完整输出中；评分输入是其离线视图。
检索失败可直接构造 `status="retrieval_error"` 的记录，并提供真实 `error`。

## 逐题量表

以下仅是合成示例，`span-from-gold` 必须换成该题真实的 Gold span ID，
哈希必须是原始 Gold 文件摘要。不能把示例 review ID 当作真实复核记录。

```json
{
  "schema_version": "0.1",
  "question_id": "question-001",
  "gold_sha256": "<64位Gold文件摘要>",
  "rubric_version": "physics-open-answer-0.1",
  "review_record_id": null,
  "criteria": [
    {
      "criterion_id": "term",
      "description": "正确给出 deceleration 这一术语。题目不要求额外推导。",
      "core": true,
      "reference_span_ids": ["span-from-gold"]
    }
  ],
  "required_paths": [["term"]],
  "full_credit_answers": ["deceleration", "Deceleration.", "减速"],
  "alias_case_sensitive": false,
  "numeric_target": null
}
```

路径之间是 OR，路径内部是 AND。出现核心矛盾得 0 分；满足一条完整路径且无实质性错误
得 2 分；只有部分正确要点或次要错误得 1 分。无法判定时转复核，不强行给分。

`full_credit_answers` 是可以单独满足题目要求的**完整答案列表**。程序只做整段匹配，
不做关键词包含判断。长答案即使包含正确术语，仍会进入语义检查。
默认保留大小写，只有显式设置 `alias_case_sensitive=false` 才忽略文字别名大小写；
数值单位始终区分大小写。

纯数值题可配置 `numeric_target`：

```json
{
  "value": -2,
  "accepted_units": ["m/s²", "m/s^2"],
  "absolute_tolerance": 0.01,
  "relative_tolerance": 0.0
}
```

数值快捷规则仅允许一个已经足够回答问题的结果要点，并要求文字别名列表为空，
防止跳过推导要求或绕过单位大小写检查。
只有完整数值与单位形式才自动检查；含额外解释的回答交给语义评审。
单位必须明确列出，空字符串仅用于明确允许无单位的题。容差逐题确认，不设全局宽松容差。

## 预定实验清单

```json
{
  "schema_version": "0.1",
  "matrix_version": "m7-dev-open-answer-0.1",
  "gold_sha256": "<64位Gold文件摘要>",
  "rubrics_sha256": "<64位量表文件摘要>",
  "cases": [
    {
      "run_id": "run-001",
      "question_id": "question-001",
      "condition_id": "P0R0_plain",
      "student_level": "beginner",
      "generator_model": "<实际生成模型标识>"
    }
  ]
}
```

实际实验必须完整列出需要的题目、四条件和等级。程序拒绝重复单元、额外运行、错误身份、
缺失量表和未知证据引用；预定但没有保存的运行则作为未决记录留在分母里。
MCQ 不进入开放题正确率；不可回答和 answerability 未决的 Gold 显式列出排除原因。

## 自动评分

先运行无需 judge 的离线检查：

```bash
python -m cs30.evaluation.open_answer_cli score \
  --gold gold.jsonl --rubrics open_answer_rubrics.jsonl \
  --runs saved_answers.jsonl --expected-manifest expected_experiment.json \
  --output-dir artifacts/m7-open-answer/offline-check
```

完整别名、明确数值规则可自动给分，其余进入待复核队列。没有 judge 时不伪造语义判断。

使用已安装并启动的 Ollama judge：

```bash
python -m cs30.evaluation.open_answer_cli score \
  --gold gold.jsonl --rubrics open_answer_rubrics.jsonl \
  --runs saved_answers.jsonl --expected-manifest expected_experiment.json \
  --provider ollama --model <独立judge模型标识> \
  --cache-dir artifacts/m7-open-answer/judge-cache \
  --output-dir artifacts/m7-open-answer/judged
```

也支持 `--provider openai --model ...`，复用项目已有客户端和环境配置。
`--provider none` 是默认值。只有显式选择真实提供方才会发起语义评审调用。
`--max-retries` 默认 1，允许 0–3；`--timeout` 默认 120 秒；
`--max-output-tokens` 默认 2048。失败、无效 JSON 和没有原文依据的引文保留在 trace 中。

同名生成模型不能默认担任 judge。`--allow-self-judge` 仅允许明确的探索性自评，
不会使报告变成正式结果。程序还记录提供方实际返回的模型 ID；若与生成模型相同而未授权
自评，该答案转复核。模型别名和不同模型家族之间的相关偏差仍需人工审查，不能只靠名称证明独立性。

judge 不看到 condition、生成模型、学生等级或 lambda。它看到完整回答、已确认要点和
Gold 参考教材证据，不只看本次检索内容。它必须返回每个要点的结构化判断和原文引句；
0/1/2 分由程序计算，judge 不能直接提交一个总分。

缓存绑定完整评审提示词、Gold/量表摘要、judge 配置和 schema。同一答案跨条件复用
相同的盲化评审；改量表或配置会失效。缓存不能作并发多写入任务的共享数据库。
新报告不会把缓存或人工复核中保留的历史 provider 调用重新计为本次调用。

## 人工复核

`HumanDecision` JSONL 每行包含：`run_id`、`answer_sha256`、`rubric_sha256`、
`rater_id`、整数 `score`（0/1/2）、`note` 和真实 `review_record_id`。
摘要可从原始逐题评分文件读取。人工评审应查看原始完整答案、量表与教材，
不能只根据机器给出的解释填写。

```bash
python -m cs30.evaluation.open_answer_cli review \
  --scores artifacts/m7-open-answer/judged/open_answer_scores.jsonl \
  --decisions human_decisions.jsonl \
  --output-dir artifacts/m7-open-answer/reviewed
```

复核生成新目录，保留原始自动评分和机器观察。新逐题记录包含评分人、复核记录 ID，
并标为 human。不能给没有原始答案的缺失运行编造人工分，也不能覆盖已有人工决定。
需要修订人工决定时，应创建独立版本的记录与报告。

## 校准统计

`HumanRating` 的字段与复核决定相同，但不需要 `review_record_id`。每个抽样答案需要同样
两位评分人的独立记录，哈希必须匹配原始自动评分。不同意的答案必须另附
`HumanDecision` 仲裁文件；程序不会只挑双方同意的样本计算 judge 表现。

```bash
python -m cs30.evaluation.open_answer_cli calibrate \
  --scores artifacts/m7-open-answer/judged/open_answer_scores.jsonl \
  --ratings human_double_ratings.jsonl --adjudications adjudications.jsonl \
  --output-dir artifacts/m7-open-answer/calibration
```

输出原始人工一致率、线性加权 Cohen κ、0/1/2 混淆矩阵、严格正确的 precision/recall，
以及以题目为 cluster 的可复现 bootstrap 区间。只有一个类别时 κ 可能无定义；
不足两个题目 cluster 时不提供区间。某指标在重采样中无定义时，不给它一个假装完整的区间。
这些都是该人工子集的诊断，不能直接当作全体成绩估计或正式批准。

## 输出与分母

每次评分/复核写出：

- `open_answer_scores.jsonl`：逐题分数、来源、依据、模型与原始评审输出。
- `open_answer_review_queue.jsonl`：待人工复核、judge 错误和缺失运行。
- `open_answer_summary.json`、`.csv`、`open_answer_report.md`：总体、条件/等级/模型分组统计。
- `run_manifest.json`：输入快照哈希、judge 配置与调用模式。

严格正确率只统计得 2 分的答案。平均 `score/2` 单独展示，不叫准确率。
可回答题上的模型拒答、生成/检索/解析失败在端到端指标中计 0，并保留真实原因。
judge 错误、待复核和缺失运行不记 0，也不从预定分母删除；有未决项时显示上下界，
点估计为 null。正常作答的条件正确率也展示未决数量。

人工、规则和 judge 的来源数量与分项统计单独列出；人工复核后的总体标明混合评分来源。
当前分条件报告提供覆盖率和分数，不自动宣称四条件差值具有统计显著性。
引用是否支持陈述、教学解释质量和水平适配需要各自的评估，不从这份正确率推断。

退出码：0 表示所选单元均处理完成；3 表示报告已写出但仍有未决项；
2 表示输入、配置或文件错误。已存在的输出目录不会被覆盖。

## 验证范围

自动测试使用合成 Gold、模型响应和人工记录；不会自动生成实际的人工校准证据。
测试覆盖命令行三条路径、真实客户端接口的模拟调用、原文引用校验、矛盾回答、
数值符号/单位、缓存版本、真实返回模型身份、输入快照、失败分母及人工记录绑定。

要正式运行团队的 V2 结果，仍需要真实 Gold、逐题审核要点、保存的真实生成结果、
可用 judge，以及实际人工校准记录。该工具不替代上游批量生成或 Role 标签交付。
