# Agent Harness Lab · Roadmap

> 这份 roadmap 描述 Agent Harness Lab 从 v0.3.1 开源 baseline 到 v1.0 stable
> 的产品演进路径。每档独立可发布,不强求一次性把后续 milestones 全做完。
>
> 状态约定:
> - **shipped** — 已 release,代码 + docs 在 main
> - **planned** — 设计明确,已知何时启动,未必有 GitHub issue
> - **exploring** — 方向明确,具体 spec / 优先级待定
> - **future** — 长期方向,依赖前序 milestones 成熟
>
> 日期:2026-05-25。每次 minor release 时回顾更新。

---

## v0.3.1 — Open-Source Baseline [shipped]

**目标**:把 v0.3.0 Runtime Materialization M1 + 一系列 product surface
cleanup 收口到可公开发布的 baseline。

**主要交付**:

- LICENSE (MIT) + CHANGELOG.md (Keep a Changelog) + CONTRIBUTING.md +
  SECURITY.md
- 产品入口从 `connect.md` 心智改为 goal-first workflow
  (`ahl init` → `ahl walkthrough` → `ahl new --mode copilot/manual`)。
  `--mode copilot` / `--mode manual` 是当前可用的 setup mode 入口;
  `--mode auto` 是 future reserved 入口,当前会明确报 not-implemented 并
  exits 2 (Auto setup mode + autonomous iteration loop 仍在 v0.9,见下)
- 9 步产品流程文档 (`docs/product-walkthrough.md`)
- Runtime boundary + evidence level 在 Step 3 明确化
- Historical docs banner (`product-modes.md` / `v2-minimal-spec.md` /
  `agent-authoring-guide.md` / `design-v0.3.md`)
- 252 tests 全过(含 `-W error::ResourceWarning` strict 模式)

**关键依赖**:无。v0.3.0 Runtime Materialization M1 已实现。

---

## v0.4 — Evidence-Aware Result [shipped]

**目标**:让 `score` / `compare` 输出携带 evidence level 元数据,使决策时能
明确"这一轮的证据强度是 strong / medium / weak"。

**主要交付**:

- `results/score-*.json` 加 `evidence_level` 字段,据 Step 3 runtime boundary
  + snapshot 完整度推导
- `results/compare-*.md` 在版本对比表头标 evidence level
- `materials/*-evidence.md` 解析器,把 Co-pilot 路径 evidence 整合进
  snapshot 引用链
- evidence level 与 keep/discard 决策的 advisory 规则

**关键依赖**:v0.3.0 snapshot persistence (已 ship)。

---

## v0.5 — Harness Package MVP [planned]

**目标**:让 harness variant 不只是实验目录里的文件,而是一个可安装、可 hash、
可 snapshot 的 **runtime harness component**。Harness package 只装 harness
(prompt / config / tool / memory / workflow / start_command 等),**不**打包
cases / rubric / simulator —— 那些属于 experiment 不属于 harness。

**主要交付**:

- harness package manifest:
  - payload (实际要装进 runtime 的文件 / 配置 / env / start_command)
  - install target (装到 runtime 的哪些路径)
  - runtime compatibility (兼容哪些 runtime source 类型 / 哪些 base image)
- payload hash (manifest 声明的 payload 内容指纹)
- installed artifact hash (apply 到 sandbox 后的实际指纹)
- local install flow:apply harness payload into a materialized sandbox or
  local runtime workspace
- run snapshot 字段扩展:harness package id + payload hash +
  installed artifact hash
- 至少一个 local runtime example 演示 harness package 用法

具体 CLI / API 形式待 v0.5 spec 决定。

**关键依赖**:v0.3.0 snapshot fingerprint。

---

## v0.6 — Runtime Probe / Evidence Import [planned]

**目标**:让 AHL 主动从 runtime 抓取 evidence,而不是依赖人手动写
`materials/*-evidence.md`。

**主要交付**:

- local workspace probe:读 active config / plugin list / installed harness
  state
- command probe:user 提供一条 command,AHL 解析它返回的 active runtime
  summary
- cloud evidence import:deployment id / plugin list / console export /
  debug output
- probe 结果进入 evidence chain,可上调本轮实验的 evidence level
- probe 时间戳 + probe adapter version 写入 snapshot 字段

具体 CLI / API 形式待 v0.6 spec 决定。

**关键依赖**:v0.5 harness package format (用于声明 probe 期望)。

---

## v0.7 — Co-pilot Setup Productization [exploring]

**目标**:把当前 Co-pilot 模式(外层 coding agent + `brief.md` + `materials/`)
的 ergonomics 打磨成"真正能让新用户跑通"的入口。

**主要交付**:

- `materials/README.md` 模板分场景(新实验 / 迭代 / 调试)
- `brief.md` 校验器,在 review 阶段提示常见空段
- coding agent 入口文档(`docs/coding-agent-guide.md`),取代历史
  `agent-authoring-guide.md`

**关键依赖**:v0.4 evidence-aware result(Co-pilot 路径主要消费者)。

---

## v0.8 — Iteration Loop [exploring]

**目标**:把 keep/discard/next 决策从"靠人判断"变成"有命令辅助",但仍保留
人最终拍板。

**主要交付**:

- `ahl iterate <experiment>` 命令,基于 compare report 推荐下一轮 variant 方向
- iteration history 在 `goal.md` / `brief.md` 留痕
- 跨实验的 baseline 演进追踪

**关键依赖**:v0.4 + v0.7。

---

## v0.9 — Auto Mode MVP [future]

**目标**:落地 `design-v0.4.1.md` 设计的 Auto mode 第一档 — coding agent 在
budget + approval gate 约束下自主迭代 harness。

**主要交付**:

- `ahl new --mode auto` 不再 not-implemented
- approval gate schema (budget / max iterations / red line trigger)
- calibration 子系统 MVP (judge / rubric 校准锚点)
- escalation 规则:何时停 + 喊人

**关键依赖**:v0.5 + v0.6 + v0.8 — Auto mode 需要 package / probe / iteration
loop 都成熟。

---

## v1.0 — Stable Product [future]

**目标**:API / file format / CLI 命令稳定承诺。breaking change 走 deprecation
cycle。

**主要交付**:

- 全 CLI 命令 + 全 file format 标稳定
- API 版本承诺策略发布
- 至少 1 个 case study 公开
- Auto mode 至少 1 个真实 dogfood loop 跑过

**关键依赖**:v0.3 - v0.9 全部 shipped 且稳定使用过一段时间。

---

## 不在 roadmap 的方向

明确**不做**的方向(按 `docs/runtime-materialization.md` §7):

- patch DSL / templating
- 跨 source 复用 harness("把这个 prompt patch 同时应用到 git 和 docker source")
- sandbox warm pool / 并行执行优化
- distributed sandbox (多机调度)
- snapshot diff / 可视化工具
- Claude Code / Cursor 这类外层 coding agent 的 dogfood adapter 稳定版
  (`dev_agent` source 永远是实验性,证据等级降一档)

---

## 如何贡献

每个 milestone 的具体 issue / PR 入口见 GitHub Issues 的对应 milestone label。
贡献流程见 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。
