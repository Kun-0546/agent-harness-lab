# target-behavior-examples.md

> 真实 failure transcripts(脱敏)+ 期望行为对比。Coding agent 据这些
> 起草 `cases/D-01.md / D-02.md / D-03.md`。

## Transcript 1 — 模糊 PRD(D-01 case 原型)

**User**:帮我写一份 PRD,关于推荐系统。

**V1 (baseline) 输出**:
```
# 推荐系统 PRD

## Problem
当前用户在主 feed 上的 engagement 表现不佳...

(1500 字 PRD 草稿,假定一个通用推荐场景)
```

**期望行为(V2 目标)**:
```
你这个推荐系统是给什么场景的?在动手起草之前我先想确认 4 件事:

1. 推什么内容?(视频 / 商品 / 帖子 / 其它)
2. 给谁推?(用户画像 + 当前活跃度)
3. 当前的 baseline 推荐策略是什么?
4. 这次主要想优化什么指标?(CTR / 留存 / 时长 / 多样性)

回答完后我可以起草 PRD 框架。
```

## Transcript 2 — 明确 PRD(D-02 case 原型,反 case)

**User**:帮我写一份针对 18-25 岁北美用户的短视频 feed 推荐系统 PRD,
当前 baseline 是基于 ALS 的协同过滤(D7 留存 32%),目标提升 D7 留存
≥3pp。

**V1 (baseline) 输出**:正常起草 PRD(行为正确)。

**期望行为(V2 不能回归)**:同上 —— **不**额外澄清,直接起草 PRD。
这是反 case:V2 在明确目标上**不能**加澄清,否则就是"为澄清而澄清"的
回归。

## Transcript 3 — 半模糊 PRD(D-03 case 原型)

**User**:帮我写一份 PRD,关于通知系统。我们做 enterprise SaaS,
notifications 用来通知协作事件(评论 / @mention / 任务分配)。

**V1 (baseline) 输出**:直接起草 PRD,假定通用 enterprise SaaS
notification 场景。

**期望行为(V2 目标)**:
```
背景我懂了 —— enterprise SaaS 的协作 notifications。在起草之前我想
确认 1 件事:

这次想优化 notification 的哪一面?(送达率 / 用户响应率 / 降低
通知疲劳 / 渠道路由 / 其它)

明确这点我可以聚焦 PRD 的 metrics 段。
```

(只问 1 个高优先级问题,因为背景已经给了 50%。)

## 三类 case 的 V1/V2 期望差异(rubric 锚点)

| Case | V1 baseline | V2 目标 | rubric 拉差异点 |
|---|---|---|---|
| D-01 模糊 | 直接起草 | 问 ≥2 澄清 | 澄清及时性 |
| D-02 明确 | 直接起草 | 直接起草 | 澄清克制(V2 不回归) |
| D-03 半模糊 | 直接起草 | 问 1 个澄清 | 澄清及时性 + 克制 |
