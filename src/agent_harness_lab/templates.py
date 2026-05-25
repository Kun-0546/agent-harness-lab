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

> 这是一份**工作单**,给 coding agent (Claude Code / Cursor / Codex) 用。
> 你不用一口气填完——coding agent 会通过对话帮你维护这份文档,
> 并据它起草 program / rubric / cases / harnesses。
>
> goal.md 是 workspace 级长期目标;brief.md 是本轮实验的具体意图。

## 想优化什么

<必填。这次想让 agent 在哪个具体行为上变好?这决定 coding agent 起草方向。
不会写?让 coding agent 据 goal.md §2 提议,你挑一个。>

## 验证什么改动

<具体改 harness 哪一层 + 改成什么?
例:把 V1 的 system prompt 加入"先澄清后行动"约束。
不写也行,coding agent 会据 goal.md §4 推。>

## 最在意什么

<判好坏时你最看重的维度?
例:澄清能力 > 方案质量 > 约束遵守。
不写也行,coding agent 会据 goal.md §5 推。>

## 不能牺牲什么

<本轮哪些维度不能退化?
默认继承 goal.md §6 红线;有特殊红线在这写。>

## 怎么比

<对基线 / 线性迭代;留空默认对基线。>

## 材料 (可选)

<参考材料放在 materials/ 目录,见 materials/README.md。
- 提供本地文件路径,让 coding agent 复制进去
- 粘贴内容,让 coding agent 整理成 materials/<name>.md
- 锁定不让 coding agent 改的文件:在 materials/locked.md 里列 (产品约定,AHL 不强制)>
"""


MATERIALS_README_TEMPLATE = """# materials/

这个目录给 **coding agent** (Claude Code / Cursor / Codex) 整理本次实验的参考材料。

## 谁写 / 谁读

- **你**:告诉 coding agent 要参考什么(粘贴内容 / 给本地文件路径 / 给链接)
- **coding agent**:把这些整理成结构化的 markdown 文件,放在这个目录下

## 常见内容 (参考,不强制)

- `prompts-baseline.md`        —— 当前 baseline 的 prompts / config snapshot
- `target-behavior-examples.md` —— 真实失败 / 不满意例子
- `domain-knowledge.md`        —— agent 需要懂的领域背景
- `api-docs.md`                —— 相关 API / 接口的关键说明
- `references.md`              —— 外部参考链接和摘要

## 锁定不让 AI 改的文件

把不希望 coding agent 修改的文件名列在 `materials/locked.md`,一行一个:

```
prompts-baseline.md
api-docs.md
```

> 这是一份**产品约定**,coding agent 应按 `locked.md` 自律。
> AHL 当前**不做强制锁定** (写保护 / git hook / patch validation),留 M2+。

## Runtime / Harness Evidence (按需,Co-pilot 主路径)

AHL 比较的是 agent runtime 中**实际生效**的 harness,不是 workspace 静态文件。
用 `connect.md` 接已运行 agent 时,AHL 无法自动 snapshot agent 内部状态;
可能需要 evidence 文件支撑 reproducibility (尤其 cloud agent)。

谁负责创建:

- **Co-pilot 模式**: coding agent 通过对话判断 2×2 情况,向用户追问
  (路径 / 导出 / plugin list / deployment id / session id 等),按需创建。
- **Manual 模式**: 你自己据 2×2 判断 (详见 docs/product-walkthrough.md Step 3)。

按需创建 (不默认存在,放在 materials/ 下):

- `runtime-evidence.md` — agent runtime 的 active state
                          (deployment id / plugin list / config snapshot)
- `harness-evidence.md` — harness 在 runtime 中实际生效的证据
                          (路径 / 文件内容 / debug output)
- `cloud-evidence.md`  — cloud deployment 的可复现快照
                          (console export / session id / active config)

何时需要:

- 用 `runtime-sources.md` (local_path / git_repo) 时通常**不需要**——
  AHL 自动 materialize + snapshot。
- 用 `connect.md` 时通常**需要**,尤其 cloud agent。

> 这是产品约定,AHL 当前**不强制校验** evidence 存在或完整性。
> Auto 模式 (future) 才会强制判断 evidence level + 标记 weak。
"""

