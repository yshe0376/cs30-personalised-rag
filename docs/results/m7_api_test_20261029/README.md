# M7 主模型 Test 生成交付（2026-10-29，未评分）

gpt-oss-20b 已执行全部 **187 题 × 3 档等级 × 4 条件 = 2244 个单元**：
**2243 answered、1 output_truncated**。截断单元保留原始检查点和分母。
这是完整生成交付，`reportable=false`；尚未进行 Test 质量评分。

| 条件 | 成功回答 | 输出截断 | 总数 |
|---|---:|---:|---:|
| P0R0 plain | 561 | 0 | 561 |
| P1R0 prompt only | 561 | 0 | 561 |
| P0R1 reranking only | 560 | 1 | 561 |
| P1R1 combined | 561 | 0 | 561 |
| 合计 | 2243 | 1 | 2244 |

## 固定配置与范围

- 生成代码基线：`d1c216fdabf8067fe0b4d35e4321b93a1ae3ea8c`。
  生成实现的 13 个文件与已验证 Dev 运行逐项哈希一致；本次未修改生成实现或提示词。
- 模型：DeepInfra `openai/gpt-oss-20b`，temperature=0、reasoning_effort=low、
  JSON Object、4096 输出 token、3 并发。公开别名尚未核实为不可变权重版本。
- 检索：Qwen3-Embedding-0.6B，Dense 0.10 / BM25 0.90，原生 top-20 候选，
  最终送入 5 条证据；Dev 选 λ=0.1，profile confidence=1。
- Gold v0.1.3 共 341 题，154 Dev / 187 Test 无题号交集；全部 30 道
  proposed_test 和 82 道 CK-12 题均包含于此次 Test。四教材语料和 Role 标签继续哈希绑定。
- 候选 SHA-256：`1bb7e491b6506ad8cdabcf6831db83baac06128b9392f5df973e183c54d65ca9`。
  划分 SHA-256：`991d9a68d0fa256b5d418549ffa62c331c6f31c0aacbc144f064f507bfd100fb`。
- Dev λ 全网格已离线复算，选择与指标均一致。Test 未用于调整 λ、prompt、格式或 token 上限。
- 只执行原先指定的主模型。其他两个模型仅保留离线准备记录，没有运行其 Test，也不在本交付中。

## Release 与文件

- [完整 Test 生成 Release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m7-api-test-gpt-oss20b-20261029)
- [完整原始结果包](https://github.com/yshe0376/cs30-personalised-rag/releases/download/v2-m7-api-test-gpt-oss20b-20261029/m7_api_test_gpt_oss20b_20261029.tar.gz)
- [归档校验文件](https://github.com/yshe0376/cs30-personalised-rag/releases/download/v2-m7-api-test-gpt-oss20b-20261029/SHA256SUMS.txt)
- [核验摘要](verification.json)；发布及公开下载核验见 [发布记录](publication.json)。

完整包为 27,225,573 字节，SHA-256：
`c9545bf50cb161a8f923546431ba9efda8dd3c40077114061f9827a2a4511ebc`。
含 6799 个清单覆盖文件及清单本身；大体积数据不进入 Git。

包内保留 `gpt-oss20b-prepared/`、`gpt-oss20b-run/` 的全部冻结输入、答案、轨迹、
checkpoints、API 请求与返回缓存，以及 M8 原生适配输入、187 题正确性量表草稿、
画像/配置快照、核验程序和状态表。原始字节未为发布而改写。
包内 README 的发布状态为打包时快照，当前发布状态以本页及 Release 页面为准。

## M8 接手与离线核验

解压到新目录，以当前仓库或生成实现与上述基线一致的副本核验：

```bash
python EXTRACTED/m7-api-test-20261029/tools/verify_handoff.py \
  --package EXTRACTED/m7-api-test-20261029 \
  --repo PATH_TO_REPOSITORY
```

核验不需要 API 密钥，也不调用模型。M8 从 `handoff_manifest.json` 的相对路径读取：

- `evaluation-adapter/generation_evaluation_inputs.jsonl`：2244 条原生评分输入。
- `evaluation-adapter/adapter_manifest.json`：源运行、答案、Gold、λ 与输入文件绑定。
- `test-correctness-rubrics/`：187 题参考绑定量表草稿，审核状态仍为 pending。
- `evaluation-config/`：已冻结画像、沿用的 Dev judge 配置和明确标为 draft 的适用范围标签。

评分与缓存必须绑定源运行目录、run manifest/答案哈希；不得仅按 run_id 合并。
不得把缺失 judge 分数填成 0，或将其他批次缓存冒充本次独立评分。
输出截断依现有系统级正确性规则处理，继续保留独立原因与原始分母。

## 核查结果与费用

- 全仓工程回归：**1434 passed / 0 failed / 0 skipped**。此前缺失的 M2 解析输出与
  固定 tokenizer 已补齐；全部测试均执行。
- 逐项核验 2244 份答案、轨迹和检查点；重算所有证据选择与原始 prompt 哈希，
  验证 2243 份已生成答案的引用归属及全部输出摘要。
- M8 原生读取接口接受全部 2244 条评分输入；新位置解压后再验通过，文件损坏被拒绝。
- 6799 个文件摘要与密钥扫描通过；核验和打包没有追加模型调用。
- 运行共 2261 次 HTTP 尝试，2260 次返回成功、1 次限流后按既定规则恢复，最终无待完成请求。
  返回用量为 6,662,812 input / 250,192 output tokens。
  按[核查当日价目](https://deepinfra.com/openai/gpt-oss-20b)估算已知用量费用 **US$0.23491124**。
  未返回 usage 的错误响应不是实测免费，最终以平台账单为准。

## 结论边界

本次是用户批准的 Test 生成交付，不能替代尚未完成的评估冻结和审核。
Test 质量评分、judge 独立重复/顺序反转及第二家族检查、独立人工审核、
适用范围标签审核冻结与正式统计登记均不由此次生成核验宣称完成。
Dev 的 280 个未解决请求及 12 条正确性待复核记录继续保留，未在本次补跑或删去。

画像沿用 Leader 的独立物理复核豁免；Gold 与 Role 的开发状态保持可见。
187 题仅相对于生成侧调参未暴露，曾进入 M6 检索侧开发比较。
因此不能把生成成功率当正确率，也不能将本交付称为正式质量评估通过。
原始教材许可与署名沿用上游交付，非商业课程研究的使用范围不变。
