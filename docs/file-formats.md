# Agent Harness Lab · 文件格式

> 本文描述 ahl 当前已实现的文件格式 —— 工具实际读写的。
> 产品流程心智见 [`product-walkthrough.md`](product-walkthrough.md);
> 顶层产品定义见 [`product-definition.md`](product-definition.md)。
> 历史架构 reference: [`design-v0.3.md`](design-v0.3.md) (v1) / [`design-v0.4.1.md`](design-v0.4.1.md) (v2+ 长期方向)。
> v0.3.0 新增 Runtime Materialization 部分见本文 §Runtime Materialization。
> 各格式都对着 `src/agent_harness_lab/` 的解析代码核过。

## 工作目录

`ahl init` 只建 `goal.md` + `experiments/` (v0.3.1 Step 0/1 后)。`connect.md` /
`runtime-sources.md` / `materials/*-evidence.md` 均**不默认创建** —— 在 Step 3
据 runtime boundary 选择按需手动创建(见 [`product-walkthrough.md`](product-walkthrough.md) Step 3)。

```
<工作目录>/
├── goal.md                  workspace 级长期目标 (ahl init 创建)
├── experiments/             ahl init 创建
│   └── <编号-名字>/         ahl new <名字> 创建 (产物按 setup mode 不同,见下)
│       └── results/         run / score / compare 的产出
│
├── connect.md               (可选,Step 3) legacy running-agent runtime 接入配置
├── runtime-sources.md       (可选,Step 3) local_path / git_repo runtime 声明
└── calibration/             (可选,v2.5+) golden cases 等校准锚点
```

### Setup mode 产物 (`ahl new --mode <mode>`,见 [`product-walkthrough.md`](product-walkthrough.md) Step 4)

- **copilot** (默认): `brief.md` + `materials/README.md` + `cases/` + `harnesses/`
- **manual**: `program.md` + `rubric.md` + `simulator.md` + `cases/` + `harnesses/`
- **auto**: 当前 not implemented,不创建任何文件

按需可在 `materials/` 下放 `runtime-evidence.md` / `harness-evidence.md` /
`cloud-evidence.md`(Step 3 evidence 文件,Co-pilot 主路径,不默认创建)。

---

## connect.md

工作目录根一份。工具怎么连被测 agent(design-v0.3 §3.2 的四种接入方式)。

```
# connect

## 类型
外部命令行          # 进程内库 / 外部命令行 / HTTP无状态 / HTTP有状态

## 配置
命令:wsl python3 /path/to/agent.py
```

- 四种接入都已实现(见 examples/ 各一个样例)。外部命令行 = 子进程 + JSON 行:stdin 收 `{"input": ...}`,stdout 回 `{"response": ...}`。
- agent 在 WSL 里,命令写 `wsl ...`。
- **跨平台**:`命令:` 行是 shell 直接 exec 的命令。Python agent 解释器名 macOS / Linux 用 `python3`、Windows 用 `py`(Python Launcher);跨机器 handoff 时记得改对应解释器,或脚本加 shebang `#!/usr/bin/env python3` + `chmod +x` 再 `命令:./agent.py`(三平台都吃)。

---

## program.md

PM 交给 coding agent 的实验指令,一个实验一份。

```
# 实验 <编号-名字> · program

## 假设
<这次实验想验证什么>

## 声明
- 环境:<被测环境是什么 + 取的初始状态;无环境写"无">
- 对话模式:<模拟 / 回放 / 固定>
- 状态:<累积 / 重置>
- 评分:<评分器类型 + 打分粒度>
- 运行模式:<人评 / 自迭代>
- 对比方式:<对基线 / 线性迭代;可选,默认 对基线 —— 多版本 compare 怎么算 delta>

## 留/丢规则
<运行模式 = 自迭代时必填;人评留空>

## 喊人规则
<运行模式 = 自迭代时必填;人评留空>
```

---

## rubric.md

评分维度 + 权重,从 goal 推导。

```
# rubric

## <维度名>
权重: <0-1,所有维度之和 = 1;也可写百分数、和 = 100>
<这个维度衡量什么、怎么判高低分>
```

---

## simulator.md

模拟模式下扮用户的那个 agent。真 simulator 读它 + 调模型生成追问。

```
# simulator

## 人设
<simulator 扮谁>

## 背景知识
<它扮的人知道什么(可留空)>

## 追问策略
<怎么追问、什么时候收尾>
```

---

## cases/<case>.md

一个测试 case 一个文件。下面是「模拟」模式的格式;回放 / 固定模式的 case 形状不同,随后做。

```
---
id: D-01
type: D                 # 可选;分类标签
max_turns: 15           # 可选;对话轮次上限
depends_on:             # 可选;另一 case 的 id。已解析,但 run 暂未用它(占位、不生效)
---
## 起始输入
<开场那条用户消息>

## 完成标准
<可选;一个 checklist 或散文式判断要点>
```

---

## harnesses/<版本>.md

被测系统里摆出来对比的 harness variants,一个 variant 一个文件。一组里恰好一个标基线。

每个 variant 可以写自己的「类型」「配置」段,接到各自的 agent —— 比较两个不同 agent 时用;不写这两段就用全局 connect.md。

```
---
id: V1
基线: 是                # 是 / 否
---
## 这是什么
<这个版本是基线,还是相对基线改了什么>

## 类型
外部命令行              # 可选;不写则用全局 connect.md。四种接入同 connect.md

## 配置
命令:wsl python3 /path/to/this-version-agent.py
```

---

## results/

`run` / `score` / `compare` 的产出,工具写、PM 读:

- `run-<时间>.json` —— 一次 run 的对话(每条 = 版本 × case 的多轮 transcript;
  每条 record 含 `snapshot_id` 字段指向对应 `results/snapshots/<run_id>/<vid>.json`,
  legacy 路径固定 `"legacy"`,materialized 路径 `"snap-<run_id>-<vid>"`)。**v0.4
  保留 raw fact 层不变**,evidence 推断只在 score / compare 层。
- `score-<时间>.json` —— 一次打分(每条 case 的各维度分 + 加权总分,带用的哪版
  rubric、哪个评分器)。**v0.4 加 top-level `evidence` 字段** —— 从 run 的
  snapshot + 可选 `materials/*-evidence.md` 推断的 per-variant evidence level
  + summary。详见下面 §Evidence (v0.4)。
- `compare-<时间>.md` —— 一次对比报告(版本总分、跟基线的差、哪个维度退化)。
  **v0.4 在版本总分之前新增 `## Evidence` section** —— 渲染 score JSON 的
  evidence 表格;若有 weak/unknown 加 `⚠` 警告,若 level 不一致加 `ℹ` 提示。
  不影响 winner / score diff 逻辑。
- `snapshots/<run_id>/<vid>.json` —— 一次 run 内每个 variant 的运行环境指纹
  (v0.3.0 加,详见下面 §Runtime Materialization)。**v0.4 evidence 推断的事实
  来源** —— 不动 schema。

---

## Runtime Materialization (v0.3.0)

v0.3.0 加的能力:把 harness variant 应用到具体 runtime source (本地目录 /
git 仓库) 后跑,留下可复现指纹。详细设计见 `runtime-materialization.md` +
`runtime-materialization-m1-spec.md`。下面只列**文件格式**。

### runtime-sources.md (工作目录根,可选)

声明可被 variant 引用的 runtime sources。文件不存在 → 所有 variant 走 legacy
(用 connect.md);存在但 0 个 source → 报错。

```markdown
# runtime sources

## openmanus-main
type: git_repo
url: https://github.com/example/openmanus.git
ref: main

## local-aider
type: local_path
path: <home>/projects/aider
```

约束:
- 二级 heading `## <name>` = source name (必 unique)
- `type:` ∈ `{local_path, git_repo}` (其他 type 留 M2+)
- `local_path`:必 `path:`
- `git_repo`:必 `url:` + `ref:` (ref 可 commit / branch / tag)
- 不识别字段:忽略 + warning

### harnesses/V*.md 加 `runtime_source` 字段 + `## Patch` 段 (可选)

```markdown
---
id: V2
基线: 否
runtime_source: openmanus-main
---

## 这是什么
极简模式的 system prompt。

## Patch

files:
  - target: prompts/system.md
    source: patches/V2/system.md
  - target: config/tools.yaml
    source: patches/V2/tools.yaml

env:
  HARNESS_MAX_DEPTH: "5"

start_command: python -m openmanus.agent
```

约束:
- `runtime_source:` 是 frontmatter 可选字段
  - 不写 → variant 走 legacy (用 connect.md + agentconn 的「类型」「配置」段)
  - 写了但 source 名不在 runtime-sources.md → preflight WorkflowError
- `## Patch` 段 (仅 `runtime_source` 写了才解析;否则忽略):
  - `files:` 列表 — `target:` (相对 source root) + `source:` (相对 experiment root,
    通常 `patches/<vid>/`)。**target / source 都做 path traversal 防御** (越界
    抛 RuntimeError / ValueError,不允许写出 sandbox 或 读 experiment 外)
  - `env:` map — value 用字符串避免类型歧义
  - `start_command:` 启动命令 (M1 必填,不假设默认)
- patches 文件存放:`experiments/<id>/patches/<vid>/<filename>`,纯文本整文件替换。

### results/snapshots/<run_id>/<variant_id>.json (snapshot 指纹)

每次 `ahl run` 给每个 variant 写一份 snapshot,记录跑这次用的运行环境指纹。
**legacy 路径也写**,字段精简但保持证据链统一。

**Legacy 路径** (variant 无 `runtime_source`):
```json
{
  "snapshot_id": "legacy",
  "run_id": "run-20260523-103045",
  "variant_id": "V1",
  "experiment": "001-foo",
  "created_at": "2026-05-23T10:30:45+00:00",
  "runtime_source": {
    "type": "legacy_connect",
    "connect_md_hash": "sha256:..."
  },
  "harness_patch": null,
  "sandbox": null,
  "environment": {"python_version": "3.14.0", "os": "...", "captured_at": "..."}
}
```

**Materialized 路径** (`runtime_source` 写了):
```json
{
  "snapshot_id": "snap-run-20260523-103045-V2",
  "run_id": "run-20260523-103045",
  "variant_id": "V2",
  "experiment": "001-foo",
  "created_at": "2026-05-23T10:30:45+00:00",
  "runtime_source": {
    "type": "local_path",
    "name": "local-aider",
    "path": "<home>/projects/aider",
    "source_dir_hash": "sha256:<pre-patch raw source 指纹>"
  },
  "harness_patch": {
    "applied": [
      {"target_path": "prompts/system.md", "source_path": "patches/V2/system.md", "hash": "sha256:..."}
    ],
    "env": {"HARNESS_MAX_DEPTH": "5"},
    "start_command": "python -m openmanus.agent",
    "patch_hash": "sha256:<files+env+start_command 的整体 hash>"
  },
  "sandbox": {
    "type": "copy_dir",
    "path": "sandbox/run-20260523-103045/V2",
    "start_command": "python -m openmanus.agent"
  },
  "environment": {"python_version": "...", "os": "...", "captured_at": "..."}
}
```

git_repo 多 `url` / `ref` / `commit_sha` 三个字段,`sandbox.type=git_clone`。
详细各 source 类型 schema 见 `runtime-materialization-m1-spec.md` §2.1。

### `ahl run --cleanup-sandboxes` (可选 flag)

默认: keep sandbox dir (sandbox 是证据链一部分,默认保留方便事后调查)。

显式 `--cleanup-sandboxes`:跑完 finally 块对每个 `sandbox.path` 做 `shutil.rmtree`。
snapshot.json 不受影响 (snapshot 是 evidence,不删)。legacy variant 无 sandbox
path,该 flag 对它们无效。

---

## Evidence (v0.4)

v0.4 在 score JSON 加 top-level `evidence` 字段;compare report 加 `## Evidence`
section。Evidence 是从 v0.3.0 snapshot **推断**出来的 decision-grade signal,
不动 runtime / snapshot / scoring math。完整契约见
[`evidence-aware-result.md`](evidence-aware-result.md)。

### `score-<时间>.json` 的 `evidence` 段

```json
{
  "run": "run-20260525-160000.json",
  "rubric": "rubric.md",
  "grader": "...",
  "scores": [...],
  "evidence": {
    "variants": {
      "V1": {
        "level": "strong",
        "runtime_source_type": "local_path",
        "snapshot_id": "snap-run-20260525-160000-V1",
        "snapshot_available": true,
        "materials_evidence": [],
        "reasons": ["local_path with source_dir_hash and patch_hash"]
      }
    },
    "summary": {
      "levels": {"strong": 1, "medium": 0, "weak": 0, "unknown": 0},
      "warning": null,
      "note": null
    }
  }
}
```

`level` ∈ `{strong, medium, weak, unknown}`。判定规则见
[`evidence-aware-result.md`](evidence-aware-result.md) §3。

### `compare-<时间>.md` 的 Evidence section

在版本总分之前出现:

```markdown
## Evidence

| variant | level | source | snapshot | materials | reasons |
|---|---|---|---|---|---|
| V1 | strong | local_path | ✓ | — | local_path with source_dir_hash and patch_hash |
| V2 | weak   | legacy_connect | ✓ | — | legacy_connect with no materials evidence files |

⚠ weak/unknown evidence may be behavioral-only or missing metadata; do not
   treat this as fully reproducible harness comparison
```

三档信号(spec §5.1,**判断顺序固定**:先检查 weak/unknown,再检查 level 是否一致):
- 所有 variant 都是 strong,或都是 medium(uniform 且无 weak/unknown) → 只表格,无 warning/note
- 无 weak/unknown 但 level 不一 → `ℹ` caution
- **任意** weak/unknown(含全 weak / 全 unknown / weak+medium 等所有混合) → `⚠` warning

### Old result 兼容

| 场景 | 行为 |
|---|---|
| v0.4+ score 含 `evidence` | 直接读用 |
| v0.3.x score 无 `evidence` + run-*.json 可读 | on-the-fly 从 run + snapshots 重算;不 rewrite 旧 score 文件 |
| Snapshot 文件缺失 / 损坏 | 该 variant level = unknown,Evidence section 仍出现 |
| **run-*.json 缺失 / 损坏(Blocker 2 fix)** | **从 score `scores` 数组合成** unknown evidence,每个 unique `version_id` 一条;Evidence section + `⚠` warning 仍出现。不 crash 不 block。 |

详见 [`evidence-aware-result.md`](evidence-aware-result.md) §6。
