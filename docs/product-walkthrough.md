# Agent Harness Lab · Product Walkthrough

> 这份文档讲 AHL 的完整产品流程：从「我想改善某个 agent」到「我做出 keep/discard 决策」走 9 步。
> 你不用一口气读完——按当前在哪一步,跳到对应章节即可。
>
> 想看产品定位和概念架构:[`docs/product-definition.md`](product-definition.md)
> 想看具体文件格式:[`docs/file-formats.md`](file-formats.md)
> 想看 runtime materialization 细节:[`docs/runtime-materialization.md`](runtime-materialization.md)

## 概览

AHL 的工作循环:

```
goal → mode → runtime → experiment → variants → cases/rubric
                                                      │
                                                      ▼
decision ← evidence ← score/compare ← run
```

每个 workspace 一份 `goal.md`,跨多个实验长期有效。
每次迭代一份 `brief.md` + 一个 `experiments/<id>/`,负责本轮 keep/discard 决策。

---

## Step 1 — Define goal

**这一步回答**:这个 workspace 想改善哪个 agent 的什么行为?

**改哪里**:`goal.md`(由 `ahl init` 生成)

**产出**:6 段填好的 goal——目标 agent / 想改善的行为 / 当前 baseline / Harness 层假设 / 成功标准 / 红线。

**常见误区**:
- §2「想改善的行为」写得太抽象(只写"更好"、"更智能",不举真实 case)。先收集 2-3 个真实失败例子再继续。
- 跳过 §4 Harness 层假设直接改 prompt,后面无法回答"这次改动验证了哪一层"。

---

## Step 2 — Choose mode

**这一步回答**:本轮你打算怎么工作?

**改哪里**:不创建文件,只是认知层面的选择。

**三种模式**:

| 模式 | 谁做主 | 用什么场景 | 状态 |
|---|---|---|---|
| **Manual** | 你 | 探索阶段、第一次接触 AHL、改动方向还没收敛 | ✅ 可用 |
| **Co-pilot** | 外层 coding agent | 改动方向清楚、想让 Claude/Cursor/Codex 起草实验文件 | ✅ 可用 (v2-minimal) |
| **Auto** | AHL + agent | 多轮自动迭代,异常喊你 | 未来模式 (依赖 M2+ calibration + approval gates) |

**常见误区**:
- 第一次用就选 Co-pilot,但 goal.md 还没写清——coding agent 没有方向,起草质量不会好。
- 把 mode 当成 workspace 级设定。其实它是 per-experiment 的,每次实验可以换。

---

## Step 3 — Declare runtime

**这一步回答**:AHL 在哪里跑你的 agent?

**改哪里**:据你选的 runtime 创建对应文件——

- 本地源码 → `runtime-sources.md`,声明 `type: local_path` + `path`
- Git repo → `runtime-sources.md`,声明 `type: git_repo` + `url` + `ref`
- 已运行的 agent(legacy) → `connect.md`,声明类型 + 配置

**产出**:一份描述「agent 在哪里、怎么找到它」的声明文件。

具体格式见 [`docs/file-formats.md`](file-formats.md)(legacy `connect.md` 四种类型 + runtime sources schema)。
runtime materialization 的设计动机和细节见 [`docs/runtime-materialization.md`](runtime-materialization.md)。

**怎么选**:
- 想验证 prompt / 配置 / patch 改动是否真的进了 runtime → `local_path` 或 `git_repo`
- 只想测一个已部署 agent 的对话效果 → `connect.md` (legacy)
- 想跨 commit 跑回归实验 → `git_repo`

**常见误区**:
- 把所有 agent 都装进 legacy `connect.md` 模式——这样 patch / snapshot / 可复现性都拿不到。
- `git_repo` 模式下 `ref` 写成分支名(会随时间漂移)。生产实验请固定 commit SHA。

---

## Step 4 — Create experiment

**这一步回答**:把这次实验装进 AHL 的目录结构。

**跑哪个命令**:
- Manual:`ahl new <name>` → 生成 `experiments/<id>-<name>/` 含 `program.md` / `rubric.md` / `harnesses/` / `cases/` / `simulator.md` 模板
- Co-pilot:`ahl draft <name>` → 生成 `experiments/<id>-<name>/brief.md` 模板,让外层 coding agent 据它起草其他文件

**产出**:一个自包含的 `experiments/<id>-<name>/` 目录。每个实验可单独复制、单独 re-run。

---

## Step 5 — Design harness variants

**这一步回答**:你要 A/B 测试哪几版?每版改了什么?

**改哪里**:`experiments/<id>/harnesses/V1.md`、`V2.md`、...,一份文件一个 variant。约定 V1 是 baseline,V2+ 是改动版本。

**每个 variant 声明两件事**:
1. 绑定哪个 `runtime_source`(Step 3 声明的某个)
2. `Patch`——这个 variant 对 runtime 做了什么改动(files / env / start_command)

详细 patch 语法见 [`docs/file-formats.md`](file-formats.md) §Harness Variant + §Runtime Materialization。

**常见误区**:
- variant 改的层不是 goal.md §4 选的层。如果 §4 说「想改 memory 层」但所有 variants 都改 prompt——这次实验没验证假设。
- 一个 variant 同时改多层(prompt + tool + memory)——结果跑出来不知道是哪个改动起作用。一次只改一层。

---

## Step 6 — Prepare cases and rubric

**这一步回答**:用什么 case 触发行为差异?用什么标尺打分?

**改哪里**:三个文件,缺一不可——
- `cases/` —— 一个 case 一个文件,要能触发 goal.md §2 描述的行为差异
- `rubric.md` —— 评分维度 + 权重(总和 1.0),据 goal.md §5 推导
- `simulator.md` —— 模拟模式下扮用户的 agent 人设

**常见误区**:
- case 太"开放"——V1/V2 在所有 case 上表现都差不多,这次实验无信号。case 必须有针对性。
- rubric 维度太多(>5)——judge 评分一致性下降。先 2-4 个核心维度。

---

## Step 7 — Run experiment

**这一步回答**:跑起来,AHL 替你做了什么?

**跑哪个命令**:`ahl run <id>`

AHL 对每个 variant:
1. **Materialize sandbox** —— `local_path` 走 copy directory + apply patch;`git_repo` 走 clone + checkout + apply patch;`legacy` 直接连
2. **跑 cases** —— 每个 case 一场 simulated conversation(simulator 扮用户,agent 答),记录 transcript
3. **写 snapshot** —— 记录这次跑的版本指纹:`source_dir_hash`(pre-patch 原始源码) + `patch_hash` + `commit_sha`(git_repo)

每条 run 完整可复现——两个月后只看 snapshot 就能知道当时实际跑的什么。

**产出**:
- run result: `experiments/<id>/results/run-*.json` (canonical transcripts + run metadata)
- snapshot: `experiments/<id>/results/snapshots/<run_id>/<variant_id>.json` (版本指纹)
- sandbox: `experiments/<id>/sandbox/<run_id>/<variant_id>/` (materialized 实际运行的源码副本)

默认 sandbox 留着方便调试;跑完想清理:`ahl run <id> --cleanup-sandboxes`。

---

## Step 8 — Inspect evidence

**这一步回答**:结果怎么读?

**跑哪个命令**:
- `ahl score <id>` —— judge 据 rubric 给每段对话打分
- `ahl compare <id>` —— 把 variants 放一起比:总分、每维度 delta、回归点

**证据分三层**:
1. **Score** —— 每个 (variant, case) 的分数
2. **Compare report** —— 总分、每维度相对 V1 的 delta、回归维度(变差的维度)
3. **Transcript + snapshot** —— 一段对话实际说了什么 + 跑的什么版本

**怎么读**:先看 compare 总分找赢家 → 看每维度 delta 找回归点(这是 keep/discard 决策的核心) → 不确定的差异打开 transcript 看,不要只看分数。

---

## Step 9 — Decide next iteration

**这一步回答**:这一轮要 keep、discard,还是 next?

**改哪里**:据 compare report 决定,在 goal.md / brief.md 里记一笔。**目前没有专门的 CLI 命令**——靠你判断。

**三种决策**:
- `keep` —— 这版 harness 留下,作为下一轮 baseline。把 Patch 落到正式代码 / prompt 库,V1 推进到这一版。
- `discard` —— 丢掉这版,回到上一版 baseline。compare report 留着,作为「这个方向不行」的证据。
- `next` —— compare 看出新的问题方向,设计下一轮 variants。新建 experiment,回到 Step 4。

未来 Auto mode 会让这一步部分自动化(approval gates + budget rules),M2+ 推进。

---

## 跳出来一下:这 9 步在干嘛?

本质上是把 PM / 工程师做 agent 改进的「手感」变成可重复的实验流程:

| 没有 AHL 时 | AHL 怎么帮 |
|---|---|
| 凭感觉改 prompt,试跑两个 case | goal → variants → cases → rubric,产生可比较的证据 |
| 改动多了忘了哪版好 | snapshot + compare report 留下来 |
| 不知道下一轮该改什么 | rubric 维度 delta 指明回归点 |
| 改 prompt 改源码 改 tool config 混在一起 | harness 层假设把改动分类,实验聚焦一层 |

**一句话**:AHL 不是评测裸 agent,是通过实验持续设计和改进 agent 的 runtime harness。
