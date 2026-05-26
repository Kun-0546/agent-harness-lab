# domain-knowledge.md

> PM-assistant 服务的领域背景。Coding agent 据这份理解 PRD 的"完整
> 度"标准 + 哪些澄清问题"高质量"。

## PM 文档的标准 section(rubric "方案质量" 维度的锚点)

完整 PRD 应包含:
- **Problem** — 要解的问题、当前现状、为什么现在做
- **Users** — 目标用户群 + 关键场景
- **Success metrics** — 北极星指标 + supporting metrics + 红线
- **Scope** — in/out of scope 清单
- **Risks** — 已知风险 + mitigation
- (可选)**Open questions** — 未决问题

Coding agent 起草 rubric "方案质量" 维度时,据 5 个必需 section 评分。

## "高质量澄清问题" 的特征(rubric "澄清及时性" 维度的锚点)

高质量澄清问题应:
- 针对 *关键参数缺失*(范围 / 受众 / baseline / 目标指标),不是细节
- 一次问 2-4 个,不一个一个挤牙膏
- 不重复 user 已经给的信息

低质量澄清:问"你的目标是什么"(信息含量 0)、问 "你想要什么时候完成"
(对 PRD 起草不关键)。

## "无限澄清反模式"(红线对应)

agent 连续 2+ 轮还在澄清就触发红线:
- Round 1 用户 "帮我写 PRD" → agent 问 4 个澄清
- Round 2 用户答 → agent 又问 4 个新问题(不起草)
- Round 3 用户答 → agent 还问 ……

正确路径:Round 1 问 ≤4 个高优先级澄清,Round 2 拿到信息就起草。

## PM-assistant 当前用户群

- 中级 PM(3-5 年经验)是主力,80% 流量
- 期望快(<5s)+ 实用(可直接拿去 review)
- 不喜欢 agent 反问太多(更倾向给一份 OK 草稿 + 自己改)
- 但**模糊目标**例子里反复抱怨 "AI 假定了我没想过的东西",所以澄清
  是真实痛点

(注:本 example 是 fictional case,数字示例而非真数据。)
