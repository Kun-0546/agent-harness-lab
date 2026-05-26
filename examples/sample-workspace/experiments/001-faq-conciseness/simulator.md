# simulator

## 人设
一个普通用户,问 FAQ 类问题。回答收到后想确认数字、想看在情况变化时
agent 怎么调整。

> 这份人设描述的是**接 `--llm` 真模拟器后**的预期行为。本 sample 默认
> 跑 `stub_simulator`(下方说明),桩**不读** persona / 背景知识 / 追问策略,
> 三段对真模拟器才生效。

## 背景知识
对产品 FAQ 主题无先验背景。

## 追问策略
接 `--llm` 真模拟器时:确认关键数字,再追问一次"情况变化"。

**本 sample 默认行为(stub_simulator)**:不读上面三段,固定产 2 句追问、
然后收尾,每个 case 共 3 轮对话:

| 轮 | 谁 | 内容 |
|---|---|---|
| 0 | 用户 | case 的 `## 起始输入`(例:`How do I reset my password?`) |
| 0 | agent | 第 1 次回应 |
| 1 | 用户 | 固定追问 #1:`这个能再具体点吗?给个数。` |
| 1 | agent | 第 2 次回应 |
| 2 | 用户 | 固定追问 #2:`那如果情况变了,你会怎么调整?` |
| 2 | agent | 第 3 次回应 |
| 3 | 用户 | stub 返 `None` → 对话收尾 |

源:`src/agent_harness_lab/simulator.py` 里的 `stub_simulator`
(`_STUB_FOLLOWUPS` 列表)。

要换成由本文件 persona / 追问策略驱动的真模拟器,设
`AHL_SIM_BASE_URL` / `AHL_SIM_MODEL` / `AHL_SIM_API_KEY` 环境变量并跑
`ahl run 001 --llm`(本 sample 不要求,可保持桩模式跑完整 product flow)。
