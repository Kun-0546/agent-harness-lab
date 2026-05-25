# docs

Agent Harness Lab 的文档。读哪个,看你要什么。

## 当前主线 (5 份)

- **`product-walkthrough.md`** —— 9 步标准产品流程(goal → mode → runtime →
  experiment → variants → cases/rubric → run → evidence → decide)。
  **首次接触、跟着 `ahl init` / `ahl walkthrough` 走一遍读这份。**
- **`product-definition.md`** —— Agent Harness Lab 的产品定义、三层架构
  (Harness / Experiment / Loop)、核心对象与术语表。**理解产品定位读这份。**
- **`file-formats.md`** —— 工具实际读写的文件格式(goal / brief / program /
  harnesses / cases / rubric / simulator / connect / runtime-sources /
  snapshots)。**想知道现在怎么填,看它。**
- **`runtime-materialization.md`** —— Harness Runtime Materialization &
  Snapshotting 总设计 spec。M1 已实现 local_path + git_repo (v0.3.0)。
- **`runtime-materialization-m1-spec.md`** —— v0.3.0 M1 实现合同。

## Historical / Deprecated (背景,跳过即可)

> 下列文档保留作历史 reference,**已不是当前主路径**。每份顶部都有 banner
> 说明它跟当前实现的冲突点。当前 coding agent / 用户主线见上面 5 份。

- **`product-modes.md`** —— v0.2.0 时代的产品模式描述 (Manual / Co-pilot / Auto)。
  **已被 `product-walkthrough.md` Step 2 setup mode + Step 3 runtime boundary 取代。**
  §3 authority matrix 仍作 long-term architecture background。
- **`v2-minimal-spec.md`** —— v0.2.0 / v2-minimal 实现切片。**已被 Step 2 取代**——
  当前入口是 `ahl new --mode copilot/manual`,不是 `ahl draft`;`brief.md` 是
  coding agent 工作单,不是 human-owned。
- **`agent-authoring-guide.md`** —— v2-minimal 时代给外层 coding agent 的指南。
  **已被 `product-walkthrough.md` + `materials/README.md` 取代。**
  当前 coding agent 应读 `product-walkthrough.md` + `file-formats.md` + 用户实验的
  `materials/README.md`。
- **`design-v0.3.md`** —— v1 / HDL (Harness Design Loop) 时代的架构。三层模型
  仍是 `product-definition.md` §2 的底,但 HDL / hdl 命名是历史代号 (当前是
  Agent Harness Lab,Phase 2/3 已完成迁移)。
- **`design-v0.4.1.md`** —— v2+ 长期方向 (authority matrix / calibration /
  路线图)。§1-§9 仍是长期 architecture 输入;§4 / §8 的 "Designer Agent"
  已被 external coding agent 取代。
- **`archive/`** —— 已被取代的早期草稿 (design-v0.1 / v0.2 / v0.4 / handoff)。
- **`handoffs/release-v0.2.0-summary.md`** —— v0.2.0 release 的 phase 1-4
  handoff 备忘 (历史 release artifact)。

## 一句话

- **首次接触** → `product-walkthrough.md`
- **产品定位** → `product-definition.md`
- **具体填什么文件** → `file-formats.md`
- **runtime materialization** → `runtime-materialization.md`
- **其他都是历史** (Historical / Deprecated 段)
