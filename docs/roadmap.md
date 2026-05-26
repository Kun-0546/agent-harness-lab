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
> 日期:2026-05-26。每次 minor release 时回顾更新。

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

## v0.5 — Harness Package MVP [shipped]

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

## v0.6 — Runtime Probe / Evidence Import [shipped]

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

## v0.7 — Complete Product Flow MVP [shipped]

**目标**:把已经实装的 v0.3.0 runtime materialization、v0.4 evidence、v0.5
harness package、v0.6 runtime probe 收敛到一条"完整可跑的产品流",让一个
刚 clone 的新用户能在 <30 分钟内、零 API key、零云端、零外部依赖,跑完一次
完整的 probe → run → score → compare。**内部产品完成**,**不是** public
launch / PyPI / 公开发布 / visibility flip。

> 原 v0.7 计划方向("Co-pilot Setup Productization")在 2026-05-26 调整为
> "Complete Product Flow MVP" — 见 `docs/product-flow-completion.md`。
> Co-pilot ergonomics 打磨延后到 v0.8+ exploring。

**主要交付**:

- `examples/sample-workspace/` — 端到端可跑的 sample,纯本地 + 离线 +
  零 API key:tiny-runtime + `concise-prompt@0.1.0` harness package +
  1 实验(V1 baseline vs V2 packaged harness)× 2 cases
- 完整 product flow validation:`ahl probe → run → score → compare`
  落 probe-results / run records / snapshots / score evidence / compare
  Evidence section
- snapshot `harness_package` 块完整 fingerprint(manifest_hash +
  payload_hash + effective_harness_hash)在 sample 中可见
- README + README_CN 围绕 9 个概念问题重写(AHL / problem / runtime /
  harness / harness package / probe / evidence / simplest workflow /
  not-yet-implemented),EN/CN 1:1
- docs/README.md 加 "首次接触推荐顺序" 路径;product-walkthrough.md +
  4 份 MVP spec 互相 cross-link
- 3 个 sample workspace E2E acceptance tests(465 总数)+ 跨 run 评分确定性
  + 仓内 sample 不含生成产物的保证
- v0.7 spec(`docs/product-flow-completion.md`)18 节,作为本档实施合同

**关键依赖**:v0.3.0 + v0.4 + v0.5 + v0.6(全部已 shipped)。

**显式不做**:不加 CLI 命令、不加 src 模块、不变 snapshot / evidence /
scoring / package / probe 合同、不发 PyPI、不公开仓、不发 announcement。

---

---

## v0.8 — Product Reliability / Co-pilot Productization [exploring]

**目标**:在 v0.7 完整产品流的基础上,补 product reliability 与原计划 v0.7
未落地的 Co-pilot 入口打磨。具体方向待 v0.8 spec 决定。

**候选方向**(待选,见 `temp/v0.8.0-planning.md`):

- `ahl package inspect / validate` —— 让 harness package 离 install
  之前能 read-only 检查 manifest / payload 完整度
- probe ↔ snapshot 更紧的绑定(snapshot 引用最近一次成功 probe id)
- evidence import 改进(`materials/*-evidence.md` 解析 + write-evidence
  覆盖更多 source 类型)
- product acceptance hardening(更多边界 case 的 E2E 覆盖、CI workflow
  可选项)
- 原 v0.7 计划的 Co-pilot ergonomics(`materials/README.md` 模板分场景、
  `brief.md` 校验、coding agent 入口文档)
- `ahl iterate <experiment>`(可推迟到 v0.9)

**关键依赖**:v0.7 Complete Product Flow MVP(已 shipped)。

**显式不做**:public launch、PyPI、visibility flip — 公开发布作为 future
option,不是 v0.8 默认轨。

---

## v0.9 — Auto Mode MVP + 候选并入项 [exploring]

**主线目标**:落地 `design-v0.4.1.md` 设计的 Auto mode 第一档 — coding agent
在 budget + approval gate 约束下自主迭代 harness。

**主线候选交付**:

- `ahl new --mode auto` 不再 not-implemented
- approval gate schema (budget / max iterations / red line trigger)
- calibration 子系统 MVP (judge / rubric 校准锚点)
- escalation 规则:何时停 + 喊人

**候选并入项**(deferred from v0.8 spec §15 lock — **不保证 v0.9 落地**,
具体取舍待 v0.9 spec):

- `ahl package inspect` / `ahl package validate`(read-only package
  inspection + standalone preflight,v0.8 因 "no new CLI" redline 推迟)
- 更紧的 probe ↔ snapshot 绑定(snapshot 引用最近一次成功 probe id,
  v0.8 因 "no snapshot schema change" redline 推迟)

**关键依赖**:v0.5 + v0.6 + v0.8 — Auto mode 需要 package / probe / iteration
loop 都成熟;并入项需要 v0.8 reliability/evidence 工作落地。

**显式不做**:public launch / PyPI / visibility flip 仍是独立 cycle,
v0.9 默认不包含。

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
