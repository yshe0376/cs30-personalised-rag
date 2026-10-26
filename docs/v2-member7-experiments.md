# M7 V2 API 批量生成与 M8 交接

入口：`python -m cs30.v2.experiment_cli`（安装后为 `cs30-experiment-v2`）。
M7 负责固定候选上的个性化重排、Dev λ 选择、四条件生成及交付；M8 负责 judge、
校准、评分与评估报告。本文对应 2026-10-23 任务及 #201 的生成侧划分。

**2026-10-26 执行更新：** [真实三模型 Dev 与独立重复结果及完整附件](results/m7_api_dev_20261026/README.md)
已生成，λ 重选为 0.1；模型为 DeepInfra 的 gpt-oss-20b、Gemma 3 12B 与 Llama 3.1 8B。
合计 6,624 个单元执行完成（6,540 answered、84 个 Llama 格式失败保留），无最终截断。
Qwen 因限流按用户决定替换，历史记录和费用保留；不表示 Leader 已批准新的正式 Test 对比方案。
结果仍为 `reportable=false`，未调用 M8 judge、未运行 Test。下文未注明日期的待执行说明
是 2026-10-23 的准备快照，当前状态以新结果说明为准；Test 冻结要求仍有效。

2026-10-23 已完成真实 Gold 转换与输入审计：341 题、154 Dev / 187 Test、352 条精确
证据绑定，四教材 6,184 个 chunk 的 Role 标签全部覆盖。
见 [readiness](results/m7_api_readiness_20261023/README.md)。
M6 候选已发布（见下文「M6 候选」）；API 提供方、固定模型版本和预算尚未指定。新 λ、真实 API 冒烟、
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

`python scripts/fetch_v2_experiment_inputs.py --output-dir <新目录>` 会一次下载上面三项
和下文的 M6 候选，逐字节核验固定的 SHA-256 并解压语料；若用它，把下面的变量改指该目录。

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
必须是 M6 发布的 [Qwen3 候选](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/m6-w6-qwen3-hybrid-dev-v1)
`m7_qwen3_d0.10_b0.90_original_top20.jsonl`（SHA-256 `1bb7e491b6506ad8cdabcf6831db83baac06128b9392f5df973e183c54d65ca9`），
即全部 341 题的 Qwen3-Embedding-0.6B Dense 0.10 / BM25 0.90、top-20 候选，与决策表 2026-10-23 的系统检索器一致。
`--require-retrieval` 在 prepare 阶段提前检查；manifest 记录候选文件 SHA-256。
API 的 `run --provider openai-compatible` 还会**强制拒绝**缺少 `source_retrieval_sha256` 的
准备目录，即使 prepare 时两个参数都忘记，也不会把隐式 BM25 当成正式候选运行。
此保护同时适用于 CLI、直接 Python 调用和 `--resume`，在创建输出目录/读取密钥前检查。
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
`--extra-body` 接受平台参数 JSON 对象；参数原文内容（规范化 JSON）进入 client manifest、
请求 payload 和缓存身份，`--resume` 必须完全一致。不能覆盖 model/messages/temperature/
max_tokens/seed/response_format 等受控字段，不能在这里传认证信息。
平台只提供可漂移别名时，要如实说明版本不可验证，不能填一个自创版本号冒充固定版本。

先核对提供方实时输入/输出价格；以冒烟实测平均输入 token 估算费用，输出取 token 上限。
`M7_MAX_OUTPUT_TOKENS` 必须先按模型、推理强度和截断率冒烟确定；gpt-oss 的推理 token 也会
占输出预算，不能默认 2048 足够。提高 token 预算后须重新估费，并在提供方设置金额上限：

```bash
python -m cs30.v2.experiment_cli estimate \
  --prepared-dir artifacts/m7-api-dev-final \
  --input-usd-per-million "$M7_INPUT_PRICE" --output-usd-per-million "$M7_OUTPUT_PRICE" \
  --mean-input-tokens "$M7_MEAN_INPUT_TOKENS" --max-output-tokens "$M7_MAX_OUTPUT_TOKENS" \
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
  --api-key-env M7_GENERATION_API_KEY --extra-body "$M7_EXTRA_BODY" \
  --structured-output "$M7_OUTPUT_FORMAT" \
  --timeout 120 --max-output-tokens "$M7_MAX_OUTPUT_TOKENS" --transport-retries 3 \
  --concurrency 3 --max-api-requests "$M7_APPROVED_REQUEST_CAP" --stop-after-errors 3
```

上例是**批准预算后的完整 Dev 命令**，1,848 个单元；冒烟需替换 prepared/output 目录和请求上限。
正式运行前，`M7_OUTPUT_FORMAT` **必须**填写冒烟验证通过的固定值
`json_schema` / `json_object` / `text`，不能使用 `auto`；`M7_EXTRA_BODY` 和 token 预算也同时冻结。
例如平台的 JSON Object 冒烟成功后可设 `M7_OUTPUT_FORMAT=json_object`。
`auto` 仅用于探索平台能力，会逐单元重复发送不支持的 Schema 探测请求，这些 400 也计入请求预算。
不能用一个已开始的 `auto` 批次改参数续跑：固定设置后新建正式 run 目录。
同模型支持 3–5 并发，每个模型独立进程和输出目录，同一目录受单写者锁保护。
温度固定为 0；只有提供方支持时才加 `--api-seed`，默认不发送 seed。
本轮只用 API。旧 `openai` Responses / `ollama` 入口供历史兼容，不用于新实验。

模型特有参数也须先冒烟验证，平台确认支持后再使用。例如：

```bash
# 支持 reasoning_effort 的 gpt-oss API：固定推理强度，不能仅依赖平台默认值。
export M7_EXTRA_BODY='{"reasoning_effort":"low"}'
# Qwen3 8B 的 vLLM 兼容端点：若平台支持该开关，关闭 thinking 后再验证严格 JSON。
export M7_EXTRA_BODY='{"chat_template_kwargs":{"enable_thinking":false}}'
```

这两行是**不同模型的独立示例**，按实际平台选其一或使用其文档指定的 JSON；不承诺所有
托管商都支持相同字段。[Groq reasoning 文档](https://console.groq.com/docs/reasoning) 说明
其 gpt-oss 的 reasoning_effort；[Qwen vLLM 文档](https://qwen.readthedocs.io/en/latest/deployment/vllm.html)
说明 chat_template_kwargs/enable_thinking。平台若采用顶层 `enable_thinking`，就按其文档传入。
Qwen 若仍把 `<think>…</think>` 放进 content，冒烟应判为未通过，核对 thinking 开关/提供方；
不静默删除任意思考文本或放宽答案契约。单独的 reasoning 字段留在原始响应缓存中，不当成答案。

冒烟时的 `auto` 先用 JSON Schema；只有明确返回不支持 response_format 的 400/422 才降到
JSON Object，再降到普通文本。正式运行固定冒烟确认的模式。
manifest 的 `client.structured_output` 记录请求策略；`api_audit.http_attempts_by_format` 和
`successful_responses_by_format` 记录实际发送/收到 2xx 的模式及数量，原始响应缓存也保存
`format_mode`；2xx 表示平台接受请求，答案是否通过本地 schema 校验仍以单元状态为准。
普通文本仍需满足严格 JSON 契约，仅容忍整个输出包在 JSON 代码围栏中。
不接受任意说明文字、不放松必填字段/引用约束；非法输出进入原有有界修复。
429/临时 5xx/连接故障执行有界退避，尊重 `Retry-After`；等待超过 60 秒预算时停止该调用，稍后恢复。
`finish_reason=length` 单独记为 `output_truncated`，含空内容。
401/403/404 会在保存原始错误后**直接终止整批**，不进入生成层重试，也不再处理后续题目。
并发中已发送的请求可能结束并落检查点；共享的致命错误状态阻止其余 worker 再发新请求。
修正密钥/权限后用原参数 `--resume`；模型或 endpoint 要改则建立新批次，不能混入旧批。

## 中断、断线与恢复

重用完整原运行命令，追加 `--resume`。恢复前核验冻结输入、代码、提供方、endpoint、
模型版本、温度、seed、extra-body、输出格式、token 上限；不同模型或配置不能混入同批。
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

## Dev 重复生成诊断、M8 评分噪声底与 Test

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
整段答案逐字不一致率在 API 上可能接近 100%，仅作文本复现诊断；final_choice 和引用集合
变化用于解释可观察的答案/证据差异，它们也不能直接代替评分指标或用于设定 δ。
命令名 `noise-floor` 保留兼容，输出明确标记 `diagnostic_only=true`、
`scoring_noise_floor_status=pending_m8_scoring`，不会宣称评分噪声底已经完成。

**360 个重复单元必须连同基线中对应的 360 个单元交给 M8 评分**。交接前与 M8 确认：
沿用同一冻结 judge、rubric、评分参数及失败分母政策；两批答案的缓存/结果分别绑定
“run 目录 + manifest/答案哈希”，避免重复 run_id 误复用旧评分。
M8 在两批配对的正确性、适配和其他登记指标上估计波动，并报告评分层面的噪声及不确定性；
δ 与主要比较仍由 Leader 预先登记，不能从文本不一致率推导。
M7 交付重复答案和证据，M8 接管评分；本次没有运行或变更 M8 judge，也没有实测评分噪声值。
报告须明确“API 温度为 0 或提供 seed 仍不能保证逐字复现”，分别列出文本诊断和 M8 的评分噪声结果，
不能用历史本地结果代替。

Test 只在 M8 冻结 judge、Leader 登记 δ/主要比较及对比模型抽样方案后运行一次。
主模型 187 × 12 = 2,244 单元；对比模型规模由 Leader 决定，不能擅自按原 60 × 6 开跑。
不在 Test 选择 λ、修 prompt 或测噪声底。

## 交付 M8

交付完整基线与重复批次的 prepared/run 目录、文本诊断报告及上述 M8 评分交接项，包含：
`input_manifest.json`、`expected_experiment.json`、`saved_answers.jsonl`、
`generation_records.jsonl`、`generation_summary.json`、`generation_report.md`、
`run_manifest.json`、全部 `checkpoints/` 和 `api_cache/`。
manifest 绑定原始 Gold、划分、候选、Role、模型及代码身份；生成产物仍为 `reportable=false`，
不因工程测试通过而自动成为正式评估结论。原始教材与大体积记录放 Release/本地 artifacts，不提交进 Git。
