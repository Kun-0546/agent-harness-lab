# Agent Harness Lab · Runtime Materialization M1 Implementation Spec

> 本文是 **M1 的实现 spec** —— 把 `docs/runtime-materialization.md`(总 spec)的 §8 M1
> 落到代码层的逐字段、逐文件、逐 commit 的可执行 plan。总 spec 是设计意图,本文是
> 实现合同(implementation contract)。
>
> Target: **v0.3.0** | Branch: **`runtime-materialization-mvp`**
> Date: 2026-05-22
> Status: **spec 阶段(代码未实现);C1 commit 把本 spec 落盘 + 后续 C2-C7 实现**

---

## 0. 范围与边界(spec 固定)

### 0.1 M1 只做

- ✅ `local_path` source
- ✅ `git_repo` source
- ✅ legacy connect no-materialize adapter(包 v0.2.0 的 `agentconn` 4 种接入)
- ✅ materialize → sandbox → snapshot 三段管线
- ✅ run result 引用 `snapshot_id`
- ✅ v0.2.0 行为 100% 兼容(legacy path)

### 0.2 M1 不做(明确禁止 / 留后续档)

- ❌ `docker_image` / `remote_api` / `dev_agent` source(留 M2 / M3)
- ❌ Auto Mode / approval gates
- ❌ calibration / self-improving loop
- ❌ direct / replay run mode(only `simulated` 已有)
- ❌ `ahl sources` 子命令(留 M1.1 单独决定)
- ❌ **experiment-level** `runtime_source`(只支持 variant-level)
- ❌ sandbox warm pool / 并行优化(M2+)
- ❌ patch DSL / templating
- ❌ snapshot diff / 可视化工具

---

## 1. 文件格式草案

### 1.1 `runtime-sources.md`(workspace 根,可选文件)

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

**约束**:

- 二级 heading `## <name>` = source name(必 unique)
- `type:` ∈ `{local_path, git_repo}`(M1 范围;其它 type 抛 `ValueError`)
- `local_path` 必须 `path:`
- `git_repo` 必须 `url:` + `ref:`(ref 可为 commit / branch / tag)
- 文件不存在 OK(所有实验走 legacy);存在但 0 个 source → 抛错(避免空文件 misleading)
- 不识别的字段:忽略 + warning(不抛错)
- 跟 `connect.md` 在同一层(workspace 根);不放进 experiment 目录

### 1.2 `harnesses/V*.md` 新增字段(向后兼容)

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

**约束**:

- **`runtime_source:` 是 frontmatter 可选字段**
  - 不写 → variant 走 legacy(用 connect.md + agentconn)
  - 写了但 source 名不在 `runtime-sources.md` → 抛 `WorkflowError`
- **`## Patch` 段**(仅当 `runtime_source` 写了才解析;否则忽略),YAML-like 结构:
  - `files:` 列表,每项含:
    - `target:` 相对 source root 的目标位置(将被 patch 覆盖)
    - `source:` 相对 experiment 根的 patch 内容路径(通常 `patches/<variant_id>/`)
  - `env:` map,key:value 形式注入环境变量(value 用字符串避免类型歧义)
  - `start_command:` 覆盖 source 默认启动命令(必填;M1 不假设默认命令)
- **v1 字段 `类型` / `配置` 段**:仅当 `runtime_source` 不写时按 v1 解析(legacy 路径)

**patches 文件存放**:`experiments/<id>/patches/<variant_id>/<filename>`。
纯文本,整文件替换 source 里对应路径的文件。不解析 patch 内容,直接 `shutil.copy()` 覆盖。

### 1.3 不在 M1 范围的文件格式

- `program.md` 不动(实验级 runtime_source 不支持)
- `simulator.md` / `rubric.md` / `cases/D*.md` 不动
- `brief.md` / `connect.md` / `goal.md` 不动

---

## 2. snapshot.json schema

路径:`experiments/<id>/results/snapshots/<run_id>/<variant_id>.json`

### 2.1 Materialized path(`runtime_source` 写了)

**runtime_source 必填的可复现指纹**:
- `source_dir_hash` (local_path / git_repo 共有):**apply patch 之前**对 raw
  source 目录算的 sha256(算法见 `src/agent_harness_lab/hash_utils.py`)。
  忽略 `.git` / `.venv` / `__pycache__` / `node_modules` / `.idea` / `.vscode` /
  `.pytest_cache` / `*.pyc` / `*.pyo` / `.DS_Store` / `Thumbs.db`。
- `commit_sha` (仅 git_repo,C6 实现):checkout 的 commit hash
- `harness_patch.patch_hash`:patch files + env + start_command 的整体 hash

只记 path / url 不算 reproducible —— 必须有 source_dir_hash + patch_hash 才能
"在另一台机器上重放出等价 sandbox 状态"。

#### 2.1.1 local_path (C5)

```json
{
  "snapshot_id": "snap-<run_id>-<variant_id>",
  "run_id": "run-20260522-103045",
  "variant_id": "V2",
  "experiment": "001-greedy-explorer",
  "created_at": "2026-05-22T10:30:45Z",

  "runtime_source": {
    "type": "local_path",
    "name": "local-aider",
    "path": "<home>/projects/aider",
    "source_dir_hash": "sha256:<raw source pre-patch 的 dir hash>"
  },

  "harness_patch": {
    "applied": [
      {"target_path": "prompts/system.md", "source_path": "patches/V2/system.md", "hash": "sha256:..."}
    ],
    "env": {"HARNESS_MAX_DEPTH": "5"},
    "start_command": "python agent.py",
    "patch_hash": "sha256:<sorted files + env + start_command 的 hash>"
  },

  "sandbox": {
    "type": "copy_dir",
    "path": "sandbox/run-20260522-103045/V2",
    "start_command": "python agent.py"
  },

  "environment": {
    "python_version": "3.14.0",
    "os": "Windows-10.0.26200",
    "captured_at": "2026-05-22T10:30:45Z"
  }
}
```

#### 2.1.2 git_repo (C6)

**实现策略:clone mode** —— 每 variant `git clone <url> <sandbox>` + `git checkout
<ref>` (worktree mode 留 M2+ 优化,共享 bare cache)。`sandbox.type = "git_clone"`。

```json
{
  "snapshot_id": "snap-<run_id>-<variant_id>",
  "run_id": "run-20260522-103045",
  "variant_id": "V2",
  "experiment": "001-greedy-explorer",
  "created_at": "2026-05-22T10:30:45Z",

  "runtime_source": {
    "type": "git_repo",
    "name": "openmanus-main",
    "url": "https://github.com/.../openmanus.git",
    "ref": "main",
    "commit_sha": "abc123def456...",
    "source_dir_hash": "sha256:<checkout 后 pre-patch dir hash>"
  },

  "harness_patch": {
    "applied": [
      {"target_path": "prompts/system.md", "source_path": "patches/V2/system.md", "hash": "sha256:..."},
      {"target_path": "config/tools.yaml", "source_path": "patches/V2/tools.yaml", "hash": "sha256:..."}
    ],
    "env": {"HARNESS_MAX_DEPTH": "5"},
    "start_command": "python -m openmanus.agent",
    "patch_hash": "sha256:<all-files+env+start-cmd 的整体 hash>"
  },

  "sandbox": {
    "type": "git_clone",
    "path": "sandbox/run-20260522-103045/V2",
    "start_command": "python -m openmanus.agent"
  },

  "environment": {
    "python_version": "3.14.0",
    "os": "Windows-10.0.26200",
    "captured_at": "2026-05-22T10:30:45Z"
  }
}
```

### 2.2 Legacy path(`runtime_source` 未写)

```json
{
  "snapshot_id": "legacy",
  "run_id": "run-20260522-103045",
  "variant_id": "V2",
  "experiment": "001-old",
  "created_at": "2026-05-22T10:30:45Z",

  "runtime_source": {
    "type": "legacy_connect",
    "connect_md_hash": "sha256:..."
  },
  "harness_patch": null,
  "sandbox": null,
  "environment": {
    "python_version": "3.14.0",
    "os": "Windows-10.0.26200",
    "captured_at": "2026-05-22T10:30:45Z"
  }
}
```

**legacy path 也写 snapshot.json** —— 保持证据链统一,字段精简。

### 2.3 不在 M1 字段(留 M2+)

- `dependencies_lockfile_hash`(总 spec §5)
- `harness_base` 元数据
- runtime image digest / container_id(docker_image)
- model_version / endpoint(remote_api)

---

## 3. run result 增量字段

`experiments/<id>/results/run-<timestamp>.json` 每条 record 加 **`snapshot_id`**:

**Materialized**:
```json
{
  "version_id": "V2",
  "case_id": "D-01",
  "snapshot_id": "snap-20260522-103045-V2",
  "transcript": [...]
}
```

**Legacy**:
```json
{
  "version_id": "V2",
  "case_id": "D-01",
  "snapshot_id": "legacy",
  "transcript": [...]
}
```

**其他字段不动**。`results/run-*.json` 顶层结构不变。

**spec 固定**:legacy path `snapshot_id` = **`"legacy"`**(字符串,不是 null)。
tests 用 `assertEqual(snapshot_id, "legacy")` 验。

---

## 4. Legacy behavior(向后兼容契约)

### 4.1 触发条件

variant 的 `harnesses/V*.md` frontmatter **没有 `runtime_source` 字段**。

### 4.2 行为契约(与 v0.2.0 完全等价 + 两个新增)

| 阶段 | v0.2.0 | v0.3.0 legacy path |
|------|--------|---------------------|
| Parse V*.md | `Version(id, baseline, connect, ...)` | + `runtime_source=None`, `patch=None` |
| Build session | `agentconn.open_session(connect)` | `LegacyAdapter.start()` → `agentconn.open_session(connect)` |
| Run transcript | `runner.run_experiment(session)` | 不变 |
| Persist run | `results/run-*.json`(无 snapshot_id) | **+ `snapshot_id: "legacy"`** |
| Persist snapshot | n/a | **+ `results/snapshots/<run_id>/<variant_id>.json` (精简字段)** |

### 4.3 不强迫迁移

- 老用户不改任何文件,v0.3.0 行为 = v0.2.0 + 多两个字段(run-*.json 的 `snapshot_id`、`snapshots/` 目录)
- 工作目录可以**混合**:一些 variant 用 runtime_source(materialized),另一些不用(legacy)
- `runtime-sources.md` 不存在 → 所有 variant 必须 legacy(强制)
- `runtime-sources.md` 存在 → variant 可选用任一 source 或不用(legacy)

### 4.4 兼容性强约束

**现有 57 tests 必须保持全 OK**。特别是 `test_e2e.py` 用 connect.md type=外部命令行 跑实验 → 走 LegacyAdapter → 结果跟 v0.2.0 行为等价(多 `snapshot_id="legacy"` 字段不影响 assert)。

---

## 5. Test matrix

| # | 测试点 | 测试文件 | source 类型 | 备注 |
|---|--------|----------|-------------|------|
| 1 | parse runtime-sources.md(local_path + git_repo 混合) | test_runtime_source | both | |
| 2 | parse runtime-sources.md 缺 path / 缺 url / unknown type | test_runtime_source | - | 抛 ValueError |
| 3 | parse runtime-sources.md 文件不存在 → 返回空 list | test_runtime_source | - | 不抛错 |
| 4 | parse V*.md with runtime_source | test_version(扩) | both | |
| 5 | parse V*.md without runtime_source = legacy | test_version(现有) | legacy | 加 `runtime_source is None` assert |
| 6 | parse Patch 段(files + env + start_command) | test_patch | both | |
| 7 | V*.md runtime_source 写了但 source 不在 .md → WorkflowError | test_workflow(扩) | both | 在 preflight 抓 |
| 8 | local_path materialize:复制 + apply patch | test_materialize_local_path | local_path | |
| 9 | local_path snapshot:dir_hash + patch_hash | test_materialize_local_path | local_path | |
| 10 | local_path teardown:默认 keep, `--cleanup-sandboxes` 删 | test_materialize_local_path | local_path | |
| 11 | git_repo materialize:worktree + ref checkout + patch | test_materialize_git_repo | git_repo | 本地 `git init` mock |
| 12 | git_repo snapshot:commit_sha + patch_hash | test_materialize_git_repo | git_repo | |
| 13 | git_repo teardown:默认 keep, `--cleanup-sandboxes` worktree remove | test_materialize_git_repo | git_repo | |
| 14 | legacy materialize:no-op | test_materialize_legacy | legacy | sandbox.type="legacy", path=None |
| 15 | legacy start:等同 v1 agentconn.open_session | test_materialize_legacy | legacy | |
| 16 | legacy snapshot:connect_md_hash | test_materialize_legacy | legacy | |
| 17 | Snapshot JSON 序列化/反序列化 | test_snapshot | all | |
| 18 | run result 加 snapshot_id(legacy = "legacy") | test_workflow(扩) | legacy | |
| 19 | run result 加 snapshot_id(materialized) | test_e2e_materialize | git_repo | |
| 20 | materialize 失败 → hard fail run(WorkflowError, 结构化信息) | test_materialize_* | both | 不 skip case |
| 21 | **E2E:git_repo source × 2 variant × 1 case, run/score/compare 跑通** | test_e2e_materialize | git_repo | 本地 mock repo |
| 22 | **现有 57 tests 全 OK** | (all existing) | legacy | 不动 setup, 加 `snapshot_id="legacy"` assert(或 ignore) |

**总测试数预计**:57(现有) + ~25(新增) = ~82 tests。

**git_repo 测试网络隔离**:
```python
import tempfile, subprocess
with tempfile.TemporaryDirectory() as repo:
    subprocess.run(["git", "init", repo], check=True)
    # write file + commit
    url = f"file://{repo}"   # 用 file:// 协议,无网络
```

---

## 6. 分阶段 commit plan

按主题分 7 commits(在 `runtime-materialization-mvp` 分支)。每 commit 后
`compileall` + `pytest` 必须 pass。

| # | Subject | 内容 | 安全 checkpoint |
|---|---------|------|------|
| **C1** | `docs: add v0.3.0 M1 implementation spec` | 本 spec 落到 `docs/runtime-materialization-m1-spec.md` | 文档 only,无 risk |
| **C2** | `feat(parser): runtime_source.py + patch.py + V*.md ext` | runtime_source / patch parser + V*.md frontmatter 扩展。tests 4/5/6/7。**legacy 全绿** | parser 仅扩字段,不动行为 |
| **C3** | `refactor: RuntimeAdapter abstraction + LegacyAdapter` | RuntimeAdapter 抽象基类 + 注册表 + LegacyAdapter wrap agentconn。改 workflow.py 用 adapter dispatch(仅 legacy 路径),改 runner.py 接受 AgentSession。**现有 57 tests 全绿**(这是 refactor,行为不变) | 关键 checkpoint:legacy 完全等价 |
| **C4** | `feat(snapshot): RuntimeSnapshot + persistence + run-id->snapshot-id` | snapshot.py + workflow 写 snapshots/ 目录 + run-*.json 加 snapshot_id。legacy path 写 `snapshot_id: "legacy"`。tests 17/18/22 | snapshot 加字段,legacy 行为不变(仅多两个产出) |
| **C5** | `feat(materialize): local_path adapter` | LocalPathAdapter + tests 8/9/10/20 | local_path materialize 上线 |
| **C6** | `feat(materialize): git_repo adapter (clone mode)` ✅ | GitRepoAdapter (clone + checkout + commit_sha + source_dir_hash 跟 C5 一致) + tests 11/12/13/20 + e2e 21/19。worktree mode 留 M2+ 优化(spec 原案是 worktree,实际选 clone 是因为 simpler + sandbox 隔离 strong) | git_repo materialize 上线 + e2e 验证 |
| **C7** | `feat(cli): --cleanup-sandboxes flag + docs` | cli.py 加 flag, docs/file-formats.md + runtime-materialization.md 标 M1 实现, product-definition.md 更新 | docs 收尾 + flag |

**M1 release 时**:merge `runtime-materialization-mvp` → `main`,打 `v0.3.0` annotated tag,
release note 同时补 v0.2.0 留下的 release note(一并发)。

**Failure / rollback**:每 commit 独立可 revert。C3 必须保持 legacy 行为不变是关键
门槛 —— 如果 C3 把 57 tests 跑挂,rollback to C2 + 重做 refactor。

---

## 7. 数据结构(最小集)

```python
# src/agent_harness_lab/runtime_source.py

from dataclasses import dataclass
from typing import Literal
from pathlib import Path

@dataclass
class RuntimeSource:
    name: str                                      # e.g. "openmanus-main"
    type: Literal["local_path", "git_repo"]        # M1 范围
    config: dict                                   # local_path: {"path"}; git_repo: {"url", "ref"}


# src/agent_harness_lab/patch.py

@dataclass
class PatchFile:
    target_path: str                               # 相对 source root
    source_path: Path                              # patch 内容绝对路径
    hash: str                                      # sha256:...

@dataclass
class HarnessPatch:
    files: list[PatchFile]
    env: dict[str, str]
    start_command: str | None


# src/agent_harness_lab/materialize/__init__.py

from typing import Protocol

@dataclass
class Sandbox:
    type: str                                      # "copy_dir" | "git_worktree" | "legacy"
    path: Path | None                              # None for legacy
    start_command: str | None
    metadata: dict

class RuntimeAdapter(Protocol):
    def materialize(self, source, patch, run_id, variant_id) -> Sandbox: ...
    def start(self, sandbox) -> "AgentSession": ...
    def snapshot_fields(self, source, patch, sandbox) -> dict: ...
    def teardown(self, sandbox) -> None: ...


# src/agent_harness_lab/snapshot.py

@dataclass
class RuntimeSnapshot:
    snapshot_id: str                               # "snap-<run_id>-<variant_id>" or "legacy"
    run_id: str
    variant_id: str
    experiment: str
    created_at: str                                # UTC ISO
    runtime_source: dict
    harness_patch: dict | None                     # None for legacy
    sandbox: dict | None                           # None for legacy
    environment: dict                              # python_version, os, captured_at
```

`AgentSession` 复用现有 `agentconn.py` 接口(receive/send/close),不改。

---

## 8. 文件影响面

### 8.1 新文件(14 个)

| 路径 | 作用 |
|------|------|
| `src/agent_harness_lab/runtime_source.py` | `runtime-sources.md` parser + `RuntimeSource` dataclass |
| `src/agent_harness_lab/patch.py` | `## Patch` 段 parser + `HarnessPatch` / `PatchFile` + 应用逻辑 |
| `src/agent_harness_lab/snapshot.py` | `RuntimeSnapshot` dataclass + JSON I/O + 持久化 |
| `src/agent_harness_lab/materialize/__init__.py` | `RuntimeAdapter` 抽象 + `Sandbox` + 注册表 + dispatch |
| `src/agent_harness_lab/materialize/local_path.py` | `local_path` adapter(copy_dir + apply patch) |
| `src/agent_harness_lab/materialize/git_repo.py` | `git_repo` adapter(worktree mode 默认) |
| `src/agent_harness_lab/materialize/legacy.py` | `connect.md` → no-materialize adapter |
| `tests/test_runtime_source.py` | parser unit tests |
| `tests/test_patch.py` | patch parser tests |
| `tests/test_materialize_local_path.py` | local_path materialize + snapshot + teardown |
| `tests/test_materialize_git_repo.py` | git_repo(本地 `git init` mock repo) |
| `tests/test_materialize_legacy.py` | legacy adapter 与 v0.2.0 等价性 |
| `tests/test_snapshot.py` | RuntimeSnapshot 序列化 |
| `tests/test_e2e_materialize.py` | git_repo × 2 variant × 1 case 端到端 |

### 8.2 改动文件(8 个)

| 路径 | 改动 |
|------|------|
| `src/agent_harness_lab/version.py` | `Version` dataclass 加 `runtime_source: str \| None` + `patch: HarnessPatch \| None`;parser 识别新字段 |
| `src/agent_harness_lab/agentconn.py` | 拆出 `open_session` 给 LegacyAdapter 用;原 4 种接入实现移到 `materialize/legacy.py` 或保留导入 |
| `src/agent_harness_lab/workflow.py` | `run()` 加 4 步:resolve source → materialize → snapshot → start → run → teardown |
| `src/agent_harness_lab/runner.py` | 接受 `AgentSession`(来自 adapter.start),不再直接拿 connect |
| `src/agent_harness_lab/cli.py` | 加 `--cleanup-sandboxes` flag 到 `ahl run` |
| `docs/file-formats.md` | 加 `runtime-sources.md` 格式 + `V*.md` 的 `runtime_source` 字段 + `## Patch` 段(含 files / env / start_command) |
| `docs/runtime-materialization.md` | §8 M1 标"已实现";§3 表的 local_path/git_repo 行加状态标 |
| `docs/product-definition.md` | §8 "下一阶段核心" 加 "M1 已实现" 状态 |

### 8.3 不动文件

- `program.md` / `simulator.md` / `rubric.md` / `cases/D*.md` 格式 parser
- `ahl init` / `new` / `draft` / `review` 行为
- `brief.md` parser / writer

---

## 9. 边界 reminder

**最容易被踩的边界**:

1. **C3 之后必须 57/57 全绿** —— 这是 legacy 完全等价的硬验证。绿了再进 C4
2. **legacy path 也写 snapshot.json** —— 不是 v0.2.0 行为的最小增量,这是 spec 固定;tests 18 验证
3. **`runtime_source` 不写 = legacy** —— parser 不抛错,默认走老路
4. **`## Patch` 段在 legacy 路径下被忽略** —— 不解析就不解析,不抛错
5. **sandbox 默认 keep** —— `--cleanup-sandboxes` 是 opt-in
6. **物理 sandbox vs snapshot metadata 分目录**
   - 物理:`sandbox/<run_id>/<variant_id>/`
   - metadata:`results/snapshots/<run_id>/<variant_id>.json`
7. **materialize 失败 = hard fail** —— 整个 run 抛 WorkflowError,不 skip 某 (variant, case)
