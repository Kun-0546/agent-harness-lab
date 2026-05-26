# docs

Agent Harness Lab 的文档。读哪个,看你要什么。

## 首次接触的推荐顺序

新用户按这条路径走 — 30 分钟内能跑完一次完整 compare:

1. **[`product-walkthrough.md`](product-walkthrough.md)** —— 9 步标准产品流程
   (goal → mode → runtime → experiment → variants → cases/rubric → probe →
   run → evidence → decide)。先读这份建立心智模型。
2. **[`product-definition.md`](product-definition.md)** —— Agent Harness Lab
   的产品定义、三层架构 (Harness / Experiment / Loop)、核心对象与术语表。
   补完概念深度。
3. **[`../examples/sample-workspace/README.md`](../examples/sample-workspace/README.md)**
   —— 跑一遍现成的、可复现的、零 API key 的端到端 sample。这是产品流的
   canonical runnable path。

## 当前主线 (depth specs,按需读)

每份 spec 都是某一档 MVP 的深度合同。需要时按 product-walkthrough.md 的
Step 锚点跳到对应那份。

- **[`product-walkthrough.md`](product-walkthrough.md)** —— 9-step 产品流程
  (Step 1 Define goal → Step 9 Decide;Step 6.5 = probe)。
- **[`product-definition.md`](product-definition.md)** —— 产品定义 + 三层
  架构 + 术语表。
- **[`file-formats.md`](file-formats.md)** —— 工具实际读写的文件格式
  (goal / brief / program / harnesses / cases / rubric / simulator /
  connect / runtime-sources / snapshots)。**想知道某个文件具体怎么填,
  看它。**
- **[`runtime-materialization.md`](runtime-materialization.md)** 与
  **[`runtime-materialization-m1-spec.md`](runtime-materialization-m1-spec.md)**
  —— Runtime Materialization 总设计 + v0.3.0 M1 实现合同
  (`local_path` + `git_repo` + snapshot)。Walkthrough Step 3 + Step 7 的深度。
- **[`evidence-guide.md`](evidence-guide.md)** —— 用户指南:解读 compare
  report 的 evidence 四档(strong / medium / weak / unknown)、怎么升级、
  为什么 supplied evidence 不是 cloud attestation、harness package 怎么
  影响 evidence、probe 跟 evidence 什么关系。**读 compare report 之前
  先看这份。**
- **[`evidence-aware-result.md`](evidence-aware-result.md)** —— v0.4 evidence
  四级标签 (strong / medium / weak / unknown) **推断规则合同**(实现导向)+
  score JSON + compare report `## Evidence` section。Walkthrough Step 8 的
  深度。用户层解读看上面 `evidence-guide.md`。
- **[`harness-package-mvp.md`](harness-package-mvp.md)** —— v0.5 harness
  package 目录格式、`harness_package: <id>@<version>` frontmatter、install
  order (materialize → package → patch → snapshot)、三个 hash 字段。
  Walkthrough Step 5 + Step 7 的深度。
- **[`runtime-probe-mvp.md`](runtime-probe-mvp.md)** —— v0.6 `ahl probe`
  CLI、per-source probe 规则、`--write-evidence` 通道、smoke 命令支持。
  Walkthrough Step 6.5 的深度。
- **[`product-flow-completion.md`](product-flow-completion.md)** —— v0.7
  product-flow MVP spec(sample workspace 设计 + README 概念重写 + docs
  导航 + E2E 验收)。本次 docs 重组的合同。
- **[`roadmap.md`](roadmap.md)** —— 从 v0.3.1 开源 baseline 到 v1.0
  stable 的版本演进路径。

## Historical / Deprecated (背景,跳过即可)

> 下列文档保留作历史 reference,**已不是当前主路径**。每份顶部都有 banner
> 说明它跟当前实现的冲突点。当前 coding agent / 用户主线见上面 "首次接触"
> 与 "当前主线"。

- **[`product-modes.md`](product-modes.md)** —— v0.2.0 时代的产品模式描述
  (Manual / Co-pilot / Auto)。已被 `product-walkthrough.md` Step 2 + Step 3
  取代;§3 authority matrix 仍作 long-term architecture background。
- **[`v2-minimal-spec.md`](v2-minimal-spec.md)** —— v0.2.0 / v2-minimal
  实现切片。已被 Step 2 取代——当前入口是 `ahl new --mode copilot/manual`,
  不是 `ahl draft`。
- **[`agent-authoring-guide.md`](agent-authoring-guide.md)** —— v2-minimal
  时代给外层 coding agent 的指南。已被 `product-walkthrough.md` +
  `materials/README.md` 取代。
- **[`design-v0.3.md`](design-v0.3.md)** —— v1 / HDL (Harness Design Loop)
  时代的架构。三层模型仍是 `product-definition.md` §2 的底,但 HDL / hdl
  命名是历史代号(当前是 Agent Harness Lab)。
- **[`design-v0.4.1.md`](design-v0.4.1.md)** —— v2+ 长期方向 (authority
  matrix / calibration / 路线图)。§1-§9 仍是长期 architecture 输入;§4 / §8
  的 "Designer Agent" 已被 external coding agent 取代。
- **`archive/`** —— 已被取代的早期草稿 (design-v0.1 / v0.2 / v0.4 / handoff)。
- **`handoffs/release-v0.2.0-summary.md`** —— v0.2.0 release 的 phase 1-4
  handoff 备忘 (历史 release artifact)。

## 一句话

- **首次接触** → `product-walkthrough.md` + `examples/sample-workspace/`
- **产品定位** → `product-definition.md`
- **具体填什么文件** → `file-formats.md`
- **解读 evidence(weak/medium/strong/unknown 各是什么)** → `evidence-guide.md`
- **某档 MVP 的深度** → `runtime-materialization.md` / `evidence-aware-result.md`
  / `harness-package-mvp.md` / `runtime-probe-mvp.md`
- **版本路线** → `roadmap.md`
- **贡献 / 安全** → `../CONTRIBUTING.md` / `../SECURITY.md`
- **其他都是历史** (Historical / Deprecated 段)
