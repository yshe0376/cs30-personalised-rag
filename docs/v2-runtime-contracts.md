# v2 运行时与 Concept Check 契约

本文件记录 M1 已落地的 v2 接缝。它只定义跨模块 payload 和 Protocol，不把
Concept Check 接入当前 `src/cs30/v2/pipeline.py` 的语料构建入口。

## 代码位置

| 接缝 | 位置 |
|---|---|
| v2 公共模型 | `src/cs30/v2/contracts/models.py` |
| 公共导出 | `src/cs30/v2/contracts/__init__.py` |
| M6/M7/M8 Protocol | `src/cs30/v2/ports.py` |
| Topic sidecar 与确定性解析 | `src/cs30/v2/topics.py` |
| LearnerContextSnapshot 纯函数 | `src/cs30/concept_check/snapshot.py` |
| Concept Check 配置 | `src/cs30/v2/config.py` 的 `ConceptCheckConfig` |

## 问答运行时顺序

```text
RetrievalResult
  -> TopicResolver.resolve_retrieval_topic
  -> LearnerContextSnapshot
  -> EvidenceBundle / AnswerGenerator
  -> ValidatedAnswer
  -> TopicResolver.resolve_cited_topic
  -> Concept Check provider / grader / event store
```

`RetrievalResult.hits` 可以为空，表示检索成功但没有证据；非拒答的
`GeneratedAnswer` 必须携带至少一个 citation，拒答不能携带 citation。
`EvidenceBundle.citation_map` 必须完整映射每个展示 evidence ID 到真实 `chunk_id`。
回答通过 citation validation 后，cited-topic resolver 还必须确认所有 resolved citation
来自初始 retrieval；否则返回 `no_topic_available` 并记录
`CITATION_NOT_IN_RETRIEVAL`。

## Concept Check 题目与证据

`ConceptCheckQuestion` 固定为四选一、`split_guard=practice_only`，题目永久保存
章节内半开区间的 `EvidenceSpan`，不保存 `document_id`、全局偏移或 `chunk_id`。
同一道题在某个语料版本上的 binding 单独保存为
`ConceptCheckQuestionBinding`；只有每个 anchor 都是当前 corpus 的 `resolved`
binding 时，`ConceptCheckQuestionRelease` 才能发布。

`GoldQuestion` 也使用同一个 `EvidenceSpan`，所以 M4 后续可以让 Gold 与练习题
共用 span-to-chunk resolver。SciQ 练习题只允许 `train`/`validation` provenance，
不能在题目契约层绕过 `test` split。

题目 provider 接收 `topic_id`、按优先级排列的目标 `StudentLevel`、当前
`corpus_version`/`corpus_hash`、本轮 cited chunk IDs 和历史排除题目 IDs，并返回当前语料
绑定成功的 `ConceptCheckQuestionRelease`；mastery 阈值策略由独立的 M7 纯函数决定。

## Topic 与动态画像

`resolve_topic_from_retrieval()` 和 cited-topic resolver 都按初始 retrieval 的 `1 / rank`
加权；一个 chunk 映射多个 Topic 时平均分配该 chunk 的权重。只有唯一最高且达到
`min_topic_support` 才返回 `resolved`。topic sidecar 在加载时针对当前 manifest 和一次性
读取的 corpus chunk IDs 校验；sidecar 缺失、corpus hash/version 不一致、retrieval provenance
缺失、registry 版本不一致或引用未知 Topic 都是显式失败码，不会静默变成普通的“无 Topic”。

`build_learner_context_snapshot()` 是无副作用纯函数：

- `enabled=false` 时完全旁路 learner state 与 resolver，返回静态 profile，记录
  `profile_source=static_profile`；
- `enabled=true` 且 Topic 唯一时，用该 Topic 的 `TopicState.level` 生成快照；
- `confidence` 保持静态 profile 的值，`attempt_coverage` 单独记录，不覆盖 confidence；
- 同一快照对象供 reranker 和 generator 使用。

## 配置安全

`[concept_check]` 固定十个配置项。`demotion_threshold` 必须严格小于
`promotion_threshold`。`allow_llm_generation` 和
`allow_unreviewed_questions` 在 staging/production 为 `true` 时直接拒绝配置，
不会静默改成 `false`。默认 `enabled=false`，正式四条件实验沿用静态 profile 路径。

后续 M7/M3/M4/M8 只应实现这些 Protocol 或补充独立 adapter，不应在各自模块复制
同名 schema，也不应修改 v1 `src/cs30/contracts`。
