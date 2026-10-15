# M7 V2 批量实验与交接

入口是 `python -m cs30.v2.experiment_cli`，安装当前项目后也可用
`cs30-experiment-v2`。它把 V2 Gold、原生检索结果、Role 重排、三个等级的四条件生成、
开放题离线评分和人工校准材料接起来。每一步保留输入摘要，拒绝覆盖已有输出。

## 当前可运行范围

- 三个固定实验等级 × 四条件：plain、prompt-only、reranking-only、combined。
- 同题各条件共用一份冻结的 top-20 候选，重排后取 top-5；P0 条件关闭等级提示。
- 默认复用生产 BM25；也可传入 M6 保存的原生 V2 检索结果，不要求重新构建 Dense 索引。
- 所有候选都必须与发布语料的内容、来源、版本及哈希匹配。Gold 参考答案不进入生成提示词。
- 逐单元保存完整证据、重排轨迹、模型原始输出、引用、耗时和 token 用量。
- 模型失败作为技术失败保留；其他单元继续运行，失败和缺失不从预定分母消失。
- 开放题评分使用独立模块；没有 judge 时保留待评分状态，仍会生成覆盖率和运行报告。
- Dev 才能选择 lambda；结果按 Gold 完整 OR/AND 证据命中率、要点覆盖率、较小 lambda
  的顺序确定。Test 只接受复用已有选择，不参与调参。
- 导出匿名 Dev 评分材料、空白评分表，导入真实人工评分，复用已有校准统计入口。

这些功能不自动把实验变为正式评估。Gold 状态、Role 缺项、量表审查和 Test 暴露情况
仍需要如实披露。语义引用支持和学生等级适配质量由独立评估负责，不能由引用 ID 合法率代替。

## 1. 获取已经发布的开发输入

在仓库根目录、安装当前项目的 Python 环境中运行：

```bash
python scripts/fetch_v2_experiment_inputs.py --output-dir artifacts/v2-experiment-inputs
```

脚本固定下载并核对以下资产的 SHA-256，已存在但内容不同的文件会报错：

- [M3 Gold v0.1.2 开发包](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m3-gold-v0.1.2-dev-v1)：
  188 题，原始 split 为 162 个 `pending`、26 个 `proposed_test`。
- [M4 三教材开发语料](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m4-structure-v2-dev-v1)：
  `2.0.0-dev.m4-structure-v2-main-3553825`，5976 个 chunk。

下载目录包含原始文件、`corpus-release/` 及 `download_manifest.json`。
本包没有配套的 V2 Role 标签。26 道 Test 曾在 M6 检索实验中暴露，不能当作未见测试集。

## 2. 显式转换 Gold

M3 原始格式和原生 V2 格式不同，必须先转换。默认保留原 split；下面明确采用与现有
M6 开发诊断一致的临时映射 `pending → dev`、`proposed_test → test`。
映射只是运行标签，原标签逐题写入转换记录，不构成正式划分审批。

```bash
python -m cs30.v2.experiment_cli convert-gold \
  --gold artifacts/v2-experiment-inputs/gold_v0_1_1_integrated.jsonl \
  --corpus-dir artifacts/v2-experiment-inputs/corpus-release \
  --split-map docs/examples/v2-m7-provisional-splits.json \
  --output-dir artifacts/v2-experiment-inputs/converted-provisional
```

转换保留参考答案、原始章节坐标、证据注释和审查状态。新的教材身份只能由唯一的
chapter/block/原文匹配确定。无法唯一定位、跨 chunk 的片段或失效 block 需要 M4 提供
已解决的锚点；程序会拒绝猜测，不会通过改写 Gold 或忽略大小写来掩盖差异。

输出 `gold.jsonl`、`gold_bindings.jsonl`、`conversion_manifest.json`。
直接使用原生 V2 Gold 时不需要转换。

## 3. 生成评分标准草稿

```bash
python -m cs30.v2.experiment_cli rubrics \
  --gold artifacts/v2-experiment-inputs/converted-provisional/gold.jsonl \
  --output artifacts/v2-experiment-inputs/draft_rubrics.jsonl
```

每道可回答的开放题得到两个起始要点：主要答案是否正确、是否满足题目明确要求的完整性。
主要答案绑定该题真实参考答案及教材片段，简短术语题不会被额外要求推导。
草稿不生成人工审查 ID，也不把参考答案自动加入整段快捷匹配列表。
涉及计算、多个原子事实或可替代推理路径时，应按
[开放题评分说明](open-answer-scoring.md)细化逐题要点、单位、容差及 OR/AND 路径。
草稿可用于开发诊断，正式评估前仍需审查量表。

## 4. 准备 Role 标注

```bash
python -m cs30.v2.experiment_cli role-template \
  --corpus-dir artifacts/v2-experiment-inputs/corpus-release \
  --gold artifacts/v2-experiment-inputs/converted-provisional/gold.jsonl \
  --output artifacts/v2-experiment-inputs/dev_role_annotation_form.csv
```

表中包含 Dev BM25 top-20 的去重 chunk ID 和原文，Role 列留空。实际标注者填写
`definition`、`example`、`comparison`、`application`、`derivation`、`boundary` 之一。
空白、非法值、原文改动、未知或重复 chunk 会使导入失败。使用其他候选检索包时，应由其
相应候选全集提供标签；此模板只覆盖这里的 BM25 候选。

```bash
python -m cs30.v2.experiment_cli import-roles \
  --corpus-dir artifacts/v2-experiment-inputs/corpus-release \
  --form artifacts/v2-experiment-inputs/dev_role_annotation_form.csv \
  --annotator-id ACTUAL_ANNOTATOR_ID \
  --output-dir artifacts/v2-roles
```

标注者身份必须填写真实来源，机器预标注不能冒充人工。输出符合现有 M3/M8 交接格式的
`role_labels.jsonl` 和 `role_manifest.json`。Dev 和 Test 后续复用 lambda 时应使用同一
配套 Role 包，其文件摘要必须一致，并覆盖各自实际候选。旧 V1 Role 包会因版本不符被拒绝。

## 5. 冻结实验输入

配齐标签后的标准准备命令：

```bash
python -m cs30.v2.experiment_cli prepare \
  --corpus-dir artifacts/v2-experiment-inputs/corpus-release \
  --gold artifacts/v2-experiment-inputs/converted-provisional/gold.jsonl \
  --gold-conversion-manifest artifacts/v2-experiment-inputs/converted-provisional/conversion_manifest.json \
  --rubrics artifacts/v2-experiment-inputs/draft_rubrics.jsonl \
  --role-manifest artifacts/v2-roles/role_manifest.json \
  --model gpt-oss:20b --split dev \
  --output-dir artifacts/v2-dev-prepared
```

默认 lambda=0.35 是固定的探索参数；confidence=1.0 是三个控制实验等级共同使用的显式
输入，不能解释为已经测得的真实学生掌握度。两项都记录在 config 和运行 manifest 中。

若先做接线验证，移除 `--role-manifest`，明确添加 `--allow-missing-roles --limit 1`，
并使用新的输出目录。缺标签时按既有策略回退到原检索得分；报告会标为重排效果不可解释。
该开关不能把缺失标签变成已标注。`--limit` 只允许 Dev。

M6 保存的原生候选可通过 `--retrieval retrieval.jsonl` 导入，每行形状为：

```json
{"question_id": "QUESTION_ID", "retrieval": {"schema_version": "2.0", "query": "题干", "mode": "bm25", "hits": [], "provenance": {}}}
```

上例仅表示外层结构，真实文件的完整 provenance/hits 必须符合原生 V2 契约，不能直接
使用空对象。所有选中题目的候选必须齐全；程序核对正文及完整来源字段，不只比对 chunk ID。

准备目录保存原始 Gold/量表字节、固定候选、配置、完整预定矩阵、候选标签、语料 manifest、
精确 Gold 绑定、转换记录及 lambda 选择记录。运行前逐一核对文件摘要；改过输入就需要
重新准备一个目录。默认三个等级和四条件不可在运行时偷偷缩减。

```bash
python -m cs30.v2.experiment_cli check --prepared-dir artifacts/v2-dev-prepared
```

`check` 不调用模型，不验证模型服务连接；它验证的是输入和矩阵完整性。

## 6. 只在 Dev 上选择 lambda

需要完整的候选 Role 标签。程序不调用生成模型，不使用 Test 评分结果。

```bash
python -m cs30.v2.experiment_cli select-lambda \
  --prepared-dir artifacts/v2-dev-prepared --lambdas 0 0.1 0.2 0.35 0.5 \
  --output artifacts/v2-dev-selected-lambda.json
```

重新 `prepare` Dev 或 Test 时加 `--selected-lambda artifacts/v2-dev-selected-lambda.json`，
另选新的输出目录。Corpus、完整 Gold 文件、Role 文件摘要、candidate/evidence-k 和
confidence 必须与选择时一致。lambda 从选择文件读取；不在 Test 上重选。
命中目标以某个完整 Gold OR 路径中的每个 AND 片段均被选中为准，不能把部分证据拼成满分。
当前选择仍是开发结果；正式划分和参数冻结由团队确认。

## 7. 真实模型生成及报告

确认指定模型已在本机安装并且 Ollama 服务运行后：

```bash
python -m cs30.v2.experiment_cli run \
  --prepared-dir artifacts/v2-dev-prepared \
  --provider ollama --timeout 180 --max-output-tokens 2048 \
  --output-dir artifacts/v2-dev-run
```

这条命令真实调用生成模型。默认不调用 judge，所以开放题语义评分会留待复核。
有独立评分模型时加 `--judge-provider ollama --judge-model INDEPENDENT_JUDGE_MODEL`，
也可选 `openai` 并使用已有客户端的环境配置。不要把生成模型名称直接当作独立 judge。
探索性同模型自评需要显式 `--allow-self-judge`，仍不等于人工校准或正式评估。

输出如下：

- `expected_experiment.json`：完整预定矩阵。
- `saved_answers.jsonl`：逐单元原始答案和技术失败，直接兼容开放题评分入口。
- `generation_records.jsonl`：完整证据、条件与等级、重排过程、提示词摘要和每次模型原文。
- `generation_summary.json` / `generation_report.md`：分条件/等级的运行、耗时、用量统计。
- `run_manifest.json`：输入来源及摘要、运行配置、实现文件摘要、输出摘要和完成状态。
- `scoring/`：开放题正确性、覆盖率、未决队列和 Markdown/CSV 报告。

每完成一个单元立即写入详细记录和答案，并显示进度。中断时原目录保留，不会被重写。
没有自动续跑选项；可用已保存答案与原始预定矩阵独立评分，未保存单元保持 missing。
重新运行需要新目录。退出码：0 为处理完成且无未决；2 为输入/配置错误；
3 为输出已写出但仍有待评分项目或生成技术失败。

## 8. 人工校准材料

```bash
python -m cs30.v2.experiment_cli review-packet \
  --prepared-dir artifacts/v2-dev-prepared \
  --runs artifacts/v2-dev-run/saved_answers.jsonl \
  --question-count 10 --seed 0 --output-dir artifacts/v2-calibration-packet
```

按题目抽取 Dev 样本，然后包含这些题目所有已回答的实验单元；缺失和技术失败不伪装成
可评答案。给两位独立评分者各发 `rater_items.jsonl` 和一份 `rating_form.csv`。
材料包含完整问题、答案、参考答案、量表和证据，不包含条件、生成模型、学生等级或自动分。
`administrator_mapping.json` 由实验管理员保管，不发给评分者。

人工填写每条的 0/1/2 分和理由后，分别导入，rater ID 使用实际身份：

```bash
python -m cs30.v2.experiment_cli import-ratings \
  --packet-dir artifacts/v2-calibration-packet \
  --form path/to/completed-rater-a.csv --rater-id ACTUAL_RATER_A \
  --output artifacts/ratings-a.jsonl
```

对第二位评分者重复导入，随后将两份 JSONL 记录合并为一份 ratings 文件，调用
`cs30-score-open-answers calibrate`。有分歧时需提供真实仲裁记录；具体格式见
[评分说明](open-answer-scoring.md)。空白表、缺项目和无理由的评分不能导入为已完成人工评分。

## 交接边界

M7 的可运行代码、数据转换/检查、生成、评分衔接和校准材料工具已提供。
配套 V2 Role 的实际标注、逐题量表的人工审查、独立人工评分，以及正式 Dev/Test 划分和
批准仍依赖对应负责人完成。代码检查通过不代替这些工作；报告始终保留 development 标记。
