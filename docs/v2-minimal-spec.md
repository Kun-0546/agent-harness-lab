# Harness Design Loop · v2-minimal 实现 spec

> **⚠ 命名与抽象注（Phase 1.5 加入，2026-05-21）**
>
> **产品抽象以 `product-definition.md` 为准。**
> - External coding agent is the Designer.
> - Agent Harness Lab does **not** call a built-in Designer LLM to draft experiment files.
> - 本文 §4 / §9 的论断与此一致；旧文档里残留的 "Designer Agent" / "AHL 内置 Designer LLM" 路径不是当前主抽象。
>
> **命名已对齐到 Agent Harness Lab**(Phase 2/3 已完成):CLI `ahl`、环境变量 `AHL_*`、Python 包 `agent_harness_lab`、实验目录 `harnesses/` / `cases/` / `simulator.md`。Python 模块文件 `version.py` / `testset.py` 仍沿用旧名(留作后续重构)。
>
> 本文作为 v2-minimal 的实现切片仍然有效——产品抽象以 `product-definition.md` 为准，v2-minimal 的当前实现契约以本文为准，命名以新主线为准。

> v2 第一刀(external-agent authored lab 的最小切片)的**实现级 spec** —— 具体到能照着写代码。
> 架构依据:`design-v0.4.1.md`。本文把 v0.4.1 §9 的「v2」那一档落成可建的细节,但把「Designer 是 AHL 内置 LLM」这条原始设计**主动改成**「外层 coding agent 是 Designer,AHL 是协议」。
> 分支:`v2-agent-drafted-lab`。日期:2026-05-19。
> 范围严格最小 —— §0 和 §9 划清边界。

> **核心原则**
>
> External coding agent is the Designer.
> AHL is the protocol, validator, reviewer, and runner.
> AHL does not think up the experiment; it makes agent-authored experiments inspectable, runnable, and reproducible.

---

## 0. 这一刀做什么、不做什么

**做**:把 AHL 立成**外层 coding agent**(Claude Code / Cursor / Codex 等)author 实验时的协议工具。人写一份自然语言 `brief.md`,外层 agent 据此起草整套实验定义(program / harnesses / cases / rubric / simulator),AHL 出 `review.md` 供人审,确认后走现有的 `run / score / compare`。

**AHL 自己不调模型起草实验。** 那是外层 agent 的活。AHL 只做 scaffold(`ahl draft`)、validate / review(`ahl review`)、execute(`ahl run / score / compare`)。

**不做**(留给 v2.5 及以后,见 §9):sentinel cases、adversarial bad versions、judge regression、calibration 校验闭环、authority matrix 可编辑、mode 选择器、agent-operated loop、自迭代、per-file frontmatter provenance、**AHL 内置 Designer LLM 模型路径**。

v1 的手动流程不动 —— `ahl new`(人手写模板)继续在。v2 在它旁边加一条 `ahl draft`(给外层 agent 开 authoring workspace)+ `ahl review`(出审核入口),两条并存。

**三个文件的分工**:`brief.md` 是人的意图入口(想优化什么、不能牺牲什么);`program.md` 是实验的**执行协议** —— AHL 真正读它来跑实验;`review.md` 是人的审核入口。V1 是人直接写 `program.md`,V2 是人写 `brief.md`、**外层 coding agent** 据此起草 `program.md` —— 两条路最终都收敛到同一份 `program.md`。从 `program.md` 往后(harnesses / cases / rubric / run / score / compare),V1 和 V2 完全同构。

`program.md` 是中枢,不是垃圾桶。进 program 的:实验假设、对话 / 运行 / 对比方式、留-丢规则、喊人规则、红线摘要。不进 program 的各有各的位置:provenance → review.md 的「来源」段;审核全文 → review.md;golden case → calibration/golden/;agent 的推理过程 → 不落盘;authority matrix 复杂配置 → 以后单独配。

---

## 1. v2 流程

```
人:写 goal.md(一次性)
   │
   ▼
ahl draft <名字>      为外层 agent 开 authoring workspace
                      —— 建实验目录 + brief.md 模板 + 空 harnesses/ + 空 cases/
   │
人:填 brief.md(想优化什么、验证什么改动、最在意什么、不能牺牲什么、怎么比)
   │
   ▼
外层 coding agent     据 brief.md 起草 program.md / harnesses/ / cases/ / rubric.md / simulator.md
   │                 (agent 读 docs/agent-authoring-guide.md + docs/file-formats.md;AHL 不调模型)
   │
   ▼
ahl review <名字>     宽松校验,出 review.md;缺什么标「未起草」,不抛错。可多次跑。
   │
人:读 review.md,改 rubric / 红线等锚点,确认
   │
   ▼
ahl run / score / compare   —— 跟 v1 完全一样,不变
```

---

## 2. 新增 / 改动的 CLI

**`ahl draft <名字>`** —— 为外层 agent 开 authoring workspace。**幂等可重跑。**

- 建 `experiments/NNN-<名字>/`,放 `brief.md` 模板,建空的 `harnesses/`、`cases/`。
- 已存在则不重建模板,只补缺的部分。
- 不调模型、不起草 program / rubric / simulator —— 那是外层 agent 的活。
- 输出里明示外层 agent 的下一步(读 `docs/agent-authoring-guide.md` + `docs/file-formats.md`,据 brief 起草)。

**`ahl review <名字>`** —— 出 review.md。**宽松,不抛错。**

- 读实验里现有的 brief / program / harnesses / cases / rubric / simulator。
- 缺哪份 / 哪份 parse 不动,就在 review.md 对应行标「未起草」。
- review.md 是 authoring loop 里的状态快照,可以多次跑。
- 硬关卡是 `ahl run` 的 preflight,不在这里。

其余命令(`init` / `new` / `show` / `cases` / `rubric` / `simulator` / `versions` / `run` / `score` / `compare`)不变;`ahl new` 仍是 v1 手动模板。

---

## 3. brief.md 格式

人写的自然语言入口。`ahl draft` 首次生成这个模板:

```
# brief — <实验名>

## 想优化什么
<这个 agent,你想让它哪方面变好>

## 验证什么改动
<这次具体要试的那个改动>

## 最在意什么
<判好坏时你最看重的>

## 不能牺牲什么
<哪些方面无论如何不能退化 —— 这是红线,外层 agent 会把它写进 program / rubric>

## 怎么比
<对基线 / 线性迭代;拿不准就留空,默认对基线>
```

`brief.md` 是 **human-owned** —— 外层 agent 读它,不改它,除非用户明确叫它改。

---

## 4. External-Agent Authoring Contract —— 本刀的核心

> 概念对应：本节的 external coding agent / Lab as protocol 抽象，对应 `product-definition.md` §0 三句定义和 §3 核心对象（Harness Variant / Runnable Subject）。本节是该抽象在 v2-minimal 阶段的具体契约。

AHL **不**内置 Designer 模型。author 实验这事是**外层 coding agent**(Claude Code / Cursor / Codex 等)的活。AHL 给 agent 提供:

- 一个 scaffolded 实验目录(`ahl draft`),
- 起草格式的权威 spec(`docs/file-formats.md` + 本文 + `docs/agent-authoring-guide.md`),
- 一个宽松的 review 入口(`ahl review`),
- 硬关卡(`ahl run` 的 preflight + 各 parser 的 `validate()`)。

**外层 agent 的职责**:

- 读 `goal.md`(用户总目标)和 `experiments/<id>/brief.md`(用户这次意图)。
- 起草:`program.md`、`harnesses/V*.md`、`cases/D*.md`、`rubric.md`、`simulator.md`,全部写进 `experiments/<id>/`,格式按 `docs/file-formats.md`。
- **不动** `brief.md`、`goal.md`、`connect.md` —— 这些是 human-owned,除非用户明确要求。
- 把 brief 的「不能牺牲什么」落进 `rubric.md` 的某个维度或 `program.md`(人审 review 时重点核这条)。
- 起草完跑 `ahl review <名字>` 自验。

**AHL 的职责**(本刀):

- `ahl draft`:scaffold 实验目录 + brief.md 模板。**不调模型。**
- `ahl review`:读现有产物,出 review.md。**宽松,不抛错。**
- `ahl run / score / compare`:跟 v1 完全一样。preflight 是硬关卡。

**AHL 明确不做**:不内置 Designer LLM,不调模型起草 program / harnesses / cases / rubric / simulator。理由:外层 coding agent 有上下文、有文件编辑能力、有自己的 token 预算 —— AHL 再装一个 Designer LLM 是 information disadvantage 摆到决策位上,也违反 Unix-tool 美学(`pytest` 不写测试,`ahl` 不写实验)。

**Agent-facing 文档**:`docs/agent-authoring-guide.md` 是给外层 coding agent 读的「authoring 指南」—— 角色、必读输入、要造的工件、不变量、起草前 checklist、命令清单。本文 + `docs/file-formats.md` 是协议规范;guide 是把规范翻译成给 agent 的 actionable 指引。

---

## 5. Provenance(集中式)

本刀的 provenance 是**集中式**的 —— 不往每个文件的 frontmatter 塞来源戳,而是在 `review.md` 里用「来源」段统一交代:

```
- brief.md:human
- program.md:external_agent_drafted
- harnesses/:external_agent_drafted
- cases/:external_agent_drafted
- rubric.md:external_agent_drafted
- simulator.md:external_agent_drafted
```

哪份产物没起草,对应行标 `未起草`。

这样不动 v1 的 parser(program / version / testset / rubric / simulator 都不必多认一段 frontmatter),provenance 又有地方落 —— review.md 本就是人的审核入口。

留到 v2.5(见 §9):per-file frontmatter 来源戳、`approval_state` 字段、`ahl approve` 审批闭环、`run` 跑前对未批准产物的提醒 / 硬拦。

---

## 6. review.md

`ahl review` 生成,放实验目录。人只看这一份,不必翻五六个文件:

```
# review — <实验名>

- 实验目标:<program 假设的一句话,缺则标「program.md 未起草」>
- V1 / V2 / …:<每个版本一句「这是什么」+ 基线标记>
- rubric:<各维度 + 权重>
- 红线(brief):<brief「不能牺牲什么」原文 —— 人审时核它是否落进 rubric / program>
- cases:<case 数;下逐条列 id + 一句起始输入>
- simulator 人设:<一句>

## 来源
<见 §5 的集中式来源>
```

review.md 是只读呈现 —— 人要改就改底下的实际文件(尤其 rubric.md),再跑 `ahl review` 重出。

---

## 7. golden cases(最小结构)

本刀只立 `calibration/golden/` 的目录和文件格式,不做「拿 golden 校 judge」的闭环(那是 v2.5)。

```
calibration/              工作区根,跨实验共用
└── golden/
    └── <case>.md
```

golden case = 一段对话 + 人给的明确判断:

```
---
id: golden-01
verdict: good             # good / bad
---
## 对话
<一段 user / agent 对话>

## 为什么
<人为什么判它 good / bad —— 一两句>
```

到此为止:目录在、格式定了。用它回归测 judge 是 v2.5。

---

## 8. 跟 v1 的关系

- `ahl new`(v1 手动)和 `ahl draft`(v2 给外层 agent 开 scaffold)并存,人选哪条跑哪个命令。
- 外层 agent 起草出的 program / harnesses / cases / rubric / simulator,跟人手写的同格式 —— 所以 `run / score / compare` 一行不用改,直接复用。
- v2-minimal 是在 v1 管线**前面**接「scaffold + agent 起草 + 审」,管线本身不动。
- **V2 生成的所有实验文件,以 `program.md` 为共同锚点;`run / score / compare` 不关心实验是人手写还是外层 agent 起草的,只读同一套 v1 文件格式。** 这是 v1 可信底座不被 v2 污染的关键(见 §0「三个文件的分工」)。

---

## 9. 不做的(v2.5 及以后)

sentinel cases、adversarial bad versions、calibration 校验闭环(拿 golden / 坏版本测 judge)、judge regression、per-file frontmatter 来源戳、`ahl approve` 审批闭环、`run` 跑前提醒 / 硬拦未批准产物、authority matrix 可编辑 + mode 选择器、agent-operated loop、自迭代、escalation 规则 —— 对应 v0.4.1 §9 的 v2.5 / v3 / v4。

**AHL 内置 Designer LLM** —— **主动放弃,不是 deferred**。外层 coding agent 是 Designer 这条是产品定位,不会再回头加内置 Designer。

---

## 10. 建议实现顺序

新实现按这个顺序走(也是当前代码到位的顺序):

1. `ahl draft` 退到 scaffold-only:建实验目录 + brief.md 模板 + 空 harnesses/ cases/。幂等可重跑。
2. brief.md parser + `Brief.compare_mode` / `Brief.validate()`(空 / 占位符 / 非法 → 对基线)。
3. `ahl review` + `workflow.review`:宽松读现有产物,缺什么标「未起草」,出 review.md;不调模型,不抛错。
4. `_build_review`:支持任何产物为 None,统一渲染。
5. `calibration/golden/` 目录约定 + golden case 格式(约定为主,代码极少)。
6. 文档:本文 + `docs/agent-authoring-guide.md`(给外层 agent 读)+ `docs/file-formats.md` 同步状态。
7. e2e:模拟外层 agent 写文件 → `ahl review` → `run / score / compare` 跑通。

每步保持现有测试绿。

---

## 关系

依据 `design-v0.4.1.md`(v2 架构),落地其 §9 的 v2 一档,但把「Designer 是 AHL 内置 LLM」这条原始设计**主动改成**「外层 coding agent 是 Designer,AHL 是协议」。v1(`design-v0.3.md` + 现有代码)不动。
