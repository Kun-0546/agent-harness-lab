# Agent Harness Lab

[English](README.md) | 中文

一个用于设计、运行、评估 **agent harness 实验**的工作台。**harness** 指包裹 agent
runtime、塑造其行为的那一层 —— 提示词、工具配置、记忆规则、工作流。改动一个 harness，
让它在固定的一组 case 上对真实的 Agent Runtime 跑一遍，收集可复现的证据，看这次改动到底
有没有用。

> **状态：v1，正式版（`1.0.0`）。** 下面的内容如实说明当前实现了什么、还没实现什么。
> 这份文档以准确为先，叙事和表达会在后续完善，但 README 不会声称超出代码已有的能力。
>
> **Changelog：**[GitHub Releases](https://github.com/Kun-0546/agent-harness-lab/releases)
> 即权威 changelog。仓库不设 `CHANGELOG.md` 文件 —— 变更说明随每个 release 发布。

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
| Auto 两层 | Auto Run；**有界 / 确定性**的 Auto Optimize（copy-only + `mutation_script`；**仅支持 single_turn** —— 多轮 simulator 在优化循环内使用时 review 会报错） | LLM 驱动的变异；完全自主、远程 / 分布式优化；通用自我改进引擎 |
| Connector | `local_cli`、`script` | `remote_devbox`、`api`、`bridge`、`manual` —— 可声明但**不执行**（review 会拒绝） |
| 评估 | `benchmark`（确定性脚本）；`llm_judge`（配置 `AHL_JUDGE_BASE_URL` / `AHL_JUDGE_MODEL` / `AHL_JUDGE_API_KEY` 时**调用真实 LLM 评判**；任意 OpenAI 兼容端点 —— Anthropic 等经兼容网关接入；没 key 则 **pending** —— 绝不编造评分）；`human_annotation`（有标注文件就读入，否则 **pending**）；`llm_rubric`（v1.1 —— 多维加权 LLM 评分：rubric markdown 表格声明各维度名称 + 权重，逐维打分后加权汇总为 0-100 总分，明细落 `dimensions` 字段；与 `llm_judge` 共用 `AHL_JUDGE_*` 配置；无 key → **pending**） | 流式 / 多模型评判；按 provider 分发协议（无 `AHL_JUDGE_PROVIDER`） |
| 多轮 simulator（v1.1） | 三种类型：`role_play`（LLM 扮演用户，依据四段式 policy card；需要 `AHL_SIM_*`；无 key → `simulator_unconfigured` 错误，绝不编造跟进问题）；`scripted`（确定性 playbook —— 零 LLM 调用，零密钥）；`script`（外部程序决定每轮用户输入 —— 完全自定义逻辑）。`single_turn` 仍是默认值且已冻结。Auto Optimize 仅支持 `single_turn` | —— |
| 多 trial | `execution.trials: N` 重复运行 N 次（追加式证据，不覆盖）；`hlab run --trials N` 单次覆盖；`hlab run --fresh` 清空重跑；`hlab eval --trial N` 评估历史 trial；compare 输出跨 trial 的 mean/stddev/win_rate | —— |
| 状态策略 | `isolated`、`reset`（已执行） | `cumulative`、`snapshot_branch`、`replay` —— 可声明 → WARN，不执行 |
| 报告 | `reports/report.md` + 真正渲染的 `reports/report.html`（stdlib 渲染器，零依赖）；`compare` → `reports/compare.json`；`conclude` → `conclusion.md` | 托管面板；HTML 图表 |
| 产出 | 证据树（traces / raw / artifacts / scores / inspections / issues） | —— |
| Runtime 来源 pinning（v1.1） | 实验可将 runtime 锁定到一个来源（`local_path` / `git_repo` / `harness_package`），配合可选 patch，生成 snapshot 证据（`evidence/snapshots/<runtime_id>.json`，含 source_dir_hash / commit_sha / patch_hash），驱动 compare 报告的 `strong` 证据等级；`hlab review` 执行只读来源体检（存在性 / 可达性 / 指纹校验）并输出可与运行后 snapshot 对账的指纹 | —— |

任何 pending 或未运行的步骤，AHL 都会在 `review`、`status` 和报告里如实说明。

## 不在范围内（刻意）

- **没有托管面板 / Web UI** —— AHL 把文件写到本地供你查看。
- **不做自主自我改进** —— Auto Optimize 是有界、确定性的循环。
- **不做远程 connector** —— `remote_devbox` / `api` / `bridge` 可声明但不执行。
- **不是企业级 Agent-Eval 平台** —— 它是单用户的本地工作台。

## 快速开始

```bash
pip install -e .          # 提供 `hlab` 命令（以及 `python -m agent_harness_lab`）
```

生成一个完整、可运行的 A/B 实验，并跑通整条路径 —— 本地、确定性、**无网络、无 API key**：

```bash
hlab init
hlab new memory-policy-ab --template memory-policy-ab-lite
hlab review   experiments/memory-policy-ab
hlab run      experiments/memory-policy-ab     # 驱动两个 harness、收集证据、评估
hlab report   experiments/memory-policy-ab     # -> reports/report.md + reports/report.html
hlab compare  experiments/memory-policy-ab     # -> reports/compare.json（winner：B）
hlab conclude experiments/memory-policy-ab --winner B \
  --reason "Filtered retrieval cut leakage while keeping task success."
```

确定性 benchmark 在**无 API key** 时就能定出胜者。`llm_judge` 仅在配置了
`AHL_JUDGE_BASE_URL` / `AHL_JUDGE_MODEL` / `AHL_JUDGE_API_KEY` 时加上一个 LLM 视角 ——
没 key 就保持 **pending**，绝不编造评分。`report` 会同时生成 `report.md` 和渲染后的 `report.html`。

自带样例（可浏览或运行）都在 [`examples/`](examples/)，含旗舰样例
[`memory-policy-ab-lite`](examples/memory-policy-ab-lite/)。完整走查见
[`docs/quickstart.md`](docs/quickstart.md)。

## 命令一览

```text
hlab init                   初始化工作区（goal.md、evaluation-methods/、experiments/）
hlab new <name>             脚手架一个实验；--template <name> 生成完整可运行的实验
hlab review <experiment>    运行前校验 experiment.yaml（PASS / WARN / ERROR）
hlab run <experiment>       Copilot：渲染 agent-task.md · Auto：运行 + 收集 + inspection + 评估
hlab eval <experiment>      对已有 evidence 重算全部评测 track（scores 重写；evidence 只读 ——
                            traces/raw/issues 不会被修改；支持人工标注回流：run → pending →
                            写标注文件 → eval → 打分）
hlab status <experiment>    查看状态与证据 / 评估情况
hlab report <experiment>    从证据生成 reports/report.md（含 report.html）
hlab compare <experiment>   把 A/B 结果汇总进 reports/compare.json
hlab conclude <experiment>  把你的决定记为 conclusion.md（--winner、--reason）
```

`hlab <cmd>` 与 `python -m agent_harness_lab <cmd>` 等价。

所有命令遵守同一份退出码契约（loop 或脚本可以直接据此分流）：

| 退出码 | 含义 |
|--------|------|
| `0` | 成功 —— pending 的评估（无 judge key / 尚无标注）、*failed* 的评估（"实验答案是失败"是合法结果）、warn/info 级 issue 都**不**算运行失败 |
| `1` | 配置或预检错误 |
| `2` | v1 未实现 |
| `3` | 运行期失败 —— 任一 error 级 issue，或任一评估 track 处于 `error`；stderr 同时输出机器可读的 `HLAB_*` 错误码 |

> **`1.0.0` 的 breaking change（rc2 引入）：**运行期失败原先退出 `0`，现在退出 `3`。迁移指引见
> [release notes](https://github.com/Kun-0546/agent-harness-lab/releases)。完整契约
> （每命令产物路径、`HLAB_*` 错误码、可重入性）见
> [`docs/v1-spec/cli.md`](docs/v1-spec/cli.md)。

`ahl`（已退役的 v0.x 栈）不再运行：它的工作区格式与 `hlab` **不**兼容，旧 `ahl` 命令
也不能 1:1 映射到 v1 命令面。请用 `hlab init` 重新开始；迁移指南
（[`docs/migrating-from-ahl.md`](docs/migrating-from-ahl.md)）给出旧文件到 v1 的逐项映射。

## 规格

v1 的权威约定都在 [`docs/v1-spec/`](docs/v1-spec/)：

- [`product-definition.md`](docs/v1-spec/product-definition.md) —— AHL 是什么、核心对象
- [`experiment-structure.md`](docs/v1-spec/experiment-structure.md) —— 磁盘布局
- [`experiment-yaml-schema.md`](docs/v1-spec/experiment-yaml-schema.md) —— `experiment.yaml` 每个字段
- [`execution-model.md`](docs/v1-spec/execution-model.md) —— 模式、connector、状态策略、Auto Optimize
- [`cli.md`](docs/v1-spec/cli.md) —— 命令面

## 环境要求

Python **3.10–3.12**，仅一个依赖 **PyYAML**。本地运行；核心流程和自带样例都不需要网络。

> **暂不支持 Python 3.13。** 有 reviewer 在 3.13.5 上报告了无法稳定复现/修复的测试套件挂起，
> 因此 3.13 被 pin 掉（`requires-python = ">=3.10,<3.13"`），待解决后再开。请用 3.10–3.12 解释器。

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
