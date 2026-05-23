# docs

Agent Harness Lab 的文档。读哪个，看你要什么。

## 主线（先读这两份）

- **`product-definition.md`** —— Agent Harness Lab 的产品定义、三层架构（Harness / Experiment / Loop）、三种产品模式、核心对象与术语表。**顶层文档，第一次接触读这份。**
- **`product-modes.md`** —— Manual / Co-pilot / Auto 三种模式的用户心智、流程、谁拥有什么、当前状态、选择指南。

## 实现细节

- **`file-formats.md`** —— 工具实际读写的文件格式（program / rubric / harnesses / cases / connect / simulator / brief / review）。**想知道现在怎么填，看它。**
- **`v2-minimal-spec.md`** —— v2-minimal 分支的实现切片，Co-pilot Mode 最小落地。**概念以本文为准**（external coding agent is the Designer / Lab is protocol）；命名已对齐到 Agent Harness Lab（`ahl` CLI、`AHL_*` 环境变量、Python 包 `agent_harness_lab`、`harnesses/` / `cases/` / `simulator.md`）。
- **`agent-authoring-guide.md`** —— 给**外层 coding agent**（Claude Code / Cursor / Codex 等）读的起草指南。Lab 不调模型起草——这块由外层 agent 据本指南完成。命名已对齐到 Agent Harness Lab。

## 设计 spec（未实现）

- **`runtime-materialization.md`** —— Harness Runtime Materialization & Snapshotting 的设计 spec。下一阶段核心底层能力，**设计阶段，当前不实现**。对应 `design-v0.4.1.md` 路线图的 v2.5 / v3。

## 设计演进史（背景，可跳过）

- **`design-v0.3.md`** —— v1 的架构：三层模型、两个角色、四种接入、run / score / compare。`file-formats.md` 配它看。当前实现仍以它为准。
- **`design-v0.4.1.md`** —— v2 及以后的产品方向（长期架构）：authority matrix、calibration、provenance、red lines。被 `product-definition.md` 在产品定位和命名层上取代——文件顶部 notice 说明 "Designer Agent" 已被 external coding agent 取代；§3 / §5 / §6 / §7 / §9 仍是长期方向有效输入。
- **`archive/`** —— 已被取代的早期草稿（design-v0.1 / v0.2 / v0.4）和旧交接 note，留作记录。

## 一句话

`product-definition.md` 是顶层，`product-modes.md` 讲怎么用，`file-formats.md` 讲现在能写什么文件，`v2-minimal-spec.md` 是当前 v2 分支的实现切片，`runtime-materialization.md` 是下一阶段的 spec，`design-v0.3.md` / `design-v0.4.1.md` 是设计演进史。
