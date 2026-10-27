# M7：全局等级画像与逐级核查清单 v1

日期：2026-10-21。对应评估方案 §3.1、§3.4 和 backlog B14。

**状态：M7 编写完成，等待 Leader 共同确认、M3 物理核对后冻结。** 本稿不表示 Leader 已参与编写，不表示 M3 已审核，也不表示 judge 已校准。机器文件中 `frozen=false`、`physics_reviewer_ids=[]`；M8 的冻结包加载器会拒绝本稿。

**修订（2026-10-21，Leader 审核意见）：** 用 M7 的画像和清单试跑本地 judge 时，一句话的识别题答案在推理类条目上被判为不通过。为此补充识别题的判定规则（B1、B2、I1、I2、A4），并把混水计算题换成识别型示例题 `m7-anchor-siren-doppler`；草稿内容哈希随之更新，审核仍待完成。

英文画像、清单与锚点用于英文物理问答的 judge 输入；下列内容与同目录的 `profile_checklist.draft.json` 对应。

## 使用原则

- 三档是跨 Topic 的固定先验，不按章另建画像；陌生专业概念在任何档都可能需要解释。
- 以学生先备知识和所需推理决定适配，不以字数、术语数量、公式数量或句数代替评分。
- 每次只读一份匿名答案。适切度读取目标档画像及清单；区分度读取三份画像，但隐藏目标档。不得要求对三份答案排序。
- 清单统一 `pass / fail / not_applicable`（是 / 否 / 不适用）。通过与不通过必须给简短理由；通过附答案精确子串。不通过若因内容缺失，可用 `exact_quote=null` 并明确缺了什么；已有错误内容时引用原文。不适用须 `exact_quote=null` 并依据题目和先验说明原因。不得编造不存在的原文。
- 题目只要求识别或说出名称、不问为什么或怎样时，答对且没有无依据的说法即满足 B2、I1、I2、A4，不能因为没有推导而判不通过；题目本身已用的术语不要求再解释（B1）。
- 不适用只由题目和目标档判断，不能因答案漏写而使用。不适用从该条分母剔除；整份无适用项时不记满分。B1/B2/B4、I1/I2/I3、A1/A4 对有内容的答案均评；B3、A2、A3 的触发条件写在各条内。
- 画像中陌生术语、符号和关键推理不能因“高级”一词就自动视为已知。高级学生不是所有领域的专家。
- 正确性按三档统一标准另评；适配通过率不能补偿错误事实。适切度达标阈值、judge 有效性阈值、λ 和题目 eligibility 不由本交付擅自设定。
- 示例用于理解标准，不是硬性答案模板，不要求复写其长度或措辞；同一答案适合多档是允许的。

## 画像总览

| 等级 | 学生定位 | 数学与推理边界 |
|---|---|---|
| 初学者 | 未学过大学物理，不假设已学过高中物理 | 算术和比例；新物理概念逐步连接，公式须解释 |
| 中级 | 正在修或刚修完代数版大一基础物理 | 代数、初等向量和三角；原理到结论清楚，常规变形可省略 |
| 高级 | 已修完微积分版基础物理 | 可跟随标准微积分模型；保留重要假设、边界和非显然推理，避免冗余基础教学 |

这是本项目的**操作性定义**，不是对所有真实学习者的测量结论。高级写作避免冗余的设计参考 [Kalyuga 等（2003），The Expertise Reversal Effect](https://doi.org/10.1207/S15326985EP3801_4)：教学支持的作用会随已有知识改变；本项目仍须单独验证 judge。

## 初学者（beginner）

### 1. 学生定位

A learner who has not taken university physics. Everyday observations are available, but high-school physics coverage is not assumed. This is one global prior across topics, not a different level for each chapter.

### 2a. 已有物理基础

- Everyday experience of pushes, falling, warm and cool objects, light, sound, and household batteries; these experiences do not imply knowledge of their physical mechanisms.
- No prior mastery of Newton laws, conservation laws, fields, waves, thermal models, or circuit laws; introduce any required law or physical quantity in context.

### 2b. 已有数学基础

- Arithmetic, fractions, ratios, unit reading, and substitution into a fully explained simple relation.
- Do not assume algebraic rearrangement, vector components, trigonometric identities, calculus, or differential equations; explain any indispensable extension.

### 3. 可不加解释使用的术语

- everyday uses of push, pull, heavier, warmer, cooler, distance, time, and speed
- common units such as seconds, metres, grams, and degrees Celsius; introduce unfamiliar units and scientific meanings in context

### 4a. 可接受的推理跨度

Make each new physical inference explicit: observation or given condition -> explained physical idea -> consequence -> requested answer. Ordinary arithmetic may be combined if its meaning is stated. This is a dependency rule, not a maximum sentence count or a fixed number of reasoning steps.

### 4b. 可省略的步骤

- Counting and elementary arithmetic after explaining what is being calculated.
- Restating information already made concrete in the question; use that situation as support instead of adding an unnecessary second analogy.

### 5a. 有帮助的写法

- Introduce a needed physics term in everyday words when first used, including ordinary words used with a specialised meaning such as work, power, or field.
- Use the given situation, a concrete example or a bounded analogy to make an unfamiliar concept understandable; explicitly connect it to the conclusion.
- Explain the meaning of each introduced formula and symbol, why the relation applies, and the physical meaning of the result. A correct simple equation is welcome when useful.

### 5b. 应避免的写法

- A bare name, unexplained symbol, or law citation standing in for an explanation the question asks for.
- Unexplained calculus, vector notation, or technical analogies; a literal claim based on an analogy that changes the physics.
- Filling a sentence quota, adding decorative examples, or treating shorter answers or formula-free answers as automatically better.

## 中级（intermediate）

### 1. 学生定位

A learner currently taking or recently completing an algebra-based first-year introductory physics course. The assumed core is shared globally across topics; unfamiliar specialist topics still need explanation.

### 2a. 已有物理基础

- Introductory kinematics, Newton laws, work and energy, momentum and conservation principles.
- Basic temperature, heat transfer, waves, superposition, charge, potential difference, Ohm law, and simple series/parallel circuits at introductory course level.
- Can recognise standard idealisations such as negligible friction and ideal voltage sources; does not know every advanced model or exception.

### 2b. 已有数学基础

- Algebraic rearrangement, proportions, graphs and slopes, powers and roots, units and dimensional checks.
- Basic vectors and trigonometry for introductory components; calculus and differential-equation solutions are not assumed.

### 3. 可不加解释使用的术语

- displacement, velocity, acceleration, net force, mass, inertia, work, kinetic and potential energy, momentum
- heat, temperature, specific heat, thermal equilibrium, frequency, wavelength, superposition
- charge, current, voltage, resistance, series and parallel, Newton laws, conservation of energy and charge, Ohm law

### 4a. 可接受的推理跨度

Name the governing principle, connect the question conditions to it, and state how it produces the conclusion. Routine substitution and algebra may be compressed; do not omit the choice of model, causal link, sign convention when consequential, or a non-obvious approximation. No sentence quota applies.

### 4b. 可省略的步骤

- Routine arithmetic, elementary rearrangement, and repeated definitions of mastered course terms.
- A full proof of a standard introductory law when naming and applying it supplies the requested explanation.

### 5a. 有帮助的写法

- Organise around the governing principle, its application to the givens, and the resulting physical interpretation.
- Use standard course terms accurately and introduce specialist quantities or notation not in the assumed core.
- Use equations when they clarify the mechanism or calculation and explain an important approximation or ambiguity.

### 5b. 应避免的写法

- Repeating elementary dictionary definitions without advancing the answer.
- Quoting a law without connecting it to the requested result, or substituting arithmetic for the physical argument.
- Assuming a calculus derivation or unfamiliar specialist terminology is automatically known.

## 高级（advanced）

### 1. 学生定位

A learner who has completed calculus-based introductory university physics, not a subject specialist or research physicist. The same global prior applies to all topics; advanced specialist results still require context.

### 2a. 已有物理基础

- Calculus-based mechanics, energy and momentum, oscillations and waves, basic thermal physics, electricity and magnetism.
- Can select introductory models, follow conservation and field arguments, and recognise the role of idealisation, initial conditions, limiting cases and dimensional consistency.
- Does not automatically know quantum field theory, advanced statistical mechanics, tensor methods, or every named specialist effect.

### 2b. 已有数学基础

- Algebra, trigonometry, vectors, derivatives and elementary integrals with physical interpretations.
- Can interpret a standard introductory differential equation, approximation, or limiting relation; solving an arbitrary differential equation and advanced mathematical methods are not assumed.

### 3. 可不加解释使用的术语

- standard introductory mechanics, thermal, wave and electromagnetism terminology listed for the intermediate level
- derivative, integral, vector component, small-angle approximation, ideal source, boundary condition, conservation equation, limiting case and dimensional analysis

### 4a. 可接受的推理跨度

A standard law-to-model-to-result chain may be compressed into a well-defined relation and interpretation. Routine calculus and algebra can be omitted when recoverable from the stated model. Keep any non-obvious model choice, important assumption, boundary of validity, or logical qualification visible. Concision never excuses an unsupported leap.

### 4b. 可省略的步骤

- Definitions of familiar introductory terms and standard laws.
- Routine algebra, elementary differentiation/integration, and numeric substitutions when they do not resolve an ambiguity.
- Beginner scaffolding or a second analogy that merely repeats an already transparent physical relation.

### 5a. 有帮助的写法

- Give the requested result with a compact physical argument and state assumptions that change its validity.
- Use a quantitative relation, scaling argument, or limiting case only when it clarifies the question; define specialised symbols.
- Account for expertise reversal: support that explains an unfamiliar step can help, while repeated mastered definitions can impose redundant processing. Judge redundancy by its role, not by answer length.

### 5b. 应避免的写法

- Automatic tutorials on familiar concepts that obscure the requested result.
- Prestige jargon, gratuitous equations, or specialist methods used to signal sophistication.
- Unqualified generalisations beyond an ideal model, unexplained novel notation, or compression that hides a necessary inference.

## 6. 非 Gold 示例题与三档好答案

三道题由本次 M7 交付新写，覆盖力学、声学和电路；第 2 题为识别题（2026-10-21 替换原混水计算题）。每档回答同一题。检查器只比较 Gold 题号与规范化题干，不读 Gold 参考答案或使用已有生成答案；精确不重合不等于已完成人工语义审查。

### 示例 1：m7-anchor-pendulum-mass

**题目**

Two ideal simple pendulums have the same length and are released from rest at the same small angle at the same location. One bob has twice the mass of the other. Neglect string mass, friction, and air resistance. Does the heavier bob take longer to complete one swing? Explain.

**初学者答案**

No. The period, the time for one complete swing, is the same. Gravity pulls twice as strongly on the heavier bob, but its greater mass also makes its motion twice as hard to change. These effects balance. With equal lengths and small starting angles, neither bob takes longer.

**为什么符合该档：** Defines period and explains both causal links without requiring a familiar pendulum formula; the concrete comparison in the question supplies B3 support.

**中级答案**

The periods are equal. By Newton's second law, the tangential gravitational force and inertia both scale with bob mass, so mass cancels when finding tangential acceleration. With equal lengths and the same small initial angle, the two pendulums have the same motion in time.

**为什么符合该档：** Names the governing law and connects force scaling to mass cancellation; does not redefine force or acceleration.

**高级答案**

The periods are equal. For an ideal point bob on a massless inextensible string, the small-angle equation is theta-double-dot + (g/L)theta = 0, giving T = 2 pi sqrt(L/g), independent of bob mass. Here L is pendulum length, g is local gravitational acceleration, theta is angular displacement, and T is period. The equal-length, small-angle and negligible-damping assumptions justify this expression.

**为什么符合该档：** Uses a compact quantitative argument with its idealisation and small-angle scope; no introductory explanation of gravity or inertia.

### 示例 2：m7-anchor-siren-doppler

这是只要求说出名称的识别题。Dev 中识别与定义题共 93/162，本题示范 B2、I1、I2、A4 在这类题上如何判：答对且没有无依据的说法即可通过，不要求题目没问的推导；各档的差别体现在术语解释（B1）和是否冗余（I3、A1）。

**题目**

An ambulance siren sounds higher in pitch while the ambulance approaches a listener standing at the roadside, and lower in pitch after it passes. What is this effect called?

**初学者答案**

This is called the Doppler effect: the pitch you hear, meaning how high or low a sound seems, changes when the source of the sound moves toward you or away from you. The siren itself keeps making the same sound; only the pitch reaching you changes.

**为什么符合该档：** Names the effect and explains the new term in everyday words. The question asks only for the name, so B2 is met by the correct identification without a derivation, and the situation in the question already supplies concrete support. Separating the sound made from the sound heard avoids a misleading claim.

**中级答案**

The Doppler effect. Motion of the sound source relative to the listener changes the frequency the listener receives: it is higher while the source approaches and lower while it recedes.

**为什么符合该档：** The correct name satisfies I1 for an identification question, and one sentence links it to the observed pitch change in course terms such as frequency, without redefining sound or pitch. No derivation is needed because the question asks only for the name.

**高级答案**

The Doppler effect for sound: the observed frequency is higher than the emitted frequency while the source approaches and lower while it recedes; the siren's emitted frequency itself is unchanged.

**为什么符合该档：** A precise identification that separates observed from emitted frequency passes A4 without an argument the question does not ask for. No quantitative relation is needed, so A3 is not applicable, and there is no redundant tutorial on sound or frequency (A1).

### 示例 3：m7-anchor-parallel-current

**题目**

An ideal 9 V battery initially supplies one 6 ohm resistor. A second constant 6 ohm resistor is then connected in parallel, across the same battery terminals. Neglect wire resistance. How do the total battery current and the current in the original resistor change? Explain.

**初学者答案**

The battery current doubles, from 1.5 A to 3 A; the original resistor still carries 1.5 A. Current is the rate at which electric charge, a property of particles such as electrons, passes a point; it is measured in amperes (A). Parallel means that both resistors connect across the same two battery terminals. Each therefore has the same 9 V voltage, the energy supplied per unit charge. Resistance measures how strongly a component opposes this flow. For a resistor, dividing voltage by resistance gives current: 9 divided by 6 is 1.5 A. The two branch currents add, giving 3 A.

**为什么符合该档：** Defines current, voltage and parallel connection, introduces the current calculation in words, and shows branch addition rather than using an unexplained equivalent-resistance shortcut.

**中级答案**

Ohm's law gives I = V/R = 9/6 = 1.5 A in each branch because each parallel resistor has the full battery voltage. Kirchhoff's junction rule gives total current 1.5 + 1.5 = 3 A. Thus battery current doubles, while the original branch current remains 1.5 A.

**为什么符合该档：** Connects Ohm's law and charge conservation to the two requested currents without repeating elementary definitions.

**高级答案**

With ideal fixed terminal voltage and constant ohmic resistances, I_original = V/R = 1.5 A before and after the change. Adding the identical parallel branch changes equivalent resistance from R to R/2 = 3 ohms, so I_total changes from V/R = 1.5 A to 2V/R = 3 A. Nonzero battery internal resistance could lower terminal voltage and invalidate the unchanged-branch-current conclusion.

**为什么符合该档：** Uses compact relations and identifies the important ideal-source boundary; no redundant introduction to current or voltage.

物理关系交叉核对资料（仅核对原理，本题情境、参数及答案为本次编写）：

- [OpenStax：Pendulums](https://openstax.org/books/university-physics-volume-1/pages/15-4-pendulums)：小角度单摆模型及质量消去。
- [OpenStax：The Doppler Effect](https://openstax.org/books/university-physics-volume-1/pages/17-7-the-doppler-effect)：声源靠近时观察频率升高、远离时降低，声源发出的频率不变。
- [OpenStax：Parallel Circuits](https://openstax.org/books/physics/pages/19-3-parallel-circuits) 与 [Electromotive Force](https://openstax.org/books/university-physics-volume-2/pages/10-1-electromotive-force)：并联支路同电压、理想电池假设。

这些资料支持公式和物理模型，不替代 M3 审核，也不证明画像已经得到真实学习者验证。

## 逐级核查清单

下列条目由上述先备知识、推理跨度和写作需求推出。完整说明直接进入 M8 的 `ChecklistCriterion.description`，避免只有人工文档知道“不适用”的触发条件。

### 初学者

**B1** — Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained.

**B2** — Make the physical reasoning needed to answer the question recoverable from the beginner prior: connect the givens, the introduced physical idea, and the conclusion without an unexplained conceptual jump. Routine arithmetic can be combined. Always assess. If the question only asks to identify or name a term, object, quantity, or fact, and does not ask why or how, a correct identification with no unsupported claim passes; do not require reasoning the question does not ask for. Otherwise a missing necessary step is fail, never not_applicable.

**B3** — When an unfamiliar abstract concept needs concrete support, supply a correct example, bounded analogy, explicit concrete calculation, or explanatory use of the situation already in the question. Assess necessity from the question and beginner prior before inspecting whether support was supplied. If no such support is needed for this question, use not_applicable; if needed but missing, use fail. Extra decorative examples earn no credit.

**B4** — Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule.

### 中级

**I1** — Identify the governing principle, law, or concept relevant to the question. Use standard terminology accurately. If the question only asks to identify or name a term, object, quantity, or fact, the correct identification itself satisfies I1. Always assess substantive answers. Do not demand an irrelevant law or a proof just to make the answer look longer.

**I2** — Explain how the givens, evidence, or governing principle lead to the conclusion at the intermediate prior. Routine algebra may be compressed, but a non-obvious physical inference or consequential assumption must remain clear. Always assess. If the question only asks to identify or name a term, object, quantity, or fact, and does not ask why or how, a correct identification with no unsupported claim passes; do not require an explanation the question does not ask for. Otherwise a missing necessary connection is fail, not not_applicable.

**I3** — Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length.

### 高级

**A1** — Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language.

**A2** — State or unambiguously invoke important assumptions and scope when relaxing them could change the answer. Conditions already explicit in the question may be invoked compactly without copying all givens. Determine applicability from the question and advanced prior: if no consequential restriction requires discussion, use not_applicable; if one is necessary but omitted, use fail.

**A3** — Use an accurate quantitative, scaling, or limiting relationship when it materially explains the question or is required for the requested result, with sufficient symbol meaning for the advanced prior. Determine usefulness from the question and prior, not whether the answer contains an equation. If none is useful, use not_applicable; if useful but absent or incorrectly used, use fail. Gratuitous formulas do not count as success.

**A4** — Give a logically supported, precise physical argument with appropriately qualified claims, consistent quantities and no misleading over-generalisation. Standard recoverable steps may be compressed; specialist notation and non-obvious inferences still require enough context. Always assess substantive answers. If the question only asks to identify or name a term, object, quantity, or fact, and does not ask why or how, a correct and precisely stated identification with no unsupported or over-general claim passes; do not require an argument the question does not ask for. Apparent sophistication and formula count do not establish rigour.

## 与生成 prompt 的独立性及差异记录

The profiles are specified from learner prerequisites and the evaluation plan, independently of prompt wording. A subsequent comparison with _LEVEL_GUIDANCE in src/cs30/generation/prompt.py (member7-prompt-v1) finds that the generator prescribes two to four sentences for beginner and three to five for intermediate, whereas this evaluation has no sentence quotas. The prompt does not enumerate the physics/mathematics prior, allowed terminology, omittable steps or expertise-reversal redundancy rule. These differences are recorded, not resolved by weakening the profiles or changing generation guidance; no existing generated answers were used to choose anchors or criteria.

本稿未修改 `_LEVEL_GUIDANCE`，也未重跑或打分 Dev/Test 答案。后续若调整生成 prompt，应另行记录版本并遵循评估方案的重跑规则，不能修改评价标准去迎合输出。

## M7 → Leader / M3 / M8 交接

1. Leader 逐条确认学生定位、先备知识、清单及示例。M3 独立核对物理关系、理想化条件、量纲和三个答案的教学表述；特别检查单摆的小角度模型、多普勒效应中观察频率与发出频率的区分、并联电路的理想电源边界。
2. 在 `review_record.template.json` 的副本填写真实审核人、审核记录 ID、带时区时间及理由；尚未核对必须保持 `pending`。任何内容修订都先更新草稿内容哈希，再重审；旧审核记录不能批准新内容。
3. 两份真实审核均为 `approved` 后，用下面的导出命令生成 M8 原生 `ProfileChecklistPackage`；工具保留独立审核人、原草稿哈希、审核记录哈希和冻结包哈希，不会把软件测试当作 M3 签名。
4. M8 用既有 `load_profile_checklist_package` 读冻结包；适切度和区分度使用同一个内容包。再进行 Dev judge 校准和有效性检查，不能把导出成功当作 judge 已有效。
5. M3 按画像做 eligibility 标注、Leader 决定相关阈值。这些是后续团队任务，不阻止本次 M7 编写成果入库；B14 的“已共同同意”验收仍待团队记录。

```sh
python -m cs30.evaluation.profile_authoring \
  docs/evaluation/level-profile-v1/profile_checklist.draft.json \
  --gold m3_gold/gold_v0_1_1.jsonl
```

需要时为 `--gold` 追加实际使用的 v0.1.2 Gold 文件；验证记录已另核对现有 188 题文件。以下冻结命令**仅在真实审核完成后**运行：

```sh
python -m cs30.evaluation.profile_authoring \
  docs/evaluation/level-profile-v1/profile_checklist.draft.json \
  --gold m3_gold/gold_v0_1_1.jsonl path/to/actual-v2-gold.jsonl \
  --review-record path/to/completed-review-record.json \
  --output artifacts/evaluation/level-profile-v1.frozen.json
```

工具同时保存 `.review.json` 来源记录。冻结表示画像审核完成，不代表整个实验 `reportable=true`；该决定仍由 M8 的其余冻结配置及检查控制。

当前草稿内容哈希：`2c61590cf98989d652602750cc6519e05fcc25122ac82a7b579e78890ee0716e`。

**2026-10-27 已冻结。** Leader 批准草稿原样冻结，并豁免 M3 物理审核（见 `docs/构思与待定.md` 已定表）。冻结包是 [`profile_checklist.frozen.json`](profile_checklist.frozen.json)，内容哈希 `1888c3b7fb6f2f0fd52dbe06455c40cef88ff8839ab47383a76d7c29a1088238`；审核记录是 [`review_record.leader-2026-10-27.json`](review_record.leader-2026-10-27.json)，导出来源记录是 [`profile_checklist.frozen.review.json`](profile_checklist.frozen.review.json)。包内 `physics_reviewer_ids` 为空，`physics_review_waiver` 记录豁免人、时间和理由；报告须写明画像未经独立物理审核。锚点与 Gold v0.1.3 全部 341 题的题号/规范化题干碰撞为 0。

## 本次 M7 自检记录

- 专项核查：23 项通过，覆盖内容完整性、草稿禁止进入冻结加载器、旧哈希/缺审核拒绝、审核记录完整性、内存修改后的重新校验、Gold 碰撞、真实 M8 两类请求组装和导出来源记录。
- 全量回归：隔离的最终代码副本中 **1086 passed, 2 skipped**；全仓代码规范检查通过。隔离副本使用 `main` 中的公共契约，未带入用户原有的无关未提交修改。
- 两项跳过原因：本机未配置 M2 parser 输出目录，以及未缓存固定版本的 BERT tokenizer；没有将其记作通过。
- 20 题已入库 Gold 与现有 v2 188 题文件的题号/规范化题干碰撞均为 0。只做锚点独立性校验，未运行 Test 生成、judge 评分或 Test 调参；自动校验不能代替 M3 的语义核对。
- 人工可读文档与机器文件的 90 个画像、锚点及条目文本字段一致；并联电流结果另行复算，单摆模型与多普勒效应另对照教材原理。
- 详细来源、文件哈希及检查范围见 [verification.json](verification.json)。本次只有 M7 编写与软件自检完成；Leader/M3 的真实审核和 judge 校准仍待各负责人执行。
