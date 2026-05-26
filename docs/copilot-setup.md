# Co-pilot Setup Guide

> 这份文档讲 **Co-pilot setup mode** 该怎么用 —— 既给**人类操作者**
> (你想跑实验的那位),也给**外层 coding agent**(Claude Code /
> Cursor / Codex 等被你叫来协作的工具)。**两边各读一节就够**。
>
> 想看 9 步完整产品流程:[`docs/product-walkthrough.md`](product-walkthrough.md)
> 想看具体文件格式:[`docs/file-formats.md`](file-formats.md)
> 想解读 compare 报告的 evidence:[`docs/evidence-guide.md`](evidence-guide.md)
> 想看 setup-state 长什么样:
> [`examples/copilot-setup-example/`](../examples/copilot-setup-example/)

## 1. What this guide covers

Co-pilot mode 是 `ahl new` 的**默认 setup mode**,意思是:用户写一份
工作单 `brief.md` + 整理一份参考目录 `materials/`,外层 coding agent
据这两个文件起草 program / rubric / cases / harnesses。AHL 本身**不
调 LLM**,只读写文件。

本文档:
- §2-§3:背景 —— 三种 mode 的边界、co-pilot 8 步 loop
- §4:**人类操作者**读这节 —— brief.md 怎么填、什么时候交给 coding agent
- §5:**外层 coding agent** 读这节 —— 在 co-pilot 实验里能改什么、不能改
  什么、什么时候跑哪个 `ahl` 命令
- §6-§9:Done criteria / 常见失败 / Manual-Co-pilot-Auto 边界 / Reference

## 2. When to use co-pilot mode

三种 setup mode 的选法(详见 [`product-walkthrough.md`](product-walkthrough.md)
Step 2):

| 场景 | 推荐 mode | 状态 |
|---|---|---|
| 已经知道想试什么 harness 改动,实验数少 | manual | ✅ |
| 实验多,起草成本是瓶颈,想让 coding agent 协助 | **copilot (默认)** | ✅ |
| 想让 coding agent 跑通宵自动迭代 | auto | ❌ 未实现 |

Co-pilot mode 的本质:**目录结构 + 模板文件 + 给 coding agent 的指南
**,**不是 AHL 自动调 LLM**。你在外层 coding agent (Claude Code / Cursor /
Codex) 里读 brief.md 然后让它 emit 文件,AHL 只读这些文件。

## 3. The co-pilot loop (8 steps)

```
1. ahl init                       (workspace 级一次性)
   写 goal.md
2. ahl new <name>                 (默认 --mode copilot)
   建 experiments/01-<name>/brief.md + materials/README.md
                              + cases/ + harnesses/
3. 用户读 brief.md  (12 sections,见 §4)
   能自填的填,不能自填的让 coding agent 助填
4. 用户在外层 coding agent (Claude Code / Cursor / Codex) 里
   说 "据 goal.md + brief.md + materials/ 起草" 
5. Coding agent 读 → 起草 program/rubric/simulator/cases/harnesses
   (规则见 §5)
6. ahl review <id>                (结构校验,no LLM)
7. ahl probe <id>                 (可选,runtime readiness)
   ahl run <id>                   (materialize + run cases)
   ahl score <id>
   ahl compare <id>
8. 据 compare 报告决策:keep / discard / next
```

**关键点**:`ahl run/score/compare` **不知道**你用的是 manual 还是
copilot —— setup mode 只影响 step 2 建什么结构。

## 4. For the human operator — writing brief.md

### 4.1 12 sections cheatsheet

`brief.md` 模板 12 节,按这个顺序填:

1. **想优化什么** — 这轮 agent 哪个行为变好,goal.md §2 的哪个 subset
2. **目标行为** — 输入 X 时期望 Y(给 2-3 个 case 类型)
3. **当前问题** — V1 baseline 现在做错什么,failure mode 哪一类
4. **Runtime 信息** — local_path / git_repo / legacy_connect,cloud or local
5. **Harness 假设** — 改哪一层(prompt / workflow / tool / memory / ...)
6. **Cases 要覆盖什么** — 2-4 类 case + 为什么能拉出 V1/V2 差异
7. **Rubric 应该如何判断** — 2-4 维度 + 权重提案 + 高/低分长什么样
8. **Evidence / probe expectations** — 目标 level + 哪些 materials/*-evidence.md
9. **Files the coding agent may create** — 白名单(默认即 program/rubric/...)
10. **Files the coding agent should not change** — 黑名单(goal.md /
    results/ / sandbox/ / locked.md 列表 / .git)
11. **Acceptance commands** — review → (probe) → run → score → compare
12. **Done criteria** — §1-§8 全填 + §11 全 exit 0 + evidence level 对齐

### 4.2 What "good" looks like

- §1-§3 用 2-3 个真实 case 类型撑起来(光写"更好"不够)
- §4 明确 evidence 路径(`runtime-sources.md` 还是 `connect.md` + evidence)
- §5 一次实验只改一层(不要 prompt + tool + memory 同改)
- §6 case 必须有 V1/V2 区分能力(不挑刺 case = 无信号实验)
- §7 维度 ≤4(>5 维 judge 一致性下降)
- §8 跟 [`evidence-guide.md`](evidence-guide.md) 的目标对齐,不重复内容

### 4.3 When to stop polishing and hand off

不必一次填全。够 coding agent 起草的最低门槛:**§1 + §2 + §5 + §6**
有内容。其余可以让 coding agent 在 `> [proposal]` 段落里建议,你
review 后接受。

**不要**在 brief.md 里写敏感配置(API keys / 私密 endpoint),那些放
进 `materials/<file>.md` + 加到 `materials/locked.md`。

### 4.4 Coding agent 改 brief.md 的边界

Coding agent 可以**添加**带标签的段落,**不可**静默改写原始意图:

```markdown
## 1. 想优化什么

让 agent 在收到模糊目标时先澄清,再动手。

> [proposal] 据 goal.md §2,建议把"模糊目标"具体化为 "用户给的目标
> 缺关键参数 (如时间窗口 / 范围 / 受众)" —— 否则 §2 cases 不好挑。

> [open question] 你想把澄清能力跟方案质量一起优化,还是分两轮做?
```

如有疑问,**留 `> [open question]` 不要猜**。重大改动在 handoff 里
报告。

## 5. For the coding agent — operational rules

> 这一节是给外层 coding agent (Claude Code / Cursor / Codex 等) 读的。
> 用户把这个文档喂给你,或者直接说"按 docs/copilot-setup.md §5 工作"。

### 5.1 读什么

进入实验目录后,**按这个顺序读**:

1. `<workspace>/goal.md` — workspace 级长期目标(只读)
2. `<workspace>/experiments/<id>/brief.md` — 本轮工作单(规则见 §5.2)
3. `<workspace>/experiments/<id>/materials/README.md` + 全部
   `materials/*.md`
4. (如果存在)`<workspace>/runtime-sources.md` / `<workspace>/connect.md`
5. (如果存在)上一轮的 `experiments/<prev-id>/results/compare-*.md`
   —— 作为 baseline 行为参考

不要读 `results/**` / `sandbox/**` / `probe-results/**` 之外的生成
产物。

### 5.2 brief.md 的修改边界

**可以**:添加带标签的段落:
- `> [proposal]` — 你的建议(用户 review 后接受)
- `> [interpretation]` — 你对用户原文的理解(用户确认)
- `> [open question]` — 你不确定、不应该猜的地方

**不可以**:静默改写用户的原始意图。

不知道某节怎么填?**留 `> [open question]` 不要猜**。重大改动在
handoff message 里列出来。

### 5.3 可建 / 可改的文件白名单

- `experiments/<id>/program.md`
- `experiments/<id>/rubric.md`
- `experiments/<id>/simulator.md`
- `experiments/<id>/cases/*.md`(一个 case 一文件,命名 `D-NN.md`)
- `experiments/<id>/harnesses/*.md`(`V1.md` baseline / `V2.md` 改动版)
- `experiments/<id>/materials/<topic>.md`(从 URL / 粘贴内容整理出来的
  新参考材料)
- `<workspace>/runtime-sources.md`(仅当不存在时;存在时不动)

### 5.4 不可改的文件黑名单

- `<workspace>/goal.md`(workspace 级,人 own)
- `<workspace>/experiments/<id>/brief.md` 的**原始内容**(可添加
  标签段落,见 §5.2)
- `<workspace>/experiments/<id>/results/**`(AHL 生成产物)
- `<workspace>/experiments/<id>/sandbox/**`(AHL 生成产物)
- `<workspace>/experiments/<id>/probe-results/**`(AHL 生成产物)
- 任何在 `materials/locked.md` 里列出的文件
- `.git/**`

### 5.5 什么时候跑哪个 `ahl` 命令

- 起草完文件 → `ahl review <id>`(结构校验,no LLM,**必须 PASS**)
- brief.md §4 涉及 materialized runtime → `ahl probe <id>`(可选,
  read-only)
- `ahl review` PASS 后 → `ahl run <id>` → `ahl score <id>` →
  `ahl compare <id>`

每跑一个命令,在 handoff message 里报告 exit code + 关键输出摘要。

### 5.6 最小修改原则

- 一个逻辑步骤一个文件改动(不要 bulk multi-file rewrite)
- 优先 minimal diff(不要重写整份文件)
- 不要"顺手"做范围外的整理(目录重排 / 风格统一)
- handoff 里只列**真的改了**的文件,不列"考虑过但没改"的

### 5.7 Handoff message 应该包含什么

用户向你要进度时,写一份 markdown handoff,3 个 section:

```markdown
## Files to create / modify
- experiments/01-<name>/program.md  (new)
- experiments/01-<name>/rubric.md   (new, 3 维度)
- ...

## Acceptance commands
- `ahl review 01` → exit 0
- `ahl run 01`    → 2 variants × 3 cases,exit 0

## Risks / open questions
- brief.md §8 evidence level 目标 strong,但 §4 是 legacy_connect,
  当前路径只能到 medium —— 建议补 materials/runtime-evidence.md
```

参考 [`examples/copilot-setup-example/expected-coding-agent-plan.md`](
../examples/copilot-setup-example/expected-coding-agent-plan.md)。

## 6. What "done" means

一次 co-pilot setup 算"做完"的 verifiable signals(对应 brief.md §12):

- brief.md §1-§8 全填(`> [proposal]` 段落用户已 ack)
- brief.md §9 列出的文件全在
- `materials/locked.md` 存在(可为空)
- `ahl review / probe (可选) / run / score / compare` 全 exit 0
- compare 报告 `## Evidence` section 的 evidence level 跟 brief.md §8
  目标对齐(不达标 → 补 `materials/*-evidence.md` → 再跑 `ahl compare`)
- 一个完整跑通的实验应能用 `ahl compare` 解释 baseline harness (V1)
  跟 candidate harness (V2+) 的差异 —— 这是 co-pilot setup 的最终目
  的。compare 报告里读不出差异,说明 cases / rubric / variants 中至
  少一项需要回头改

setup-state 示例见
[`examples/copilot-setup-example/`](../examples/copilot-setup-example/);
runnable end-state 示例见
[`examples/sample-workspace/`](../examples/sample-workspace/)
(v0.7 canonical)。

## 7. Common failure modes

5 个 coding agent 应该避开的反模式:

1. **静默改 brief.md** — 用户写的"想优化澄清能力",改成"想优化方案
   质量"。**正确做法**:加 `> [proposal]` 段提建议,用户 review 后接受。
2. **rubric 维度 >5** — judge 一致性下降。Cap 在 4 维。
3. **一次实验改多层 harness** — V1 跟 V2 同时改 prompt + tool config,
   结果不可归因。**正确做法**:一次 variant 只改一层。
4. **改 `materials/locked.md` 列的文件** — 产品约定违规,handoff
   被 reject。
5. **跳过 `ahl review` 直接跑 `ahl run`** — review 抓的是结构问题,
   跑完才发现 cases 缺 frontmatter 浪费时间。**正确做法**:review 先,
   run 后。

## 8. Manual / Co-pilot / Auto boundary

三种 mode 共享同一套 `run / score / compare / probe / review` 行为
—— AHL runtime 不识别 mode、不读 `.mode` 文件。Setup mode 只影响
`ahl new` 建什么结构:

| `ahl new --mode` | creates                                              | 谁起草             |
|---|---|---|
| `manual`         | program/rubric/simulator + cases/ + harnesses/       | 你手写             |
| `copilot` (默认) | brief.md + materials/README.md + cases/ + harnesses/ | 外层 coding agent |
| `auto`           | (nothing — exit 2 with not-implemented message)      | future            |

Auto mode 详细背景见 v0.2.0 历史档
[`product-modes.md`](product-modes.md) §3
(banner-tagged HISTORICAL,§3 authority matrix 仍是长期 architecture
background)。

## 9. Reference

- 9 步产品流程: [`product-walkthrough.md`](product-walkthrough.md)
- 具体文件格式: [`file-formats.md`](file-formats.md)
- evidence 解读: [`evidence-guide.md`](evidence-guide.md)
- evidence 自填模板: [`../examples/evidence-examples/`](../examples/evidence-examples/)
- runnable end-state 示例: [`../examples/sample-workspace/`](../examples/sample-workspace/)
- setup-state 示例: [`../examples/copilot-setup-example/`](../examples/copilot-setup-example/)
- 历史背景(三种 mode): [`product-modes.md`](product-modes.md) (HISTORICAL)
- 历史背景(v2-minimal): [`v2-minimal-spec.md`](v2-minimal-spec.md) (HISTORICAL)
- 历史背景(v0.2.0 authoring): [`agent-authoring-guide.md`](agent-authoring-guide.md)
  (HISTORICAL — superseded by this guide for the modern co-pilot path)
