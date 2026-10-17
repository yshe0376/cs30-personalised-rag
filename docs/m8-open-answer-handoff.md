# M8 开放题评分代码交接（待 review）

此 PR 从 M7 的旧混合 PR 提取已有评分实现、测试、2026-10-15 方案和历史 scoring/ 报告。
除移动 rubric 草稿函数及纠正入口说明外，不新增 M8 评分行为；由 M8 审查并自行负责。
M7 的生成矩阵和记录交接见 `docs/v2-member7-experiments.md`。

M7 新矩阵 schema=0.2 不再含 rubric 哈希。M8 需在自己的评分 manifest 中绑定 rubric、Gold、
生成矩阵及答案摘要；旧评分入口仍接收旧 schema=0.1 的 OpenAnswerExperiment，适配由 M8 完成。
新答案可能含 output_truncated，不能混为服务中断或普通正确性答案。

M8 后续负责：盲评包和校准按唯一答案统计、报告技术失败列、生成失败计分策略、rubric 审查、
judge 选择、评分测试的9处编码及报告模块编码问题。本 PR 不代替这些决定。
旧 Dev 结果 R0/R1 prompt 每个 P 设置下均相同（486/486），等 M7 完成 lambda=0.2 的新一轮
生成后再比较条件。旧评分状态不构成已完成的答案正确性评估。

独立评分回归：65 项通过（macOS）；Windows 的剩余编码问题如上留给 M8。
