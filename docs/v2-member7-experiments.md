# M7 V2 API 批量生成与 M8 交接

入口：`python -m cs30.v2.experiment_cli`（安装后为 `cs30-experiment-v2`）。
M7 负责固定候选上的个性化重排、Dev λ 选择、四条件生成及交付；M8 负责 judge、
校准、评分与评估报告。本文对应 2026-10-23 任务及 #201 的生成侧划分。

2026-10-23 已完成真实 Gold 转换与输入审计：341 题、154 Dev / 187 Test、352 条精确
证据绑定，四教材 6,184 个 chunk 的 Role 标签全部覆盖。
见 [readiness](results/m7_api_readiness_20261023/README.md)。
M6 新候选尚未发布；API 提供方、固定模型版本和预算尚未指定。新 λ、真实 API 冒烟、
全量生成和实测噪声底均未完成。没有生成 Test 答案，也没有调用付费 API。

[旧 1,944 条 Ollama Dev 答案](results/m7_v2_dev_20261017_lambda02/README.md)
使用三教材、旧 Gold 和 BM25，只供 M8 提前校准，不能进入这轮 API 实验报告。
主模型为托管的 gpt-oss-20b；对比模型为 Qwen3 8B，加 Llama 3.1 8B / Gemma 3 12B
二选一（Leader 决定）。真实 API 的模型 ID、部署版本、提供方需在运行前登记。

## 固定输入并转换 Gold

下载下面发布包，按 `results/m7_api_readiness_20261023/readiness.json` 核验 SHA-256：

- [四教材语料](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m4-four-book-dev-v1)：
  `M4_to_M5_four_book_corpus_a1fe99e.zip`，解压后目录为 `2.0.0-dev.m4-four-book-main-a1fe99e/`。
- [四教材 Role](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-role-labels-v2-four-book-dev-v1)：
  `role_labels_v2.jsonl` 与 `role_labels_v2_provenance_manifest.json` 放在同一目录。
- Gold v0.1.3 的 Release 尚待 M3 发布。本次读取的是 [#199 固定提交中的文件](https://github.com/yshe0376/cs30-personalised-rag/blob/7dc50ab329c1acc75b00a7a6592148c610ed26f0/m3_gold/final_v0_1_1/gold_v0_1_3.jsonl)，
  SHA-256 为 `7d69af416591b64198bf25806424347366eb2123fdcdcf36ad757d37c4f942b8`。
  M3 发布后必须核对相同字节；若有变更，重新转换和审计。

下面变量指向已校验的本地文件；所有输出目录必须是新目录：

```bash
export M7_CORPUS=artifacts/m7-api-readiness-20261023/inputs/corpus/2.0.0-dev.m4-four-book-main-a1fe99e
export M7_GOLD=artifacts/m7-api-readiness-20261023/inputs/gold_v0_1_3.jsonl
export M7_ROLES=artifacts/m7-api-readiness-20261023/inputs/role_labels_v2_provenance_manifest.json
export M7_CONVERTED=artifacts/m7-api-readiness-20261023/converted
python -m cs30.v2.experiment_cli convert-gold \
  --gold "$M7_GOLD" --corpus-dir "$M7_CORPUS" \
  --split-map docs/examples/v2-generation-split-dev154-test187.json \
  --output-dir "$M7_CONVERTED"
```

转换按题号检查全部 Gold 的精确覆盖，拒绝遗漏、多余 ID、重复 JSON 键和无效划分。
不把数目硬编码为 341，因此合成测试和未来版本也能复用；当前固定文件精确为 154/187。
`conversion_manifest.json` 保存原始划分、逐题映射、各 split 数量和**输入文件原始字节**哈希。
旧的标签映射仅保留兼容。参考答案和原始章节坐标不变，证据按章节/block/原文唯一匹配；
参考答案不进入生成提示词。30 道 `proposed_test` 和全部 82 道 CK-12 题都在 Test。

## M6 候选、5 题准备冒烟与 Dev λ

取得 M6 的**原生 V2 FrozenRetrieval JSONL** 后，先核对交付摘要，再设置 `M7_RETRIEVAL`。
必须是全部 341 题的 BGE-M3 Dense 0.10 / BM25 0.90、top-20 候选。
`--require-retrieval` 防止遗漏参数时静默回落到 BM25；manifest 记录候选文件 SHA-256。
这里的模型变量必须填写提供方实际支持的固定模型 ID，不沿用 Ollama 的 `gpt-oss:20b`。

```bash
export M7_MODEL='填写托管 API 的固定模型 ID'
export M7_RETRIEVAL='填写已核验的 M6 原生候选文件路径'
python -m cs30.v2.experiment_cli prepare \
  --corpus-dir "$M7_CORPUS" --gold "$M7_CONVERTED/gold.jsonl" \
  --gold-conversion-manifest "$M7_CONVERTED/conversion_manifest.json" \
  --role-manifest "$M7_ROLES" --retrieval "$M7_RETRIEVAL" --require-retrieval \
  --model "$M7_MODEL" --split dev --candidate-k 20 --evidence-k 5 \
  --limit 5 --output-dir artifacts/m7-api-prepare-smoke
python -m cs30.v2.experiment_cli check --prepared-dir artifacts/m7-api-prepare-smoke
```

去掉 `--limit 5`，另用新目录 `artifacts/m7-api-dev-candidates` 准备完整 Dev，然后：

```bash
python -m cs30.v2.experiment_cli select-lambda \
  --prepared-dir artifacts/m7-api-dev-candidates \
  --lambdas 0 0.1 0.2 0.35 0.5 --output artifacts/m7-api-dev-lambda.json
```

只计算检索完整证据命中率，不调用 LLM/judge。在三个等级合并的 154 × 3 = 462 个 case 上，
选命中率不低于 λ=0 减**绝对 1 个百分点**的最大正 λ；没有合格正值就停止。
RRF 分数分布已变，旧 λ=0.2 不可直接沿用。保存的选择文件绑定候选源 SHA-256，
最终 `prepare` 必须仍传相同候选文件，附加 `--selected-lambda artifacts/m7-api-dev-lambda.json`，
输出到 `artifacts/m7-api-dev-final`。不能从另一候选文件或隐式 BM25 借用选择结果。

## API 配置、预算与逐模型冒烟

新 provider 为 `openai-compatible`，使用 [Chat Completions 协议](https://developers.openai.com/api/reference/resources/chat)，
`--base-url` 为 API 根地址（需要时含 `/v1`），程序追加 `/chat/completions`。
密钥只从 `--api-key-env` 指定的**环境变量名**读取；不会自动加载 `.env`。
`--provider-name` 记录托管平台，`--model-version` 记录平台承诺的固定权重/部署版本；
同时记录响应实际 model、system_fingerprint（若有）、请求 ID、completion ID、token 用量。
平台只提供可漂移别名时，要如实说明版本不可验证，不能填一个自创版本号冒充固定版本。

先核对提供方实时输入/输出价格；以冒烟实测平均输入 token 估算费用，输出取 token 上限：

```bash
python -m cs30.v2.experiment_cli estimate \
  --prepared-dir artifacts/m7-api-dev-final \
  --input-usd-per-million "$M7_INPUT_PRICE" --output-usd-per-million "$M7_OUTPUT_PRICE" \
  --mean-input-tokens "$M7_MEAN_INPUT_TOKENS" --max-output-tokens 2048 \
  --max-api-requests "$M7_APPROVED_REQUEST_CAP" --output artifacts/m7-api-cost-plan.json
```

输出只是假设条件下的规划金额；输入长度和计费可变化。还须在提供方账户设置批准的金额上限。
`--max-api-requests` 是本地**累计 HTTP 尝试上限**：失败、限流、格式降级、重试及已中断请求都计入，
跨 `--resume` 累计，达到后立即停止。它不等同美元硬上限。明确增加此参数才可扩大原批次请求预算，
变更记录在 `budget_history`；不能取消或降低原有上限。未批准预算时只做约定的冒烟，不跑全量。

按上面的 prepare 流程使用 `--limit 10`，逐模型各建一个目录，完成约 10 Dev 题 × 12 单元冒烟。
先检查截断、解析/引用失败率和实测用量，再固定输出预算及格式模式。每个模型都单独
`prepare --model`，共用相同 Gold、候选、Role、λ。以下 API 配置需由实际提供方填写：

```bash
python -m cs30.v2.experiment_cli run \
  --prepared-dir artifacts/m7-api-dev-final --output-dir artifacts/m7-api-dev-run \
  --provider openai-compatible --base-url "$M7_BASE_URL" \
  --provider-name "$M7_PROVIDER" --model-version "$M7_MODEL_VERSION" \
  --api-key-env M7_GENERATION_API_KEY --structured-output auto \
  --timeout 120 --max-output-tokens 2048 --transport-retries 3 \
  --concurrency 3 --max-api-requests "$M7_APPROVED_REQUEST_CAP" --stop-after-errors 3
```

上例是**批准预算后的完整 Dev 命令**，1,848 个单元；冒烟需替换 prepared/output 目录和请求上限。
同模型支持 3–5 并发，每个模型独立进程和输出目录，同一目录受单写者锁保护。
温度固定为 0；只有提供方支持时才加 `--api-seed`，默认不发送 seed。
本轮只用 API。旧 `openai` Responses / `ollama` 入口供历史兼容，不用于新实验。

`auto` 先用 JSON Schema；只有明确返回不支持 response_format 的 400/422 才降到 JSON Object，
再降到普通文本。也可在冒烟后固定 `json_schema` / `json_object` / `text`。
普通文本仍需满足严格 JSON 契约，仅容忍整个输出包在 JSON 代码围栏中。
不接受任意说明文字、不放松必填字段/引用约束；非法输出进入原有有界修复。
429/临时 5xx/连接故障执行有界退避，尊重 `Retry-After`；等待超过 60 秒预算时停止该调用，稍后恢复。
`finish_reason=length` 单独记为 `output_truncated`，含空内容。

## 中断、断线与恢复

重用完整原运行命令，追加 `--resume`。恢复前核验冻结输入、代码、提供方、endpoint、
模型版本、温度、seed、输出格式、token 上限；不同模型或配置不能混入同批。
并发数可调整，密钥可轮换但仍使用原环境变量名。

每个单元有原子检查点；HTTP 请求在发送前持久化，返回在解析前持久化。
`api_cache/` 保留实际请求 payload、原始返回、HTTP 状态、耗时及请求 ID，**不保存认证头/密钥**。
已收到且落盘的响应即使尚未形成单元检查点，恢复时也可复用，避免重复付费。
相同 prompt 的不同单元仍独立调用；噪声底必须用新目录，不能重用基线缓存。
连接已被平台接收但本地尚未落盘就中断的请求可能重复计费，普通 API 无法保证 exactly-once；
这些 pending 请求计入本地请求预算，账单仍须与提供方核对。

成功单元不重跑；仅纯 provider 失败单元可恢复，其旧检查点留在 `checkpoints/superseded/`。
引用、解析或截断失败保留在分母中；若需调整格式/token 配置，应重建完整批次。
聚合文件中断时可能不完整，从原子检查点重建。并发模式每个 worker 完成后即写检查点，
聚合文件最终按冻结矩阵顺序输出；停止后等待正在执行的有界请求结束，途中可再次恢复。
`run_manifest.json` 的 `api_audit` 汇总全部 HTTP 尝试及平台返回的 token 用量（含被替代失败），
缺失用量不代表免费。退出码：0 完成；3 完成但有失败/截断；2 配置/预算/服务停机错误。

## 实测噪声底与 Test

已固定 [30 题 Dev 重复样本](results/m7_api_readiness_20261023/noise_question_ids.json)，
从排序后的 154 Dev ID 以 seed=20261023 抽样；这是抽样 seed，不是 API seed。
完成基线后，以相同输入/配置 `prepare`，附加：

```bash
--question-ids docs/results/m7_api_readiness_20261023/noise_question_ids.json
```

输出到新的 prepared 目录；不加 `--limit`。以相同 API 设置在**新 run 目录**独立生成 360 个单元，
使用单独批准的请求预算。然后：

```bash
python -m cs30.v2.experiment_cli noise-floor \
  --baseline-dir artifacts/m7-api-dev-run --repeat-dir artifacts/m7-api-noise-run \
  --output artifacts/m7-api-noise-floor.json
```

报告校验输出哈希、检查点、来源、模型版本、prompt 和证据一致性。
以成功配对数为不一致率分母，另外列出技术失败配对数、final_choice 变化和引用集合变化。
完整结构化答案精确相等是文本噪声诊断，不是语义正确性或 judge 分数；后两者归 M8。
报告须明确“API 温度为 0 或提供 seed 仍不能保证逐字复现”，并填入这次实测数据，不能用历史本地结果代替。

Test 只在 M8 冻结 judge、Leader 登记 δ/主要比较及对比模型抽样方案后运行一次。
主模型 187 × 12 = 2,244 单元；对比模型规模由 Leader 决定，不能擅自按原 60 × 6 开跑。
不在 Test 选择 λ、修 prompt 或测噪声底。

## 交付 M8

交付完整 prepared/run 目录及独立噪声报告，包含：
`input_manifest.json`、`expected_experiment.json`、`saved_answers.jsonl`、
`generation_records.jsonl`、`generation_summary.json`、`generation_report.md`、
`run_manifest.json`、全部 `checkpoints/` 和 `api_cache/`。
manifest 绑定原始 Gold、划分、候选、Role、模型及代码身份；生成产物仍为 `reportable=false`，
不因工程测试通过而自动成为正式评估结论。原始教材与大体积记录放 Release/本地 artifacts，不提交进 Git。
