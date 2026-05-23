# Agent Authoring Guide

> 给**外层 coding agent**(Claude Code / Cursor / Codex 等)读的。你正在帮用户 author 一个 AHL 实验。AHL 不会自己想实验 —— 那是你的活。

## Your role(你的角色)

你是 **external Designer**。AHL 是 **protocol + validator + reviewer + runner**。

具体说:

- 你据 `goal.md` 和 `experiments/<id>/brief.md` 起草整套实验文件。
- AHL 不调模型自己起草。它只 scaffold、validate、review、run、score、compare。
- 你写的文件和人手写的同格式 —— `run / score / compare` 不区分谁写的。

## Inputs to read(必读的输入)

| 文件 | 是什么 |
|------|--------|
| `goal.md`(工作区根) | 用户对这个 agent 的总目标。一次性,长期不动。 |
| `experiments/<id>/brief.md` | 用户这次实验的意图(想优化什么、要试什么改动、最在意什么、不能牺牲什么、怎么比)。**human-owned,你不要改。** |
| `docs/v2-minimal-spec.md` | v2 实现 spec。§3 brief 格式、§4 你的角色契约、§5 集中式 provenance、§6 review 格式。 |
| `docs/file-formats.md` | v1 文件格式权威定义(`program.md` / `rubric.md` / `cases/` / `harnesses/` / `connect.md` / `simulator.md`)。 |

## Artifacts to create(你要造的文件)

全部写进 `experiments/<id>/` 下:

- `program.md` —— 实验执行协议(假设 + 声明 + 留/丢规则 + 喊人规则)。**中枢锚点。** `对比方式` 一行据 `brief.compare` 写:`对基线` / `线性迭代`;`brief.compare` 空就默认 `对基线`。
- `harnesses/V1.md`、`harnesses/V2.md`(……)—— 被对比的版本。**恰好一个**标 `基线: 是`(对基线模式),其余 `基线: 否`。每个版本「这是什么」段写清和基线的差异。
- `cases/D-01.md`(……)—— 测试 case,一个 case 一个文件。frontmatter 至少含 `id`,body 必须有 `## 起始输入`。
- `rubric.md` —— 评分维度 + 权重,**权重之和 = 1.0**(或百分数 = 100)。
- `simulator.md` —— 模拟模式下扮用户的 agent(人设 / 背景知识 / 追问策略)。

格式严格按 `docs/file-formats.md`。AHL 的 parser 会校验;过不了 `ahl review` 会标错,过不了 `ahl run` 的 preflight 会硬退。

## Invariants(不变量)

- **V1 / V2 在 `program.md` 汇合。** V1 是人手写 `program.md`,V2 是你据 `brief.md` 写 `program.md`。从 `program.md` 往后(harnesses / cases / rubric / run / score / compare),两条路完全同构。
- **`run / score / compare` 不区分文件来源。** 你写的文件和人手写的同格式,跑同一套管线。
- **`brief.md` 是 human-owned,不要改它。** 除非用户明确叫你改。
- **`connect.md` 是 human / user-owned,不要改。** 除非用户明确叫你改。
- **`goal.md` 同样不要改。**
- **brief 的「不能牺牲什么」(红线)必须落进 `rubric.md` 的某个维度,或写进 `program.md`。** 这是人审 review 时的重点。

## Checklist before review(起草完跑 `ahl review` 前自查)

- `program.md`:`假设` / `声明`(环境 / 对话模式 / 状态 / 评分 / 运行模式 / 对比方式)/ `留/丢规则` / `喊人规则` 都填了。
- `harnesses/`:至少 V1 + V2;每个版本「这是什么」段写清楚和基线的差异。
- 当 `对比方式: 对基线` 时,**恰好一个**版本标 `基线: 是`(线性迭代不要求基线)。
- `cases/`:每个 case 有 `id`(frontmatter)和 `## 起始输入` 段。
- `rubric.md`:维度齐 + 权重之和 = 1.0(或百分数和 = 100)。
- **brief 的「不能牺牲什么」已经落进 rubric 或 program。**
- 跑 `ahl review <name>` 看 review.md,没有「未起草」即可走 `ahl run`。

## Commands(命令)

```
ahl draft <name>      用户或外层 agent 运行 —— 开一个 authoring workspace。
                      建实验目录 + brief.md 模板 + 空 harnesses/ 和 cases/(scaffold-only)。
                      如果 workspace 还不存在,先运行它;已存在则读 brief.md 接着起草。

(你 author program / harnesses / cases / rubric / simulator ……)

ahl review <name>     出 review.md(宽松:缺什么标「未起草」)。
                      你可以多次跑,看 authoring 进度。
ahl run <name>        preflight 是硬关卡:program / 版本 / case / 基线数
                      任一不过都拦下。
ahl score <name>      按 rubric 给最近一次 run 的对话打分。
ahl compare <name>    把版本分数放一起比,出对比报告。
```

## Cross-platform(跨平台)

version-level connect 的 `## 配置 命令:` 是 shell 直接 exec 的命令。Python agent 解释器名跨平台不一样:

- **Windows**:用 `py`(Python Launcher,Windows 自带)。例:`命令:py support_v1.py`。
- **macOS / Linux**:用 `python3`。例:`命令:python3 support_v1.py`。

跨机器 handoff 时记得改对应解释器,或者脚本加 shebang `#!/usr/bin/env python3` + `chmod +x`,然后 `命令:./support_v1.py` —— 三平台都吃。

## Provenance(来源)

v2-minimal 用**集中式** provenance,统一写在 `review.md` 的「来源」段:

```
- brief.md:human
- program.md:external_agent_drafted
- harnesses/:external_agent_drafted
- cases/:external_agent_drafted
- rubric.md:external_agent_drafted
- simulator.md:external_agent_drafted
```

per-file frontmatter 来源戳留到 v2.5,本期不写。

---

> External coding agent is the Designer.
> AHL is the protocol, validator, reviewer, and runner.
> AHL does not think up the experiment; it makes agent-authored experiments inspectable, runnable, and reproducible.
