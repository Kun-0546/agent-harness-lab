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
  exits 2 (Auto setup mode + autonomous iteration loop 推到 post-open-source
  或 v1.x,见下;v0.9 改走 Co-pilot Setup Productization MVP)
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

## v0.8 — Product Reliability & Evidence Hardening [shipped]

**目标**:在 v0.7 完整产品流可跑的基础上,补 (1) **evidence 链 user-facing
解读**(让读 compare-*.md 的人知道 strong/medium/weak/unknown 各是什么、
怎么升、自填 evidence 文件长什么样) + (2) **doc / sample / CLI drift 回归
保护**(让后续 PR 不能默默改坏 docs ↔ code 链)。**docs + tests only,
zero src behavior change,no new CLI command,no contract change**。

> 原 v0.7 时挂在 v0.8 entry 的"Co-pilot Setup Productization"方向 deferred
> 到 v0.9 / v0.10 候选项;v0.8 spec lock-in 后路线调整为"Reliability &
> Evidence Hardening" — 见 `docs/product-reliability-evidence-hardening.md`。

**主要交付**:

- `docs/evidence-guide.md`(centerpiece,~560 行,10 节)—— 5 个 evidence
  artifact 类型解释、4 档 level 推断规则、`materials/*-evidence.md` 格式
  说明、harness package 怎么影响 evidence、probe 跟 evidence 什么关系、
  4 个 worked example、"AHL 不证明什么"诚实清单
- `examples/evidence-examples/{README, runtime-evidence, harness-evidence,
  cloud-evidence}.md` —— 用户自填模板,每份明确"checked / supplied by /
  captured at / can support / cannot prove / limitations"六段;cloud-
  evidence.md 显著 disclosure"not cloud attestation"
- `docs/product-acceptance-checklist.md`(~260 行,12 组 A-L) —— 新装
  AHL 跑 sample workspace、或 maintainer 准备 merge/tag/release 前的
  自验收清单
- `tests/test_doc_consistency.py`(10 测) —— 8 项 drift detector:docs
  mainline 链接 / evidence-guide 被引用 / key spec 可达 / simulator.md
  跟 stub_simulator 行为对齐(这条能 catch v0.7 PASS-WITH-DOC-BLOCKER)/
  sample workspace 仓内 cleanliness / evidence-examples 完整 + 限制语言 /
  current docs 无 dead link(skip `docs/archive/` + banner-tagged 历史
  doc)
- `tests/test_readme_command_flow.py`(4 测,scoped 到 README §8 + sample-
  workspace recipe) —— README 命令 anchor + 实际 CLI 可跑
- `docs/file-formats.md` 新 §Materials Evidence Files (v0.4) 段 + cross-
  link 到 evidence-examples 和 evidence-guide
- README.md / README_CN.md §7 + docs/README.md / docs/evidence-aware-
  result.md cross-link 到新 evidence-guide
- `docs/product-reliability-evidence-hardening.md` v0.8 spec(16 节)

**测试**:465 → **479 passed**(+14:10 doc-consistency + 4 README
command-flow)。strict ResourceWarning 模式也 479。

**关键依赖**:v0.4 + v0.5 + v0.6 + v0.7(全部已 shipped);v0.8 不引入
新依赖。

**显式不做(redline 已确认)**:不加 CLI 命令、不加 src 模块、不变 snapshot
schema、不变 v0.4 evidence 推断规则、不变 scoring / package / probe 合同、
不发 PyPI、不公开仓、不发 announcement。

---

## v0.9 — Co-pilot Setup Productization MVP [shipped]

> 原 v0.9 计划方向("Auto Mode MVP")在 2026-05-26 调整为 "Co-pilot
> Setup Productization MVP" —— 见
> [`copilot-setup-productization.md`](copilot-setup-productization.md)。
> Auto mode 推到 **post-open-source 或 v1.x**(不在 v0.10)。

**主线目标**:把 `ahl new` 默认走的 **Co-pilot setup mode** 从一个轻量
目录脚手架升级成一份真正可用的 human + coding-agent 工作流 —— 12 节
`brief.md` + 8 节 `materials/README.md` + 一份用户/coding agent 共读的
驱动指南 + 一份 setup-state 示例 + drift 测试。**docs + templates +
tests + 一行 cmd_new UX 提示,zero src behavior change,no new CLI
command,no contract change。**

**主线交付**:

- `BRIEF_TEMPLATE` 重写为 12 节(想优化什么 / 目标行为 / 当前问题 /
  Runtime 信息 / Harness 假设 / Cases 覆盖 / Rubric 判断 / Evidence-probe
  expectations / Files coding agent may create / Files coding agent
  should not change / Acceptance commands / Done criteria),≤200 行
- `MATERIALS_README_TEMPLATE` 重写为 8 节,≤80 行
- 新文档 [`copilot-setup.md`](copilot-setup.md) —— 9 节,合并 human
  operator + coding agent 两个 audience,≤400 行(目标 ~280)
- 新示例 [`../examples/copilot-setup-example/`](../examples/copilot-setup-example/)
  —— setup-state only(不含 program/rubric/simulator/cases/harnesses/
  results),含填好的 12 节 brief + 3 份 materials + locked.md +
  expected-coding-agent-plan.md(3-anchor schema)
- README EN/CN §"Three product modes" + docs/README mainline + product-
  walkthrough Step 2/4 + file-formats setup-mode 段全部 cross-link 到
  新指南
- `tests/test_copilot_templates.py` + `tests/test_ahl_new_copilot_default.py`
  + `tests/test_copilot_setup_example.py` + extend
  `tests/test_doc_consistency.py` —— co-pilot setup 各环节 drift 防护
- `src/agent_harness_lab/cli.py:cmd_new` auto-mode error 增 1 行 UX
  提示指向 `docs/copilot-setup.md`(no behavior change,no new CLI)

**关键依赖**:v0.7 sample workspace + v0.8 evidence-guide(co-pilot 指南
cross-link 到这两份)。**不**依赖 Auto / calibration / approval gates。

**显式不做(redline)**:public launch / PyPI / visibility flip / Auto
mode / MCP / registry / package inspect-validate CLI / probe-snapshot
binding / 新 runtime source 类型 / snapshot schema / evidence rules /
scoring math / 删 v0.7 sample workspace / 删 manual mode。

---

## v0.10 — Open-Source Readiness Freeze / Release Candidate / Final Acceptance [shipped]

**主线目标**:把 v0.3.1 → v0.9 累计的产品 surface 收口到 OSS-ready 状
态 —— freeze CLI / file format / API,跑完整 acceptance,产出 release
candidate。**v0.10 不是 Auto mode cycle**;Auto 推到 post-open-source
或 v1.x。

**候选交付方向**(具体待 v0.10 spec lock-in,**不保证全做**):

- API / file format / CLI 命令名 + 参数 freeze 评估(为 v1.0 稳定承诺
  做准备)
- `docs/product-acceptance-checklist.md` 升级为 RC 验收清单
- 公开发布所需 governance / SECURITY / CONTRIBUTING / SUPPORT 文档复审
- 一次完整 pre-release acceptance run(479+ 测、所有 sample + co-pilot
  example 端到端验证)
- License audit + dependency policy(stdlib-only 哲学最后确认)
- v1.0 spec draft(列必须完成的最后一档稳定承诺)

**关键依赖**:v0.7 + v0.8 + v0.9 全部 shipped 且稳定使用过一段时间。

**显式不做**:Auto mode / package inspect-validate / probe-snapshot
binding —— 这些都推到 **post-OSS 或 v1.x**。

---

## v1.x / post-open-source — Deferred candidates [future]

v0.10 OSS freeze 之后才考虑的方向(**不在 v0.10**):

- **Auto Mode MVP** —— `ahl new --mode auto` 不再 not-implemented;
  approval gate schema(budget / max iterations / red line trigger);
  calibration 子系统 MVP(judge / rubric 校准锚点);escalation 规则
  (何时停 + 喊人)。需要 calibration + approval gates 先成熟。
- **`ahl package inspect` / `ahl package validate`** —— read-only
  package inspection + standalone preflight(v0.8 / v0.9 因 no-new-CLI
  redline 推迟)。
- **更紧的 probe ↔ snapshot 绑定** —— snapshot 引用最近一次成功
  probe id(v0.8 / v0.9 因 no-snapshot-schema-change redline 推迟)。

具体取舍 + 启动时间待相关 cycle spec。

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
