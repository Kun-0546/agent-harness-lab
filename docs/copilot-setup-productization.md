# Co-pilot Setup Productization · v0.9 Spec

> 这份 spec 定义 Agent Harness Lab 的 v0.9 **Co-pilot Setup Productization
> MVP** —— 在 v0.8 把 evidence 链做厚 + 给文档加上 drift 防护的基础上,
> 把 **co-pilot setup mode** 从一个轻量目录脚手架升级成一份真正可用的
> human + coding-agent 工作流。**docs + templates + tests + 一个轻量
> example,zero src behavior change(除 templates.py 模板字符串)、
> no new CLI command、no contract change**。
>
> Status: target v0.9.0,branch `v0.9.0-planning` (local-only,
> unpushed)。**spec lock-in only —— 代码尚未实现**。
> Date: 2026-05-26 (immediately after v0.8.0 ship)。
> Direction (per Kun): "Co-pilot Setup Productization MVP" —— **不是**
> Auto mode、**不是** public launch、**不是** registry、**不是** cloud
> attestation、**不是** package inspect/validate、**不是** probe-snapshot
> binding。这些全部 deferred 到 v0.10+。

---

## 1. Purpose

v0.7 / v0.8 把 AHL 的"完整产品流"+"evidence 解读"两条线立起来:用户能
跑完一份端到端 sample workspace,能读懂 compare 报告里 evidence level 是
什么意思,能自己手填 `materials/*-evidence.md`。

但**新用户的真实入口不是 sample workspace,而是 `ahl init` →
`ahl walkthrough` → `ahl new <name>`**。`ahl new` 默认 `--mode copilot`
建出来的东西是:

```
experiments/01-<name>/
  brief.md              # 6 节,每节一句"在这里填"
  materials/README.md   # 把"协作说明"+"evidence 说明"混在一起的 50 行
  cases/                # 空目录
  harnesses/            # 空目录
```

这是一份**目录脚手架**,**不是**一份让 coding agent (Claude Code /
Cursor / Codex) 能照着干活的"工作单"。结果:

- coding agent 拿到 brief.md 不知道用户究竟想验证什么,只能反复追问
- 用户不知道 brief 该写到多详,什么才算"填好了"
- 没有"哪些文件 agent 可以建 / 哪些不能动"的规则
- 没有"跑完算完了吗"的 done criteria
- 没有一份给 coding agent 看的现代化指南(`agent-authoring-guide.md`
  是 v0.2.0 历史档,banner-tagged HISTORICAL)
- 没有一份示例 brief.md 让用户参考"填完长什么样"

**v0.9 修这件事**:把 co-pilot setup mode 的**模板内容 + 配套指南文档 +
示例 + drift 防护**一次性补齐,让新用户走 default 路径就能产出一份让
coding agent 能直接开工的实验包。

---

## 2. Product problem

具象 friction list (来自读 `templates.py` + `cli.py:cmd_new` + 现有
co-pilot docs):

- 用户跑 `ahl new my-experiment` 打开 `brief.md` 看到 6 个空槽位
  (想优化什么 / 验证什么改动 / 最在意什么 / 不能牺牲什么 / 怎么比 /
  材料) —— **不知道这些槽位填到多详才够 coding agent 用**。
- 用户问 coding agent "据 brief 起草",coding agent 没有 runtime
  信息、没有 harness 层假设、没有 case 覆盖意图、没有 acceptance
  commands —— **必须反复回问**。
- 用户看不到任何 "files coding agent may create" / "files coding
  agent should not change" 的边界声明,只能靠口头约定。
- `materials/README.md` 同时是"什么是 co-pilot 协作"+"什么时候要写
  evidence 文件"+"怎么 lock 文件",**三件事混在一起**,用户读完不
  知道目录该装什么。
- 没有"setup 流程长什么样"的端到端示例:v0.7 sample workspace 是
  *end-state* (完整跑完的实验),v0.8 evidence-examples 是 *evidence
  artifacts* 模板,**没有 setup-state 示例**(brief.md 填完 +
  materials/ 整理好 + coding-agent output plan)。
- `docs/agent-authoring-guide.md` 是 v0.2.0 时代写的,banner 标
  HISTORICAL,**让今天的 coding agent 去读这份历史文档不合适**;但
  AHL 当前没有现代化替代。
- README 与 walkthrough Step 2 在表格里描述了 co-pilot mode 是什么,
  但**没有链接到任何"怎么驱动 co-pilot 模式"的指南** —— 后面就断了。
- 没有任何 drift 测试守住 `BRIEF_TEMPLATE` / `MATERIALS_README_TEMPLATE`
  的 section 锚点 —— 任何 PR 都可能默默改掉 template 不被测试 catch。

v0.9 目标就是消掉这 8 类 friction。

---

## 3. Why v0.9 follows v0.8

v0.8 的工作模式 ("docs + reference templates + drift tests + 用户解读
guide") 用 evidence 这条线验证过了:**6 节 evidence-guide + 3 份
evidence-examples + 14 个 drift detectors + zero contract change** 顺
利落地 (465 → 479 tests, 默认 + strict 双模式 passing)。

v0.9 把同一套工作模式套到 co-pilot setup 这条线:

```
v0.7 完成 product flow (sample workspace + e2e tests)
v0.8 完成 evidence 解读 (evidence-guide + evidence-examples + drift)
v0.9 完成 co-pilot setup 解读 (copilot-guide + copilot-example + drift)
                                                                  ↑
                                              这条线之前一直缺这一块
```

v0.7 落 sample workspace 后,用户首次接触 AHL 的体验是:**README →
walkthrough → ahl init → ahl walkthrough → ahl new (默认 copilot) →
然后呢?** v0.7 的答案是"看 brief.md 模板提示填一下"。v0.8 没改这一段
(v0.8 redline 不动 templates)。v0.9 把这一段补完。

**为什么不能再 defer 一档**:co-pilot 是 `ahl new` 的**默认 mode**。
manual 是次选,auto 还没实现。Default 路径上的体验是产品体验的下限,
不补这一块就把"AHL 是个能用的产品"这件事一直锁在 sample workspace
那条 manual-完成 路径上,新用户走 default 路径会感觉"目录建好了但接
下来 AHL 帮不了我什么"。

---

## 4. Co-pilot mode definition

明确写下 co-pilot mode **是什么 / 不是什么**:

### Co-pilot mode 是

- 一份**目录结构 + 模板文件**,由 `ahl new <name> --mode copilot` (或省略
  `--mode`) 创建
- 一份**工作单**(`brief.md`) + 一份**协作目录**(`materials/`),
  用户和外层 coding agent (Claude Code / Cursor / Codex 等) 在这两份
  文件上协作
- 一份**给 coding agent 看的操作指南**(v0.9 新增
  `docs/coding-agent-guide.md` 或合并到 setup guide),告诉 coding
  agent 读什么、改什么、不改什么、什么时候跑哪个 `ahl` 命令
- **协作的产物**:`program.md / rubric.md / simulator.md / cases/ /
  harnesses/` 这些文件由 coding agent 据 `brief.md + materials/` 起草
  或更新,**人类 review 后接受**

### Co-pilot mode **不是**

- **不是 AHL 自动调 coding agent**。AHL 不发 API 请求、不 invoke
  Claude / Cursor / Codex、不集成 MCP、不 ferry messages 给 LLM。
  Coding agent 是外层工具,user 在外层工具里读 brief.md 然后 emit
  文件,AHL 只负责读这些文件。
- **不是单一目录的运行时配置**。Setup mode 只影响 `ahl new` 建什么
  结构,**不**影响 `ahl run / score / compare / probe / review` 的
  行为。这一原则跟 v0.3.1 / v0.7 / v0.8 一致。
- **不是 Auto mode 的预览**。Co-pilot mode 没有 approval gates、没有
  budget rules、没有 escalation 规则、没有 calibration sub-system。
  Auto 是未来另一档,v0.9 不沾。

---

## 5. Manual vs Co-pilot vs Auto boundary

```
                  Manual              Co-pilot                 Auto (future)
─────────────────────────────────────────────────────────────────────────────
ahl new --mode    manual              copilot (default)        auto (exit 2)
creates           program.md          brief.md                 (nothing)
                  rubric.md           materials/README.md
                  simulator.md        cases/  (empty)
                  cases/  (empty)     harnesses/  (empty)
                  harnesses/ (empty)

primary           user writes         coding agent drafts;     AHL orchestrates
authoring         everything by       user reviews + acks      iteration loop
                  hand                via brief / materials    under budget +
                                                                approval gates

AHL's job         scaffold + run +    scaffold + workflow      orchestrate +
                  score + compare     pieces + run + score     calibrate +
                                      + compare                escalate +
                                                                approval gates

coding-agent      none required       expected (Claude Code,   AHL drives the
involvement                           Cursor, Codex, etc.)     loop; user is
                                      called by user           on-call

evidence path     user fills          coding agent fills       AHL auto-judges
                  materials/*-        materials/*-evidence.md  evidence + asks
                  evidence.md         after dialogue           user if weak

current status    ✅ shipped          ✅ shipped, but the      ❌ not
                  (v0.3.1+)           templates / guide are    implemented;
                                      what v0.9 finishes        --mode auto
                                                                exits 2 with
                                                                "M2+"
                                                                message
```

**核心边界规则**:

1. 三种 mode 共享同一套 `run / score / compare / probe / review` 行为
   ——AHL runtime 不识别 mode、不读 `.mode` 文件、不查 program.md
   frontmatter mode 字段(没有)。
2. Co-pilot mode **不**自动调 LLM。它只产文件、读文件、跑 `ahl`
   子命令。
3. 用户可以**自由切换**:同一 workspace 下,某个实验可以是 manual,
   下一个可以是 copilot,再下一个还是 copilot —— 互不影响。
4. Auto **不在 v0.9 实装**;`--mode auto` 依然 exit 2,但 error
   message 应该指向 v0.9 写的 copilot guide 让用户先用 copilot。

---

## 6. Non-goals (redlines, consolidated)

v0.9 explicitly **does not**:

- **NOT** flip repo visibility — repo stays **PRIVATE**.
- **NOT** publish to PyPI.
- **NOT** prepare public announcement / blog post / social.
- **NOT** add any new CLI command (the 14 already shipped are the
  cap: `init / walkthrough / connect / new / show / cases / rubric /
  simulator / harnesses / run / score / compare / review / probe`).
- **NOT** implement Auto mode / autonomous iteration / approval
  gates / calibration sub-system.
- **NOT** invoke coding agents automatically — AHL stays a file-
  oriented protocol, no LLM ferry, no API call.
- **NOT** integrate MCP / Claude Desktop / Cursor Composer / etc.
- **NOT** add a registry / package distribution / `ahl package
  publish`.
- **NOT** add cloud attestation API — evidence files remain honor-
  system.
- **NOT** add new runtime source types (no docker_image, no
  remote_api, no dev_agent).
- **NOT** change runtime materialization contract.
- **NOT** change harness package install contract.
- **NOT** change runtime probe contract.
- **NOT** change v0.4 evidence inference rules.
- **NOT** change snapshot schema.
- **NOT** change scoring / comparator math.
- **NOT** delete or rewrite v0.7 `examples/sample-workspace/`.
- **NOT** remove or weaken manual mode.
- **NOT** make co-pilot mode "heavy" or "magical" — no hidden
  orchestration, no implicit LLM call.
- **NOT** delete `docs/agent-authoring-guide.md` (HISTORICAL banner
  stays; cross-link will note it's superseded by v0.9 guide).

---

## 7. Desired user workflow

After v0.9 ships, a new user's first 30 minutes look like this:

```
1. clone repo  →  read README §1-§3 (what is AHL, what is harness)
                  README §4 mentions co-pilot mode + links to
                  docs/copilot-setup.md (or coding-agent-guide.md)
                  the user does NOT need to read that yet

2. ahl init                       # writes goal.md template
   ahl walkthrough                # prints 9 steps in one screen

3. fill goal.md (workspace-level, multi-experiment)

4. ahl new clarify-questions      # default --mode copilot
                                  # output:
                                  #   experiments/01-clarify-questions/
                                  #     brief.md  (12 sections)
                                  #     materials/README.md  (8 sections)
                                  #     cases/  harnesses/

5. user reads brief.md.  Sections are concrete enough that user can
   either fill them by hand OR paste the whole brief into Claude
   Code / Cursor / Codex and say "help me fill this in based on
   goal.md".

6. coding agent reads brief.md + goal.md + (whatever user put in
   materials/), reads docs/coding-agent-guide.md (or the merged
   setup-guide), and drafts:
     program.md
     rubric.md
     simulator.md
     cases/D-01.md, D-02.md, ...
     harnesses/V1.md, V2.md
   (Coding agent does NOT touch results/ if it exists; does NOT
   modify any file listed in materials/locked.md.)

7. user reviews drafted files.  Reads docs/coding-agent-guide.md
   §Acceptance to confirm "done criteria" are satisfied.

8. ahl review clarify-questions   # validates structure, no LLM
   ahl probe clarify-questions    # optional, runtime readiness
   ahl run clarify-questions      # materialize sandboxes + run
   ahl score clarify-questions
   ahl compare clarify-questions
```

The two **new artifacts** in this flow vs. v0.8:

- (a) the user has a brief.md that **says what to fill in**, including
  acceptance commands and done criteria
- (b) the coding agent has a guide that **says what to do/not-do**,
  so it doesn't need to be told via prompt every time

The same `ahl` CLI surface (14 commands) drives everything.

---

## 8. `brief.md` template design

Replace current 6-section `BRIEF_TEMPLATE` with a 12-section template.
Each section has a **heading**, a **1-line purpose**, **2-4 prompts**
of "what goes here", and (where useful) **1 short worked example**.

### 12 sections (in order)

1. **想优化什么**  · 这一轮要在哪个具体行为上让 agent 变好。
   Prompts:agent 现在的哪个动作不够好?改完应该看起来怎么样?
   跟 goal.md §2 是什么关系(这轮是哪个 subset)?
2. **目标行为**  · 期望行为的可观察描述。
   Prompts:输入是什么时,期望 agent 产出什么?给 2-3 个 case 类型描述。
3. **当前问题**  · baseline 当前在 §2 case 上做错了什么。
   Prompts:V1 (baseline) 现在的产出 vs. 期望产出?failure mode 是哪一类?
4. **Runtime 信息**  · agent 在哪里运行,AHL 怎么接到它。
   Prompts:local_path / git_repo / legacy_connect?cloud or local?
   是否有 evidence 路径(如有,指向 materials/<file>.md)?
5. **Harness 假设**  · 这轮要改的是哪一层 (goal.md §4 子集)。
   Prompts:system prompt / workflow / tool config / memory /
   context packaging / output schema / guardrails 中的哪几层?
   为什么这一层最可能改善 §2 行为?
6. **Cases 要覆盖什么**  · 哪些 case 类型必须出现在 cases/。
   Prompts:列 2-4 类型;每类型至少 1 个 case;说明为什么这些 case 能
   把 V1 跟 V2 拉出差异。
7. **Rubric 应该如何判断**  · 评分维度 + 怎么算高 / 低分。
   Prompts:2-4 维度 (>5 维 judge 一致性下降);每维权重提案;
   每维"满分什么样 / 最低分什么样"的口头描述。
8. **Evidence / probe expectations**  · 这轮的 evidence level 目标
   是什么,需要什么 evidence 文件 / probe。
   Prompts:目标 evidence level (strong / medium / weak)?为什么?
   需要哪些 `materials/*-evidence.md`?是否跑 `ahl probe`?
   Cross-link 到 `docs/evidence-guide.md`。
9. **Files the coding agent may create**  · 明确白名单。
   Prompts:`program.md` / `rubric.md` / `simulator.md` /
   `cases/*.md` / `harnesses/*.md` / `runtime-sources.md`
   (workspace 级,仅当不存在);允许在 materials/ 下增删自己整理出来
   的文件(`prompts-baseline.md` / `target-behavior-examples.md` /
   `domain-knowledge.md` 等)。
10. **Files the coding agent should not change**  · 明确黑名单。
    Prompts:`goal.md` (workspace 级,人 own);`brief.md`
    (work item — coding agent **可以建议改**但**不直接 mutate**);
    `results/**`,`sandbox/**` (生成产物);`materials/locked.md`
    列出的所有文件;`.git/**`。
11. **Acceptance commands**  · 跑完哪些命令才算这轮 setup 完成。
    Prompts:`ahl review <id>` 必须 PASS;`ahl probe <id>` (可选,
    如果 §4 涉及 materialized runtime);`ahl run <id>` 必须 exit 0;
    `ahl score <id>` + `ahl compare <id>` 必须出非空报告。
12. **Done criteria**  · 这轮 setup 算"做完"的可验证标志。
    Prompts:brief.md §1-§7 全填(coding agent 助填后用户 ack);
    files (§9) 全在;`materials/locked.md` 存在(可为空);§11
    所有命令 PASS;compare 报告里 `## Evidence` section 跟 §8
    目标 evidence level 对齐。

### 长度预算

整份 brief.md 模板 **≤200 lines**,每节平均 ~15 行。Acceptance test
(§13) 检测总行数。

### 例

模板每节末尾可加 **1 行 "示例:" 行**,只展示 1 个浓缩示例。**不**
塞 placeholder 文字,让用户和 coding agent 自由填。

### 顶部 preamble

模板顶部保留现有 preamble (goal.md vs brief.md 的关系),加一句:
"读完这份模板再开始填:`docs/copilot-setup.md` (或
`coding-agent-guide.md`,见 §10)。"

---

## 9. `materials/README.md` template design

Replace current ~50-line mixed-purpose template with 8-section
template. 每节短:**≤8 行** 包括标题。

### 8 sections (in order)

1. **What materials are for** · 一句话:co-pilot 协作的参考材料目录,
   coding agent 据这里的内容理解 baseline + 期望行为 + 领域背景。
2. **What user should put here** · 用户可以扔进来的 4 类材料:
   baseline prompts / failure example transcripts / domain references /
   external API docs。Prompts:粘贴 / 给本地路径 / 给 URL。
3. **Runtime notes** · 如果 §4 brief.md 已经声明 runtime 信息,
   是否需要在 materials/ 加 runtime 备注(如 cloud deployment id 不
   方便放进 brief.md 的)?Cross-link 到 brief.md §4。
4. **Example transcripts** · 把真实 failure 例子粘进来的格式约定
   (一个 case 一个文件,`example-<short-name>.md`,1 段背景 + 1 段
   user input + 1 段 baseline output)。
5. **Product requirements** · 用户要表达"这次实验有什么特别约束"的
   地方(如 latency budget / cost budget / safety constraint),
   coding agent 起草 rubric / cases 时必须照顾。
6. **Evidence files** · 何时需要 `runtime-evidence.md` /
   `harness-evidence.md` / `cloud-evidence.md`;指向
   `examples/evidence-examples/` 和 `docs/evidence-guide.md`。
   **不重复 evidence-guide 内容**,只指针。
7. **Locked files convention** · `materials/locked.md` 列不让 coding
   agent 改的文件,一行一个。AHL 不强制锁定 (write-protect / git hook
   / patch validation 都没做),靠 coding agent 自律。Cross-link 到
   §10 brief.md。
8. **How coding agent should use this folder** · 简短列表:
   - read all `materials/*.md` before drafting program / rubric / cases
   - may add new `materials/<topic>.md` after extracting from URL or
     pasted content; mention added files in the review handoff
   - never mutate any file listed in `materials/locked.md`
   - never mutate `results/**` or `sandbox/**` (these are AHL-generated)
   - cross-link to `docs/coding-agent-guide.md` for full rules

### 长度预算

整份 materials/README.md ≤80 行。Acceptance test 检测。

### 注意

- 现有 template 里"按需创建 runtime-evidence.md / harness-evidence.md
  / cloud-evidence.md"那段不重复;统一指向 §6 evidence files + v0.8
  artifacts。
- `locked.md` 约定保留 (跟 v2-minimal-spec 时代一致),没有 AHL 强
  制校验改动 — 这是 product convention,不是 enforced contract。

---

## 10. Coding-agent guide design

**Open question**: ship as one merged doc, or two thinner docs?
(See §17 Open questions.) Spec assumes **one merged doc**
`docs/copilot-setup.md` aimed at both audiences with two clearly
headed sections, unless content grows past ~400 lines during
drafting.

If two docs are chosen instead:
- `docs/copilot-setup.md` — for the **human** operator (how to
  drive co-pilot mode, how to write brief.md, what to check)
- `docs/coding-agent-guide.md` — for the **coding agent**
  (operational rules when working in a co-pilot experiment)

### Doc structure (merged version, ~9 sections)

1. **What this guide covers** · who reads what (human vs coding
   agent), 1 paragraph.
2. **When to use co-pilot mode** · vs. manual vs. auto. Cross-link
   to `docs/product-walkthrough.md` Step 2.
3. **The co-pilot loop** · text-only diagram of the 8-step workflow
   in §7 of this spec.
4. **For the human operator: writing brief.md** · How to fill the
   12 sections; what "good" looks like; when to stop polishing and
   hand off to coding agent.
5. **For the coding agent: operational rules** ·
   - read goal.md first
   - read brief.md (treat as work order — do not silently mutate;
     propose edits in the review handoff)
   - inspect materials/; read all files; respect
     `materials/locked.md`
   - may create / update: program.md, rubric.md, simulator.md,
     cases/*.md, harnesses/*.md, runtime-sources.md (only if not
     present)
   - may not modify: goal.md (workspace-level), results/**,
     sandbox/**, anything in materials/locked.md, .git/**
   - prefer minimal, reviewable changes (one file edit per logical
     step; not bulk multi-file rewrites)
   - when to run which `ahl` subcommand:
     `ahl review` after drafting; `ahl probe` if runtime info in
     brief.md §4 indicates a materialized runtime; `ahl run / score /
     compare` only after `ahl review` PASSes
   - report changed files + acceptance results in a handoff message
6. **What "done" means** · brief.md §12 done criteria expanded to
   acceptance-test language.
7. **Common failure modes** · 5-7 short anti-patterns the coding
   agent should avoid (e.g., writing rubric with >5 dimensions,
   editing `materials/locked.md` files, skipping `ahl review`).
8. **Manual ↔ Co-pilot ↔ Auto boundary** · 1 paragraph + table
   (mirrors §5 of this spec). Cross-link to `docs/product-modes.md`
   HISTORICAL banner (don't replicate that doc).
9. **Reference** · cross-links to: `docs/file-formats.md`,
   `docs/evidence-guide.md`, `docs/product-walkthrough.md`,
   `examples/sample-workspace/` (end-state reference), v0.9
   `examples/copilot-setup-example/` (setup-state reference).

### 长度预算

整份指南 **target ~280-360 lines**。Hard cap **400 lines** — 超
过就拆。Acceptance test 检测总行数。

### 旧 doc 处理

`docs/agent-authoring-guide.md` 保留 HISTORICAL banner;在 banner
里加一句 "Superseded by `docs/copilot-setup.md` for the modern
co-pilot path."。**不删 file**(保留 v0.2.0-era 设计审计轨)。

---

## 11. Example design

New directory: `examples/copilot-setup-example/`.

### Contents

```
examples/copilot-setup-example/
  README.md                              # 1 页:这个 example 是什么
  goal.md                                # 浓缩版 workspace goal
  experiments/01-clarify-questions/
    brief.md                             # 12 节全填的参考样本
    materials/
      README.md                          # 8 节,跟模板一致
      prompts-baseline.md                # V1 system prompt 浓缩示例
      target-behavior-examples.md        # 2-3 个 failure example
      domain-knowledge.md                # 1 段领域背景
      locked.md                          # 列出 prompts-baseline.md
    expected-coding-agent-plan.md        # coding agent 应该输出的
                                          # 文件列表 + 1 段 rationale
    # 故意 NOT 包含:program.md / rubric.md / simulator.md /
    # cases/*.md / harnesses/*.md / results/** / sandbox/**
    # —— 这个 example 演示 setup-state,不是 end-state
```

### What this example demonstrates

- 一份**填好的 brief.md** 12 节是什么样 (用户参考)
- `materials/` 里 user-supplied 文件长什么样 (baseline prompts /
  failure transcripts / domain knowledge)
- `locked.md` 怎么用 (列 prompts-baseline.md,coding agent 不改)
- `expected-coding-agent-plan.md` —— coding agent 在交付时应该写一份
  这种 plan (changed files + rationale + acceptance results)

### What this example does NOT do

- **不 run end-to-end** (no `ahl run / score / compare` artifacts)
- **不 duplicate v0.7 sample workspace** (那是 end-state reference)
- **不调任何 LLM API**
- **不带 results/ / sandbox/ / snapshots/** —— acceptance test 会
  assert 这些目录不存在

### Acceptance test for this example

- 目录结构存在,文件名跟 above 一致
- `brief.md` 含所有 12 section anchors
- `materials/README.md` 含所有 8 section anchors
- 不存在 `program.md / rubric.md / simulator.md / cases / harnesses
  / results / sandbox` (acceptance: setup-state only)
- `materials/locked.md` 至少含 1 行(`prompts-baseline.md`)
- `expected-coding-agent-plan.md` 提到至少 4 个 "will create"
  files: program.md / rubric.md / simulator.md / cases/D-01.md

---

## 12. README / docs updates

### `README.md` + `README_CN.md` (EN/CN 1:1 maintained)

- §1-§3 (what is AHL / harness / runtime): unchanged
- §4 (simplest workflow): explicit Manual / Co-pilot / Auto callout
  paragraph; cross-link to `docs/copilot-setup.md`
- §8 (commands cheatsheet): unchanged (no new CLI)
- New short bullet near the bottom of "more docs" section pointing
  to `docs/copilot-setup.md` and `examples/copilot-setup-example/`

### `docs/README.md`

- Add `docs/copilot-setup.md` to mainline reading order, right after
  `product-walkthrough.md`, before `evidence-guide.md`
- Update first-time-reader path: walkthrough → copilot-setup →
  file-formats → evidence-guide → 4 MVP specs
- Note `docs/agent-authoring-guide.md` is superseded (in the
  HISTORICAL banner section)

### `docs/product-walkthrough.md`

- Step 2 (Choose mode): add a "→ Co-pilot guide" link in the copilot
  row of the modes table
- Step 4 (Create experiment): under the `--mode copilot` section,
  add 1 line "After `ahl new` finishes, read `docs/copilot-setup.md`
  for how to drive co-pilot mode end-to-end."

### `docs/roadmap.md`

- Rewrite v0.9 entry from "Auto Mode MVP + 候选并入项 [exploring]"
  to **"Co-pilot Setup Productization MVP [shipped]"** (filled in
  during release-prep commit).
- Add new v0.10 entry **"Open-Source Readiness Freeze / Release
  Candidate / Final Acceptance [exploring]"** — v0.10 is the OSS
  freeze cycle, NOT an Auto mode cycle. Auto mode stays deferred to
  **post-open-source or v1.x**; deferred candidates (package
  inspect/validate, probe-snapshot binding) move into the v1.x
  bucket. Do not frame v0.10 as Auto.

### `docs/product-modes.md` (HISTORICAL)

- Banner stays. No content edits.
- Cross-link from banner to new `docs/copilot-setup.md` as "current
  primary reference".

### `docs/agent-authoring-guide.md` (HISTORICAL)

- Banner stays. Add 1 line to banner: "Superseded by
  `docs/copilot-setup.md` for the modern co-pilot path."

### `docs/file-formats.md`

- §Brief (Co-pilot setup) section: update to reference 12-section
  schema (just structure, not full content); cross-link to
  `docs/copilot-setup.md` for full template details.
- §Materials directory section: update to reference 8-section
  README schema; cross-link.

### CLI `--mode auto` error message

In `src/agent_harness_lab/cli.py:cmd_new`, the "Auto mode 暂未实现"
error message currently points to product-walkthrough Step 2 + Step 9.
Add a third line:

```
当前推荐路径:--mode copilot (默认) ── 见 docs/copilot-setup.md
```

This is the **only** code-flow change in v0.9 (1 line `print()` in
`cmd_new`). Templates.py constants are also updated, but those are
data, not behavior.

---

## 13. Test plan

Target: **479 → ~493 passing** (+14 tests:6-10 co-pilot template +
4 example + 2-3 docs cross-link).

### 13.1 `tests/test_copilot_templates.py` (new, 6-10 tests)

- `test_brief_template_has_12_section_anchors` — `BRIEF_TEMPLATE`
  contains all 12 markdown `## ` headings from §8 above
- `test_brief_template_under_200_lines` — len budget check
- `test_brief_template_mentions_acceptance_commands` — section §11
  lists `ahl review / run / score / compare`
- `test_brief_template_mentions_done_criteria` — section §12 anchor
  present
- `test_brief_template_mentions_modes_boundary` — preamble or
  somewhere mentions Manual / Co-pilot / Auto
- `test_materials_readme_template_has_8_section_anchors` —
  `MATERIALS_README_TEMPLATE` contains all 8 markdown `## ` headings
  from §9 above
- `test_materials_readme_under_80_lines` — len budget check
- `test_materials_readme_mentions_locked_md` — `locked.md` convention
  present
- `test_materials_readme_mentions_generated_results_not_to_mutate` —
  §8 explicitly references results/** / sandbox/**
- `test_materials_readme_links_to_evidence_guide` — content contains
  `docs/evidence-guide.md` reference

### 13.2 `tests/test_ahl_new_copilot_default.py` (extend existing or new, ~4 tests)

- `test_ahl_new_default_creates_copilot_mode` — running `ahl new
  test-x` without `--mode` creates brief.md + materials/README.md +
  cases/ + harnesses/
- `test_ahl_new_copilot_does_not_create_manual_files` — no
  program.md / rubric.md / simulator.md after `ahl new --mode
  copilot`
- `test_ahl_new_copilot_brief_has_all_12_sections` — file written to
  disk after `ahl new` matches §8 anchors (catches drift between
  template constant and on-disk artifact)
- `test_ahl_new_copilot_materials_readme_has_all_8_sections` — same
  drift check for materials/README.md

### 13.3 `tests/test_copilot_setup_example.py` (new, ~4 tests)

- `test_copilot_setup_example_dir_exists` — directory at expected
  path
- `test_copilot_setup_example_brief_complete` — brief.md exists and
  contains all 12 section anchors with **non-empty body in each
  section** (not just templates)
- `test_copilot_setup_example_no_endstate_files` — assert absence of
  program.md / rubric.md / simulator.md / cases/*.md /
  harnesses/*.md / results / sandbox (this is setup-state, not
  end-state)
- `test_copilot_setup_example_locked_md_nonempty` — locked.md exists
  and lists at least `prompts-baseline.md`

### 13.4 Extend `tests/test_doc_consistency.py` (+2-3 assertions in
existing tests, no new test functions if possible)

- Mainline links: assert `docs/README.md` references
  `copilot-setup.md`
- Walkthrough cross-link: assert `docs/product-walkthrough.md`
  references `docs/copilot-setup.md`
- README cross-link: assert `README.md` and `README_CN.md` reference
  `docs/copilot-setup.md`
- Dead-link check: existing dead-link detector skips banner-tagged
  HISTORICAL docs; verify the new banner update in
  `agent-authoring-guide.md` doesn't introduce broken links

### 13.5 Existing tests must still pass

- All 479 existing tests pass (no regression)
- Default and `-W error::ResourceWarning` strict modes both pass

---

## 14. Acceptance criteria

v0.9 is "done" when **all** of the following hold:

A. **`BRIEF_TEMPLATE` rewritten to 12 sections** matching §8, total
   length ≤200 lines, with prompts and 1-line examples per section.
B. **`MATERIALS_README_TEMPLATE` rewritten to 8 sections** matching
   §9, total length ≤80 lines.
C. **New doc `docs/copilot-setup.md` exists** (or paired
   `copilot-setup.md` + `coding-agent-guide.md` if §17 open
   question resolves that way), 9 sections per §10, ≤400 lines.
D. **New example `examples/copilot-setup-example/`** with the exact
   structure in §11, including filled brief.md / 3 materials files /
   locked.md / expected-coding-agent-plan.md; no end-state files
   present.
E. **README + README_CN + docs/README + product-walkthrough + roadmap +
   file-formats + product-modes (banner) + agent-authoring-guide
   (banner)** all updated per §12.
F. **`cmd_new` auto-mode error message** has the extra
   "推荐路径:--mode copilot" line per §12.
G. **Tests**: 479 → 493 passing (±2 acceptable if test consolidation
   merges some); default + strict modes both PASS.
H. **No new CLI command**. `ahl --help` shows exactly 14 subcommands.
I. **No snapshot / evidence / scoring / package / probe contract
   change.** Existing snapshot JSON / evidence inference / score JSON
   / compare md / probe-results JSON byte-identical for unchanged
   inputs.
J. **No PyPI publish / no visibility flip / no public announcement.**
K. **Repo PRIVATE**; branch `v0.9.0-planning` exists locally; no
   push without explicit Kun authorization.
L. **No deletion of `docs/agent-authoring-guide.md` or
   `docs/product-modes.md`.** Both keep HISTORICAL banner.

---

## 15. Implementation plan

Standard v0.X cycle pattern, split into **C1 (templates + docs)** and
**C2 (example + tests + cross-links)**.

### C1 — Templates and primary guide doc

Allowed files:
- `src/agent_harness_lab/templates.py` (rewrite `BRIEF_TEMPLATE` and
  `MATERIALS_README_TEMPLATE`)
- `src/agent_harness_lab/cli.py` (1-line auto-mode error message
  addition only)
- `docs/copilot-setup.md` (new file; or pair if §17 resolves that
  way)
- `docs/product-modes.md` (banner cross-link only)
- `docs/agent-authoring-guide.md` (banner "Superseded by" line
  only)
- `temp/v0.9.0-c1-review-bundle/` (review artifacts; do not commit
  to main)

Forbidden files this cycle:
- everything not listed above (no `runner.py`, no `evidence.py`, no
  `snapshot.py`, no test changes yet)

C1 acceptance:
- All §14 A / B / C / F / H / I / J / K / L hold
- Existing 479 tests still pass (templates being longer doesn't
  break anything)
- Manual smoke-test: `ahl new smoke-test` produces 12-section
  brief.md and 8-section materials/README.md on disk

### C2 — Example, tests, cross-links

Allowed files:
- `examples/copilot-setup-example/**` (new directory, all contents)
- `tests/test_copilot_templates.py` (new file)
- `tests/test_ahl_new_copilot_default.py` (new file OR extend
  existing `test_cli_new.py` if shorter)
- `tests/test_copilot_setup_example.py` (new file)
- `tests/test_doc_consistency.py` (extend existing assertions; no
  new test functions if avoidable)
- `README.md`, `README_CN.md` (EN/CN 1:1 callout updates)
- `docs/README.md` (mainline reading order)
- `docs/product-walkthrough.md` (Step 2 + Step 4 cross-links)
- `docs/file-formats.md` (Brief + Materials section refs)
- `docs/roadmap.md` (v0.9 → shipped; new v0.10 entry)
- `CHANGELOG.md` (v0.9.0 section)
- `temp/v0.9.0-c2-review-bundle/`

Forbidden files this cycle:
- everything not listed (still no `runner.py` / `snapshot.py` etc.)

C2 acceptance:
- All §14 A-L hold
- 479 → 493 passing (default + strict)
- Manual smoke-test: `ahl new` flow + example flow both verified by
  test suite
- Doc-consistency drift detectors green

### Release-prep + tag

After C2 PASS:
- Bump `src/agent_harness_lab/version.py` and `pyproject.toml` to
  `0.9.0`
- Add CHANGELOG v0.9.0 entry
- `docs/roadmap.md` v0.9 entry status → `[shipped]`; v0.10 entry
  added with Auto mode forward-rolled
- Annotated tag `v0.9.0` on the release-prep commit (peeled commit
  = release-prep, not the C2 last commit)
- GitHub Release notes from `temp/v0.9.0-release-notes.md`
- **STOP**. Do not start v0.10. Wait for Kun.

---

## 16. Redlines

Reproduced for cycle-lock convenience (full list in §6):

- Repo PRIVATE
- No new CLI command (14-cap)
- No Auto / orchestration / LLM call
- No MCP / registry / cloud attestation / publish
- No new runtime source type
- No snapshot / evidence / scoring / package / probe contract change
- No deletion of v0.7 sample workspace
- No deletion of manual mode
- No deletion of historical docs (banners stay)
- No `--no-verify` / hook bypass
- No push without Kun explicit OK (per [[feedback-no-implicit-push]])

---

## 17. Open questions (for Kun to lock before C1 starts)

### Q1 · Single merged guide vs. pair of docs? — **LOCKED**

**Merged.** One `docs/copilot-setup.md` aimed at both audiences with
clearly headed sections. Do not create paired docs unless the merged
guide exceeds the 400-line hard cap.

### Q2 · Can coding agent mutate `brief.md`? — **LOCKED**

**Yes, with boundaries.** Coding agent may add labeled
**proposal / interpretation / open-question** sections. It must
**not silently overwrite** the user's original intent. The
brief.md template must make this explicit.

### Q3 · `expected-coding-agent-plan.md` schema — **LOCKED**

**Fixed lightweight schema.** Required anchors:
1. `## Files to create / modify`
2. `## Acceptance commands`
3. `## Risks / open questions`

Drift test asserts these 3 anchors exist.

### Q4 · Done criteria — **LOCKED**

`examples/copilot-setup-example/` is **setup-state only**;
no runnable end-state files. But the brief template should still
teach that a completed real experiment eventually passes:
`ahl review / ahl probe / ahl run / ahl score / ahl compare`.

### Q5 · `docs/roadmap.md` v0.10 framing — **LOCKED**

v0.10 is **NOT** Auto. v0.10 is **"Open-Source Readiness Freeze /
Release Candidate / Final Acceptance [exploring]"**. Auto mode stays
deferred to **post-open-source or v1.x**. Deferred candidates
(package inspect/validate, probe-snapshot binding) roll into v1.x.

### Q6 · CLI auto-mode error-message addition — **LOCKED**

Allowed as **tiny UX guidance only** (1-3 lines, no behavior
change, no new CLI command, no workflow contract change). If it
grows past 1-3 lines or touches behavior, stop and report.

### Q7 · `docs/file-formats.md` updates — **LOCKED**

**Prefer updating existing Brief / Materials sections.** Add a new
small section only if necessary. Do not duplicate
`docs/copilot-setup.md`.
