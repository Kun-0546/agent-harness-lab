"""ahl init / new 生成的文件模板。"""

PROGRAM_TEMPLATE = """# 实验 {name} · program

## 假设
<这次实验想验证什么>

## 声明
- 环境:<被测环境是什么 + 取的初始状态;无环境写"无">
- 对话模式:<模拟 / 回放 / 固定>
- 状态:<累积 / 重置>
- 评分:<评分器类型(规则脚本 / LLM Judge / 组合)+ 打分粒度>
- 运行模式:<人评 / 自迭代>
- 对比方式:<对基线 / 线性迭代;多版本怎么比,默认 对基线、可不写>

## 留/丢规则
<一个改动满足什么算"留下",否则回滚;人评模式留空>

## 喊人规则
<coding agent 跑到什么情况停下、交回 PM;人评模式留空>
"""

RUBRIC_TEMPLATE = """# rubric

> 评分维度 + 权重,从实验 goal 推导。权重之和 = 1.0(或写百分数,和 = 100)。

## <维度名,例:战略深度>
权重: <0-1>
<这个维度衡量什么、怎么判高低分>

## <维度名>
权重: <0-1>
<...>
"""

CONNECT_TEMPLATE = """# connect —— 工具怎么接到被测 agent

## 类型
<进程内库 / 外部命令行 / HTTP无状态 / HTTP有状态>

## 配置
<外部命令行:跑 agent 的命令(agent 在 WSL 就写 wsl ...);HTTP:端点 URL;进程内库:可 import 的模块>
"""

GOAL_TEMPLATE = """# Goal — <一句话总目标>

> 这是 workspace 级目标,跨多个实验长期有效。
> 单次实验的具体迭代意图写在 `experiments/<id>/brief.md`。

> 如果你还说不清楚 §2「想改善的行为」,先补 2-3 个真实例子:
> agent 现在哪里做得不好?你希望它下次怎么表现?
> AHL 的实验会围绕这些行为差异来设计。

## 1. 目标 agent

<这个 workspace 优化的是哪个 agent?它的角色、典型用途是什么?>

## 2. 想改善的行为

<具体哪种行为不满意?尽量写成真实 case 类型。

例:
- 用户给模糊目标时,agent 直接动手写文档,不先澄清。
- 给出方案时缺少 trade-off 说明。
- 长对话里忘记前面定过的约束。>

## 3. 当前 baseline

<现在用什么作为对比?
例:v1 prompt、某个 commit、某个 production version、当前人工流程。>

## 4. Harness 层假设

<你认为优先应该改哪一层 harness?可以多选,并写一句为什么。>

- [ ] system prompt / instruction
- [ ] workflow / task flow
- [ ] tool configuration
- [ ] memory / retrieval
- [ ] context packaging
- [ ] output format / schema
- [ ] guardrails / escalation
- [ ] other: ______

为什么这些改动可能改善 §2:
<每个选择写一两句。>

## 5. 成功标准

<这个 workspace 推到什么样算成功?
可以先写方向,正式评分维度会在 rubric.md 里细化。>

## 6. 不能牺牲的红线

<哪些维度不能退化?
例:安全、事实性、延迟、成本、用户体验、guardrail 行为。>
"""


WALKTHROUGH_TEXT = """Agent Harness Lab — 9 步标准产品流程

  Step 1  Define goal
          编辑 goal.md:workspace 级北极星
          - 目标 agent / 想改善的行为 / baseline
          - Harness 层假设(prompt? workflow? tool? memory? ...)
          - 成功标准 / 红线

  Step 2  Choose setup mode
          决定本轮 ahl new 怎么配置实验 (setup mode 只影响 ahl new
          建什么结构,不影响 run/score/compare):
          - copilot (默认)  AI 引导式实验配置:coding agent
                            (Claude/Cursor/Codex) 通过对话维护
                            brief.md / materials/,生成或补全
                            program/rubric/cases/harnesses
          - manual          你手动编辑完整骨架
                            (program/rubric/simulator + cases/ + harnesses/)
          - auto            未来模式,依赖 calibration + approval gates
                            (M2+);--mode auto 当前报 not implemented

  Step 3  Declare runtime boundary and evidence level
          agent 在哪?harness 在哪?2×2 决定 evidence 强度
          (strong / medium / weak)。Local agent + Local harness = strong;
          Cloud agent 默认 weak,除非补 deployment evidence。
          Co-pilot 模式下 coding agent 通过对话按需在 materials/ 下整理
          runtime / harness / cloud evidence。详见 docs/product-walkthrough.md Step 3。

  Step 4  Create experiment
          ahl new <name>                 默认 setup mode=copilot
                                         → brief.md (工作单) + materials/README.md
                                         + cases/ + harnesses/
          ahl new <name> --mode manual   完整骨架
                                         (program/rubric/simulator + cases/ + harnesses/)
          ahl new <name> --mode auto     not implemented (M2+),exit 2,
                                         不创建任何文件

  Step 5  Design harness variants
          experiments/<id>/harnesses/V1.md, V2.md, ... 一个 variant 一份。
          variant 改的是 §4 选定的 harness 层(prompt / workflow / tool / memory ...)。
          每个 variant 声明 runtime_source + Patch:把哪些改动应用到 runtime。

  Step 6  Prepare cases and rubric
          cases/       触发 §2 行为差异的具体 case
          rubric.md    评分维度 + 权重,据 §5 成功标准推导
          simulator.md 模拟模式下扮用户的 agent 人设

  Step 7  Run experiment
          ahl run <id>      AHL 为每个 variant materialize 一份隔离 sandbox:
                              - local_path  copy directory + apply patch
                              - git_repo    git clone + checkout + apply patch
                              - legacy      连接到已运行的 agent
                            然后对每个 case 跑 simulated conversation,记录 transcript。
                            每条 run 写一份 snapshot:source/commit/patch hash,可复现。

  Step 8  Inspect evidence
          ahl score <id>     judge 据 rubric 给每段对话打分
          ahl compare <id>   把 variants 放一起比:总分、每维度 delta、回归点
          results/snapshots/<run_id>/<variant_id>.json  这次跑的实际版本指纹

  Step 9  Decide next iteration
          据证据决定:
          - keep    这版 harness 留下来,作为下一轮 baseline
          - discard 这版丢掉,回到上一版
          - next    根据 compare 看到的问题,设计下一轮 variants

完整说明: docs/product-walkthrough.md
当前模式状态:Manual ✅ Co-pilot v2-minimal ✅ Auto 未来模式
Runtime Materialization M1:local_path ✅ git_repo ✅ docker M2+ remote M2+
"""

SIMULATOR_TEMPLATE = """# simulator —— 模拟模式下扮用户的那个 agent

## 人设
<模拟器扮谁;例:一个 CEO,沟通直接、要数据、被说服前会追问>

## 背景知识
<喂给模拟器的背景材料;它扮的人知道什么(可留空)>

## 追问策略
<怎么追问:盯没答透的点、适时换角度、什么时候收尾>
"""

BRIEF_TEMPLATE = """# Brief — Co-pilot Experiment Setup

> 这是一份**工作单**,给外层 coding agent (Claude Code / Cursor / Codex) 用。
> 你不用一口气填完——coding agent 会通过对话帮你维护这份文档,
> 并据它起草 program / rubric / cases / harnesses。
>
> goal.md 是 workspace 级长期目标;brief.md 是本轮实验的具体意图。
>
> **Setup mode 边界**:本实验跑在 Co-pilot mode (默认)。Manual mode 由你
> 手动写全部文件;Auto mode 暂未实现 (M2+)。详见
> [`docs/copilot-setup.md`](../../docs/copilot-setup.md) §2。
>
> **Coding agent 对 brief.md 的修改规则**:可以**添加**带标签的
> `> [proposal]` / `> [interpretation]` / `> [open question]` 段落,
> **不可**静默改写用户的原始意图。如有疑问,留 `> [open question]` 不
> 要猜。重大改动在 handoff 里报告。

## 想优化什么

<必填。这次实验想让 agent 在哪个具体行为上变好?这一节决定起草方向。
跟 goal.md §2 的关系:这一轮是 goal.md §2 的哪个 subset?

不会写?让 coding agent 据 goal.md §2 提议,你挑一个。>

## 目标行为

<可观察的期望行为。给 2-3 个 case 类型描述:
- 输入 X 时,期望 agent 产出 Y(对比当前的 Z)
- 输入 X' 时,期望 agent 不做 Z'

跟「Cases 要覆盖什么」一节直接挂钩。>

## 当前问题

<baseline (V1) 在「目标行为」case 上具体做错了什么?failure mode 属于哪一类?
- 不澄清 / 过早动手 / 缺 trade-off / 漏前提约束 / 输出格式不规范 / ...

把真实失败例子粘到 materials/target-behavior-examples.md,这里只点名。>

## Runtime 信息

<agent 在哪运行,AHL 怎么接到它?
- runtime 类型:local_path / git_repo / legacy_connect
- 本地还是 cloud
- 是否需要 evidence 文件支撑(指向 materials/<name>-evidence.md)

参考 docs/product-walkthrough.md Step 3 2×2 矩阵决定 evidence 强度。>

## Harness 假设

<这一轮要改 harness 的哪一层(goal.md §4 的子集)?可以多选,但 variant 一次只改一层:
- [ ] system prompt / instruction
- [ ] workflow / task flow
- [ ] tool configuration
- [ ] memory / retrieval
- [ ] context packaging
- [ ] output format / schema
- [ ] guardrails / escalation

为什么这一层最可能改善「目标行为」?一句话说明。>

## Cases 要覆盖什么

<列 2-4 类 case,每类至少 1 个 case 文件。说明为什么这些 case 能把 V1
跟 V2 的差异拉出来 —— 如果所有 case 都让 V1/V2 表现一样,这次实验
没信号。

每个 case 一个文件,放 cases/D-01.md / D-02.md / ...。>

## Rubric 应该如何判断

<2-4 个评分维度(>5 维度 judge 一致性下降),每维给权重提案(总和 1.0),
每维写一句"满分什么样 / 最低分什么样"的口头描述。

coding agent 据这一节起草 rubric.md。>

## Evidence / probe expectations

<目标 evidence level:strong / medium / weak?为什么?
需要哪些 materials/*-evidence.md 文件(runtime / harness / cloud)?
是否在 run 之前跑 `ahl probe <id>`?

evidence 四档怎么判,见 docs/evidence-guide.md。
自填模板见 examples/evidence-examples/。

**不要在 brief.md 里复述 evidence-guide 的内容,只点关键决策。**>

## Files the coding agent may create

<允许 coding agent 起草 / 更新的文件白名单(默认即下面这些):
- experiments/<id>/program.md
- experiments/<id>/rubric.md
- experiments/<id>/simulator.md
- experiments/<id>/cases/*.md
- experiments/<id>/harnesses/*.md
- experiments/<id>/materials/<topic>.md(从粘贴内容 / URL 整理出的新文件)
- runtime-sources.md(workspace 级,仅当不存在时;存在时不动)

需要扩白名单?在这一节加。>

## Files the coding agent should not change

<禁止 coding agent 改的文件(同时是本轮**红线**;coding agent 不可
静默改 / 删):
- goal.md(workspace 级,人 own)
- brief.md(本文件 — coding agent 可加 [proposal]/[interpretation]/
  [open question] 标签段落,不可静默改写原始意图)
- experiments/<id>/results/**(AHL 生成产物)
- experiments/<id>/sandbox/**(AHL 生成产物)
- experiments/<id>/probe-results/**(AHL 生成产物)
- 任何在 materials/locked.md 里列出的文件
- .git/**

继承 goal.md §6 红线;有特殊红线在这写。需要锁更多?在 materials/
locked.md 里加。>

## Acceptance commands

<这一轮 setup 完成后,跑这些命令应该全部 exit 0:
- `ahl review <id>`  —— 结构校验
- `ahl probe <id>`   —— (可选)runtime readiness 检查,Runtime 信息
  涉及 materialized runtime 时建议跑
- `ahl run <id>`     —— materialize sandbox + 跑 cases
- `ahl score <id>`   —— judge 据 rubric 打分
- `ahl compare <id>` —— 出 compare 报告(含 `## Evidence` section)

完整说明:docs/product-walkthrough.md Step 7 / Step 8。>

## Done criteria

<这一轮 setup 算"做完"的可验证标志:
- 上面所有段全填(coding agent 助填的段落用户已 ack)
- 「Files the coding agent may create」列出的文件全在
- materials/locked.md 存在(可为空)
- 「Acceptance commands」全 exit 0
- compare 报告里 `## Evidence` section 的 level 跟「Evidence / probe
  expectations」目标对齐(不达标说明 evidence 路径需补
  materials/*-evidence.md)

`expected-coding-agent-plan.md` 这种交付物可参考
[`examples/copilot-setup-example/`](../../examples/copilot-setup-example/)。>
"""


MATERIALS_README_TEMPLATE = """# materials/

Co-pilot 协作的**参考材料目录**。Coding agent (Claude Code / Cursor /
Codex) 据这里的内容理解 baseline + 期望行为 + 领域背景。

## 1. What materials are for

让 coding agent 起草 program / rubric / cases / harnesses 时,有
*可读的、版本化的*参考材料,而不是靠用户每次粘到对话框里。

## 2. What user should put here

4 类材料(粘贴 / 给本地路径 / 给 URL):
- baseline prompts / config snapshot → `prompts-baseline.md`
- 真实失败 / 不满意例子 → `target-behavior-examples.md`
- agent 需要懂的领域背景 → `domain-knowledge.md`
- 外部 API / 链接摘要 → `references.md` / `api-docs.md`

## 3. Runtime notes

brief.md §4 已声明 runtime 类型(local_path / git_repo /
legacy_connect)。runtime 相关的环境备注、deployment id、私密配置
不便放 brief.md 时,可在这里加 `runtime-notes.md`。Cross-link 见
brief.md §4。

## 4. Example transcripts

把真实 failure 例子按一个 case 一个文件粘进来,命名
`example-<short-name>.md`,推荐结构:1 段背景 + 1 段 user input +
1 段 baseline output。Coding agent 据这些起草 cases/D-*.md。

## 5. Product requirements

本轮实验的特别约束 —— latency budget / cost budget / safety
constraint / 合规约束。Coding agent 起草 rubric / cases 时必须照顾。

## 6. Evidence files

何时需要 `runtime-evidence.md` / `harness-evidence.md` /
`cloud-evidence.md`,见
[`docs/evidence-guide.md`](../../../docs/evidence-guide.md)
+ [`examples/evidence-examples/`](../../../examples/evidence-examples/)
(自填模板)。**不在这里重复 evidence-guide 内容,只指针。**

## 7. Locked files convention

不让 coding agent 改的文件,一行一个列在 `materials/locked.md`:

```
prompts-baseline.md
api-docs.md
```

产品约定,coding agent 自律。AHL 当前**不强制锁定**(无 write-
protect / git hook / patch validation)。

## 8. Coding-agent operational rules

简短列表(完整见
[`docs/copilot-setup.md`](../../../docs/copilot-setup.md)):

- 起草 program / rubric / cases 前,**读全部** `materials/*.md`
- 可新增 `materials/<topic>.md`(从 URL / 粘贴内容整理出来),在
  handoff 里报告新增文件
- **不修改** `materials/locked.md` 列出的任何文件
- **不修改** AHL 生成产物:`results/**` / `sandbox/**` /
  `probe-results/**`
- 不知道时留 `> [open question]` 给用户,**不要猜**
"""

