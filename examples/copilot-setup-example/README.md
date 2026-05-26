# Co-pilot Setup Example

> **Setup-state reference**(不是 runnable end-state)—— 演示一份
> *刚 ahl new 后被用户 + coding agent 填好但还没 run* 的 co-pilot 实验
> 长什么样。

## 这个 example 是什么

它**不是** v0.7
[`sample-workspace`](../sample-workspace/) 的替代品。
sample-workspace 是 *runnable end-state*(跑完整 `probe → run → score
→ compare`,有 `results/` / `sandbox/` / `snapshots/`)。

这个 example 是 *setup-state* —— 用户走完
[`docs/copilot-setup.md`](../../docs/copilot-setup.md) §4 + §5、还没跑
`ahl run` 之前的目录长什么样:

- `goal.md`:workspace 级目标(浓缩版)
- `experiments/01-clarify-questions/brief.md`:**12 节全填好**的工作单
- `experiments/01-clarify-questions/materials/`:用户提供的参考材料
  + coding agent 整理出的新文件
- `experiments/01-clarify-questions/expected-coding-agent-plan.md`:
  coding agent 在 handoff 时给用户看的 3-anchor 计划

## 故意 NOT 包含

- `program.md` / `rubric.md` / `simulator.md`
- `cases/*.md` / `harnesses/*.md`
- `results/` / `probe-results/` / `sandbox/`
- 任何 AHL 生成产物

这些会在 coding agent 真的开工时产生 —— 本 example 演示的是**它们生成
之前**的状态。

## 怎么用

把它当 brief.md 参考样本读。看 12 节填到什么颗粒度算 "good"。看
`expected-coding-agent-plan.md` 怎么写 handoff。

不要 copy-paste 这个 example 当模板使,**用 `ahl new <name>` 生成
新模板**;这个 example 是参考,不是模板。

## Cross-link

- co-pilot 完整指南: [`docs/copilot-setup.md`](../../docs/copilot-setup.md)
- 9 步产品流程: [`docs/product-walkthrough.md`](../../docs/product-walkthrough.md)
- runnable end-state: [`examples/sample-workspace/`](../sample-workspace/)
- evidence 自填模板: [`examples/evidence-examples/`](../evidence-examples/)
