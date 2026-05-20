# Harness Design Loop

[English](README.md) | 中文

> 一个做 AI 产品研究的命令行工具：改了你的 agent 之后，量一下这个改动让它变好了、变差了、还是没变。

`hdl` 跑实验。你描述自己的 agent、一个目标、一组测试 case、一份 rubric；工具让 agent 的每个版本过一遍测试，给对话打分，再把各版本并排摆出来，让你看清这个改动带来了什么。

## 为什么有这个工具

我是一个 AI 产品经理。日常工作是给 AI agent 设计记忆、技能、harness 这类功能 —— 这种功能没法周一写 PRD、周五上线，因为设计面一直在动，开始做的时候根本不知道正确答案。

几个月里我在自己的工作上反复跑同一个循环：定目标、做一个改动、跑实验、看数据、修目标、再来。这个模式稳定到我开始把它当成一种架构，而不是一个工作流。`hdl` 就是这个循环，抽成了一个工具。

## 它做什么

一个实验，拿一个 agent 的几个**版本** —— `V1`、`V2`、`V3`，其中一个固定不动当基线 —— 用同一套测试集来比。

- **run** —— 让每个版本过一遍测试集，每个 case 跑成一段多轮对话。
- **score** —— 拿一份 rubric（维度 + 权重）给每段对话打分。
- **compare** —— 把各版本并排比：总分、各维度相对基线的差、退化的维度。

每个实验是一个自包含的文件夹 —— 它的 program、版本、测试集、rubric、结果 —— 可以重跑、重打分。

## 安装

需要 Python 3.10+。

```
git clone <仓库地址>
cd harness-design-loop
pip install -e .
```

这会装上 `hdl` 命令。如果终端报 `hdl: command not found`，是脚本目录不在 PATH 上 —— 把它加进 PATH，或者改用 `python -m harness_design_loop` 来跑（Windows 上用 `py -m harness_design_loop`）。

## 快速上手

```
hdl init                     # 生成 connect.md、goal.md、experiments/
# 编辑 connect.md —— 告诉工具怎么连到你的 agent
hdl new my-experiment        # 搭出 experiments/001-my-experiment/
# 填 program.md、rubric.md、versions/、测试集/
hdl run 001                  # 让每个版本过一遍测试集
hdl score 001                # 给对话打分
hdl compare 001              # 比较各版本
```

`examples/` 里给四种接入方式（进程内库、外部命令行、HTTP 无状态、HTTP 有状态）各放了一个最小 agent，每个都写清了自己的协议 —— 先拿其中一个对着工具跑通。

`run` 和 `score` 默认用内置的桩（一个写死的模拟器、一个基于哈希的评分器）—— 够冒烟测管线，但出不了真实结果。要跑真实的，加 `--llm`，并设好模型环境变量（模拟器用 `HDL_SIM_*`、评分器用 `HDL_JUDGE_*`）。

## 命令

`init` · `connect` · `new` · `show` · `cases` · `rubric` · `simulator` · `versions` · `run` · `score` · `compare` · `draft` · `review`。细节跑 `hdl --help` 或 `hdl <命令> --help`。

## 状态

**v1 —— 可信的手动 loop。** `init → run → score → compare` 整条管线能端到端跑通，跑前会拦下坏输入。`--llm`（真实模拟器 + LLM judge）已在本地的一次真实实验里端到端跑通，不只是内置桩;公开 case study 尚未整理。已知缺口：

- `depends_on`（用前一个 case 跑完的对话给后一个 case 当起始上下文）已解析、也会显示，但 `run` 还没用它。
- `run` / `score` 默认走桩；真实打分要 `--llm` 和 API key。
- 只实现了「模拟」对话模式；回放和固定模式、自迭代运行模式、环境快照、噪声/trial 处理，都还没做。
- 还没有打磨成公开的 case study —— 当前把它当成一个被提出的架构。

在 `v2-agent-drafted-lab` 分支，`hdl draft` 为**外层 coding agent**（Claude Code / Cursor / Codex）开一个 scaffolded authoring workspace —— agent 据 `brief.md` 起草 `program.md` / `versions/` / `测试集/` / `rubric.md` / `模拟器.md`；HDL 自己**不调模型**起草。`hdl review` 再出可审的 `review.md`（宽松：缺什么标「未起草」）。实现切片见 `docs/v2-minimal-spec.md`，agent 起草指南见 `docs/agent-authoring-guide.md`。

v2 及以后的方向（agent 起草、运行实验，人守住锚点）见 `docs/design-v0.4.1.md`。

## 相关工作

**Heuristic Learning** —— Jiayi Weng,《Learning Beyond Gradients》(2026)：一个 coding agent 通过编辑代码（规则、状态、测试、记忆）来改进一个软件系统，而不是训练神经网络参数。`hdl` 是跑这类循环的一个工具。

**Karpathy 的 AutoResearch** (2026) 在 ML 训练上演示了一个针对固定目标的自动研究循环。`hdl` 处理的是一个相邻的问题 —— AI **产品**研究，其中目标本身一直在被修正。是参考，不是模板。

## 作者

Kun，一个 AI 产品经理。
