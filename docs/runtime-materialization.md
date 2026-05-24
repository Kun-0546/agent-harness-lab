# Agent Harness Lab · Runtime Materialization Spec

> 本文是**总设计 spec**,定义 Agent Harness Lab 的核心底层能力——**Harness
> Runtime Materialization & Snapshotting**——的对象、流程、文件格式与策略表。
>
> **M1 已实现 (v0.3.0, 2026-05-23)**:`local_path` + `git_repo` (clone mode) +
> snapshot persistence (含 source_dir_hash / patch_hash / commit_sha 可复现指纹) +
> sandbox per variant lifecycle + path traversal 防御 + `--cleanup-sandboxes` flag。
> 实现合同见 `runtime-materialization-m1-spec.md`(实际 commits: d5939e5 → C7)。
>
> **M2+ 留**:`docker_image` / `remote_api` / `dev_agent` source、git worktree mode
> 优化、calibration、Auto mode + approval gates。
>
> 日期:2026-05-21 (设计),2026-05-23 (M1 完成)。

---

## 0. 为什么需要 Materialization

当前 v1 / v2-minimal 的接入模型（`connect.md` + `version.connect`）有一个隐含假设：

> 被测 agent 是个**已经存在**的运行体——你只要告诉 Lab 怎么连上它（命令 / URL / 模块路径），它就能逐轮喂消息。

这个假设在两类场景下不够：

1. **从开源项目起步**——你想拿 OpenManus / Aider / 某个 GitHub agent 当 harness base，在它上面打 patch、起几个 variant、对比。`connect.md` 没法表达"先 clone、checkout 某 commit、apply patch、再 start"这一串。
2. **多 variant 隔离**——`run_experiment` 现在直接调 `open_session(connect)`。多个 variant 共享 same runtime，prompt / config / memory / cache 会串线。`design-v0.3.md` §3.1 说每个 variant 起一个 sandbox——但 v1 并没真落地。

Materialization 就是补齐这两块：

> **Harness Variant + Agent Runtime → Materialized Sandbox**——把一份 harness 设计应用到一个具体 runtime，在隔离环境里起一个可运行实例。

---

## 1. 核心对象

### 1.1 Runtime Source

可运行 agent 项目的来源。五种典型：

| 类型 | 内容 |
|---|---|
| `local_path` | 本地目录 |
| `git_repo` | git 仓库 URL + ref（commit / tag / branch） |
| `docker_image` | 镜像名 + digest |
| `remote_api` | 远端服务 endpoint + 配置（model version、session）|
| `dev_agent` | 开发机上正在运行的 agent（如本机 Claude Code 实例） |

Runtime source 决定 materialization 策略（见 §3）。

### 1.2 Harness Base

可被扩展的 harness 基底——某个 agent framework / template / workflow scaffold。Harness Base 通常**就是**一个 Runtime Source 配上「这里可以打 patch」的约定。

例：OpenManus 当 harness base 时，runtime_source 是它的 git repo，harness base 多了一份「prompt 放在 `prompts/system.md`、tool 配置在 `config/tools.yaml`」的约定，告诉 Lab 哪些文件是 harness patch 的入口。

### 1.3 Harness Variant

`product-definition.md` §3.1 已经定义：一种具体的 harness 设计方案。落到文件层面，一个 variant = `harnesses/V*.md` + 0 或多个 patch artifact（见 §1.4）。

Variant 自身不可执行：

> **Harness Variant is not executable by itself.**

它必须绑定到 Agent Runtime 并经过 Materialization 才形成 Runnable Subject。

### 1.4 Harness Patch

把 harness 设计写入 runtime 的实际工程改动。可能形态：

- prompt 文件 patch（替换 `prompts/system.md`）
- config 文件（覆盖 `config/tools.yaml`）
- workflow / tool 配置（追加新工具）
- memory / retrieval 配置
- code patch（diff/patch 文件）
- environment variables（启动时注入）
- start command（替换默认启动命令）

Patch 的存放约定：variant 文件里**声明** patch 的逻辑名称和应用方式，patch 内容存在 variant 同级或独立目录。具体文件格式见 §4。

### 1.5 Runtime Adapter

`connect.md` 的进化版。Adapter 知道**对于这种类型的 runtime source，如何 materialize → start → connect**。它替代当前 `agentconn.py` 里硬编码的四种接入方式。

Adapter 的接口（抽象）：

```python
class RuntimeAdapter:
    def materialize(self, source: RuntimeSource, patch: HarnessPatch) -> Sandbox: ...
    def start(self, sandbox: Sandbox) -> AgentSession: ...
    def snapshot(self, sandbox: Sandbox) -> RuntimeSnapshot: ...
    def teardown(self, sandbox: Sandbox) -> None: ...
```

不同 runtime source 对应不同 adapter 实现（见 §3）。

### 1.6 Sandbox / Materialized Sandbox

一次实验中某个 harness variant 的隔离运行环境。Sandbox 包含：

- materialized 目录 / 容器 / 远端 session
- 经 patch 应用后的实际文件 / 配置
- 启动元数据（command、env）
- 唯一 sandbox id

不同 variant 在不同 sandbox 跑，避免 prompt / config 串线、memory 污染、cache 污染、log 混淆。

### 1.7 Runtime Snapshot

「这次实验实际跑了什么」的可复现记录。落盘格式见 §5。

---

## 2. 整体流程

加入 Materialization 后，`ahl run` 的内部流程：

```
ahl run <experiment>
   │
   ├─ load program / harnesses / cases / rubric
   ├─ resolve runtime source（实验级 or variant 级）
   │
   for each (variant, case):
   │
   ├─ 1. Materialize
   │     adapter.materialize(source, variant.patch) → sandbox
   │
   ├─ 2. Snapshot
   │     adapter.snapshot(sandbox) → runtime_snapshot.json
   │     存进 results/snapshots/<run_id>/<variant>/
   │
   ├─ 3. Start + Connect
   │     adapter.start(sandbox) → agent_session
   │
   ├─ 4. Run（多轮对话，跟当前一样）
   │     run_agent_session(session, opening, simulator, max_turns)
   │     → transcript
   │
   ├─ 5. Teardown
   │     adapter.teardown(sandbox)
   │
   └─ 6. 记录 run result + snapshot reference
         results/run-*.json 里每条 transcript 引用 snapshot_id
```

关键点：

- **每个 (variant, case) 起一次 sandbox**——不复用，确保隔离。优化（reuse warm sandbox per variant）留到性能阶段。
- **Snapshot 在 materialize 后立即采**——记录的是"这次跑用的 variant + source 的实际状态"，不是设计意图。
- **Run result 引用 snapshot id**——证据链 `transcript → snapshot → variant + source + patch hash` 完整可追溯。

---

## 3. 5 种 Source 的 Materialization Strategy

| Runtime Source | Materialize Strategy | Sandbox 形态 | Snapshot 记什么 |
|---|---|---|---|
| `local_path` | `copy_dir(source, tmpdir)` + `apply_patch(tmpdir, patch)` | 临时目录 | `path` + `dir_hash` + `patch_hash` |
| `git_repo` | `git clone <url> --branch <ref>` 或 `git worktree add` + checkout commit + apply patch | git worktree / 临时 clone | `repo_url` + `commit_sha` + `patch_hash` |
| `docker_image` | `docker run -d --name <sandbox_id> -v <patch_mount>:/harness <image>` | 隔离容器 | `image_digest` + `container_id` + `mount_paths` + `patch_hash` |
| `remote_api` | "逻辑 sandbox"：配置 / session / model version 在 client 端固定，不真起进程 | 客户端 session 包 | `endpoint` + `model_version` + `system_prompt_hash` + `tool_config_hash` |
| `dev_agent` | dev-machine sandbox：workspace branch 切换 / session isolation；不杀宿主 agent | 宿主上的隔离 session | `agent_name` + `session_id` + `workspace_branch` + `patch_hash` |

### 3.1 local_path 细节

最简单的策略：拿 source 目录 copy 一份到 `sandbox/<run_id>/<variant_id>/`，把 patch 应用上去，再用 `start_command` 启起来。

适合：你已经把 agent 项目 checkout 到本地，想快速试几个 prompt / config variant。

风险：copy 大目录慢；node_modules / venv 这类生成物要排除。建议加 `.harness-ignore` 约定。

### 3.2 git_repo 细节

两种实现：

- **Clone 模式**：`git clone <url> --branch <ref>`，到 `sandbox/<run_id>/<variant_id>/`。每个 variant 一份完整 clone——空间开销大但隔离最干净。
- **Worktree 模式**：`git worktree add sandbox/<run_id>/<variant_id> <ref>`。共享 `.git`，只 checkout 一份 working tree——空间省、起 sandbox 快。**推荐默认用这种**。

Patch 应用：apply 一个 patch 文件 / 替换若干文件 / 注入 env vars，按 variant 声明的方式来。

### 3.3 docker_image 细节

`docker run -d --name <sandbox_id> -v <patch_dir>:/harness <image>`。Patch 通过 mount 注入，不打新 image。

适合：harness base 本身已经打成 image（OpenManus 等），你只改 prompt / config。

风险：image 大、pull 慢；网络依赖。建议加 image cache 约定。

### 3.4 remote_api 细节

最特殊的一种——**没有真物理 sandbox**。"Materialize" 在客户端构造一个 session 对象，记下 endpoint、model version、system prompt、tool config 等。每个 variant 是一份不同的 session 配置。

适合：你测的是托管 LLM（GPT / Claude API）+ 不同 system prompt / tool config。

限制：snapshot 不能记 runtime 物理状态，只能记客户端配置——服务端的模型更新、平台改动你抓不到。Snapshot 里要老实记`(captured_at, endpoint, model_version)`，方便事后判断证据等级。

### 3.5 dev_agent 细节

最复杂的一种——你的 runtime 是**你正在用的开发机 agent**（如本机 Claude Code 实例），不能为它起独立进程，但你想试不同 harness 配置对它的影响。

策略：通过 workspace branch / session isolation，让宿主 agent 在隔离的工作目录 / session 下跑每个 variant。Patch 落在 workspace 配置（如 `.claude/` 目录）而非宿主 agent 二进制。

适合：dogfood——你用 Claude Code 测 Claude Code 的不同 harness 配置。

风险：宿主 agent 状态可能被污染；snapshot 难以完整。建议这种 source 的实验结果**默认证据等级降一档**。

---

## 4. 文件格式（草案）

### 4.1 工作目录根：`runtime-sources.md`（或 `connect.md` 的进化版）

声明本工作目录里可用的 runtime sources。一个 source 一段：

```markdown
# runtime sources

## openmanus-main
type: git_repo
url: https://github.com/.../openmanus.git
ref: main

## local-aider
type: local_path
path: <home>/projects/aider

## gpt-4-api
type: remote_api
endpoint: https://api.openai.com/v1
model: gpt-4-turbo
```

实验里的 variant 通过名字引用 source（见 §4.2）。

向后兼容：当前 `connect.md` 可视为 "default source + 启动配置" 的简化形态；Lab 同时识别两种，渐进迁移。

### 4.2 实验内：`harnesses/V*.md`（在现有格式上扩展）

当前 v1 的 variant 文件包含 `id` / `基线` / `这是什么` / 可选的 `类型` / `配置`。Materialization 阶段加：

```markdown
---
id: V2
基线: 否
runtime_source: openmanus-main           # 引用 §4.1 的 source 名
---

## 这是什么
把 system prompt 改成更激进的探索风格。

## Patch
- prompt: ./patches/V2/system.md           # 替换 source 里的 prompts/system.md
- config: ./patches/V2/tools.yaml          # 覆盖 config/tools.yaml
- env:
    HARNESS_MAX_DEPTH: 5

## 启动
command: python -m openmanus.agent
```

`runtime_source` 字段是新加的。`类型` / `配置` 段当 `runtime_source` 不写时仍按 v1 解析（向后兼容）。

### 4.3 Snapshot：`results/snapshots/<run_id>/<variant_id>/snapshot.json`

```json
{
  "snapshot_id": "snap-20260521-103045-V2",
  "run_id": "run-20260521-103045",
  "variant_id": "V2",
  "experiment": "001-greedy-explorer",
  "created_at": "2026-05-21T10:30:45Z",
  "runtime_source": {
    "type": "git_repo",
    "url": "https://github.com/.../openmanus.git",
    "ref": "main",
    "commit_sha": "abc123..."
  },
  "harness_patch": {
    "applied": [
      {"path": "prompts/system.md", "patch_file": "patches/V2/system.md", "hash": "sha256:..."},
      {"path": "config/tools.yaml", "patch_file": "patches/V2/tools.yaml", "hash": "sha256:..."}
    ],
    "env": {"HARNESS_MAX_DEPTH": "5"},
    "patch_hash": "sha256:..."
  },
  "sandbox": {
    "type": "git_worktree",
    "path": "sandbox/run-20260521-103045/V2",
    "start_command": "python -m openmanus.agent"
  },
  "environment": {
    "python_version": "3.11.5",
    "os": "Linux 6.5.0",
    "dependencies_lockfile_hash": "sha256:..."
  }
}
```

### 4.4 Run result 引用 snapshot

`results/run-*.json` 里每条记录加 `snapshot_id`：

```json
{
  "version_id": "V2",
  "case_id": "D-01",
  "snapshot_id": "snap-20260521-103045-V2",
  "transcript": [...]
}
```

这样从 compare 报告往回追，可一路定位到「这分数是基于哪一份 source + patch 跑出来的」。

---

## 5. Snapshot 字段清单

完整字段：

| 字段 | 含义 |
|---|---|
| `snapshot_id` | 唯一 id（推荐 `snap-<timestamp>-<variant>`） |
| `run_id` | 所属 run |
| `variant_id` | 对应 harness variant |
| `experiment` | 所属实验 |
| `created_at` | UTC ISO 时间戳 |
| `runtime_source.type` | local_path / git_repo / docker_image / remote_api / dev_agent |
| `runtime_source.url` / `path` / `image` / `endpoint` / `agent_name` | 类型相关 |
| `runtime_source.commit_sha` / `image_digest` / `model_version` / `session_id` | 类型相关，决定可复现性 |
| `harness_patch.applied[]` | patch 文件清单 + 各自 hash |
| `harness_patch.env` | 注入的环境变量 |
| `harness_patch.patch_hash` | 整体 patch 内容的 hash |
| `sandbox.type` | copy_dir / git_worktree / docker_container / api_session / dev_session |
| `sandbox.path` / `container_id` / `session_id` | sandbox 实例标识 |
| `sandbox.start_command` | 启动命令 |
| `environment.python_version` / `os` / `dependencies_lockfile_hash` | 环境元数据，能记多全记多全 |

Snapshot 字段在不同 source 类型下不全是必填——能记多全记多全，记不到的字段（如 remote_api 的服务端状态）老实留空。

---

## 6. 与现有代码的过渡

当前 v1 / v2-minimal 的 `connect.md` + `version.connect` 字段不会立刻被废弃。过渡分两档：

### 6.1 短期（v2-minimal 稳定阶段）

- `connect.md` / `version.connect` 继续工作，不变。
- 新加 `harnesses/V*.md` 的可选字段 `runtime_source` + `## Patch` 段——**不写**时按 v1 解析，**写了**时走 materialization 路径。
- 一个 `RuntimeAdapter` 注册表：v1 的四种接入方式（进程内库 / 外部命令行 / HTTP无状态 / HTTP有状态）注册成 4 个 adapter，行为跟当前 `agentconn.py` 一样。
- 新增 5 种 materialization adapter 后，工作目录可同时有"老 connect 风格"的实验和"新 source + patch 风格"的实验。

### 6.2 长期（materialization 稳定后）

- `connect.md` 演变为 `runtime-sources.md`。
- 旧 `connect.md` 形态作为 `local_path` source + 一份默认启动配置的特例保留。
- v1 四种接入降级为"无 materialization 的 adapter"（即 materialize 是 no-op，直接 start）。

---

## 7. 不做的（明确边界）

为防止这一档膨胀，先列**不做**：

- **不做** harness patch 的 DSL——patch 就是文件替换 / env 注入 / 启动命令覆盖，不发明 templating 语言。
- **不做** 跨 source 的 harness 复用（"把这个 prompt patch 同时应用到 git 和 docker source"）——variant 一次只绑一个 source。
- **不做** sandbox warm pool / 并行执行优化——先做 correctness，性能后说。
- **不做** snapshot 之间的 diff / 可视化工具——先把数据老实记下来，工具后说。
- **不做** distributed sandbox（多机调度）——单机够用。
- **不做** Claude Code / Cursor 这类外层 coding agent 的 dogfood adapter 的稳定版——`dev_agent` source 是实验性的，证据等级降一档。

---

## 8. 阶段化交付

实装时建议分三档：

**M1:MVP (local_path + git_repo)** ✅ **已实现 (v0.3.0, 2026-05-23)**
- 两种最常用 source 各起一个 adapter (`LocalPathAdapter` / `GitRepoAdapter`)。
- Snapshot 落盘 (含 source_dir_hash / patch_hash / commit_sha 可复现指纹) +
  run-*.json 引用 snapshot_id。
- 现有 4 种 connect 接入注册为 `LegacyAdapter` 保持 v0.2.0 行为 100% 等价。
- e2e 测试覆盖 legacy / local_path / git_repo 三 path,208 tests 全绿
  (含 `-W error::ResourceWarning` strict 模式)。
- 实现合同见 `runtime-materialization-m1-spec.md`,M1 偏离 spec 处:
  git_repo 走 clone mode (sandbox.type=`git_clone`) 而非 spec 的 worktree mode
  (worktree 留 M2+ 优化)。

**M2：docker_image + remote_api**
- 容器化 / API source 的 adapter。
- Remote_api 的 snapshot 字段做好"无法记物理状态"的明示。

**M3：dev_agent**
- 最复杂的 source，留到 M1 / M2 上线、materialization 概念在用户里站住之后再做。
- 同时为 Auto Mode（`design-v0.4.1.md` §9 的 v3）准备。

**每档独立可发布**——不强求一次性把 5 种 source 都做完。

---

## 9. 跟旧文档的关系

- `design-v0.3.md` §3.1（环境分五层）的思想在本文延续——"能快照多完整"对应不同 source 类型的 snapshot 字段完整度。
- `design-v0.4.1.md` §7（artifact provenance + run provenance）的 run_provenance schema 在本文具体化为 snapshot 字段。
- 本文取代了 `design-v0.4.1.md` 里"sandbox / 环境快照"的零散描述（散在 §6 / §10）。

---

## 10. 一句话

> **Materialization 是把一份 harness variant 应用到一个具体 runtime、在隔离环境里起一个可运行实例的过程；Snapshot 是这次实例的可复现指纹。两者一起把 Agent Harness Lab 从"对裸 agent 喂话"升级为"对一份明确的 harness × runtime 组合负责"。**
