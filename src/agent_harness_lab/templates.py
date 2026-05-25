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

  Step 2  Choose mode
          决定本轮怎么工作:
          - Manual    你自己设计 harness variants 和实验
          - Co-pilot  外层 coding agent(Claude/Cursor/Codex)据 brief.md 起草
          (Auto mode 是未来模式,依赖 calibration + approval gates,M2+)

  Step 3  Declare runtime
          告诉 AHL 你的 agent 在哪:
          - 本地源码(local_path)     → runtime-sources.md
          - Git repo(git_repo)        → runtime-sources.md
          - 已经在跑的 agent(legacy)  → connect.md

  Step 4  Create experiment
          ahl new <name>     Manual:生成 program/rubric/cases/harnesses/simulator 模板
          ahl draft <name>   Co-pilot:生成 brief.md,交给外层 coding agent 起草

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

BRIEF_TEMPLATE = """# brief — {name}

> 人写的实验意图(V2)。填好后让外层 coding agent(Claude Code / Cursor / Codex)
> 据它起草 program / harnesses / cases / rubric / simulator,完了跑 ahl review。
> AHL 自己不调模型起草。

## 想优化什么
<这个 agent,你想让它哪方面变好>

## 验证什么改动
<这次具体要试的那个改动>

## 最在意什么
<判好坏时你最看重的>

## 不能牺牲什么
<哪些方面无论如何不能退化 —— 红线>

## 怎么比
<对基线 / 线性迭代;拿不准就留空,默认对基线>
"""

