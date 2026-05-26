# Expected coding-agent plan

> Coding agent 在 handoff 时应该交给用户的 plan,使用本仓库约定的
> 3-anchor 轻量 schema。本文件演示一份合格 plan 长什么样。

## Files to create / modify

**Create**(per brief.md §9 whitelist):
- `experiments/01-clarify-questions/program.md` — assumption + declaration
- `experiments/01-clarify-questions/rubric.md` — 4 维度(澄清及时性
  0.35 / 澄清克制 0.20 / 方案质量 0.30 / 响应延迟感知 0.15)
- `experiments/01-clarify-questions/simulator.md` — PM persona,直接
  沟通,缺信息时被追问会补
- `experiments/01-clarify-questions/cases/D-01.md` — 模糊 PRD
- `experiments/01-clarify-questions/cases/D-02.md` — 明确 PRD(反 case)
- `experiments/01-clarify-questions/cases/D-03.md` — 半模糊 PRD
- `experiments/01-clarify-questions/harnesses/V1.md` — baseline(无
  patch,直接绑 runtime_source)
- `experiments/01-clarify-questions/harnesses/V2.md` — patch
  `prompts/system.md` 在 "Always produce a usable first draft" 之前
  插入 "clarify-before-act" rule(具体 diff 在该文件内)

**Modify**(per brief.md §9 + §10):
- `experiments/01-clarify-questions/brief.md` — 仅追加 `[proposal]`
  / `[interpretation]` 段;不静默改原内容
  - §7 末尾 `[open question]` 已留给用户决定 rubric 维度合并方案;
    user 答 "保持合并" 后,在该处加 `[interpretation] user ack 维度
    合并方案`

**Not modify**(per brief.md §10):
- `goal.md`
- `materials/locked.md` 列出的 `prompts-baseline.md`
- `runtime-sources.md`(workspace 级,已存在)
- `results/**` / `sandbox/**` / `probe-results/**`(尚未存在 + AHL 生成)

## Acceptance commands

按 brief.md §11 顺序:

1. `ahl review 01-clarify-questions` → expected exit 0
2. `ahl probe 01-clarify-questions` → expected exit 0(brief.md §4 是
   local_path,probe 必须 pass)
3. `ahl run 01-clarify-questions` → V1 + V2 × 3 cases = 6 transcripts,
   expected exit 0
4. `ahl score 01-clarify-questions` → 据 rubric 4 维度打分,expected
   exit 0
5. `ahl compare 01-clarify-questions` → compare 报告含 `## Evidence`
   section,evidence level 应 = **strong**(local + materialized)

跑完后 handoff 给用户报告:
- 每命令的 exit code
- compare 报告里 V1 vs V2 总分差 + 每维度 delta
- evidence level 是否 = brief.md §8 目标(strong)

## Risks / open questions

- **brief.md §7 的 open question** 已留给用户:无限澄清反模式作为独立
  rubric 维度,还是合并到"响应延迟感知"。当前假定合并;user ack 后
  确认。如果 user 选独立维度,rubric 重新分配权重 → cases / scoring 重跑。
- **D-02 反 case 检测难点**:judge 区分 "agent 不澄清" 是 "正确判断"
  还是 "懒得问"。在 rubric "澄清克制" 维度的说明里加 *明确 case 上
  不澄清 = 加分;模糊 case 上不澄清 = 扣分*。
- **延迟维度的可观测性**:本实验 simulator 模拟用户,没有真实 LLM
  调用计时。"响应延迟感知" 这一维 judge 只能 proxy 看 "agent 是否在
  ≤2 轮内开始起草",不能测真实 latency。在 rubric 说明里写清。
- **Evidence level 风险**:brief.md §8 目标 strong,需要 sandbox
  materialize 成功(V2 patch 写入 sandbox)。如 probe 报 fail,先修
  patch 再 run。
