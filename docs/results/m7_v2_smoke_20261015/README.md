# M7 V2 真实模型接线验收：2026-10-15

本目录是一次真实模型的小批量开发验收，`reportable=false`。
不是 188 题全量实验，不是人工校准结果，也不提供正式准确率。

## 实际运行

- 输入来自仓库的 M3 Gold v0.1.2 与 M4 三教材 V2 开发 Release，下载指纹见
  `download_manifest.json`。
- 全部 188 题完成原生 V2 转换，195 个 Gold 片段完成精确 chapter/block/原文定位。
- 为接线采用显式临时映射 `pending → dev`、`proposed_test → test`；完整原标签保留在
  本地转换记录中。已有 26 题 Test 暴露情况保持不变，本次不运行 Test。
- 从映射后的 Dev 题按 ID 排序取第一题 `sciq-train-00004`；三个等级 × 四条件 = 12 单元。
- 生成模型为本机 Ollama `gpt-oss:20b`，temperature=0，最多输出 2048 token，超时 180 秒。
  运行后的模型摘要见 `local_model_snapshot.json`，模型 digest 为
  `17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7`。
- 12 单元全部成功回答，12 次模型调用，技术失败 0；本机调用耗时合计约 77.15 秒。
  提供方报告输入 44726、输出 940 token。耗时是调用累计，不是全流程墙钟耗时。
- 生成实现文件指纹与验收时源文件逐一一致，记录在 `run_manifest.json`。

## 必须保留的限制

该题 top-20 候选尚无配套 V2 Role 标签，本次明确使用 `--allow-missing-roles`：
重排回退到检索得分。因此这次运行证明四条件接线和数据保存正常，不能据此比较重排收益。
lambda=0.35 为固定探索参数；confidence=1 为控制实验输入，不是已测得的学生能力。

量表仍为自动生成的参考答案草稿；没有独立 judge 或人工评分。
12 条结果全部是 `needs_review`，正确率点估计为 null，不能解释成 0% 或 100%。
`final_choice=null` 是开放题的合法输出，不再套用选择题字母评分。
引用通过 chunk ID 子集检查，不代表已经评估引用是否语义支持每条陈述。

## 保存的证据

- `saved_answers.jsonl`：12 条真实生成答案。
- `expected_experiment.json`：运行前冻结的完整 12 单元矩阵。
- `generation_records.jsonl`：每条的原始模型输出、完整证据、候选与选择顺序、等级/条件、
  重排轨迹、提示词摘要、调用耗时与用量。
- `generation_summary.json` / `generation_report.md`：运行汇总。
- `run_manifest.json`：输入/实现/输出摘要和完成状态。
- 历史 `scoring/` 未决报告已随评分工作拆到 M8 的独立 review PR；生成文件字节不变。

另一次先行接线运行也完成了 12/12 个真实单元，耗时合计约 89.17 秒；
其原始输出在本地 `artifacts/v2-experiment-real-smoke/`。
本目录保存最后一次带实现来源指纹的验收快照。

## 后续输入与运行

本地已经冻结全部 162 道 Dev 题、1944 个预定单元，位于
`artifacts/v2-experiment-inputs/dev-diagnostic-prepared/`。
为 BM25 top-20 的 2242 个唯一候选导出了空白 Role 标注表，尚未填成已标注标签。
人工校准的 12 条匿名材料和空白评分表在
`artifacts/v2-experiment-real-smoke/calibration-packet/`。
这些路径是本次操作的本地材料，不属于随仓库发布的正式数据。

配套 Role 完成后应重新准备实验并只在 Dev 选择 lambda，再配置独立 judge/人工审查量表。
全量运行、正式划分确认及人工校准没有由这次接线验收替代。
复现步骤见 [M7 V2 实验说明](../../v2-member7-experiments.md)。

本目录检索原文来自 M4 发布的 OpenStax 语料，其来源和许可以
[M4 Release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m4-structure-v2-dev-v1)
的 corpus manifest 为准（CC BY 4.0）；原文保留用于证据追溯。教材来源：
[College Physics 2e](https://openstax.org/details/books/college-physics-2e)、
[College Physics for AP Courses 2e](https://openstax.org/details/books/college-physics-ap-courses-2e)、
[Physics](https://openstax.org/details/books/physics)，出版方 OpenStax。
