# Agent Harness Lab · 产品定义

> 本文是 Agent Harness Lab 的**顶层主线文档**。如果只读一份，读这份。
> 这是产品定义，不是实现：抽象与命名以本文为准，实现细节落到 `runtime-materialization.md`（spec）、`file-formats.md`（v1 当前已实现的文件）、`v2-minimal-spec.md`（v2 当前分支的实现切片）。
> 早期设计（`design-v0.3.md` / `design-v0.4.1.md`）保留作为「设计演进史」。HDL / Harness Design Loop 是历史代号，CLI / 包名已对齐到 Agent Harness Lab（见 §11）。
> 日期：2026-05-21。

---

## 0. 一句话

**Agent Harness Lab helps humans and coding agents design, test, and improve the runtime harnesses that shape agent behavior.**

中文：Agent Harness 实验室帮助人和 coding agent 设计、测试和改进塑造 agent 行为的运行时 harness。

更展开地说：

1. **Harness defines how an agent runs.** Harness 定义 agent 如何运行。
2. **Experiment measures how a harness affects agent behavior.** Experiment 测量 harness 如何影响 agent 行为。
3. **Loop uses experimental evidence to improve the harness.** Loop 用实验证据改进 harness。

---

## 1. 它不是什么

避免被误读为相邻类别的工具：

- **不是**泛泛的 agent 评测平台。它不假设 agent 是黑盒，而是把 harness 当作被设计、被改写的一等对象。
- **不是**内置 Designer LLM 的 meta-agent。起草和迭代由外层 coding agent（Claude Code / Cursor / Codex）做；Agent Harness Lab 是协议、验证器、运行器、证据库。
- **不是** prompt manager。Prompt 只是 harness 的一种构成；workflow、tool config、memory、guardrails 等其他构成同样落在 harness 这一层。
- **不是** benchmark runner。Benchmark 假设目标固定；Agent Harness Lab 假设目标本身随实验被修正。

它是：harness 设计工作台 + harness 实验系统 + harness 改进闭环 + 人与 coding agent 协作开发 harness 的证据基础设施。

---

## 2. 三层架构

```
┌──────────────────────────────────────────────┐
│  Loop Layer       用证据改进 harness          │
│  goal / brief / review / approval gates       │
├──────────────────────────────────────────────┤
│  Experiment Layer 测量 harness 效果           │
│  program / cases / rubric / simulator /       │
│  run / score / compare / calibration          │
├──────────────────────────────────────────────┤
│  Harness Layer    被设计和改进的对象          │
│  prompt / workflow / tools / memory /         │
│  guardrails / context packaging / ...         │
└──────────────────────────────────────────────┘
```

### 2.1 Harness Layer — 被设计的对象

Harness 是 agent 运行时依赖的**外部结构**。它回答：

> 这个 agent 在真实任务中，如何被组织、约束、增强和运行？

可能的构成（不要求每一项都齐）：

- system prompt / instruction
- workflow / task flow
- tool configuration
- memory / retrieval
- context packaging
- planning strategy
- output format
- guardrails
- state management
- handoff rules
- runtime constraints

**rubric、judge、simulator、eval 不属于 harness 本身。** 它们属于 Experiment Layer——用来测量 harness 的效果，而不是 harness 的一部分。

### 2.2 Experiment Layer — 测量装置

Experiment 是测试 harness variant 对 agent 行为影响的系统。它回答：

> 我怎么知道这个 harness 是否让 agent 表现变好了？

包含：experiment protocol（`program.md`）、cases、run mode（direct / replay / simulated）、user simulator、rubric、judge、canonical transcripts、raw runtime logs、score、compare、calibration。

### 2.3 Loop Layer — 改进闭环

Loop 把实验结果反馈进下一版 harness 设计。它回答：

> 结果出来后，谁决定 harness 怎么改？怎么进入下一轮？

包含：`goal.md`、`brief.md`、`review.md`、human approval、coding agent authoring、next harness proposal、keep / discard、auto rules、budget gates、provenance、decision history。

---

## 3. 核心对象

### 3.1 Harness Variant

一种具体的 harness 设计方案，定义 agent runtime 如何被配置、约束和编排。

**Harness Variant is not executable by itself.** 它必须绑定到 Agent Runtime 并经过 Materialization，才形成可运行对象。

### 3.2 Agent Runtime

实际生成输出的执行体。可能是：本地 CLI agent、开发机上的 coding agent、Python library、HTTP API、Docker service、内部 agent service、某个开源项目 checkout 后的 runtime。

### 3.3 Runnable Subject

**Runnable Subject = Harness Variant + Agent Runtime + Materialized Sandbox**

实验真正运行的对象——不是单独的 harness，也不是裸 agent。

### 3.4 Runtime Source / Harness Base

引入开源项目时，它通常不是已经可复现实验的 harness variant，而是：

- **Runtime Source**：可运行 agent 项目的来源（GitHub repo、local checkout、Docker image）；或
- **Harness Base**：可被扩展的 harness 基底（某个 agent framework / template / workflow scaffold）。

只有当 source 被固定到具体 commit / tag / image digest，并应用具体配置或 patch 后，才形成具体的 harness variant / runtime snapshot。

### 3.5 Harness Patch

把 harness design 写入 runtime 的实际工程改动：prompt 文件 patch、config 文件、workflow / tool 配置、memory / retrieval 配置、code patch、environment variables、start command。

### 3.6 Materialization

把 harness variant 应用到 agent runtime，生成隔离可运行实例的过程。中文：harness 实体化 / 落地。

### 3.7 Runtime Sandbox

一次实验中某个 harness variant 的隔离运行环境。不同 variant 在不同 sandbox 运行，避免：prompt / config 串线、memory 污染、cache 污染、log 混淆、依赖与环境差异不可追踪。

### 3.8 Runtime Snapshot

「这次实验实际跑了什么」的可复现记录。记录：runtime source、base commit / tag / image digest、harness patch hash、config hash、dependency / environment metadata、start command、sandbox path、connect / runtime adapter metadata、created_at、run_id。

Snapshot 不只是实验记录，也是下一轮开发的起点。

详细 spec 见 `runtime-materialization.md`（设计阶段，未实现）。

---

## 4. 三种产品模式

产品层只暴露三种模式，底层复杂度（matrix、authority、provenance）下沉。三种模式的详细心智、流程、当前状态见 `product-modes.md`。

| 模式 | 用户心智 | 当前状态 |
|---|---|---|
| **Manual** / 手动 | 我自己设计 harness 和实验，Lab 帮我校验、运行、评分、比较 | v1 已完成 |
| **Co-pilot** / 人机协作 | Coding agent 帮我起草 harness 方案和实验方案，关键节点我确认 | v2-minimal 分支 |
| **Auto** / 自动改进 | Coding agent 在规则、预算、审核门槛下自动迭代 harness；异常喊我 | 未来模式，依赖 materialization 成熟 |

---

## 5. Run Modes — 实验如何生成对话数据

Run mode 定义实验过程中「用户侧输入」如何产生。它属于 Experiment Layer。

| 模式 | 做什么 | 适合 | 限制 |
|---|---|---|---|
| **Direct Case Run** | 固定 case 起始输入，直接发给 runnable subject | 单轮评测、smoke test、简单对照 | 不支持多轮交互演化 |
| **Replay Run** | 用历史真实用户消息序列，把 user turns 固定喂给不同 variants | 历史日志回归、真实数据重跑 | 用户后续问题不会随不同 agent 回答变化 |
| **Simulated Conversation Run** | 从 opening input 起，agent 答完，User Simulator 据当前 transcript 生成下一句 | 多轮对话、澄清能力、情绪处理 | Simulator 引入噪声和成本 |

当前 v1 / v2-minimal 只实现 simulated 模式。Replay / direct 留到后续。

---

## 6. Evidence Chain — 证据链

一次实验形成的证据链：

```
1. Case Source                  人工 case / 历史日志 / dataset
2. Run Mode                     direct / replay / simulated
3. Runnable Subject             Harness Variant + Agent Runtime + Sandbox
4. Canonical Transcript         用户输入和 agent 输出的标准记录
5. Raw Runtime Logs             stdout / stderr / tool calls / debug events
6. Judge Score                  基于 transcript + rubric 的评分
7. Compare Report               版本差异证据
8. Human / Coding Agent         据证据提下一轮 harness 改进
```

要点：

- **Canonical transcript 是评分主证据**。Raw logs 用于 debug，不默认进入 judge。
- **Compare report 是证据，不是最终产品结论。** 最终解释权属于人。
- **Snapshot 跟着每条 run 走**，让证据可回溯到「这次实际跑的是哪一份 harness」。

---

## 7. 文件与目录定义

下表在新概念视角下重述每个文件的意义（不是改名映射——改名计划见 §11）。

| 文件 / 目录 | 所属层 | 含义 |
|---|---|---|
| `goal.md` | Loop | 长期 harness 改进目标 |
| `brief.md` | Loop | 单次 harness improvement brief（人写的实验意图） |
| `program.md` | Experiment | experiment protocol——定义本次实验如何测试 harness variants |
| `harnesses/`（原 `versions/`） | Harness | 一个 harness variant 一个文件 |
| `cases/`（原 `测试集/`） | Experiment | 一个 case 一个文件——触发行为差异 |
| `simulator.md`（原 `模拟器.md`） | Experiment | user simulator——模拟模式下扮用户的 agent |
| `rubric.md` | Experiment | 评分维度 + 权重 |
| `connect.md` | Harness / Runtime Boundary | runtime 通信配置；未来由 Runtime Adapter 扩展（见 `runtime-materialization.md`） |
| `review.md` | Loop | human checkpoint / review packet |
| `results/run-*.json` | Experiment | canonical transcripts + run metadata |
| `results/score-*.json` | Experiment | judge scoring result |
| `results/compare-*.md` | Experiment Output | evidence report，不是最终结论 |
| `calibration/golden/` | Experiment Governance | 校准 judge / rubric / method 的锚点（golden cases） |
| provenance | Loop / Evidence Governance | artifact / run 的来源、审批、快照记录 |

---

## 8. Runtime Materialization — 下一阶段核心主题

> **v0.3.0 (2026-05-23) M1 已实现 `local_path` + `git_repo`**。详细实现合同见
> `runtime-materialization-m1-spec.md`,文件格式见 `file-formats.md` §Runtime
> Materialization,总设计 spec 见 `runtime-materialization.md`。

v2-minimal 已经解决 authoring + review + run/score/compare。Runtime Materialization
是 v0.3.0 之后持续推进的核心底层能力:

> **Harness Runtime Materialization & Snapshotting**

不同 runtime source 需要不同 materialization 策略:

| Runtime Source | Materialization Strategy | Status |
|---|---|---|
| local path | copy directory / apply patch | ✅ v0.3.0 |
| git repo | git clone / checkout commit / apply patch | ✅ v0.3.0 (clone mode;worktree 留 M2+) |
| docker image | start isolated container / mount harness config | 留 M2 |
| remote API | logical sandbox via config / session / model version | 留 M2 |
| existing dev agent | dev-machine sandbox / workspace branch / session isolation | 留 M3 |

每次 materialize 落 snapshot.json,含 `source_dir_hash` (pre-patch raw source 指纹)
+ `patch_hash` (files+env+start_command) + `commit_sha` (git_repo) 等可复现指纹,
配合 `--cleanup-sandboxes` flag 控 sandbox 留删。

---

## 9. 术语表

| 英文 | 中文 | 定义 |
|---|---|---|
| Agent Harness Lab | Agent Harness 实验室 | 通过实验设计和改进 agent runtime harness 的工作流工具 |
| Harness | Harness / 运行时框架 | 定义 agent 如何运行的外部结构 |
| Harness Variant | Harness 变体 | 一种具体的 harness 设计方案 |
| Agent Runtime | Agent Runtime / agent 运行体 | 实际生成输出的 agent / model / service / CLI / API |
| Runtime Source | 运行时来源 | runtime 的来源：git repo、local path、docker image、API |
| Harness Base | Harness 基底 | 可被扩展的开源 harness / runtime template |
| Harness Patch | Harness 改动 | 把 harness 设计写入 runtime 的实际配置或代码改动 |
| Materialization | 实体化 / 落地 | 把 harness variant 应用到 runtime，生成可运行实例 |
| Sandbox | 隔离运行环境 | 某次 run 中某个 variant 的独立运行环境 |
| Runtime Snapshot | 运行时快照 | 记录实验实际运行版本的可复现信息 |
| Runnable Subject | 可运行对象 | Harness Variant + Agent Runtime + Materialized Sandbox |
| Experiment Protocol | 实验协议 | `program.md`，定义实验如何运行 |
| Run Mode | 运行模式 | direct / replay / simulated，定义用户侧输入如何产生 |
| Canonical Transcript | 标准对话记录 | judge 评分的主证据 |
| Raw Logs | 原始日志 | debug 证据，不默认进入评分 |
| Judge Agent | 评分 agent | 据 rubric 和 transcript 打分 |
| Compare Report | 对比报告 | 版本差异证据，不是最终结论 |

---

## 10. 跟旧文档的关系

| 旧文档 | 还有效吗 | 关系 |
|---|---|---|
| `design-v0.3.md` | 部分有效 | v1 架构（三层模型、四种接入、run / score / compare）仍是当前实现 |
| `design-v0.4.1.md` | 部分有效 | authority matrix（§3）、escalation（§5）、calibration（§6）、provenance schema（§7）、路线图（§9）仍是长期方向有效输入；§4 / §8 里的 "Designer Agent" 已被 external coding agent 取代（见该文件顶部 notice） |
| `v2-minimal-spec.md` | 概念 + 命名已同步 | 概念层（external coding agent is the Designer / Lab is protocol）以本文为准；命名已对齐到 Agent Harness Lab（`ahl` CLI、`AHL_*`、`agent_harness_lab` 包、`harnesses/` / `cases/` / `simulator.md`） |
| `agent-authoring-guide.md` | 概念 + 命名已同步 | 给外层 coding agent 读的起草指南；命名已对齐到 Agent Harness Lab |
| `file-formats.md` | 描述 v1/v2-minimal 实际行为 | 工具实际读写的文件格式；Phase 2 改名后这份文件随之更新 |
| `archive/` 下的 v0.1 / v0.2 / v0.4 / handoff | 历史 | 已被取代的早期草稿 |

读哪个：

- 想了解产品定位和概念架构 → 本文
- 想知道当前工具实际读写什么 → `file-formats.md`
- 想知道 v1 怎么实现的 → `design-v0.3.md`
- 想知道长期产品方向 → `design-v0.4.1.md`
- 想知道当前 v2 分支怎么实现 → `v2-minimal-spec.md`
- 给外层 coding agent 读 → `agent-authoring-guide.md`
- 想知道 materialization 怎么落地 → `runtime-materialization.md`（spec）

---

## 11. 命名过渡

旧名：**HDL / Harness Design Loop**——保留作为历史代号 / 旧分支名 / 旧 commit 信息。

新名：**Agent Harness Lab**——文档、CLI、Python 包、目录命名全部对齐到这一层。

具体改名（Phase 2/3 已完成）：

| 旧 | 新 |
|---|---|
| Python 包 `harness_design_loop` | `agent_harness_lab` |
| CLI 命令 `hdl` | `ahl` |
| 实验目录 `versions/` | `harnesses/` |
| 实验目录 `测试集/` | `cases/` |
| 实验文件 `模拟器.md` | `simulator.md` |
| 环境变量 `HDL_SIM_*` / `HDL_JUDGE_*` / `HDL_AGENT_TIMEOUT` | `AHL_SIM_*` / `AHL_JUDGE_*` / `AHL_AGENT_TIMEOUT` |
| CLI 子命令 `hdl versions` | `ahl harnesses` |

保留：`brief.md` / `review.md` / `program.md` / `goal.md` / `connect.md` / `rubric.md`——文件名不动，语义按 §7 重新定义。

---

## 12. 还在决策的问题

1. `connect.md` 是否最终被 Runtime Adapter 完全替代，还是作为 adapter 的一种特例保留？
2. Materialization 是显式命令 `ahl materialize`，还是集成进 `ahl run` 前置阶段？
3. Runtime sandbox 默认用 copy_dir、git worktree 还是 docker？
4. Runtime snapshot 是每次 run 都强制生成，还是只在正式实验中生成？
5. Replay / direct run mode 何时实装？
6. Auto Mode 的 escalation 规则 schema 是否已经稳定到可落代码？

这些问题的现状和取舍见 `runtime-materialization.md` 与 `design-v0.4.1.md`。

---

## 13. 最终一句话

> **Agent Harness Lab 不是为了评测裸 agent，而是为了通过实验持续设计和改进 agent runtime harness。**

更展开：

> 人或 coding agent 设计 harness variant；Agent Harness Lab 把它绑定到 agent runtime，在 direct / replay / simulated 模式下运行实验，保存 transcript、logs、snapshot，再用 score / compare 反馈推动下一版 harness 改进。
