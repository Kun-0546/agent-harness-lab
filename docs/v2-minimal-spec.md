# Harness Design Loop · v2-minimal 实现 spec

> v2 第一刀(agent-drafted lab 的最小切片)的**实现级 spec** —— 具体到能照着写代码。
> 架构依据:`design-v0.4.1.md`。本文把 v0.4.1 §9 的「v2」那一档落成可建的细节。
> 分支:`v2-agent-drafted-lab`。日期:2026-05-18。
> 范围严格最小 —— §0 和 §9 划清边界,sentinel / adversarial / 自迭代 / authority matrix 一律不在本刀。

---

## 0. 这一刀做什么、不做什么

**做**:让人少写实验文件。人写一份自然语言的 `brief.md`,Designer Agent 据此起草整套实验定义(program / versions / 测试集 / rubric / 模拟器),人审一份 `review.md`,确认后走现有的 `run / score / compare`。

**不做**(留给 v2.5 及以后,见 §9):sentinel cases、adversarial bad versions、judge regression、calibration 校验闭环、authority matrix 可编辑、mode 选择器、agent-operated loop、自迭代。

v1 的手动流程不动 —— `hdl new`(人手写模板)继续在。v2 在它旁边加一条 `hdl draft`(agent 起草),两条并存。

**三个文件的分工**:`brief.md` 是人的意图入口(想优化什么、不能牺牲什么);`program.md` 是实验的**执行协议** —— HDL 真正读它来跑实验;`review.md` 是人的审核入口。V1 是人直接写 program.md,V2 是人写 brief.md、Designer 据此生成 program.md —— 两条路最终都收敛到同一份 program.md。从 program.md 往后(versions / 测试集 / rubric / run / score / compare),V1 和 V2 完全同构。

`program.md` 是中枢,不是垃圾桶。进 program 的:实验假设、对话 / 运行 / 对比方式、留-丢规则、喊人规则、红线摘要。不进 program 的各有各的位置:provenance → review.md 的「来源」行;审核全文 → review.md;golden case → calibration/golden/;Designer 的推理过程 → 不落盘;authority matrix 复杂配置 → 以后单独配。

---

## 1. v2 流程

```
人:写 goal.md(一次性)
   │
   ▼
hdl draft <名字>      首次 —— 建实验目录 + brief.md 模板
   │
人:填 brief.md(想优化什么、验证什么改动、最在意什么、不能牺牲什么)
   │
   ▼
hdl draft <名字>      再次 —— Designer 据 brief + goal 起草整套实验定义,生成 review.md
   │
人:读 review.md,改 rubric / 红线等锚点,确认
   │
   ▼
hdl run / score / compare   —— 跟 v1 完全一样,不变
```

---

## 2. 新增 CLI:`hdl draft`

`hdl draft <名字>` —— 一个命令、两阶段,按实验当前状态分发:

- **实验不存在** → 建 `experiments/NNN-<名字>/`,放一个 `brief.md` 模板,建空的 `versions/`、`测试集/`。提示:「填 brief.md,再跑 hdl draft <名字>」。
- **brief.md 已填、还没起草** → 调 Designer(§4)起草 program.md / versions/ / 测试集/ / rubric.md / 模拟器.md,再生成 review.md(§6),provenance 集中记进 review.md(§5)。提示:「草案生成,审 review.md」。
- **已起草过**(program.md 已存在)→ 默认拒绝覆盖;`--force` 才重起草。

其余命令(`init` / `new` / `show` / `run` / `score` / `compare` / …)不变;`hdl new` 仍是 v1 手动模板。

---

## 3. brief.md 格式

人写的自然语言入口。`hdl draft` 首次生成这个模板:

```
# brief — <实验名>

## 想优化什么
<这个 agent,你想让它哪方面变好>

## 验证什么改动
<这次具体要试的那个改动>

## 最在意什么
<判好坏时你最看重的>

## 不能牺牲什么
<哪些方面无论如何不能退化 —— 这是红线,Designer 会把它写进 program / rubric>

## 怎么比
<对基线 / 线性迭代;拿不准就留空,默认对基线>
```

Designer 只读 brief.md,不改它(brief.md 是 human_owned)。

---

## 4. Designer Agent 契约 —— 本刀的核心

新模块 `src/harness_design_loop/designer.py`。Designer 是 **hdl 内置能力**(像 llm simulator / llm judge):hdl 自己持有 prompt、自己调模型。对应 v0.4.1 §9「v2 必须实现 Designer Agent」。

**三个我按推荐做法定下的决定(你审)**:

- **① 两次调用,program 先行。** 一次性让模型生成整包,文件之间容易不自洽(rubric 维度对不上假设)。分两步:
  - Call 1:`brief.md + goal.md` → `program.md`。
  - Call 2:`program.md + brief.md` → `versions/V1.md`、`V2.md` + `测试集/*.md` + `rubric.md` + `模拟器.md`。
  program 是实验的锚,先定它,其余都挂在它上面。
- **② 内置,不外接。** Designer = hdl 里的一段 prompt + 一次模型调用,复用现有 `llm.py`。理由:Designer 的质量取决于那段 prompt,hdl 自己持有才能自己迭代;外接会把 prompt 质量甩给用户。
- **③ 新的 `HDL_DESIGNER_*` 环境变量**(`BASE_URL` / `MODEL` / `API_KEY`),跟 `HDL_SIM_*`、`HDL_JUDGE_*` 同构。Designer 是第三个 LLM 角色,可能要用比 simulator / judge 更强的模型,配置分开干净。

**契约**:

- 输入:`brief.md`(解析后)、`goal.md`(原文)。
- 输出:program.md、versions/、测试集/、rubric.md、模拟器.md —— 写进实验目录;来源信息集中写入 review.md(§5)。
- Designer 不碰 `goal.md`、`brief.md`、`connect.md`(都是人的)。
- **失败硬退**:模型调用失败、或输出解析不出来 → 抛 WorkflowError;此时还没落盘,原有草案不动。落盘后没过 parser / validate 校验同样抛错;半成品留在原地,下次 `hdl draft --force` 重起草前会清掉。draft 失败即时回滚半成品留 v2.5。
- 起草出的文件,要能过现有 parser(program / version / testset / rubric / simulator)和它们的 `validate()` —— prompt 里带格式要求;生成后 hdl 自己跑一遍 parser 校验,不过就当 Designer 失败。

---

## 5. Provenance(集中式)

本刀的 provenance 是**集中式**的 —— 不往每个文件的 frontmatter 塞来源戳,而是在 `review.md` 里用一行「来源」统一交代:program / versions / 测试集 / rubric / 模拟器 都是 Designer 据 brief 起草、待人确认。

这样不动 v1 的 parser(program / version / testset / rubric / simulator 都不必多认一段 frontmatter),provenance 又有地方落 —— review.md 本就是人的审核入口。

留到 v2.5(见 §9):per-file frontmatter 来源戳、`approval_state` 字段、`hdl approve` 审批闭环、`run` 跑前对未批准产物的提醒 / 硬拦。

---

## 6. review.md

`hdl draft` 起草后生成,放实验目录。人只看这一份,不必翻五六个文件:

```
# review — <实验名>

- 实验目标:<program 假设的一句话摘要>
- V1 / V2:<两个版本各一句「这是什么」>
- rubric:<各维度 + 权重>
- 红线:<brief「不能牺牲什么」→ program / rubric 怎么落的>
- 测试集:<case 数 + 每个 case 一句起始输入>
- 来源:<每类文件 human / agent_drafted>
- 要你重点核:rubric 和红线是锚点(v0.4.1 §3)。
```

review.md 是只读呈现;人要改就改底下的实际文件(尤其 rubric.md)。

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

- `hdl new`(v1 手动)和 `hdl draft`(v2 起草)并存,人选哪条跑哪个命令。
- Designer 起草出的 program / versions / 测试集 / rubric / 模拟器,跟人手写的同格式 —— 所以 `run / score / compare` 一行不用改,直接复用。
- v2-minimal 是在 v1 管线**前面**接「起草 + 审」,管线本身不动。
- **V2 生成的所有实验文件,以 `program.md` 为共同锚点;`run / score / compare` 不关心实验是人手写还是 Designer 起草的,只读同一套 v1 文件格式。** 这是 v1 可信底座不被 v2 污染的关键(见 §0「三个文件的分工」)。

---

## 9. 不做的(v2.5 及以后)

sentinel cases、adversarial bad versions、calibration 校验闭环(拿 golden / 坏版本测 judge)、judge regression、per-file frontmatter 来源戳、`hdl approve` 审批闭环、run 前提醒 / 硬拦未批准产物、draft 失败即时回滚半成品、authority matrix 可编辑 + mode 选择器、agent-operated loop、自迭代、escalation 规则 —— 对应 v0.4.1 §9 的 v2.5 / v3 / v4。

---

## 10. 建议实现顺序

1. `HDL_DESIGNER_*` 配置 + `designer.py` 骨架(先打通一次模型调用)。
2. `hdl draft` 首阶段:建目录 + brief.md 模板。
3. brief.md parser。
4. Designer Call 1(→ program.md)+ 生成后跑 parser 校验。
5. Designer Call 2(→ versions / 测试集 / rubric / 模拟器)。
6. provenance:`hdl draft` 把来源集中写进 review.md 的「来源」行(per-file 头留 v2.5)。
7. review.md 生成。
8. `calibration/golden/` 目录约定 + golden case 格式(约定为主,代码极少)。
9. e2e:`hdl draft` 两阶段 + 接着 `run / score / compare` 跑通 —— Designer 那步先用一个桩 Designer(像 stub simulator)测,不烧真模型。

每步保持现有 40 测试绿。

---

## 关系

依据 `design-v0.4.1.md`(v2 架构),落地其 §9 的 v2 一档。v1(`design-v0.3.md` + 现有代码)不动。
