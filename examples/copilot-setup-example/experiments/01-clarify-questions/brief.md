# Brief — Co-pilot Experiment Setup

> 这是一份**工作单**,给外层 coding agent (Claude Code / Cursor / Codex) 用。
> 你不用一口气填完——coding agent 会通过对话帮你维护这份文档,
> 并据它起草 program / rubric / cases / harnesses。
>
> goal.md 是 workspace 级长期目标;brief.md 是本轮实验的具体意图。
>
> **Setup mode 边界**:本实验跑在 Co-pilot mode (默认)。Manual mode 由你
> 手动写全部文件;Auto mode 暂未实现 (M2+)。详见
> [`docs/copilot-setup.md`](../../../../../docs/copilot-setup.md) §2。
>
> **Coding agent 对 brief.md 的修改规则**:可以**添加**带标签的
> `> [proposal]` / `> [interpretation]` / `> [open question]` 段落,
> **不可**静默改写用户的原始意图。如有疑问,留 `> [open question]` 不
> 要猜。重大改动在 handoff 里报告。

## 想优化什么

让 PM-assistant 在收到模糊目标时**先澄清,再动手**。

跟 goal.md §2 的关系:这是 §2 case-1 的 subset(模糊 PRD 请求),
case-2 / case-3 留后续实验。先把 prompt 层的 clarify-before-act 约束
跑通,再外扩。

> [interpretation] "先澄清再动手"= agent 在 user 给的目标里检测到
> "缺关键参数"(范围 / 受众 / 当前 baseline / 期望指标),先问 ≥2 个
> 澄清问题,user 回应后再起草。

## 目标行为

3 类 case:

- **C-1 (模糊 PRD)**: 用户 "帮我写一份 PRD,关于推荐系统" → agent
  先问 ≥2 个澄清问题(推什么 / 给谁 / baseline / 目标指标),user 回
  应后再写 PRD。
- **C-2 (明确 PRD)**: 用户 "帮我写一份针对 18-25 岁北美用户的短视频
  feed 推荐系统 PRD,目标提升 D7 retention" → agent **不**多余澄清,
  直接起草。
- **C-3 (半模糊)**: 用户 "帮我写一份 PRD,关于通知系统" + 一段背景 →
  agent 据背景判断是否需要补问;问的话 ≤1 个高优先级问题。

## 当前问题

V1 baseline 三类 case 都直接出文档。failure mode = **不分情境的过早
动手**。真实失败例子在
[`materials/target-behavior-examples.md`](materials/target-behavior-examples.md)。

## Runtime 信息

- runtime_source 类型:**local_path** —— PM-assistant 跑在本地仓库
  `<private-project>/`,有完整源码可 patch
- evidence 路径:[`materials/runtime-notes.md`](materials/runtime-notes.md)
  记本地 runtime 的额外配置;不需要 cloud-evidence 文件(无 cloud
  deployment)

预期 evidence level:**strong**(local + materialized)。

## Harness 假设

- [x] **system prompt / instruction** —— 加 "clarify-before-act"
  rule + 一段 example
- [ ] workflow
- [ ] tool config
- [ ] memory

一次只改 prompt 一层,V1=baseline prompt,V2=baseline + clarify
constraint。

为什么 prompt 层最可能改善 §2 行为:当前 baseline 不澄清的根因是
prompt 没说 "ambiguous goal → ask first";加进去成本低、可解释、易回
滚。

## Cases 要覆盖什么

3 类,每类 1 个 case(共 3 case):

- **D-01 模糊 PRD**(对应 C-1):应触发澄清
- **D-02 明确 PRD**(对应 C-2):应**不**澄清,直接出 PRD —— 保证 V2
  不在明确目标 case 上回归
- **D-03 半模糊 PRD**(对应 C-3):agent 判断是否澄清

cases 必须能拉出 V1/V2 差异:V1 三个 case 都直接出文档;V2 应该在
D-01 / D-03 上澄清,在 D-02 上不澄清。

## Rubric 应该如何判断

4 维度(总和 1.0):

- **澄清及时性** (0.35):是否在 ambiguous 目标上问澄清问题
  - 满分:问 ≥2 个高质量问题(覆盖范围/受众/指标)
  - 零分:0 澄清直接动手
- **澄清克制** (0.20):明确目标 case 上**不**多余澄清
  - 满分:D-02 上直接起草,不问额外问题
  - 零分:D-02 上还问 1+ 不必要的问题
- **方案质量** (0.30):最终文档的 PRD 完整度 + 准确度
  - 满分:覆盖 problem / users / metrics / scope / risks
  - 零分:缺关键 section
- **响应延迟感知** (0.15):澄清问题不无限循环
  - 满分:user 答完一轮后就开始起草
  - 零分:3+ 轮还没动手

> [open question] §6 红线提到"无限澄清是反模式",这条要不要作为独立
> rubric 维度,还是合并到"延迟感知"?当前合并方案够吗?

## Evidence / probe expectations

- 目标 evidence level:**strong**
- 需要的 materials/*-evidence.md:**无**(local + materialized 路径
  通常不需要 supplied evidence)
- 在 `ahl run` 前跑 `ahl probe`:**是**(确认 V2 prompt 已写入
  sandbox)

evidence 4 档判断规则见
[`docs/evidence-guide.md`](../../../../../docs/evidence-guide.md)。

## Files the coding agent may create

允许创建 / 更新:
- `experiments/01-clarify-questions/program.md`
- `experiments/01-clarify-questions/rubric.md`
- `experiments/01-clarify-questions/simulator.md`
- `experiments/01-clarify-questions/cases/D-01.md / D-02.md / D-03.md`
- `experiments/01-clarify-questions/harnesses/V1.md / V2.md`
- 可在 `materials/` 下新增 `<topic>.md`(整理出的新参考材料);
  必须在 handoff 里报告新增文件

`runtime-sources.md` workspace 级已存在,**不动**。

## Files the coding agent should not change

- `goal.md`(workspace 级,人 own)
- `brief.md` 本文件 — 可加 `[proposal]`/`[interpretation]`/
  `[open question]` 标签段,**不可静默改原内容**
- `experiments/01-clarify-questions/results/**`
- `experiments/01-clarify-questions/sandbox/**`
- `experiments/01-clarify-questions/probe-results/**`
- `materials/locked.md` 列出的文件(即 `prompts-baseline.md`)
- `.git/**`

## Acceptance commands

setup 完成后,这些命令应全部 exit 0:

- `ahl review 01-clarify-questions`  —— 结构校验
- `ahl probe 01-clarify-questions`   —— runtime readiness(§4 是
  local_path,需要)
- `ahl run 01-clarify-questions`     —— V1 + V2 × 3 cases
- `ahl score 01-clarify-questions`   —— judge 据 4 维度打分
- `ahl compare 01-clarify-questions` —— 出 compare 报告含
  `## Evidence` section

## Done criteria

- §1-§8 全填(`[proposal]` / `[interpretation]` 段用户已 ack;
  §7 的 `[open question]` 用户给答案后此节再 ack)
- §9 列出的 5 类文件全在(program / rubric / simulator + 3 cases +
  2 harnesses)
- `materials/locked.md` 存在(本例已含 `prompts-baseline.md`)
- §11 acceptance commands 全 exit 0
- compare 报告 `## Evidence` section 显示 level=**strong**(§8 目标
  对齐);若 medium 则需补 materials/runtime-evidence.md

参考交付物:[`expected-coding-agent-plan.md`](expected-coding-agent-plan.md)。
