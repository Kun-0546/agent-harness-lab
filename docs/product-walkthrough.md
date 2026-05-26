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

**这一步回答**:本轮你打算怎么 *配置* 这个实验?

**改哪里**:不创建文件——这一步只决定下一步 `ahl new` 怎么调(传 `--mode`)。

> **"mode" 是 experiment setup mode**:它只决定 `ahl new` 创建什么结构,
> *不*影响 run / score / compare 的运行行为。AHL runtime 不识别 mode,
> 没有 `.mode` 元数据文件,也没有 program frontmatter 字段。

**三种 setup mode**:

| Mode | 谁做主 | 用什么场景 | 状态 |
|---|---|---|---|
| **copilot** (默认) | 你 + coding agent 协作 | AI 引导式实验配置:coding agent 据 goal.md + brief.md (工作单) + materials/ (参考材料) 跟你协作维护实验文件。你可以让 AI 全做、自己手动配一部分、提供本地材料、锁定某些文件不让 AI 改 | ✅ 可用 |
| **manual** | 你 | 探索阶段、第一次接触 AHL、想完全手动控制 | ✅ 可用 |
| **auto** | AHL + agent (未来) | 多轮自动迭代,异常喊你 | 未来模式 (M2+ 依赖 calibration + approval gates);`--mode auto` 当前报 not implemented |

**常见误区**:
- 第一次用就选 copilot,但 goal.md 还没写清——coding agent 没有方向,协作质量不会好。
- 把 setup mode 当成 workspace 级设定或 runtime 行为标记。它是 per-experiment 的,
  且只影响 `ahl new` 当下建什么结构;之后 run / score / compare 不区分 mode。

---

## Step 3 — Declare runtime boundary and evidence level

**这一步回答**:agent 在哪?harness 在哪?AHL 能看到多少?
看不到时补什么 evidence?本轮证据强度是什么?

> AHL 真正比较的不是 workspace 静态文件,而是 agent runtime 中**实际生效**
> 的 harness。如果 AHL 无法证明 variant 已经在 runtime 中生效,这轮实验
> 只是 weak evidence,不能描述成 fully reproducible。

### 2×2 矩阵

|                 | **Harness in workspace** | **Harness already installed** |
|---|---|---|
| **Local agent** | ① **strong**             | ② **strong** / weak           |
| **Cloud agent** | ③ **weak**               | ④ **weak**                    |

**条件说明**:
- **① Local + Local** 通常是 strongest:AHL 可读、可装、可 snapshot。用 `runtime-sources.md`。
- **② Local + Already installed** 看路径可读性:用户提供 harness 在本地 agent workspace 中的位置(plugin / memory.md / soul.md / skill 目录等)且路径可读 → strong;只能口头说明 → weak。
- **③ ④ Cloud 场景默认 weak**:除非用户提供 deployment evidence(deployment id / active config / plugin list / console export / session id 等),才可能升 medium。

### Evidence collection 跟 setup mode 对齐

evidence 文件**不默认创建**,按 setup mode 谁负责追问:

- **Co-pilot (主路径)**: coding agent 通过对话判断 2×2 情况,向用户追问,按需在 materials/ 下整理 `runtime-evidence.md` / `harness-evidence.md` / `cloud-evidence.md`。
- **Manual**: 用户自己据 2×2 判断;需要时手动创建。
- **Auto (future)**: 必须自动判断 evidence level;不足时请求用户补;用户不补则继续跑但**必须标记 weak**,不能假装 reproducible。

### connect.md 和 runtime-sources.md 怎么选

| 你的情况 | 用什么 | 也许需要补 |
|---|---|---|
| 本地源码可 patch | `runtime-sources.md` (local_path) | 通常不需要 |
| Git repo 可 clone+checkout | `runtime-sources.md` (git_repo) | 通常不需要 |
| 已运行的 agent(本地或云端) | `connect.md` (legacy) | **常需 materials/*-evidence.md** |

具体文件格式见 [`docs/file-formats.md`](file-formats.md)。

### 常见误区

- 把所有 agent 装进 legacy `connect.md` 但不补 evidence → 实验只是黑盒行为测试,evidence 是 weak。
- `git_repo` 模式 `ref` 写分支名(随时间漂移) → 生产实验固定 commit SHA。
- 假定 cloud agent 一定加载本地 harness → 必须提供云端 active state evidence。

---

## Step 4 — Create experiment

**这一步回答**:把这次实验装进 AHL 的目录结构。

**统一入口** `ahl new`,通过 `--mode` 选 setup mode:

```
ahl new <name>                  # 默认 setup mode=copilot
ahl new <name> --mode copilot   # = 默认
ahl new <name> --mode manual    # 你手动编辑完整骨架
ahl new <name> --mode auto      # 暂未实现 (M2+),exit 2,不创建任何文件
```

**产物按 setup mode 不同**:

- **copilot** (默认):
  - `brief.md` (工作单) + `materials/README.md` + `cases/` + `harnesses/`
  - 不创 program/rubric/simulator —— 让 coding agent 据 brief 起草
  - 下一步:跟 coding agent 协作维护 brief / materials,起草其他文件,跑 `ahl review`
- **manual**:
  - `program.md` + `rubric.md` + `simulator.md` + `cases/` + `harnesses/`
  - 不创 brief / materials —— 你手动填,跑 `ahl run` → `score` → `compare`
- **auto**:
  - 当前 exit 2,不创建任何文件。完整设计见 Step 2 + Step 9。

**产出**:一个自包含的 `experiments/<id>-<name>/` 目录。每个实验可单独复制、单独 re-run。
setup mode 选定建出什么结构后,后续 run / score / compare / review 不区分 mode。

> 旧的 `ahl draft` 命令已合并到 `ahl new --mode copilot`,跑 `ahl draft` 会拿到 redirect 提示。

---

## Step 5 — Design harness variants

**这一步回答**:你要 A/B 测试哪几版?每版改了什么?

**改哪里**:`experiments/<id>/harnesses/V1.md`、`V2.md`、...,一份文件一个 variant。约定 V1 是 baseline,V2+ 是改动版本。

**每个 variant 声明两件事**:
1. 绑定哪个 `runtime_source`(Step 3 声明的某个)
2. `Patch`——这个 variant 对 runtime 做了什么改动(files / env / start_command)

**v0.5 可选**:variant 还可引用 workspace `harness-packages/<id>/<version>/`
里的 **Harness Package**,在 `## Patch` 之前 install 到 sandbox。frontmatter
加 `harness_package: <id>@<version>`,workflow 自动 install:
materialize → package → patch → snapshot。Patch 胜出文件 / env /
start_command 冲突,实现"package 提供默认,variant patch 局部覆盖"。详见
[`harness-package-mvp.md`](harness-package-mvp.md)。

详细 patch 语法见 [`docs/file-formats.md`](file-formats.md) §Harness Variant + §Runtime Materialization + §Harness Package (v0.5)。

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

## Step 6.5 — (optional) Probe runtime readiness

**这一步回答**:run 之前先确认 runtime / harness 都装到位了吗?

**跑哪个命令**:`ahl probe <id>`(v0.6 新增,read-only,不触发任何安装)

每个 variant 检查:
- runtime_source 可访问(local_path 目录存在 / git_repo 可 ls-remote)
- harness_package(若用)manifest + payload 都齐
- start_command 可解析(patch 还是 manifest 供给)
- 可选 `--command "<smoke>"` 跑 user-supplied smoke 命令(超时默认 30s,
  stdout/stderr 各 ≤1KB)

可选 `--write-evidence`:对 legacy_connect variant + status ∈ {ok, warn}
写 `materials/runtime-evidence.md`,v0.4 evidence 推断下次会自动 pick up
(weak → medium)。fail 不写。

退出码:任一 variant fail → 1;否则 0(不阻塞 `ahl run`,advisory)。

`ahl review <id>` 读最近一次 probe 摘要并显示,但**不会**触发 probe。

详细契约见 [`docs/runtime-probe-mvp.md`](runtime-probe-mvp.md)。

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

**v0.4 Evidence level** —— compare report 在版本总分之前新增 `## Evidence` section,
据 runtime snapshot + 可选 `materials/*-evidence.md` 推断每个 variant 的 evidence
level(strong / medium / weak / unknown)。weak/unknown 时报告顶部加 `⚠` 警告;
strong/medium 混用时加 `ℹ` 提示 "evidence levels differ"。**不 block 决策,只让
keep/discard 时心里有数**。完整契约见 `docs/evidence-aware-result.md`。

**怎么读**:先看 compare 顶部 Evidence section 判断证据强度 → 看总分找赢家 →
看每维度 delta 找回归点(这是 keep/discard 决策的核心) → 不确定的差异打开
transcript 看,不要只看分数。

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
