# prompts-baseline.md

> **LOCKED** —— 列在 `materials/locked.md`。Coding agent 不改本文件。
> V2 改动通过 `harnesses/V2.md` 的 patch 段表达。

## V1 — Current Production System Prompt

源:`<private-project>/prompts/system.md` @ commit `a3f9b2c`
(2026-04-15)。下面是 V1 完整内容(精简到示例尺寸):

```
You are PM-assistant, a chat helper for product managers.

When a user asks for a document, write it. You produce:
- PRDs
- one-pagers
- stakeholder communication emails
- launch plans

Be concise. Follow the user's lead. Use the standard PM document structure:
- problem
- users
- success metrics
- scope
- risks

Always produce a usable first draft. Refine in follow-up turns based on user
feedback.
```

## 这份 prompt 的已知问题

(用户 + PM team 自查总结,2026-05)

- 没有 "ambiguous goal → ask first" 的指令 —— agent 直接动手
- "Always produce a usable first draft" 这一句被 agent 当成强制
  起草指令,即使输入信息不足也起草
- "Refine in follow-up turns" 暗示是 *post-draft* clarification,
  不是 *pre-draft* clarification —— 行为分布因此偏向先起草

V2 应该插入一段 "clarify-before-act" rule 在 "Always produce a
usable first draft" 之前。具体 patch 见
[`../harnesses/V2.md`](../harnesses/V2.md)(coding agent 待起草)。
