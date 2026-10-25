# M7 API Dev 三模型结果与 M8 交接（2026-10-26）

本轮 Dev 全量及独立重复生成已执行完成，完整性核验通过。**reportable=false**；这不是正式 Test 或质量评分结果。

| 模型（DeepInfra） | 格式 | Dev 成功 / 总数 | 独立重复成功 / 总数 | 保留失败 |
|---|---|---:|---:|---:|
| `openai/gpt-oss-20b` | JSON Object，reasoning_effort=low | 1848 / 1848 | 360 / 360 | 0 |
| `google/gemma-3-12b-it` | JSON Schema | 1848 / 1848 | 360 / 360 | 0 |
| `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` | JSON Object | 1773 / 1848 | 351 / 360 | 84 |

合计 **6624 单元：6540 answered、84 generation_error、0 最终截断**。answered 只表示通过生成侧格式与引用检查，不代表答案正确。
Llama 的 75 个 Dev 与 9 个重复失败均为严格输出校验失败，原样保留在分母，未修改解析器或挑选重跑。
其 smoke 为 117/120，另有 3 个格式失败；在记录诊断执行决定后运行完整矩阵，不表示通过正式质量接受阈值。
DeepInfra 对 Llama JSON Schema 的旧错误、Gemma 旧格式失败和已停用 Qwen 的探索均保留。

## 固定输入与配置

- 生成代码基线：`17cb2f3c25ac70b4b602f2b415a38761214b6110`；核心实现哈希逐项保存在原始 run manifest。
- 四教材共 6184 chunks；Gold v0.1.3 共 341 题，154 Dev / 187 Test，352 条精确证据绑定。
- M6 检索器：Qwen3-Embedding-0.6B，Dense 0.10 / BM25 0.90，top-20 原生候选。
  候选 SHA-256：`1bb7e491b6506ad8cdabcf6831db83baac06128b9392f5df973e183c54d65ca9`。
- 本轮 Dev 选 λ=0.1：完整证据命中率 80.95%，λ=0 为 81.82%；绝对下降 0.87 个百分点，满足不超过 1 个百分点的选择规则。
- Dev 为 154题 × 3档 × 4条件；独立重复为固定抽样的 30题 × 12单元。三个模型使用相同输入与 λ。
- 每个模型冻结 temperature=0、输出格式和 token 预算，具体 extra_body、seed、token 上限及版本限制见各 run manifest。
  公开模型别名未核实为不可变权重版本，不宣称逐字可复现或正式可报告。
- Qwen 因持续限流由用户决定替换为 Llama；这是本轮开发执行选择，不能冒充 Leader 已登记的正式 Test 对比方案。

## 费用

按所有已保存真实请求返回的 token 用量估算 **US$0.80695055**：GPT 0.24397569、Gemma 0.41074310、Llama 0.15015858、历史 Qwen 0.00207318。
包含 probe、smoke、基线、重复和历史失败/重试。未报告 usage 的错误响应不代表免费，最终以平台账单为准。
预付 US$15 是账户充值，并非本轮实际花费。详细数据见 [final-generation-summary.json](final-generation-summary.json)。

## M8 接手方式

本机已准备并验证完整包，包含每模型 Dev 与重复的 prepared/run 目录、历史真实探索、全部 checkpoints/api_cache、输入来源与哈希、λ 选择结果和本报告。
**公开原始附件尚待用户明确确认，当前 GitHub 仅提供结果汇总、核验记录和复现工具。** 包内可能包含完整教材证据和 API 提示词/返回；附件链接在发布前不可下载。
同名 run_id 可能跨批次复用；评分结果和缓存必须绑定 **run 目录 + manifest/答案哈希**，不能只按 run_id 合并。
每个重复单元须与基线的对应单元一起交给同一冻结 judge/rubric 评分；失败保留在原有分母，不把缺失答案当成功。

原始 manifest、缓存及检查点保持原字节；其中的历史本机路径仅是来源信息。解压后按目录 basename 定位。
仓库中的汇总副本只将本机绝对结果路径改为相对路径；包内原始记录未经改写。
在仓库根目录解压，使其成为 `artifacts/m7-readiness-20261026/`，安装项目依赖后可离线核验：

```bash
python scripts/verify_m7_handoff.py --root artifacts/m7-readiness-20261026
```

核验不会调用模型：检查包内文件 SHA-256、六批冻结输入、完整矩阵、输出哈希、答案/轨迹/检查点一致性、引用成员关系及重复诊断的 manifest 绑定。

## 文本重复诊断与边界

| 模型 | 成功配对 / 360 | 技术失败配对 | 答案文本变化率 |
|---|---:|---:|---:|
| GPT | 360 | 0 | 74.17% |
| Gemma | 360 | 0 | 33.06% |
| Llama | 349 | 11 | 44.99% |

这是逐字文本比较，**不表示正确率、模型排名或评分噪声底**。Llama 配对失败数包括基线与重复任一侧失败，因此不同于重复批次的 9 个失败。
M8 的评分噪声底仍待实际评分；δ 不可从文本变化率推导。

**未运行 M8 judge，未生成正式 Test 答案。** Test 须等 M8 冻结 judge、画像/清单/适用范围完成审核冻结，以及 Leader 登记 δ、主要比较和对比抽样方案后执行一次。
主模型 Test 为 187 × 12 = 2244 单元；对比模型规模仍由 Leader 决定。开发产物不能代替该登记。

发布包不含 API 密钥、本机 .env 配置、账户截图或账单资料。教材与 Gold 依各原来源许可使用，打包不改变其许可。
上传结果供团队交接，不等于 M8 已确认接收或冻结方案。后续范围为交接确认及满足前置条件后的 Test 生成。

## 预定附件与校验（尚未发布）

- 待授权发布的 [GitHub 开发结果 Release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m7-api-dev-20261026)
- 待授权上传的 [完整结果包](https://github.com/yshe0376/cs30-personalised-rag/releases/download/v2-m7-api-dev-20261026/m7_api_dev_20261026.tar.gz)（90.5 MiB，22117 个文件）
- SHA-256：`4020a9a984f759cf1948d1cd9140cf66aab4679b7f3c04a65ab4e41f686ba7ee`
- [发布元数据](release_asset.json)

```bash
shasum -a 256 m7_api_dev_20261026.tar.gz
tar -xzf m7_api_dev_20261026.tar.gz
```

## 发布验证

完整包解压后离线核验通过（22116 个证据文件，另含清单本身）；全仓回归 **1214 passed / 3 skipped**，启动器专项 **7 passed**，静态检查与差异空白检查通过。测试允许本机模拟 HTTP 服务，没有调用真实付费 API。见 [publication-verification.json](publication-verification.json)。
