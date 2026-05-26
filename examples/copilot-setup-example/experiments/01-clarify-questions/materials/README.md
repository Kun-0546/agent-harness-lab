# materials/

Co-pilot 协作的**参考材料目录**。Coding agent (Claude Code / Cursor /
Codex) 据这里的内容理解 baseline + 期望行为 + 领域背景。

## 1. What materials are for

让 coding agent 起草 program / rubric / cases / harnesses 时,有
*可读的、版本化的*参考材料,而不是靠用户每次粘到对话框里。

## 2. What user should put here

4 类材料(本 example 包含其中 3 类):
- baseline prompts / config snapshot → `prompts-baseline.md` ✓
- 真实失败 / 不满意例子 → `target-behavior-examples.md` ✓
- agent 需要懂的领域背景 → `domain-knowledge.md` ✓
- 外部 API / 链接摘要 → 本例未需要

## 3. Runtime notes

brief.md §4 声明 runtime=local_path(`<private-project>/`)。无 cloud
deployment,无需 cloud-evidence。本目录无额外 runtime-notes.md(写到
brief.md §4 已足够)。

## 4. Example transcripts

真实失败例子在 `target-behavior-examples.md`,3 个 transcripts
(D-01 / D-02 / D-03 对应类型),用作 cases/D-*.md 起草输入。

## 5. Product requirements

本轮特别约束:
- 延迟红线:agent 总响应时间不超过 5s
- 行为红线:不出现"无限澄清"(>2 轮还没动手)
- 安全 / 事实性不能回归

均来自 goal.md §6,coding agent 起草 rubric 时要照顾。

## 6. Evidence files

本例 evidence 路径:**runtime=local_path + materialized**,通常 evidence
level=strong,**不需要** `materials/*-evidence.md`。

如改为 cloud deployment,需补 `cloud-evidence.md`(模板见
[`examples/evidence-examples/cloud-evidence.md`](../../../../evidence-examples/cloud-evidence.md))。
不重复 evidence-guide 内容,详见
[`docs/evidence-guide.md`](../../../../../docs/evidence-guide.md)。

## 7. Locked files convention

`materials/locked.md` 列出不让 coding agent 改的文件,一行一个。本例:

```
prompts-baseline.md
```

prompts-baseline.md 是 baseline reference,不应被 coding agent 改写;
V2 改动通过 `harnesses/V2.md` 的 patch 段表达。

## 8. Coding-agent operational rules

简短列表(完整见
[`docs/copilot-setup.md`](../../../../../docs/copilot-setup.md) §5):

- 起草 program / rubric / cases 前,**读全部** `materials/*.md`
- 可新增 `materials/<topic>.md`(从 URL / 粘贴内容整理出来),在
  handoff 里报告新增文件
- **不**修改 `locked.md` 列出的任何文件(本例:`prompts-baseline.md`)
- **不**修改 `results/**` / `sandbox/**` / `probe-results/**`
- 不知道时留 `> [open question]` 给用户,**不要猜**
