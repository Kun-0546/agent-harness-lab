# Agent Harness Lab · 三种产品模式

> 本文细化 `product-definition.md` §4 的三种模式：**Manual / Co-pilot / Auto**——它们是用户面对 Lab 时的三种心智，背后是同一张 authority matrix（见 `design-v0.4.1.md` §3）的三档 preset。
> 与旧文档的关系：`design-v0.4.1.md` 列了 4 个 preset（Mode 1 Manual / Mode 2 Agent-Drafted / Mode 3 Agent-Operated / Mode 4 Self-Improving）。本文把它们收敛为三种**产品模式**——Co-pilot 对应 Mode 2，Auto 涵盖 Mode 3 与 Mode 4（Self-Improving 是 Auto 的进一步形态，不单列）。
> 日期：2026-05-21。

---

## 0. 为什么是三种

模式不是硬编码的四档；底层是一张 per-stage 的 authority matrix（loop 的每个阶段挂一个 authority 值，详见 `design-v0.4.1.md` §3）。**产品层**对外暴露三个常用 preset 就够：

- 从 100% 人主导（Manual），到协作起草（Co-pilot），到自动迭代（Auto）。
- 用户在三档之间选，不直接编辑 authority matrix。MVP 不开放完整矩阵编辑，但文件格式留好。
- 三种模式都共享同一套底层（Harness Layer / Experiment Layer 的对象），切模式只改 Loop Layer 的权力分配。

---

## 1. Manual Mode · 手动 harness 设计

### 用户心智

> 我自己设计 harness 和实验，Agent Harness Lab 帮我校验、运行、评分、比较。

### 流程

```
人：写 goal.md（一次性）+ connect.md
   │
人：ahl new <名字>     建实验目录 + 空模板（program / rubric / simulator）
   │
人：手写 program.md / rubric.md / simulator.md
人：手写 harnesses/V1.md、V2.md（一个 variant 一份）
人：手写 cases/D-01.md 等
   │
人：ahl run / score / compare
   │
人：读 compare 报告，决定下一步
```

### 谁拥有什么

| 阶段 | 谁 |
|---|---|
| goal / brief（这里没有 brief） | 人 |
| program / harnesses / cases / rubric / simulator | 人 |
| run / score | Lab（机械执行） |
| compare / 解释 | 人 |
| keep / discard | 人 |

整张表除 run / score 外全 `human_owned`。

### 当前状态

**v1，已完成。** 完整管线 `ahl init → ahl new → ahl run → ahl score → ahl compare` 端到端跑通，preflight 拒绝坏输入，端到端 e2e 测试覆盖。

### 适合谁

- 你已经知道自己想试什么 harness 改动，不需要别人替你起草。
- 实验数量少、单次实验设计成本能 amortize 在你身上。
- 你想对每个文件保持完全控制。

---

## 2. Co-pilot Mode · 人机协作 harness 设计

### 用户心智

> Coding agent 帮我起草 harness 方案和实验方案，但关键节点我确认。

### 流程

```
人：写 goal.md（一次性）+ connect.md
   │
人或 agent：ahl draft <名字>   为外层 coding agent 开 authoring workspace
                              建实验目录 + brief.md 模板 + 空 harnesses/ + 空 cases/
   │
人：填 brief.md（想优化什么 / 验证什么改动 / 最在意什么 / 不能牺牲什么 / 怎么比）
   │
外层 coding agent：读 goal.md + brief.md，起草
                   program.md / harnesses/V*.md / cases/D*.md / rubric.md / simulator.md
                   （agent 读 agent-authoring-guide.md + file-formats.md；Lab 不调模型）
   │
人或 agent：ahl review <名字>  宽松校验，出 review.md
                              缺什么标「未起草」，不抛错；可多次跑
   │
人：读 review.md，改 rubric / 红线等锚点，确认
   │
人或 agent：ahl run / score / compare   跟 Manual 完全一样
```

### 谁拥有什么

参考 `design-v0.4.1.md` §4 的 Mode 2 preset：

| 阶段 | Authority |
|---|---|
| goal | `human_owned` |
| brief | `human_owned` |
| program | `agent_drafted_human_approved` |
| harnesses | `agent_drafted_human_approved` |
| cases | `agent_drafted_human_sampled` |
| rubric | `agent_drafted_human_approved` |
| simulator | `agent_drafted_human_approved` |
| run | `agent_operated`（机械执行） |
| score | `agent_operated`（机械执行） |
| compare | `agent_drafted_human_interpreted` |
| keep / discard | `human_owned` |

**核心原则**：external coding agent is the Designer. Lab 是 protocol, validator, reviewer, runner. Lab 不调模型起草——那是外层 coding agent 的活。

### 当前状态

**v2-minimal**（Co-pilot 模式，已合入 main），已实现：
- `ahl draft` scaffold-only：建实验目录 + brief.md 模板，不调模型。
- `ahl review`：宽松出 review.md，不抛错。
- 集中式 provenance：写在 review.md 的「来源」段，不进各文件 frontmatter（per-file frontmatter 留到 v2.5）。

**没做**（留 v2.5+）：
- per-file frontmatter 来源戳、`approval_state` 字段
- `ahl approve` 审批闭环、`run` 跑前对未批准产物的硬拦
- sentinel cases / adversarial bad versions（calibration 校验闭环）
- authority matrix 可编辑、mode 选择器

实现 spec 见 `v2-minimal-spec.md`，agent 起草指南见 `agent-authoring-guide.md`。

### 适合谁

- 你有目标但每次重新起草整套实验文件成本高。
- 你信任外层 coding agent 的起草质量，但希望在 rubric / 红线这类锚点上有最终决定权。
- 你愿意花时间把 brief.md 写好。

---

## 3. Auto Mode · 自动 harness 改进

### 用户心智

> Coding agent 在规则、预算和审核门槛下自动迭代 harness；异常时喊我。

### 流程

```
人：写 goal.md + 红线（goal.md 的 ## 红线 段）+ escalation 规则 + budget
   │
人：定第一份 brief.md（或允许 coding agent 提议）
   │
coding agent loop：
   ├─ 提 harness variant
   ├─ Lab materialize / sandbox / run / score / compare
   ├─ 据 escalation 规则自动 keep / discard / iterate
   ├─ 撞红线 / 资源闸 / 异常 → 停下喊人
   └─ 下一轮
   │
人：被喊到时介入；否则只看周期性报告
```

### 谁拥有什么

参考 `design-v0.4.1.md` §4 的 Mode 3 / Mode 4 preset：

| 阶段 | Mode 3 Authority | Mode 4 Authority（Self-Improving 进一步） |
|---|---|---|
| goal | `human_owned` | `human_owned` |
| brief | `human_owned` | `human_owned` |
| program | `agent_drafted_human_approved`（首次）/ `agent_operated`（后续） | `agent_operated` |
| harnesses | `agent_operated` | `agent_operated` |
| cases | `agent_operated`（含探索新 case） | `agent_operated` |
| rubric | `agent_drafted_human_approved` | `agent_drafted_human_approved`（仍要人批） |
| simulator | `agent_operated` | `agent_operated` |
| run / score | `agent_operated` | `agent_operated` |
| compare | `agent_drafted_human_interpreted`（周期性） | `agent_drafted_human_interpreted` |
| keep / discard | `agent_operated` + 喊人规则兜底 | `agent_operated` + 喊人规则兜底 |
| **实验方法本身** | 不动 | `agent_operated`（Self-Improving） |

**红线和 rubric 校准权永远在人手上**——这是 `design-v0.4.1.md` §2 的四个锚点，Auto Mode 不放宽。

### Escalation 规则（Auto 的安全闸）

Auto Mode 必须配 `design-v0.4.1.md` §5 的可计算 escalation 规则。简略：

```yaml
escalation:
  score_spike:           # 分数异常跳升
    threshold: 1.0
  no_discrimination:     # 全高分但分不开
    min_mean_score: 8.0
    max_delta: 0.2
  critical_regression:   # 红线维度退化
    dimensions: [...]    # 来自 goal.md 的 ## 红线
    threshold: -0.5
  judge_disagreement:    # 多 judge 分歧过大
    min_judges: 3
    max_std: 0.8
  budget:                # 资源闸
    max_rounds: 5
    max_cost_usd: 20
```

### 当前状态

**未来模式，未实装。**

依赖以下底层成熟：
- **Runtime Materialization & Snapshotting**——见 `runtime-materialization.md`。Auto Mode 自动跑多轮，每轮必须能可复现地起新 harness variant 的 sandbox。
- **Calibration & Harness Sanity Check**——`design-v0.4.1.md` §6。判断「评测系统本身可不可信」的闭环，Auto Mode 必须站在它之上。
- **Escalation 规则的可计算化**——上面那张表的 schema 落到代码。
- **Approval gates**——`ahl approve` 闭环，未批产物 `run` 跑前硬拦。

按 `design-v0.4.1.md` §9 的路线：v2.5 做 calibration & harness sanity，v3 做 Auto Mode（Mode 3 Agent-Operated），v4 做 Self-Improving（Mode 4）。

### 适合谁（未来）

- 你已经把 goal / 红线 / rubric / escalation 规则写到稳定。
- 你愿意为「每跑一轮就要跟一次」这件事花预算让 coding agent 自动跑。
- 你接受 Auto Mode 的产出本质是「证据 + 提案」，最终接不接还是你拍板。

---

## 4. 三种模式的选择指南

| 场景 | 推荐 |
|---|---|
| 首次接触 Agent Harness Lab，想理解工具 | Manual |
| 你已经知道想试什么改动，单次实验 | Manual |
| 你每天都要跑实验，起草成本是瓶颈 | Co-pilot |
| 实验规模大，你只想守住 rubric / 红线 | Co-pilot |
| 你希望 coding agent 跑通宵，撞红线再叫你 | Auto（未来） |
| 你希望 coding agent 优化实验方法本身 | Auto 的高级形态（未来） |

**实战建议**：先用 Manual 走通一次完整 loop，理解 `program.md` / `harnesses/` / `cases/` / `rubric.md` 这些产物的含义；再切 Co-pilot 让外层 coding agent 起草。不要跳过 Manual 直接上 Co-pilot——否则你看不懂 review.md 在标什么。

---

## 5. 模式切换

三种模式不是排斥关系，可以在同一个工作目录、同一个 goal.md 下混用：

- 一个工作目录可以同时有 Manual 实验（`ahl new` 起的）和 Co-pilot 实验（`ahl draft` 起的）。
- Lab 不在工作目录层级强制选择模式；每个实验自己决定走哪条路径。
- `ahl run / score / compare` 不区分实验是哪条路径起草的——所有路径最终汇合到同一份 `program.md`。

---

## 6. 跟旧文档的对照

| 旧 | 新 |
|---|---|
| `design-v0.4.1.md` §4 的 Mode 1 Manual | Manual |
| `design-v0.4.1.md` §4 的 Mode 2 Agent-Drafted | Co-pilot |
| `design-v0.4.1.md` §4 的 Mode 3 Agent-Operated | Auto |
| `design-v0.4.1.md` §4 的 Mode 4 Self-Improving | Auto 的进一步形态（不单列） |

旧的"四档"在产品层简化为三档；底层 authority matrix 仍是同一张表。
