# Agent Harness Lab

[English](README.md) | 中文

> 一个面向人和 coding agent 的工作台，用来设计、测试和改进塑造 agent 行为的**运行时 harness**。

改一份 harness——一段 prompt、一份 tool 配置、一条 memory 规则、一段 workflow——然后量一下这个改动让 agent 变好了、变差了，还是没变。`ahl` 跑实验：你描述一个目标、一组 harness variants、一组测试 case、一份 rubric；工具让每个 variant 过一遍 case，给对话打分，再把各 variant 并排摆出来，让你看清这个改动带来了什么。

## 为什么有这个工具

我是一个 AI 产品经理。日常工作是给 AI agent 设计记忆、技能、harness 这类功能——这种功能没法周一写 PRD、周五上线，因为设计面一直在动，开始做的时候根本不知道正确答案。

几个月里我在自己的工作上反复跑同一个循环：定目标、做一个改动、跑实验、看数据、修目标、再来。这个模式稳定到我开始把它当成一种架构，而不是一个工作流。`ahl` 就是这个循环抽成的工具——但它的主张比"评估 agent"更锋利一档：**这个工具的一等对象是包裹 agent 的 harness，不是 agent 本身**。完整定位见 [`docs/product-definition.md`](docs/product-definition.md)。

## 它做什么

一个实验，拿一个 agent 的几个 **harness variants**——`V1`、`V2`、`V3`，其中一个固定不动当基线——用同一组 case 来比。

- **run** —— 让每个 variant 过一遍 case 集，每个 case 跑成一段多轮对话。
- **score** —— 拿一份 rubric（维度 + 权重）给每段对话打分。
- **compare** —— 把各 variant 并排比：总分、各维度相对基线的差、退化的维度。

每个实验是一个自包含的文件夹——它的 program、harness variants、case 集、rubric、结果——可以重跑、重打分。

## 三种产品模式

`ahl` 对外暴露三种模式（setup mode 完整 flow 见 [`docs/product-walkthrough.md`](docs/product-walkthrough.md)）：

- **Manual** —— 你自己设计 harness variants 和实验；`ahl` 校验、运行、评分、比较。**v1，已完成。**
- **Co-pilot** —— **默认 AI 引导式实验配置模式**:外层 coding agent（Claude Code / Cursor / Codex）通过对话与你协作，维护 `brief.md` 和 `materials/`，并生成或补全实验文件（program / rubric / cases / harnesses）。**已实现。**
- **Auto** —— Agent 在规则、预算、审核门槛下自动迭代 harness；异常时喊你。**未来模式。** Runtime Materialization M1 已在 v0.3.0 落地（`local_path` + `git_repo`；见 [`docs/runtime-materialization.md`](docs/runtime-materialization.md) 和 [`docs/runtime-materialization-m1-spec.md`](docs/runtime-materialization-m1-spec.md)）；Auto 模式本身仍依赖 calibration + approval gates（M2+）。

## 安装

需要 Python 3.10+。

```
git clone <仓库地址>
cd agent-harness-lab
pip install -e .
```

这会装上 `ahl` 命令。如果终端报 `ahl: command not found`，是脚本目录不在 PATH 上——把它加进 PATH，或者改用 `python -m agent_harness_lab` 来跑（Windows 上用 `py -m agent_harness_lab`）。

## 快速上手

```
# 1. 初始化工作目录
ahl init                     # 生成 goal.md + experiments/

# 2. 定义目标
# 编辑 goal.md —— 你想改这个 agent 的什么行为?

# 3. 看完整产品流程
ahl walkthrough              # 9 步:goal → mode → runtime → ... → decide
                             # 完整文档:docs/product-walkthrough.md

# 4. 声明 runtime boundary —— 三选一:
#    已运行的 agent          → 创建 connect.md (legacy;可能需要补 materials/*-evidence.md)
#    本地源码 / Git repo     → 创建 runtime-sources.md (自动 snapshot,strong evidence)
#    (完整 2×2 + evidence level:docs/product-walkthrough.md Step 3)

# 5. 新建实验 (setup mode: copilot 默认 / manual / auto)
ahl new my-experiment                      # 默认 --mode copilot
                                           #   → brief.md + materials/README.md + cases/ + harnesses/
#  或:ahl new my-experiment --mode manual # 完整骨架 (program/rubric/simulator),你手动填
#  或:ahl new my-experiment --mode auto   # 暂未实现 (M2+)

# 6. 运行、评分、对比
ahl run 001 ; ahl score 001 ; ahl compare 001
```

`examples/` 里给四种接入方式（进程内库、外部命令行、HTTP 无状态、HTTP 有状态）各放了一个最小 agent，每个都写清了自己的协议——先拿其中一个对着工具跑通。

`run` 和 `score` 默认用内置的桩（一个写死的模拟器、一个基于哈希的评分器）——够冒烟测管线，但出不了真实结果。要跑真实的，加 `--llm`，并设好模型环境变量（模拟器用 `AHL_SIM_*`、评分器用 `AHL_JUDGE_*`）。

## 命令

`init` · `walkthrough` · `connect` · `new` · `show` · `cases` · `rubric` · `simulator` · `harnesses` · `run` · `score` · `compare` · `review`。细节跑 `ahl --help` 或 `ahl <命令> --help`。

## 状态

**v1 —— 可信的 Manual loop。** `init → run → score → compare` 整条管线能端到端跑通，跑前会拦下坏输入。`--llm`（真实模拟器 + LLM judge）已在本地的一次真实实验里端到端跑通，不只是内置桩；公开 case study 尚未整理。已知缺口：

- `depends_on`（用前一个 case 跑完的对话给后一个 case 当起始上下文）已解析、也会显示，但 `run` 还没用它。
- `run` / `score` 默认走桩；真实打分要 `--llm` 和 API key。
- 只实现了"模拟"对话模式；回放和固定模式、Auto mode（含 calibration 和 approval gates）、噪声/trial 处理，都还没做。
- 还没有打磨成公开的 case study —— 当前把它当成一个被提出的架构。

在 Co-pilot 模式下（`ahl new <名字> --mode copilot`，默认），AHL 创建 `brief.md`（给 coding agent 的工作单）+ `materials/README.md`（参考材料协作目录）。**外层 coding agent**（Claude Code / Cursor / Codex）跟你协作——据 `goal.md` + `brief.md` + `materials/` 起草 `program.md` / `harnesses/` / `cases/` / `rubric.md` / `simulator.md`,并通过对话帮你维护 `brief.md` 和整理 `materials/`；`ahl` 自己**不调模型**。`ahl review` 再出可审的 `review.md`（宽松：缺什么标"未起草"）。旧 `ahl draft` 命令已合并到 `ahl new --mode copilot`。setup mode 完整 flow 见 [`docs/product-walkthrough.md`](docs/product-walkthrough.md)。

让每次 run 都可复现到具体的 harness × runtime 组合——Runtime Materialization——**M1 已在 v0.3.0 落地**（`local_path` + `git_repo` + snapshot persistence + `--cleanup-sandboxes`）；见 [`docs/runtime-materialization.md`](docs/runtime-materialization.md) 和 [`docs/runtime-materialization-m1-spec.md`](docs/runtime-materialization-m1-spec.md)。回放/固定模式、Auto、approval gates、calibration 仍是未来工作。

## 历史

这个项目最初叫 **HDL / Harness Design Loop**。现在改名为 **Agent Harness Lab**，让一等对象是什么这件事在产品名上明示出来。HDL 仍作为历史代号保留在 commit 历史、旧分支名和 v1 设计文档（`docs/design-v0.3.md` / `docs/design-v0.4.1.md`）里。

## 相关工作

**Heuristic Learning** —— Jiayi Weng,《Learning Beyond Gradients》(2026)：一个 coding agent 通过编辑代码（规则、状态、测试、记忆）来改进一个软件系统，而不是训练神经网络参数。`ahl` 是跑这类循环的一个工具。

**Karpathy 的 AutoResearch** (2026) 在 ML 训练上演示了一个针对固定目标的自动研究循环。`ahl` 处理的是一个相邻的问题——AI **产品**研究，其中目标本身一直在被修正。是参考，不是模板。

## 作者

Kun，一个 AI 产品经理。
