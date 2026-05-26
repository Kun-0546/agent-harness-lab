# Goal — Make our PM-assistant agent better at clarifying ambiguous goals

> Workspace 级目标,跨多个实验长期有效。
> 单次实验的具体迭代意图在 `experiments/<id>/brief.md`。

## 1. 目标 agent

公司内部的 **PM-assistant agent**(基于 LLM 的 chat 助手),给产品经理
草拟 PRD / spec / one-pager / 沟通邮件用。当前在 Slack bot + 内部
web app 两个 surface 上跑。

## 2. 想改善的行为

用户给模糊目标时,agent **直接动手写文档**,不先澄清。三类典型 case:

1. 用户:"帮我写一份 PRD,关于推荐系统"
   - 现状:agent 直接出 1500 字 PRD 草稿
   - 期望:agent 先问 "推什么内容?给谁推?当前 baseline 是什么?
     这次想优化哪个指标?"
2. 用户:"给我写一封 stakeholder 沟通邮件"
   - 现状:agent 假定一个通用 stakeholder + 通用议题
   - 期望:agent 先问 stakeholder 角色 / 议题 / 期望结果
3. 用户:"做个 launch one-pager"
   - 现状:agent 凑齐 5 个标准 section 直接交
   - 期望:agent 先问 launch 范围 / 受众 / 已知约束 / 风险

## 3. 当前 baseline

V1 = 当前 production system prompt(2026-04 commit `a3f9b2c`)。

## 4. Harness 层假设

- [x] system prompt / instruction —— 主路径
- [ ] workflow / task flow
- [ ] tool configuration
- [ ] memory / retrieval

第一次实验聚焦 prompt 层(在 system prompt 加入 clarify-before-act
约束),tool / memory 等下一轮。

## 5. 成功标准

- 模糊目标 case 上,agent 至少问 2 个澄清问题再动手
- 明确目标 case 上,agent **不**多余澄清(避免另一类回归)
- 用户满意度:对"agent 是否懂我想要什么"的主观评分上升

## 6. 不能牺牲的红线

- 不能因为澄清问题增加,**总响应延迟超 5 秒**
- 不能因为澄清,**用户连问 3 次后还卡在澄清阶段**(无限澄清是反模式)
- 不能出现安全 / 事实性回归
