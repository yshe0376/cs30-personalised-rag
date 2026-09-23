# Concept Check 初版设计规格

> 状态：已定（2026-09-22 定稿，已记入《构思与待定》已定表）
>
> 日期：2026-09-21 起草，2026-09-22 定稿
>
> Owner：M1（契约、整合、版本和实验管理）
>
> 相关实现者：M7（出题、验证、判分和状态更新）、M3（题目与证据审核）、M8（UI、记录和评估）

## 1. 目标

Concept Check 是回答后的可选微测，不是第二套问答系统，也不是正式 Dev/Test 评估集。它的作用是：

1. 用一道有教材证据的短题检查学生对当前 Topic 的理解；
2. 自动判分并记录一次学习事件；
3. 透明地更新 Topic mastery、attempt coverage 和 attempts；
4. 让下一轮个性化回答可以读取新的动态状态；
5. 在题目质量、证据支持或数据隔离不满足条件时安全关闭，而不是展示未经验证的题目。

初版只支持四选一题。短答案、复杂知识追踪和完整 KG 路径属于后续版本。

## 2. 范围与非目标

### 2.1 初版范围

- `practice_only` 题目池；
- 人工题、对齐后的 SciQ 题和 LLM 候选题三种来源；
- 题目结构验证、证据引用检查和人工审核状态；
- M3 维护的 provider-neutral Topic registry 和确定性 Topic resolver；
- 稳定 evidence anchor，以及按 corpus version 解析到当前 chunk 的 binding；
- 四选一自动判分；
- 跳过题目不更新状态；
- 事件日志回放得到 LearnerState；
- 透明的 TopicState 更新函数和静态 StudentProfile snapshot 适配器；
- fixture 模式端到端演示；
- 默认关闭的 Concept Check feature flag；
- 可序列化的题目、作答和 LearnerState 契约。

### 2.2 本阶段明确不做

- 不让未审核的 LLM 题目进入正式题库；
- 不把 SciQ 的 `support` 字段直接当作在线 RAG 证据；
- 不把 Concept Check 题目放入正式 Dev/Test；
- 不修改现有 `StudentProfile.topic_levels` 的类型或语义；
- 不在 Concept Check 初版接入 Restricted KG；
- 不实现短答案自动评分、BERT-KT 或复杂心理测量；
- 不改变 v1 静态个性化主实验的输入路径。
- 不让动态题目 confidence 覆盖现有静态 profile confidence；

## 3. 设计原则

### 3.1 混合出题，但审核后发布

题目来源不是“全部手写”或“全部自动生成”，而是分阶段混合：

```text
手写 fixture / 人工题 / 对齐 SciQ
              ↓
       LLM 生成候选题
              ↓
       自动结构和证据引用检查
              ↓
          M3 人工审核
              ↓
       published practice question
```

LLM 可以起草候选题，但不能单独决定题目是否可发布。staging/production 的正式 Concept
Check 只读取 `published` 题目；development 下只有显式打开 `allow_unreviewed_questions`
时才可展示未审核候选，并且必须标记为开发调试结果，不能进入正式 trace 或题库。在线生成
fallback 默认关闭。

### 3.1.1 题目来源与发布门禁

这是题库的统一规则，后续 validator、M3 审核流程和 M8 展示逻辑都必须复用，不能各自解释：

- **人工编写**：由 M3/M1 编写或维护的题目，仍然必须经过自动结构校验和 M3 审核；“人工编写”
  不等于可以跳过证据绑定或反馈审核。
- **教材对齐的 SciQ 题**：只能从 SciQ `train` 或 `validation` split 取题，再绑定到当前教材
  evidence；原始 `source_question_id` 必须保留，不能靠改题干、选项或 Concept Check 的
  `question_id` 绕过检查。
- **LLM 离线候选题**：只允许在 development 环境离线批量生成，作为 `draft` 候选进入
  validator 和 M3 审核；不能在提交答案时在线生成，也不能因为生成成功自动发布。

所有来源都必须经过同一状态流转：

```text
draft
  → auto_validated
  → reviewed (M3)
  → published
```

进入 `published` 的题目必须同时满足三项不可替代的发布条件：

1. 有 M3 的 `review_record_id`，记录唯一答案、难度、Topic、干扰项和证据支持的审核结论；
2. 有经过 M3 审核的静态反馈说明 `rationale`，提交答案时不调用 LLM 生成反馈；
3. 有稳定 evidence anchor，并且已经为当前 corpus version 生成 `resolved` binding。

任一条件缺失都只能停留在 `draft`、`auto_validated` 或 `rejected`，不得进入正式题库。

SciQ provenance 采用双向泄漏门禁：练习题的 `source_question_id` 不能出现在任何已冻结 Gold
provenance 中；冻结或更新 Gold 时，新 Gold 的 source ID 也不能与已发布练习池发生碰撞。这样
无论是“练习题先进入 Gold”，还是“Gold 先存在、练习题后加入”，都不能复用同一道 SciQ 题。

此外，Gold 泄漏检查不只针对 SciQ provenance，三种来源都必须经过两项自动检查：

- 题目的 anchor binding 到当前 corpus 后，如果其教材、章节和半开字符区间与 Gold Dev/Test
  evidence 有重叠，或其 `text_hash` 与 Gold evidence 相同，直接拒绝；
- 题干和选项与 Gold Dev/Test 题目达到冻结阈值的文本/语义相似度时，validator 输出
  `gold_leakage_suspected` 标记；该题不能自动进入 `auto_validated` 或 `published`，必须由
  M3 在审核记录中明确清除该标记或拒绝题目。

这两项检查尤其适用于 LLM 离线候选，因为“改写题干”或“换一个题目 ID”不能绕过证据重叠和
题干相似度门禁。检查器版本、阈值、命中的 Gold ID 和结果必须写入 validator trace。

### 3.2 Validator 的边界

自动 validator 负责可机械判断的约束：

- JSON 字段和类型正确；
- 选项集合正好是 A、B、C、D；
- `correct_answer` 属于选项集合；
- `evidence_anchors` 非空，并且可以通过当前 corpus version 的 binding 解析到 evidence；
- `split_guard` 为 `practice_only`；
- question ID 唯一；
- `source_question_id` 存在时可以在 Gold/SciQ provenance registry 中追溯；
- 题目没有引用正式 Test 题 ID，也没有使用 SciQ test split；
- 题目 anchor 与 Gold Dev/Test evidence 的 span/text hash 不重叠；
- 题干/选项 Gold 相似度检查没有产生 `gold_leakage_suspected`，或该标记已由 M3 在
  `review_record_id` 中明确清除；
- 难度和 Topic 字段存在且取值合法。

以下判断仍需要 M3 的人工审核：

- 是否只有一个可辩护的正确答案；
- 正确答案是否真正由教材 evidence 支持；
- 干扰项是否合理；
- 难度是否和目标学生水平匹配；
- 是否依赖教材外知识；
- 是否和正式 Test 题或答案发生语义泄漏。

LLM judge 可以作为人工审核前的提示工具，但其结果不能直接把题目标记为 `published`。

### 3.3 Topic 不能由运行时猜测

运行时不从题目文本或 LLM 回答自由猜 Topic。M3 以 Gold 的 `concept_group` 为初始来源，维护一份 provider-neutral、版本化的 Topic registry：

```text
concept_group → topic_id
textbook/chapter/section/evidence anchor → topic_id
```

`topic_id` 表示跨教材可复用的概念，不包含具体教材 ID。章节只能作为确定性映射的输入，不能直接把 `chapter_id` 当作 Topic；一个章节如果对应多个 Topic，必须由 M3 提供 section/evidence anchor 映射。

Topic 不作为 v2 Chunk 的内嵌字段；resolver 只读取与当前 retrieval manifest 的 `corpus_hash`
一致、并带有 `topic_registry_version` 的 sidecar `chunk_topic_map`。map 里没有的 chunk 视为
没有 Topic，不能从章节名或题目文本临时猜测。

必须区分两种情况：

- **正常情况：** map 有效，但某个命中的 chunk 在 map 中没有条目，该 chunk 只是不贡献 Topic
  权重；
- **配置错误：** map 缺失，或者 `validate_chunk_topic_map()` 报告 `corpus_version`/`corpus_hash`
  与当前 manifest 不一致、引用了语料中不存在的 `chunk_id`。resolver 必须接住这个错误，在
  trace 中记录错误码（`TOPIC_MAP_UNAVAILABLE` 或 `TOPIC_MAP_MISMATCH`），本轮返回
  `no_topic_available`，并由 M8 单独统计；不能把它当成正常的“没有 Topic”静默处理，否则整个
  Concept Check 会在无人察觉的情况下失效。

MVP 不依赖
v3 的 Conversation Context，而是把 resolver 明确拆成两个时序不同的操作：

1. `resolve_retrieval_topic(retrieval_hits)`：检索完成后、reranker 运行前调用。它读取检索命中
   chunk 在 `chunk_topic_map` sidecar 中的 `topic_ids`，为生成 `LearnerContextSnapshot` 选择
   本轮候选 Topic；map 中没有的命中不贡献 Topic 权重；
2. `resolve_cited_topic(cited_chunks)`：回答通过 citation validation 后调用。它只读取非拒答答案
   实际引用的 evidence，用于选择 Concept Check 题目；拒答或没有 citation 时直接返回
   `no_topic_available`，不出题。

两种操作都使用同一确定性计分规则：使用初始 retrieval 返回的 rank（不是 reranker 重新排序
后的 rank），rank 为 `r` 的 chunk 贡献 `1/r`；若该 chunk 有 `n`
   个 Topic，则每个 Topic 只分得 `1/(r*n)`，即一个 chunk 映射到多个 Topic 时平均分配证据
   权重。计算 `support(topic)=topic_weight/所有_topic_weight`，只有唯一最高 Topic 且
   `support >= min_topic_support` 时才确定 Topic。平票、Topic 缺失或支持度不足时返回
   `no_topic_available`。

检索阶段无法唯一确定 Topic 时，v1 主流水线仍可用静态 global level 构造 snapshot 以保持
   兼容，但该轮 Concept Check 必须关闭；不能用一个未经证据支持的 Topic 更新 LearnerState。
   章节到 Topic 的一对一映射只能作为 fixture 或 M3 明确登记的 fallback。

Topic registry 必须包含 `topic_registry_version`，并进入题目、状态和运行 trace；跨教材同一概念的映射由 M3 审核，不由 M7 或运行时临时创建。

## 4. 题目生命周期和来源

### 4.1 来源枚举

```text
human_authored   人工编写
sciq_aligned     与教材 evidence 对齐后的 SciQ 题（OpenStax 或 CK-12）
llm_generated    LLM 根据 evidence 生成的候选题
```

`sciq_aligned` 题目还必须记录：

```text
source_dataset = "SciQ"
source_question_id = 原始 SciQ ID
source_split = train | validation
```

Concept Check 练习池只允许 SciQ `train` 或 `validation`。`test` 题目即使改写了 question text 或换了 `question_id`，也不能进入练习池。

### 4.2 状态枚举

```text
draft            初始题目或 LLM 候选题
auto_validated   通过自动结构/引用检查，等待人工审核
reviewed         M3 已审核
published        可以进入 practice pool
rejected         自动检查或人工审核失败
```

`split_guard` 和 `status` 是两个不同字段：`split_guard=practice_only` 表示题目不能进入正式评估集；`status=published` 表示题目质量门槛已通过。

`published` 还必须有 M3 的 `review_record_id`、一条已审核的反馈说明 `rationale`，并且至少有一个当前或可重建 corpus version 的 resolved binding；`auto_validated` 不能被运行时当作 `published` 使用。对 `source_type=sciq_aligned`，`source_dataset`、`source_question_id` 和 `source_split` 必须同时存在；对 `human_authored`，这些 SciQ 字段必须为空或不出现。

### 4.3 题目最小数据结构

初版建议使用以下字段；多教材身份字段由 M1 的 v2 公共契约统一接入，不由 M7 私自发明第二套字段。持久化题目不直接把 `chunk_id` 当作 evidence 的唯一身份。

```json
{
  "schema_version": "0.1",
  "question_id": "cc_physics_0001",
  "question": "If an object moves with constant velocity, what is its acceleration?",
  "options": {
    "A": "It is zero",
    "B": "It doubles",
    "C": "It is constant but non-zero",
    "D": "It is undefined"
  },
  "correct_answer": "A",
  "topic_id": "constant_velocity_and_acceleration",
  "topic_registry_version": "topics-0.1",
  "difficulty": "beginner",
  "evidence_anchors": [
    {
      "schema_version": "2.0",
      "span_id": "cc:cc_physics_0001:1",
      "textbook_id": "openstax_college_physics_2e",
      "chapter_id": "2",
      "chapter_char_start": 1200,
      "chapter_char_end": 1260,
      "verbatim_text": "An object moving at constant velocity has zero acceleration.",
      "text_hash": "sha256:00161e370e00cb6b6a975348449ed1a812a9ba715d9251880eac9d9ee50bb24c",
      "origin_corpus_version": "2.0.0-dev.1"
    }
  ],
  "source_type": "human_authored",
  "split_guard": "practice_only",
  "rationale": "Constant velocity means velocity does not change, so acceleration is zero.",
  "review_record_id": "m3_review_cc_0001",
  "status": "published"
}
```

上面的题目和 evidence 是 synthetic fixture 示例，不得直接当作 Gold 或正式 practice 内容。
`evidence_anchors` 的每一项就是 v2 契约中的 `EvidenceSpan`（`cs30.v2.contracts`），与 v2 Gold
evidence 同一类型：偏移是**章节内**的半开区间，`verbatim_text` 的长度必须等于区间长度，
`text_hash` 是它的 SHA-256（省略时由契约自动计算，给出时必须一致）。示例中的 hash 是这段
示例文本的真实值。`span_id` 在 Gold 和 Concept Check 之间必须唯一，建议分别用 `gold:` 和
`cc:` 前缀。anchor 不保存 `document_id`、全局偏移、`chunk_id` 或 `source_locator`，这些都随语料
重建而变化，只出现在 §4.4 的 binding 里。示例题为人工题，因此不携带 SciQ provenance；`sciq_aligned`
题必须额外携带下方定义的 SciQ 字段。`rationale` 是 M3 审核后的静态反馈，不在提交答案
时调用 LLM；它必须和同一组 evidence anchor 一起审核，不能生成脱离题目证据的解释。

### 4.4 Evidence anchor 和 corpus binding

`evidence_anchors` 是题目的稳定来源事实；每个 anchor 的 `origin_corpus_version` 记录它首次
对齐的语料版本，当前索引使用的 `chunk_id` 只是运行时解析结果。每个目标 corpus version 为
每个 anchor 生成一条 `EvidenceSpanBinding`（`cs30.v2.contracts`），Gold evidence 用同一个类型：

```text
(span_id, corpus_version, corpus_hash)
    → resolution_status = resolved | stale | ambiguous
    → resolution_method = block_id | chapter_offset | verbatim_unique   # resolved 时必填
    → document_id + 文档全局区间 + chunk_ids                           # 只有 resolved 才有
```

解析规则沿用 Gold mapping：在同一 textbook/chapter 内依次用 block_id、章节内偏移加
`text_hash` 校验、verbatim text 唯一匹配，因此语料重建不会因为 chunk ID 变化而使题库失效。
需要展示来源时，由 binding 解析出的 chunk 提供 `source_locator`，它由 v2 `ids.source_locator`
builder 生成，格式为 `source=<source_name>|textbook=…|chapter=…|location=…|span=起:止`；
`source_name` 就是 `textbook_id` 本身（一本书若将来拆成多个源文件，则为 `textbook_id/<part>`），
不带文件扩展名，v2 catalog 校验会拒绝其他写法；有 PDF 页码时 `location` 为 `p<页码>`。
任何人都不能手写 locator 或继续使用 v1 的 `#chapter=...&char=...` 格式。

题目 anchor 与 v2 Gold evidence span 使用**同一个**由 M1 定义的证据区间类型 `EvidenceSpan`
（教材、章节、章节内半开字符区间、verbatim text 和 `text_hash`；`document_id`、全局偏移和
`chunk_id` 只作为解析结果，放在 `EvidenceSpanBinding` 里）。“文本区间 → chunk”的解析**只有一套实现**，由 M4 在 Gold mapping 中提供；Concept
Check 的 `anchors.py` 只是调用它的薄适配层，不另写匹配逻辑。这样 §4.5 的 Gold 重叠门禁
比较的是同一套解析结果，不会因为两套实现对同一段文字给出不同坐标而漏判。

anchor 只能落在当前 evidence policy 保留、会进入检索语料的内容类型上（W5 为 body、
example、figure_caption、glossary、table、equation）。落在 problem、summary、
conceptual_question 等被排除内容上的 anchor 必然无法 binding，题目不能发布；M3 标注种子
段落时也遵守同一限制。

解析失败、过期或有多个匹配时，题目不能标记为 `published`，也不能在线展示。这里的 binding
只要求题目审核证据能解析到当前 corpus；它不要求解析出的题目证据是本轮 top-k 检索结果的
子集。答案的 citation 仍必须遵守 v1 约束，引用只能来自本轮实际检索返回的 chunk；这是两个
不同的契约。

`resolved_chunk_ids` 只能出现在按 corpus version 保存的 binding 和运行 trace 中，不能覆盖题目的稳定 anchor。重建语料时只重建 binding，不需要把所有题目永久改写成新的 chunk ID。

Gold 已有 typed `GoldSource`/`SourceSplit` 和 `GoldSample.source` 字段；Concept Check 直接复用
它们，不在 Phase 1 再造一套 provenance 类型。这里必须区分两个命名空间：

- `GoldSample.split` 是项目的评估划分（`dev`、`test`，以及现有流程可能使用的 proposed 标记）；
- `GoldSample.source.source_split` 是 SciQ 自己的来源划分（`train`、`validation`、`test`）。

不能把 SciQ 的 `source_split` 归一化成项目的 `dev/test`，也不能用项目 split 代替 SciQ
来源 split。Practice registry 要索引 Gold 的全部 `source_question_id`，并至少单独报告 Dev/Test
命中；只要某个 ID 已进入冻结的 Gold provenance，就不能把它作为练习题来源。

本文以目标 v2 baseline 已导出这些 typed 类型为前提。实现前必须在选定的 v2 分支确认实际
导出位置；如果 checkout 仍是旧模型，应先同步该 baseline，而不是在 Concept Check 下再造一
套同名或语义相近的 provenance 类型。

### 4.5 SciQ provenance 与通用 Gold 泄漏门禁

对 `source_type=sciq_aligned`，以下字段全部必填：

```text
source_dataset = "SciQ"
source_question_id
source_split ∈ {train, validation}
```

validator 必须同时检查：

1. `source_split` 不是 `test`；
2. `source_question_id` 不在 Gold 的 Dev/Test provenance 集合中；
3. `source_question_id` 不在任何已冻结 Gold provenance 集合中；
4. 改写题干、选项或 Concept Check `question_id` 不能绕过上述检查。

对所有来源（尤其是 `llm_generated`）还必须执行 Gold 内容泄漏检查：

1. 将题目 anchor binding 与 Gold Dev/Test evidence 归一到同一当前 corpus 坐标后，若教材、
   章节和半开区间重叠，或 anchor `text_hash` 与 Gold evidence 相同，直接拒绝题目。两边都
   必须由 §4.4 的同一个 M4 resolver 解析；Gold 尚未迁移并解析到当前 corpus version 时，这一
   项视为**未通过**而不是跳过，题目不能进入 `auto_validated`；
   **跨书重复内容按重复组比较：** v2 语料里 AP 版约 94% 的可检索文本与 College Physics 2e
   逐字相同。每次构建输出的 `duplicate_blocks.json`（与 corpus hash 绑定）列出正文相同、分属
   不同教材的 block。重叠检查前先把 anchor 和 Gold evidence 覆盖的 block 都展开到各自所在的
   重复组，任一重复组相交即视为重叠，因此出现在另一本书里的**部分**重叠拷贝同样会被拒绝，
   不能只比较 `text_hash` 是否完全相同；
2. 对题干和选项运行版本固定的文本/语义相似度检查；达到冻结阈值时标记
   `gold_leakage_suspected`，不得自动通过 `auto_validated`，必须由 M3 在审核记录中明确
   清除或拒绝；
3. validator trace 记录检查器版本、阈值、命中的 Gold ID、证据重叠结果和相似度结果。

泄漏检查必须双向执行：冻结或更新 Gold 时，也要把新 Gold 的全部
`source.source_question_id` 与已发布 Concept Check practice pool 的 provenance 做反向比对。
任一方向发生碰撞都阻止发布；不能只在“练习题进入 Gold”时检查，因为后续 M3 可能把
SciQ train/validation 题选入新的 Gold。

因此当前 fixture 中带有 `sciq-test-*` 的题目不能直接进入 Concept Check fixture/provider；需要另建只含 SciQ train/validation 或 human-authored 题目的练习 fixture。

## 5. 运行流程

### 5.0 Concept Check 关闭时

当 `concept_check.enabled=false` 时，pipeline 不调用任何 Topic resolver、题目 provider、
binding resolver 或 LearnerState event store；snapshot 直接来自静态 StudentProfile，运行
manifest 和 trace 记录 `profile_source="static_profile"`。该模式不追加 Concept Check 事件，
也不显示题目。

正式的四条件 Dev/Test 实验必须统一使用该关闭模式，确保实验比较的是静态画像与检索/生成
条件，而不是被动态作答状态污染。只有独立的 Concept Check 演示或动态实验才允许开启
`concept_check.enabled`。

### 5.1 展示题目

回答完成后，UI 可显示“要不要用一道简短问题检查一下理解程度？”。学生没有选择 Concept Check 时，不创建题目、不更新状态。

题目选择顺序：

1. 如果 retrieval 阶段的 `resolve_retrieval_topic` 没有唯一确定 Topic，本轮直接返回
   `no_topic_available`，不调用回答后的 cited-topic resolver，也不出 Concept Check；
2. 只有非拒答且通过 citation validation 的回答才进入 Concept Check；没有 citation 或回答
   拒答时直接返回 `no_question_available`；
3. 用回答实际引用的 evidence 调用 `resolve_cited_topic`，不依赖尚未实现的 v3 Conversation
   Context；无法唯一确定 Topic 时不出题；
4. 从该 Topic 下筛选 binding 对当前 corpus version 解析成功的 `published` practice 题，
   并排除该学生历史上已经提交过的 `question_id`（即使该次作答后来被撤销，也不重新展示）；
5. 候选题按以下顺序排序：通常难度与当前 Topic level 相同优先，其次相邻难度；但当
   `mastery_score >= promotion_threshold` 且当前 level 不是 `advanced` 时，进入向上试探
   模式，优先选择高一级（目标 level）的未作答题，再回退到同级题。若题库没有高一级的可用
   题，不能伪造晋级证据，只能按普通难度顺序回退。与本轮回答引用 evidence 至少有一个
   resolved chunk 重叠时加软分。重叠只是排序加分，不能作为硬性 validator 或展示门槛；
6. `sciq_aligned` 题还必须满足 source split 为 train/validation 且通过双向泄漏门禁；
7. 只有在明确打开实验性 fallback 时，才允许 LLM 生成候选题；
8. 没有 binding 或可用题目时返回 `no_question_available`，保留原回答。

初版正式演示默认只走 TopicResolver、已发布 practice/SciQ 题和成功 binding，不走在线 LLM fallback。LLM 生成候选题使用离线 batch，不能因为一次在线调用成功就自动发布。

### 5.2 提交答案

提交路径不调用 LLM：

```text
ConceptCheckQuestion + selected_choice
        ↓
        Grader
        ↓
ConceptCheckGrade(correct / incorrect / skipped)
        ↓
LearnerStateUpdater
```

`selected_choice=null` 只允许在 `skipped` 状态下出现。重复提交同一个 `attempt_id` 必须幂等，不能重复累计 attempts。

提交后的反馈只读取已发布题目的 `rationale`、正确答案和当前 binding 已解析的教材证据；MVP
不调用 LLM，也不根据学生答案临时生成反馈。若后续需要按干扰项给出不同的纠错提示，再在
v2 为题目增加经过 M3 审核的 `misconception_feedback` 映射，不能把它隐含成在线生成能力。

### 5.3 失败语义

- 题目结构失败：题目进入 `rejected`；
- evidence anchor 无法解析到当前 corpus：不展示题目，并将 binding 标记为 `stale` 或 `ambiguous`；
- 题目 binding 不存在、过期或歧义：不展示题目，返回 `no_question_available`；本轮检索没有
  返回题目 anchor 对应 chunk 不构成失败，只会失去 evidence-overlap 排序加分；
- SciQ `source_question_id` 出现在 Gold 的 Dev/Test 或 SciQ test split：题目进入 `rejected`；
- Topic 无法确定：不展示题目，返回 `no_topic_available`；
- `chunk_topic_map` 缺失或与当前 manifest 不一致：同样返回 `no_topic_available`，但 trace 记录
  `TOPIC_MAP_UNAVAILABLE`/`TOPIC_MAP_MISMATCH` 配置错误，M8 单独统计；
- LLM/API/JSON 失败：只记录单题失败，不中断 batch；
- 状态更新失败：保留作答记录并报告错误，不伪造新的 LearnerState；
- 任何失败都不能让系统生成没有证据的反馈。

## 6. LearnerState 初版规则

### 6.1 状态字段

```text
state_id
profile_id
topics[topic_id]
  mastery_score       0.0–1.0
  level               beginner/intermediate/advanced
  attempt_coverage   0.0–1.0
  total_attempts
  attempts_since_level_change
  correct_attempts
  misconceptions
```

事件日志是动态学习状态的唯一事实来源；`LearnerState` 是按事件日志回放得到的当前结果，
不是独立写入的第二份事实。`attempt_coverage` 表示当前 level 估计已经积累了多少作答证据，
不是 reranker 使用的 profile confidence。

一轮运行的时序固定为：

```text
retrieval
  → resolve_retrieval_topic(retrieval hits)
  → build LearnerContextSnapshot
  → rerank / generation
  → citation validation
  → resolve_cited_topic(answer citations)
  → select Concept Check question
```

因此 snapshot 不是“每轮开始时”生成，而是在检索完成、reranker 运行之前生成：

- `profile.level`：若 `resolve_retrieval_topic` 唯一确定 Topic，取该 Topic 当前的 `level`；
  若无法确定，回退到静态 StudentProfile 的 global level，但该轮不允许用它产生 Concept Check
  状态更新；
- `profile.confidence`：继续使用静态画像的原始 confidence，不使用 `attempt_coverage` 覆盖它；
- `profile.topic_levels`：只作为旧 Prompt/接口的兼容快照，由 LearnerState adapter 即时生成，不
  作为第二份持久化状态；
- snapshot 额外携带 `topic_id`、`attempt_coverage`、`state_version` 和 TopicState；
- 同一 snapshot 同时提供给 reranking 和 generation。回答之后的 `resolve_cited_topic` 只决定
  Concept Check 题目 Topic，不回写或替换已经用于本轮回答的 snapshot。

因此冷启动时 `attempt_coverage=0` 不会把 `effective_lambda = lambda × profile.confidence` 悄悄降为 0；当前 reranker 的 confidence 语义保持不变。

`profile_source` 只有两个值：Concept Check 开启且状态由事件日志回放时为
`learner_state_replay`；Concept Check 关闭时为 `static_profile`。它必须同时写入运行
manifest/trace，不能只依赖配置文件推断本轮实际使用的画像来源。

### 6.2 更新规则

```text
correct answer   current_performance = 1.0
wrong answer     current_performance = 0.0
partial answer   current_performance = 0.5  # 初版暂不使用

level_relation = below | same | above
  # compare question.difficulty with the current Topic level before updating it
correct_weight = correct_difficulty_weights[level_relation]
wrong_weight = wrong_difficulty_weights[level_relation]
alpha_eff = 0.2 × (correct_weight if correct else wrong_weight)
new_score = previous_score + alpha_eff × (current_performance - previous_score)
```

MVP 默认使用非对称权重，数组顺序固定为 `[below, same, above]`：

```toml
correct_difficulty_weights = [0.5, 1.0, 1.0]
wrong_difficulty_weights = [1.0, 1.0, 0.5]
```

也就是说：高于当前 level 的题答对和同 level 一样有信息量，答错只按半权重；低于当前
level 的题答对只按半权重，答错仍按完整权重。它避免了对称距离把有信息量的观测打折，
也避免 advanced 学生连续答错 beginner 题时每次只产生很小的降级信号。

初版建议：

- 新 Topic 的 `mastery_score=0.5`，`total_attempts=0`；
- 学生自选的 global level 作为该 Topic 的初始 level；
- `level_change_window=3` 是唯一的 level-change 最小样本数和窗口长度，不再另设独立的
  最小作答数参数。状态回放只把当前 level epoch 内最近 3 次有效提交放入
  bounded sliding window；每次达到 3 次后都可用这 3 次重新评估一次变级。被跳过或撤销的
  作答不进入窗口；`attempts_since_level_change` 可累计记录该 epoch 的全部有效提交；
- `attempt_coverage=min(1.0, attempts_since_level_change/attempt_coverage_window)`，其中
  `attempt_coverage_window=5` 只控制展示用 coverage 的饱和速度，不是额外的变级门槛；
- 低于当前 Topic level 的题目不能单独证明晋级；高于当前 Topic level 的题目答错不能单独触发降级；
- 至少积累一个完整的 `level_change_window` 后才允许变级；
- 晋级要求 `mastery_score >= 0.75`，并且最近窗口内至少两道题的 difficulty 不低于目标 level 且答对；
- 降级要求 `mastery_score <= 0.25`，并且最近窗口内至少两道不高于当前 level 的题答错；
- 每次最多改变一级；如果窗口满足条件，先改变一级，再清空窗口和该 level epoch 的计数，
  不在同一批历史答案上连续跳级；
- 变级后把 `mastery_score` 重置为 `0.5`，把 `attempts_since_level_change` 和 `attempt_coverage` 重置为 `0`；
- `total_attempts` 和历史事件不删除，保留长期审计；
- `skipped` 不更新状态；
- `misconceptions` 初版只允许由审核后的规则或人工标签写入，不由 LLM 自由产生。

选题器在每次提交事件写入并回放完成后，读取该 Topic 的**最新 TopicState**；下一次选题时，
只要 `mastery_score >= promotion_threshold` 且当前 level 低于 `advanced`，就进入向上试探
模式，目标为当前 level 的下一级。不使用更新前的状态，也不要求是“首次”达到阈值。这样从
`mastery_score=0.5` 开始，四道同级题答对后的分数为 `0.7952`
（前三道只有 `0.744`，尚未达到阈值），随后两道目标 level 题答对即可满足最近窗口内
至少两道目标 level 正确的晋级条件，最早约第 6 次有效作答晋级。三道连续答错后的分数为
`0.256`，也仍未达到 `0.25` 的降级阈值；这里的数值例子指连续三道同级题，测试不得假设
第 3 题就会发生升/降级。

上述阈值、难度权重和 level-change window 先作为可配置的 MVP 默认值，并写入运行 manifest；不把它们表述为经过验证的心理测量结论。

## 7. 事件溯源和学生控制权

作答不直接覆盖 LearnerState。系统追加不可变事件，LearnerState 由事件回放得到：

```text
ConceptCheckEvent
  attempt_submitted | attempt_skipped | attempt_revoked | topic_level_overridden
        ↓ replay
LearnerStateSnapshot
```

事件至少包含 `event_id`、`attempt_id`、`question_id`、`topic_id`、`question_difficulty`、`selected_choice`、`performance`、`event_type`、`state_version_before`、`stream_version` 和 `created_at`。`stream_version` 由 event store 按学生流单调分配，回放按它排序；`created_at` 只用于审计，不能决定状态顺序。`attempt_id` 是幂等键；同一 `attempt_id` 携带不同 payload 时必须报冲突，不能静默覆盖。

MVP 的 event store 是单用户 demo 假设下的**单写者 append-only JSONL**（每个学生一条
stream，写入过程使用进程内锁或等价的单写者保护）。MVP 不要求 expected stream version
的跨进程并发控制；如果部署形态不再满足单写者假设，v3 必须升级为带 expected stream
version 的持久化 event store，而不是继续静默覆盖。

`LearnerStateSnapshot` 是可选缓存，不是事实来源，必须带 `derived_from_event_version`。回放同一事件日志必须得到相同状态。

学生控制权对应事件：

- 关闭 Concept Check：不追加作答事件；
- 撤销一次作答：MVP 只允许撤销该学生**唯一一条 student stream 中、属于目标 Topic 的最近一次
  有效提交**，追加
  `attempt_revoked` 事件，回放时排除被撤销的 attempt；撤销更早记录、重复撤销或不存在的
  attempt 必须拒绝。M8 报告撤销率，避免通过反复撤销错题刷高 mastery；v3 再考虑任意历史
  attempt 的通用撤销；
- 纠正 Topic level：追加 `topic_level_overridden`，记录 actor=`student` 和原因，并把该 Topic 的 mastery/window reset 到新 level 的初始状态；
- 查看 evidence：读取题目 anchor 当前 binding，只展示已解析的教材证据；
- 删除动态画像：v3 必须对该学生的事件日志和 snapshot 执行实际存储删除，不能只追加一个 `deleted` 标记来假装完成删除。

事件日志只允许追加；用户删除是受控的存储清理操作，不属于普通状态更新。

## 8. 建议的代码边界

### 8.1 M1 负责

- v2 公共契约放在 `src/cs30/v2/contracts/`：Concept Check、LearnerState、Topic、
  provenance/binding 和 `LearnerContextSnapshot`，以及题目 anchor 与 v2 Gold evidence 共用的
  证据区间类型（§4.4）；
- 复用 v2 已有的 `src/cs30/v2/ids.py`、catalog、corpus version 和 source-locator builder，
  不在 Concept Check 模块复制一套教材身份或 locator 生成规则；
- v2 Protocol 放在 `src/cs30/v2/ports.py`，覆盖 Topic resolver、validator、grader、event
  store 和状态 replay；
- v2 配置仍由 `src/cs30/v2/config.py` 管理，但不把 Concept Check 接入
  `src/cs30/v2/pipeline.py`：该文件当前是 `run_build_pipeline` 语料构建入口，不是问答流程；
- 快照构造实现为无副作用纯函数，例如 `src/cs30/concept_check/snapshot.py`，输入明确的
  LearnerState、静态 StudentProfile 和 Topic 结果，输出不可变 `LearnerContextSnapshot`；
- Concept Check 实现为回答完成后的独立组件，例如
  `src/cs30/concept_check/service.py`，负责 post-answer 选题、提交、判分和事件追加；
  它通过 Protocol 接受 retrieval/citation/state 依赖，不在当前 build pipeline 中直接调用；
- v2 问答流水线建好后，再由独立的 integration adapter 接入，不在本阶段修改 v1 的
  `src/cs30/contracts/`、`src/cs30/ports.py`、`src/cs30/config.py`、`src/cs30/pipeline.py`
  或当前仅负责构建语料的 `src/cs30/v2/pipeline.py`；
- schema/version、practice/Test 隔离、anchor binding、manifest 和集成测试；
- 失败码、运行 trace 和后续 v2 身份字段兼容。

### 8.2 M7 负责

- `src/cs30/concept_check/snapshot.py` 的纯函数实现；
- `src/cs30/concept_check/service.py` 的回答后独立组件，不直接依赖当前 v2 build pipeline；
- `src/cs30/concept_check/generator.py`；
- `src/cs30/concept_check/validator.py`；
- `src/cs30/concept_check/grader.py`；
- `src/cs30/concept_check/learner_state.py` 中的纯 replay/update 逻辑；
- `src/cs30/concept_check/topics.py` 的两个 resolver adapter；
- `src/cs30/concept_check/anchors.py`：调用 M4 共享 span resolver 的薄适配层，不另写匹配
  逻辑；
- fixture question provider 和 LLM candidate adapter；
- 单题失败隔离和 JSON 解析。

### 8.3 M3 负责

- Topic 和 difficulty 标注规则；
- provider-neutral Topic registry、`concept_group → topic_id` 映射和版本；
- `reviewed` / `rejected` 决策；
- evidence anchor 支持、唯一正确答案和 Test/SciQ split 泄漏审核；
- practice pool 与正式 Dev/Test 的物理隔离。

### 8.4 M4 负责

- “文本区间 → chunk”的共享 resolver：Gold mapping 与 Concept Check anchor binding 共用同一
  实现，按 `textbook_id` + 章节定位，不依赖会随重新解析变化的 `document_id`；
- 为每个 corpus version 生成 Gold mapping 和题目 anchor binding，记录每条的解析方式和
  `resolved`/`stale`/`ambiguous` 状态；
- 按 M3 的 Topic 映射规则，为每个 corpus version 生成 `chunk_topic_map`，发布前调用
  `validate_chunk_topic_map()`；
- 把 v1 Gold 迁移到 v2 corpus，这是 §4.5 Gold 重叠门禁能够运行的前提。

### 8.5 M8 负责

- Quiz me 入口、提交、跳过和反馈 UI；
- attempt 事件日志、撤销、关闭、evidence 查看和 LearnerState 展示/纠正 UI；
- question validation rate、answer accuracy、skip rate、generation failure rate 和 state update 分析。

## 9. 初版测试要求

### 9.1 契约测试

- 缺字段、未知字段和错误类型被拒绝；
- 选项不是 A/B/C/D 被拒绝；
- 正确答案不在选项中被拒绝；
- 题目 binding 为空、无法解析或当前 corpus version 为 stale/ambiguous 时被拒绝；
- 单独测试 v1 答案 citation 必须是本轮 retrieval 返回 chunk 的子集；不把该规则错误地套到
  Concept Check 题目的 resolved evidence 上；
- evidence anchor 无法在当前 corpus version resolved 被拒绝；
- 非 `practice_only` 题目不能发布；
- `sciq_aligned` 缺少 `source_question_id`、使用 test split 或命中 Gold Dev/Test source ID 被拒绝；
- 任一来源的 anchor 与 Gold Dev/Test evidence span/text hash 重叠时被拒绝；
- 题干/选项达到 Gold 相似度阈值时标记 `gold_leakage_suspected`，不能自动发布，且 M3
  清除必须进入审核记录；
- topic registry 缺失、平票或 topic support 不足时不出题；
- 一个 chunk 映射多个 Topic 时按 `1/len(topic_ids)` 平均分配权重；
- `chunk_topic_map` 缺失或与 retrieval manifest 不一致时，本轮返回 `no_topic_available`，trace
  记录 `TOPIC_MAP_UNAVAILABLE`/`TOPIC_MAP_MISMATCH`；map 有效但某个 chunk 没有条目时，该 chunk
  只是不贡献 Topic，不记错误；
- anchor 与 Gold evidence 经同一个 resolver 解析；Gold 尚未迁移到当前 corpus 时，重叠门禁
  判为未通过；
- anchor 落在 evidence policy 排除的内容类型上时，binding 失败，题目不能发布；
- catalog 的 `source_name` 带扩展名或不等于 `textbook_id` 时被拒绝；
- retrieval 后 snapshot 与回答后 cited-topic 的时序正确，拒答/无 citation 不出题；
- 已作答题目被排除；evidence overlap 只有排序加分，没有硬门禁；
- question ID 和 attempt ID 重复行为明确。

### 9.2 判分测试

- 正确答案返回 `correct` 和 performance 1.0；
- 错误答案返回 `incorrect` 和 performance 0.0；
- 跳过返回 `skipped`，不改变 LearnerState；
- 判分不调用 LLM。

### 9.3 状态测试

- 指数平滑数值正确；
- 高于/同于/低于当前 level 的题目分别覆盖正确和错误的非对称权重；
- level-change window 不足时不改变 level，且窗口是最近 N 次有效提交而不是无界历史；
- 从 `0.5` 连对 3 次或连错 3 次都不变级；达到晋级阈值后优先给出高一级试探题，
  两道目标 level 题答对后才允许晋级；
- 变级后 mastery、coverage 和 window counter 重置，但 total history 保留；
- Advanced 不会因一次错误直接变成 Beginner；
- 重复 attempt 通过事件回放保持幂等；
- revoke 和 student level override 的回放结果正确；
- 非最近一次作答的 revoke 被拒绝，撤销率可被 M8 统计；
- snapshot 的 profile confidence 保持静态值，topic level 使用当前 Topic 值；
- `enabled=false` 时 resolver/event store 不被调用，snapshot 使用静态画像并记录
  `profile_source="static_profile"`；四条件正式实验验证该模式；
- 单写者 JSONL event store 的幂等和回放结果稳定；
- `[concept_check]` 的每一个配置项都通过“配置读取、依赖注入、行为改变”三段式 reachability 测试；
- `allow_llm_generation` 或 `allow_unreviewed_questions` 在非 development 环境被拒绝，
  且运行 trace 记录开关和实际调用情况；
- `src/cs30/v2/pipeline.py` 不被 Concept Check 运行时调用；纯 snapshot builder 和 post-answer
  service 可独立测试；
- 新 Gold 与已发布练习池、练习池与全部冻结 Gold provenance 的双向泄漏测试通过；
- fixture 端到端链路可运行。

## 10. Feature flag 和验收门槛

初始配置：

```toml
[concept_check]
enabled = false
allow_llm_generation = false
allow_unreviewed_questions = false
promotion_threshold = 0.75
demotion_threshold = 0.25
level_change_window = 3
attempt_coverage_window = 5
correct_difficulty_weights = [0.5, 1.0, 1.0] # below, same, above
wrong_difficulty_weights = [1.0, 1.0, 0.5]   # below, same, above
min_topic_support = 0.5
```

这里正好是 10 个 Concept Check 配置项；`level_change_window` 同时定义 level-change 的最小样本数和
bounded window 长度，不再另设独立的最小作答数配置。所有 10 项都必须纳入
配置 reachability 测试，测试不仅验证 TOML 能读取，还要验证依赖注入后确实改变对应行为。

v2 运行配置另外提供环境字段 `environment ∈ {development, staging, production}`；它不计入
上述 10 个 `[concept_check]` 配置项。配置加载时必须执行：

```text
if environment != "development" and (
    allow_unreviewed_questions or allow_llm_generation
):
    reject configuration
```

不能在 staging/production 中静默把 `true` 改成 `false`。`allow_llm_generation=true` 只允许
开发环境生成候选；`allow_unreviewed_questions=true` 只允许开发环境显式展示未审核候选，
两者都不能自动把题目标记为 `published`。每次运行的 manifest/trace 必须记录
`environment`、这两个开关、`enabled`、`profile_source` 以及 `resolver_called`，使配置和
实际行为可审计。

打开正式 feature flag 前必须满足：

- 题目拥有稳定 evidence anchor，且已绑定当前 corpus version；
- 题目状态为 `published`；
- 题目有 M3 审核的 `rationale`，提交答案路径不依赖 LLM；
- 没有 Gold Dev/Test 或 SciQ test split 泄漏；
- 新冻结 Gold 与已发布 practice pool 已完成反向 source ID 检查；
- Topic registry、resolver 和 topic support 检查通过；
- snapshot 在 retrieval 后、rerank 前创建；回答拒答或无 citation 时不产生 Concept Check；
- 题目可以与本轮 evidence 零重叠；若有重叠只作为排序加分；
- 唯一正确答案和难度已人工抽查；
- 生成失败有明确降级路径；
- fixture、契约、判分和状态更新测试通过；
- UI、日志和报告可以区分题目来源、题目状态和正式/练习 split。

## 11. 分阶段实施

### Phase 1：M1 契约和 fixture

- 冻结模型、枚举和 Protocol；
- 冻结 Topic registry 的**结构、版本字段和 resolver 算法**，并提供仅用于测试的 synthetic
  registry fixture；Topic 的生产内容和跨教材映射由 Phase 3 的 M3 产出，不能在 Phase 1 宣称
  内容已冻结；
- 复用现有 typed `GoldSource`、`SourceSplit` 和 `GoldSample.source`，只建立 Gold provenance
  registry / 双向泄漏 gate，不新增平行 source 类型，也不把 source split 改写成项目 dev/test；
- stable evidence anchor 和 corpus-version binding 直接使用 v2 契约里已有的 `EvidenceSpan` 和
  `EvidenceSpanBinding`（2026-09-23 已加入 `cs30.v2.contracts`），它们同时是 v2 Gold evidence
  的类型，两者不分开定义；
- fixture 题的 anchor 用 `EvidenceSpan` 表示，需要展示的 locator 只由 v2 `ids.source_locator`
  builder 生成；textbook ID 使用 `openstax_college_physics_2e`，corpus version 格式如
  `2.0.0-dev.1`；
- 加入 feature flag；
- 添加 3–5 道带 M3-reviewed `rationale` 的手写 fixture 题；
- 建立单写者 JSONL event store、最近一次撤销规则和 replay fixture；
- 为 10 个 `[concept_check]` 配置项添加 reachability 测试；
- 快照 builder 保持纯函数，Concept Check 先作为回答后的独立组件提供 fixture/API 测试；
- 不把 Concept Check 接入当前 `src/cs30/v2/pipeline.py` 语料构建入口；
- 完成契约和集成测试；
- 不调用真实 LLM。

### Phase 2：M7 核心逻辑

- 实现题目 validator、grader、Topic resolver adapter 和事件 replay/update；
- 接入 fixture provider；
- 实现难度加权和变级后的 mastery/window reset；
- 实现候选题的 JSON 解析和失败隔离；
- 输出可供 M8 使用的 attempt/grade trace。

### Phase 3：M3/M2/M4 数据接入

- 等 v2 教材（OpenStax 三本加一本 CK-12）的 chunk、Topic 和 split 冻结；
- M4 把 v1 Gold 迁移到 v2 corpus，并提供共享 span resolver；这一步完成前，§4.5 的 Gold 重叠
  门禁无法通过，任何题目都不能发布；
- M3 完成 `concept_group → topic_id` 和 textbook/chapter/section 到 Topic 的映射，以及
  easy/medium ↔ beginner/intermediate/advanced 的难度对照；
- M4 按 M3 的映射为每个 corpus manifest 生成与 `corpus_hash` 绑定的 `chunk_topic_map`
  sidecar，并通过 `validate_chunk_topic_map()`；缺失映射的 chunk 在运行时视为无 Topic；
- M3 在做 v2 Gold 时顺带标注种子段落（能独立讲清一个概念的段落，附 topic_id 和建议难度），
  只能取 evidence policy 保留的内容类型，且不能与 Test Gold 的核心证据重叠；种子段落作为
  LLM 离线出题的输入；
- 建立对齐后的 practice pool；
- M4 用共享 resolver 为每个 corpus version 生成 evidence anchor binding；
- 从 SciQ train/validation 生成候选，和全部 Gold source IDs 做双向泄漏检查；冻结新的 Gold
  时也反向检查已发布练习池；
- 生成 LLM 候选题；
- M3 审核后标记 `published`。

### Phase 4：M8 UI 和独立动态实验

- 接入 Quiz me、反馈和跳过；
- 等 v2 问答流水线具备稳定的 post-answer seam 后，再通过 integration adapter 接入独立
  Concept Check 组件；不把问答接入逻辑塞回语料构建 pipeline；
- 记录状态前后快照；
- 使用 30–60 个多轮场景评估状态更新、补救方向和学习效果；
- Concept Check 质量不达门槛时保留 feature flag 关闭。

## 12. 完成定义

初版完成时，M1 应能展示：

```text
fixture answer
  → published practice question
  → automatic validation
  → student submit
  → deterministic grading
  → LearnerState update
  → traceable result
```

同时满足：

1. v1 静态主流水线默认行为不变；
2. Concept Check 默认关闭；
3. 未审核 LLM 题目不能被正式路径读取；
4. retrieval 后能为 rerank/generation 构造 Topic snapshot；回答后能从 cited evidence
   再次确定 Concept Check Topic，无法确定或回答拒答时安全拒绝；
5. 题目通过 stable anchor 绑定当前 corpus，而不是永久依赖 chunk ID；
6. SciQ source ID、Gold Dev/Test 和 SciQ split 泄漏都有自动门禁；
7. snapshot 不覆盖静态 profile confidence，reranker 和 generation 使用同一 snapshot；
8. 题目、证据、事件和状态更新都有稳定 ID；
9. 单题失败不会中断 batch；
10. 题目 evidence binding 不要求属于本轮 top-k；citation 子集约束仍只作用于答案；
11. 难度更新使用非对称权重，level-change 使用有界窗口，变级后只升/降一级并重置 epoch；
12. `enabled=false` 完全旁路 Concept Check，正式四条件实验使用静态画像并记录
    `profile_source`；非 development 环境拒绝两个危险开关；
13. 所有 10 个配置项、契约、回放和状态更新规则都有自动化测试；
14. 三种题目来源使用同一状态流转；published 题目同时具备 M3 审核记录、审核后的
    `rationale` 和当前 corpus 的 resolved binding；
15. snapshot builder 是纯函数，Concept Check 是回答后的独立组件；当前 v2 语料构建
    pipeline 不承担问答运行时接入，未来通过 v2 问答流水线的 integration adapter 接入；
16. 题目 anchor 与 v2 Gold evidence 使用同一个证据区间类型和同一个 M4 resolver；
    `chunk_topic_map` 配置错误会被记录和统计，而不是静默当作“没有 Topic”；
17. 后续 M7、M3、M8 可以在不重复定义 schema 的情况下继续实现。
