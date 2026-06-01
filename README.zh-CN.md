# Agent Harness Lab

[English](README.md) | 中文

一个用于设计、运行、评估 **agent harness 实验**的工作台。**harness** 指包裹 agent
runtime、塑造其行为的那一层 —— 提示词、工具配置、记忆规则、工作流。改动一个 harness，
让它在固定的一组 case 上对真实的 Agent Runtime 跑一遍，收集可复现的证据，看这次改动到底
有没有用。

> **状态：v1，预发布（`1.0.0.dev0`）。** 下面的内容如实说明当前实现了什么、还没实现什么。
> 这份草稿以准确为先，叙事和表达会在后续完善，但 README 不会声称超出代码已有的能力。

## AHL 是什么

一个实验就是一份 `experiment.yaml`：一个目标、一个或多个 harness、一组 case、一套评估，
以及（可选的）一个优化目标。AHL 让每个 harness 在这些 case 上对真实 runtime 运行，写出可
审计的证据树（traces、原始输出、artifacts、scores、issues），执行 inspection 与
evaluation，最后生成报告。

第一类对象是 **harness**，不是 agent 本身。AHL 不做通用 agent 框架，它通过一份小而明确的
connector 约定来驱动你已有的 runtime，把注意力集中在包裹 agent 的那层结构上。

## 为什么它不只是一个 eval runner

普通的 eval runner 给模型输出打分。AHL 围绕三件 eval runner 通常不做的事来设计：

- **harness 是改动单元。** 结构是 目标 → harnesses → cases → evaluation →（可选）
  optimization。实验比较的是 harness（在优化循环里则是 Incumbent 与 Candidate），不止是模型。
- **证据纪律。** 每次运行都落盘一棵结构化证据树和一份 `issues.jsonl`；inspection 与
  evaluation 是各自独立、显式的步骤。pending 或未运行的步骤会如实标为 pending，绝不编造结论。
- **有界的优化循环。** AHL 可以在受保护 / 可编辑边界内，对 harness 跑一个
  candidate → evaluate → promote 的循环 —— 具体范围见下面的诚实说明。

它源于一套工作流。作者是 AI 产品经理，日常设计 agent 的记忆、技能、harness 类功能 —— 这类
功能没法周一写 PRD、周五上线，因为设计面一直在变，开工时正确答案是未知的。那个循环（定目标、
改 harness、跑实验、读证据、修目标、再循环）稳定到可以当成一种架构来对待。AHL 就是把这个循环
抽成了一个工具。

## 模式

### Copilot Mode（`run.mode: copilot`）

AHL 准备好实验、渲染出 `agent-task.md`；由外部编码 agent（Claude Code / Codex / Cursor）
执行 runtime 相关的步骤并写出证据，AHL 再做校验、inspection、evaluation 和报告。AHL 提供
结构、检查和证据纪律，执行交给外部 agent。

### Auto Mode（`run.mode: auto`）

AHL 自己通过 connector 驱动 runtime 并收集证据。Auto Mode 有两层：

- **Auto Run** —— 通过 connector 把每个 case 派发给 runtime，收集证据、做 inspection、做
  evaluation。已实现。
- **Auto Optimize** —— 一个**有界、确定性**的 candidate → evaluate → promote 循环：把
  incumbent 复制成 candidate，可选地用用户提供的 `mutation_script` 变异它，强制 可编辑 /
  受保护 边界（碰了受保护文件会回滚），运行并评估 candidate，再按 promotion policy 决定晋升
  或拒绝，依 `stop_conditions` 停止。candidate 的生成只有 copy-only 或你自己的确定性脚本两种。
  **未实现：** LLM 驱动的变异、完全自主的优化、远程 / 分布式优化，以及任何通用自我改进引擎。

## 已实现 / 未实现

| 方面 | v1 已实现 | 未实现 |
|------|-----------|--------|
| 运行模式 | Copilot、Auto | —— |
| Auto 两层 | Auto Run；**有界 / 确定性**的 Auto Optimize（copy-only + `mutation_script`） | LLM 驱动的变异；完全自主、远程 / 分布式优化；通用自我改进引擎 |
| Connector | `local_cli`、`script` | `remote_devbox`、`api`、`bridge`、`manual` —— 可声明但**不执行**（review 会拒绝） |
| 评估 | `benchmark`（运行一个确定性脚本） | —— |
| 评估（诚实的占位） | `human_annotation`（有标注文件就读入，否则 **pending**）；`llm_judge`（**离线 stub → 永远 pending**，不调用任何模型） | 真正基于 LLM 的评判 |
| 状态策略 | `isolated`、`reset`（已执行） | `cumulative`、`snapshot_branch`、`replay` —— 可声明 → WARN，不执行 |
| 产出 | 证据树（traces / raw / artifacts / scores / inspections / issues）、`reports/report.md` | —— |

任何 pending 或未运行的步骤，AHL 都会在 `review`、`status` 和报告里如实说明。

## 快速开始

```bash
pip install -e .          # 提供 `hlab` 命令（以及 `python -m agent_harness_lab`）
```

端到端跑一个自带样例 —— 本地、确定性、无网络、无 API key：

```bash
cd examples/auto-run-local-cli-lite
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

完整走查（含 Auto Optimize 样例）见 [`docs/quickstart.md`](docs/quickstart.md)，
两个样例都在 [`examples/`](examples/)。

## 命令一览

```text
hlab init <dir>            初始化工作区（goal.md、evaluation-methods/、experiments/）
hlab new <name>            脚手架一个实验（--mode copilot|auto，--execution ab|sequential|...）
hlab review <experiment>   运行前校验 experiment.yaml（PASS / WARN / ERROR）
hlab run <experiment>      Copilot：渲染 agent-task.md · Auto：运行 + 收集 + inspection + 评估
hlab status <experiment>   查看状态与证据 / 评估情况
hlab report <experiment>   从证据生成 reports/report.md
```

`hlab <cmd>` 与 `python -m agent_harness_lab <cmd>` 等价。`ahl` 保留为指向 `hlab` 的
legacy 重定向。

## 规格

v1 的权威约定都在 [`docs/v1-spec/`](docs/v1-spec/)：

- [`product-definition.md`](docs/v1-spec/product-definition.md) —— AHL 是什么、核心对象
- [`experiment-structure.md`](docs/v1-spec/experiment-structure.md) —— 磁盘布局
- [`experiment-yaml-schema.md`](docs/v1-spec/experiment-yaml-schema.md) —— `experiment.yaml` 每个字段
- [`execution-model.md`](docs/v1-spec/execution-model.md) —— 模式、connector、状态策略、Auto Optimize
- [`cli.md`](docs/v1-spec/cli.md) —— 命令面

## 环境要求

Python 3.10+，仅一个依赖 **PyYAML**。本地运行；核心流程和自带样例都不需要网络。

```bash
git clone https://github.com/Kun-0546/agent-harness-lab.git
cd agent-harness-lab
pip install -e .
```

若 shell 提示 `hlab: command not found`，说明脚本目录不在 PATH 上 —— 加进去，或直接用
`python -m agent_harness_lab`（Windows 上是 `py -m agent_harness_lab`）。

## 相关工作

- **Heuristic Learning** —— Jiayi Weng，《Learning Beyond Gradients》(2026)：编码 agent
  通过编辑代码（规则、状态、测试、记忆）来改进一个软件系统，而非训练网络参数。AHL 是跑这类
  循环的工具。
- **Karpathy 的 AutoResearch**（2026）展示了针对固定目标的 ML 训练自动研究循环。AHL 处理的是
  相邻的问题 —— AI *产品*研究，目标本身在不断修订。作为参照，而非模板。

## 作者

由 Kun 开发，AI 产品经理。

## 许可证

MIT。
