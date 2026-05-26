# Agent Harness Lab

[English](README.md) | 中文

> 一个面向人和 coding agent 的工作台，用来设计、测试和改进塑造 agent 行为的**运行时 harness**。

改一份 harness——一段 prompt、一份 tool 配置、一条 memory 规则、一段 workflow——然后量一下这个改动让 agent 变好了、变差了，还是没变。`ahl` 跑实验：你描述一个目标、一组 harness variants、一组测试 case、一份 rubric；工具让每个 variant 过一遍 case，给对话打分，再把各 variant 并排摆出来，让你看清这个改动带来了什么。

## 1. Agent Harness Lab 是什么?

一个 CLI 工作台,用来**在同一组 case 上对比一个 agent 的多个 harness variant,并产出可复现的证据**。你把 AHL 指到一个 agent runtime、给它 2-3 版你想测的 harness、给它一组 case 和一份打分 rubric,它跑完会出一份 side-by-side 的 compare report 和一份 snapshot——后者精确记录了刚才到底跑了什么。

Python 3.10+,只用标准库(零外部依赖),本地跑。完整的[`docs/product-definition.md`](docs/product-definition.md) 描述三层架构(Harness / Experiment / Loop)和核心对象。

## 2. 它解决什么问题?

我是 AI 产品经理。日常工作是给 AI agent 设计记忆、技能、harness 这类功能——这种功能没法周一写 PRD、周五上线,因为设计面一直在动,开始做的时候根本不知道正确答案。

几个月里我在自己的工作上反复跑同一个循环:定目标、做一个改动、跑实验、看数据、修目标、再来。这个模式稳定到我开始把它当成一种架构,而不是一个工作流。`ahl` 就是这个循环抽成的工具——但它的主张比"评估 agent"更锋利一档:**一等对象是包裹 agent 的 harness,不是 agent 本身**。

## 3. Runtime 是什么?

Agent 的运行环境——源码、prompts、工具、配置、启动命令,跑起来产出 agent 行为的那一堆东西。AHL 里你在 workspace 根的 `runtime-sources.md` 里声明 runtime sources。v0.3.0 支持两种 source 类型:

- **`local_path`** —— 本地一个目录。AHL 复制到 per-variant sandbox 并 apply variant 的 patch。
- **`git_repo`** —— clone + checkout 某个 ref + apply patch。

Materialize 流程是 `materialize → snapshot → start`,每次 run 都持久化一份 `RuntimeSnapshot`(source dir hash、patch hash、commit SHA),让两个月后的 run 也可复现。深度细节:[`docs/runtime-materialization.md`](docs/runtime-materialization.md)。

## 4. Harness 是什么?

**不改模型权重就能塑造 agent 行为的那层外部结构**——prompts、tool 配置、memory 规则、workflow 步骤、start command、env。Harness variant 是这层结构的一个具体配置。AHL 的一等对象。

每个 variant 一个文件,放在 `experiments/<id>/harnesses/V*.md`。约定 `V1` 是 baseline,`V2+` 是你想测的改动。Variant 声明 `runtime_source:`(它要 patch 哪个 runtime)和一段可选的 `## Patch` 段(files / env / start_command 覆盖)。格式见 [`docs/file-formats.md`](docs/file-formats.md) §Harness Variant。

## 5. Harness package 是什么?

**可复用、有版本、可安装的 harness 组件**,在 workspace 根的 `harness-packages/<id>/<version>/{manifest.md, payload/...}` 里。Variant 在 frontmatter 加 `harness_package: <id>@<version>` 就引用,AHL 在 apply variant 自己的 patch 之前先把 package 的 payload 装到 sandbox 里。

安装顺序固定:**runtime materialize → package install → variant `## Patch` → snapshot**。Variant patch 在文件 / env / start_command 冲突时胜出。Snapshot 记录 package 的 `manifest_hash`、`payload_hash`、`effective_harness_hash`——三个指纹一起证明实际跑的是哪个 package 版本。深度细节:[`docs/harness-package-mvp.md`](docs/harness-package-mvp.md)。

## 6. Probe 是什么?

每个 variant 的**只读、跑前 inspection**:`ahl probe <experiment>`。检查 `runtime_source` 可访问、harness package(若有)完整、start command 已供、可选 run 一条 user-supplied smoke 命令(`--command "<cmd>"`,默认 30s 超时)。它**不**建 sandbox、**不**装东西、**不**改源码。

Probe 产物落到 `experiments/<id>/probe-results/<probe_id>/<variant_id>.json`。Probe 失败是**告知性**的(任一 variant `fail` → exit 1)——它**不会**阻断 `ahl run`。深度细节:[`docs/runtime-probe-mvp.md`](docs/runtime-probe-mvp.md)。

## 7. Evidence 是什么?

每个 variant 分数上的一个四级标签(`strong` / `medium` / `weak` / `unknown`),由 runtime snapshot 加可选的 `materials/*-evidence.md` 文件推断。`strong` 表示 AHL 自己 materialize 了 runtime,而且(variant 用了 package 的话)完整 fingerprint 了 package。`weak` / `unknown` 表示 AHL 不能证明实际跑了什么——典型情况是 legacy `connect.md` 适配器或没补 attestation 的 cloud agent。

Evidence 在 compare report **顶部**作为 `## Evidence` section 出现。重点不是 block 决策——是让你做 `keep / discard / next` 判断的时候,对这次数据能信几分心里有数。深度细节:[`docs/evidence-aware-result.md`](docs/evidence-aware-result.md)。

## 8. 最简端到端流程

[`examples/sample-workspace/`](examples/sample-workspace/) 已经 init 好了——纯本地、纯离线、零 API key,跑一个确定的 30 行 tiny agent。从 repo 根:

```bash
cd examples/sample-workspace
ahl probe 001            # 跑前 readiness 检查(只读)
ahl run 001              # 2 variants × 2 cases = 4 段对话
ahl score 001            # stub_grader → score-*.json 带 evidence block
ahl compare 001          # compare-*.md 带 ## Evidence + 版本总分
```

V2 用 `concise-prompt@0.1.0` package;V1 不用。Compare report 显示 package 带来了一个可测、可复现的行为 delta。完整 recipe 与预期见 [`examples/sample-workspace/README.md`](examples/sample-workspace/README.md)。

跑你自己的实验:`ahl init` → 填 `goal.md` → `ahl walkthrough`(打印 9 步产品流程) → 在 `runtime-sources.md`(推荐)或 `connect.md`(legacy)里声明 runtime → `ahl new <name>` → run / score / compare。9 步详见 [`docs/product-walkthrough.md`](docs/product-walkthrough.md)。

## 安装

需要 Python 3.10+。

```
git clone https://github.com/Kun-0546/agent-harness-lab.git
cd agent-harness-lab
pip install -e .
```

这会装上 `ahl` 命令。如果终端报 `ahl: command not found`,是脚本目录不在 PATH 上——把它加进 PATH,或者改用 `python -m agent_harness_lab` 来跑(Windows 上用 `py -m agent_harness_lab`)。

## 三种产品模式

`ahl` 暴露三种 setup mode(完整 flow 见 [`docs/product-walkthrough.md`](docs/product-walkthrough.md) Step 2):

- **Manual** —— 你自己设计 harness variants 和实验;`ahl` 校验、运行、评分、比较。**已实现。**
- **Co-pilot** *(默认)* —— 外层 coding agent(Claude Code / Cursor / Codex)通过对话与你协作,维护 `brief.md` 和 `materials/`,并生成或补全实验文件。**已实现。**
- **Auto** —— Agent 在规则、预算、审核门槛下自动迭代 harness;异常时喊你。**未来模式**(依赖 calibration + approval gates,M2+)。

## 命令

14 个命令:`init` · `walkthrough` · `connect` · `new` · `show` · `cases` · `rubric` · `simulator` · `harnesses` · `run` · `score` · `compare` · `review` · `probe`。细节跑 `ahl --help` 或 `ahl <命令> --help`。

`run` 和 `score` 默认用内置的桩(一个写死的模拟器、一个基于哈希的评分器)——够冒烟测管线,但出不了真实结果。要跑真实的,加 `--llm`,并设好模型环境变量(模拟器用 `AHL_SIM_*`、评分器用 `AHL_JUDGE_*`)。`examples/` 给四种接入方式(进程内库、外部命令行、HTTP 无状态、HTTP 有状态)各放了一个最小 agent。

## 9. 暂未实现

老实说,每条标注承载它的版本:

- **Auto mode** —— Agent 自迭代 harness,带审核门槛和 budget 规则。需要先有 calibration + approval gates(M2+)。
- **Cloud attestation** —— 证明远端 agent runtime 里实际装了什么。当前 cloud variant 默认 `weak` evidence,除非你手写 `materials/*-evidence.md`。
- **Harness package 注册中心 / 远端分发** —— Package 当前只能 workspace 本地(v0.5)。没有 `ahl package publish`、没有 fetch、没有版本求解器。
- **更多 runtime source 类型** —— `docker_image`、`remote_api`、`dev_agent` 已 spec,但 deferred 到 runtime-materialization M2+。
- **`depends_on`** —— 用前一个 case 的 transcript 给后一个 case 做开场,已解析、会显示,但 `run` 还没用。
- **回放 / 固定对话模式** —— 只实现了 simulated 模式。
- **噪声 / trial / 多 run 统计** —— 每次 run 是单次 trial。
- **打磨过的公开 case study** —— 还没有发布完整 worked example;当前把 AHL 当成一个被提出的架构。

## 历史

这个项目最初叫 **HDL / Harness Design Loop**。现在改名为 **Agent Harness Lab**,让一等对象是什么这件事在产品名上明示出来。HDL 仍作为历史代号保留在 commit 历史、旧分支名和 v1 设计文档(`docs/design-v0.3.md` / `docs/design-v0.4.1.md`)里。

## 相关工作

**Heuristic Learning** —— Jiayi Weng,《Learning Beyond Gradients》(2026):一个 coding agent 通过编辑代码(规则、状态、测试、记忆)来改进一个软件系统,而不是训练神经网络参数。`ahl` 是跑这类循环的一个工具。

**Karpathy 的 AutoResearch** (2026) 在 ML 训练上演示了一个针对固定目标的自动研究循环。`ahl` 处理的是一个相邻的问题——AI **产品**研究,其中目标本身一直在被修正。是参考,不是模板。

## 作者

Kun,一个 AI 产品经理。
