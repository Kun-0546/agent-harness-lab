# Runtime Probe MVP · v0.6 Spec

> 这份 spec 定义 Agent Harness Lab 的 v0.6 **Runtime Probe MVP** —— 在
> `ahl run` 之前(或独立调用)对每个 variant 做一次**只读**的 runtime + harness
> 现状检查,把"实际能跑吗 / 实际装上了什么"从推断变成实测,并(对 legacy
> 连接路径)自动把可用证据落到 `materials/*-evidence.md`,让 v0.4 evidence
> 链原地升级。
>
> Status: target v0.6.0,branch `v0.6.0-planning`。**spec lock-in only — 代码
> 尚未实现**。
> Date: 2026-05-26。
> 上游约束:Kun 标准 redlines + Kun 初步偏好 "Option C 最小化"(`ahl probe`
> 新 CLI + `ahl review` 只显示已有 probe artifact,不自动跑 probe)。
>
> 本文是 `product-walkthrough.md` **Step 6.5 (probe runtime readiness)**
> 的 depth-detail。还没读 walkthrough 的从
> [`product-walkthrough.md`](product-walkthrough.md) 起。可运行 sample:
> [`examples/sample-workspace/`](../examples/sample-workspace/) —
> `ahl probe 001` 对两 variant 跑只读 readiness 检查,产物落到
> `probe-results/probe-*/V*.json`。

---

## 1. Purpose

v0.3.0 给了 runtime materialization(snapshot 后说"刚才跑了什么");
v0.4 给了 evidence 推断;v0.5 给了 harness package。所有 evidence 都是
**post-hoc 从 snapshot 推断**或**用户手写 `materials/*-evidence.md` 补充**
得来的。

v0.6 Runtime Probe 加一个 **pre-run 的、只读的、显式触发的 inspection 步骤**:

> 在跑 cases 之前,对每个 variant 主动检查 runtime / package / start_command
> 是否实际就位,把检查结果落成结构化 artifact;对 legacy_connect variant 还可
> 选地把捕获到的现状直接写成 `materials/*-evidence.md`,让 v0.4 evidence 自动
> 升级。

核心一句话:

> Probe 不修改任何 runtime / sandbox / config,只观察并记录;它把 "evidence"
> 这条信息流从"做完事之后推断"变成"做事之前先观察",并提供一条 explicit
> 命令 `ahl probe <experiment>` 给用户在 keep/discard 决策前补强证据。

---

## 2. Product problem

当前几个明确的痛点:

1. **legacy_connect variant 默认 weak**:用户要手写
   `materials/runtime-evidence.md` / `harness-evidence.md` /
   `cloud-evidence.md` 才能升 medium。门槛高、容易忘。
2. **Cloud-deployed agents 评测**:即使 materialized snapshot 也无法捕获
   远端 deployment 的真实状态(部署版本 / 启用插件 / active config)。
3. **Snapshot 时点 vs 运行时点漂移**:snapshot 记的是 materialize 时的指纹,
   但 cases 跑的时候若 runtime 本身有 drift(进程被重启 / 配置被改),
   snapshot 没法反映。
4. **"我装对了吗"心智负担**:用户 `ahl new` 写完一堆文件后,要跑
   `ahl run` 才知道 runtime / package 是不是真就位 —— failure 信息混在
   run-time 错误里。

Runtime Probe 把这四块都收一收:**显式、可重复、可记录的 runtime 现状捕获**。

---

## 3. Non-goals (redlines)

v0.6 MVP **不做**:

- **不实现 Auto** —— probe 只做单次检查,不触发任何 autonomous 行为。
- **不实现 registry / remote package distribution** —— probe 不下载、
  不联网拿外部资源(除非用户显式给 `--command` 让 probe 跑用户的脚本)。
- **不实现 cloud attestation 内置 SDK** —— probe 可以通过 user-supplied
  `--command` 捕获 cloud 状态,但不直接调 AWS/GCP/Azure SDK。
- **不修改 runtime source / sandbox / config** —— probe 是**只读**的。
- **不改变 v0.5 package install** —— probe 不调用 `install_package_payload`。
- **不改变 scoring / comparator math** —— `grader.py` / `comparator.py` 不动。
- **不要求 probe** —— probe 是 opt-in。`ahl run` 永远不强制要求 probe 跑过。
- **不改 repo visibility** —— 仍 PRIVATE。
- **不新增 CLI 命令(超出 `probe` 一个)** —— review 只显示已有 probe 数据,
  不自动跑 probe。
- **不在 v0.6 MVP 改 snapshot schema** —— probe 写自己的 artifact,
  snapshot 字段保持 v0.5 状态。snapshot↔probe 绑定留 v0.7+。
- **不在 v0.6 MVP 改 evidence 规则**(除了通过 `--write-evidence` flag 让
  probe 写 `materials/*-evidence.md` 这条**v0.4 已支持的 side-channel**)。

---

## 4. Relationship to existing concepts

| 既有概念 | Probe 关系 |
|---|---|
| **runtime_source** (v0.3.0) | Probe **读** source 状态(local_path: dir 存在 + 可读 + 算 dir_hash;git_repo: git accessible + ref resolves + 拿 HEAD commit_sha)。**不**修改 source。 |
| **harness_package** (v0.5) | Probe 检查 package 现状(manifest 可读 + payload 文件存在 + runtime_compat 跟 variant 匹配)。**不** install。 |
| **sandbox** (v0.3.0) | Probe **不**创建 sandbox。Probe 是 pre-run,sandbox 还不存在。 |
| **snapshot** (v0.3.0) | Probe 写自己的 artifact 目录 `probe-results/`(独立于 `results/snapshots/`)。v0.6 MVP **不**扩 snapshot schema;snapshot 可选 reference probe_id 留 v0.7+。 |
| **evidence** (v0.4) | 对 legacy_connect variant + 成功 probe + `--write-evidence` flag → probe 写 `materials/*-evidence.md` → v0.4 evidence 原地 weak → medium。对 materialized variant → v0.6 MVP probe 是 informational only,evidence 规则不变。 |
| **run** | Probe 独立于 run。`ahl run` 不消费 probe artifact(v0.6 MVP)。 |
| **score / compare** | 不消费 probe artifact。Compare report 仍按 v0.4/v0.5 evidence section 渲染(若 probe 走 `--write-evidence` 通道升级了 legacy evidence,compare 自然反映出来)。 |

**关键**:probe 通过**已有 channel**(materials evidence files)间接影响
evidence,**不**新引入第二条 evidence 输入路径。

---

## 5. Probe timing

固定 3 种使用模式,**不再增加**:

1. **显式 pre-run**(主路径):用户在 `ahl run` 之前手动跑
   `ahl probe <experiment>`。probe 输出报告 + 写 artifact;用户根据报告
   决定要不要修配置 / 加 `--write-evidence`。
2. **`ahl review <experiment>` 中展示**:review 默认**不**触发 probe;
   若 `experiments/<id>/probe-results/` 已有 artifact,review 多打一行
   "Last probe: <timestamp> · status: <ok/warn/fail>"。
3. **独立调用**:`ahl probe <experiment>` 可以反复跑,不需要前置任何 ahl 命令
   (除 `ahl init` + `ahl new`)。

明确**不做**:

- **不**有 background daemon
- **不**有 watch / auto-rerun-on-change
- **不**自动在 `ahl run` 前隐式 probe
- **不**自动在 `ahl review` 中触发 probe

---

## 6. Probe targets

按 variant 类型分:

### 6.1 `local_path` variant

Probe 检查 source 目录:

- 目录存在 + 可读
- 计算 `source_dir_hash`(同 v0.3.0 的 `compute_dir_hash`)
- 跟最近一次 snapshot 比对(若有):报告 hash 是否漂移
- 列 source 顶层文件清单(可选,debug 用)

### 6.2 `git_repo` variant

Probe 检查 repo:

- `git ls-remote <url>` 拿 remote ref 列表(确认可访问 + ref 存在)
- 若指定 `--depth` 模式:`git fetch --depth=1 <url> <ref>` 拿 HEAD commit_sha
  (不写到 sandbox,只查)
- 跟最近一次 snapshot 比对(若有):报告 commit_sha 是否漂移

### 6.3 Packaged variant(`harness_package` 设了)

Probe 加查 package:

- manifest 可读 + 解析(`parse_manifest`)
- payload 文件全部存在
- `runtime_compatibility` 含 variant 的 runtime_source.type
- 算 `payload_hash`,跟最近 snapshot 比对(若有)

### 6.4 `legacy_connect` variant(无 runtime_source,走 connect.md)

Probe 自身能查的有限(没 sandbox 可观察)。提供两条机制:

- **基础检查**:`connect.md` 解析 OK + `start_command` 字段非空 +(对外部
  命令行 type)`command:` 字段非空。
- **可选 smoke command**:用户提供 `--command "<cmd>"`,probe 执行该命令
  并捕获 stdout(简短 truncate),作为 cloud / dev_agent 的活跃状态证据。
  此命令的安全责任**完全在用户**(spec §10 + §14)。

### 6.5 不在 v0.6 范围

- `docker_image` / `remote_api` / `dev_agent` runtime_source(尚未在 v0.5
  adapter 里实装)→ probe 视为 `status=skip`,reason `"runtime type X
  尚未实装"`。

---

## 7. Probe outputs

### 7.1 Per-variant probe result

```json
{
  "probe_id": "probe-20260601-100000",
  "variant_id": "V2",
  "experiment": "001-package-demo",
  "captured_at": "2026-06-01T10:00:00+00:00",
  "status": "ok | warn | fail | skip",
  "runtime_source_state": {
    "type": "local_path",
    "path": "<home>/projects/x",
    "exists": true,
    "readable": true,
    "source_dir_hash": "sha256:...",
    "matches_latest_snapshot": true
  },
  "package_state": {
    "ref": "minimal-strict-prompt@0.1.0",
    "manifest_readable": true,
    "payload_files_present": ["payload/system.md"],
    "payload_files_missing": [],
    "runtime_compatibility_match": true,
    "payload_hash": "sha256:...",
    "matches_latest_snapshot": true
  },
  "start_command_available": true,
  "start_command_source": "manifest | patch | none",
  "optional_smoke": {
    "command": "kubectl get pod my-agent -o json | jq .status.phase",
    "exit_code": 0,
    "stdout_excerpt": "\"Running\"",
    "stderr_excerpt": ""
  },
  "reasons": [
    "local_path source dir present + dir_hash stable",
    "package payload + runtime_compat OK"
  ]
}
```

Notes:
- `package_state` 仅在 variant 有 `harness_package` 时出现;否则 null。
- `optional_smoke` 仅在用户 `--command` 提供时出现;否则 null。
- `matches_latest_snapshot` 只在该 variant 之前有过 snapshot 时算;首次
  probe → null。

### 7.2 Artifact 路径

```
experiments/<id>/probe-results/<probe_id>/<variant_id>.json
```

`probe_id = "probe-<timestamp>"`(timestamp = `YYYYMMDD-HHMMSS`,UTC)。
多次 probe 累积,不覆盖。`latest probe` = 时间戳最大的目录。

### 7.3 Stdout 报告

```
Probe: 001-package-demo
  V1 (baseline)  status=ok    runtime=local_path:/path/x  package=—       start_command=patch
  V2             status=ok    runtime=local_path:/path/x  package=minimal-strict-prompt@0.1.0  start_command=manifest
  V3 (legacy)    status=warn  runtime=legacy_connect      package=—       start_command=patch
                 reason: legacy_connect 默认 weak evidence; 用 --command 跑 smoke / --write-evidence 写 materials/runtime-evidence.md 升 medium

probe artifact: experiments/001-package-demo/probe-results/probe-20260601-100000/
```

### 7.4 `--write-evidence` flag (locked per Kun correction)

**仅对 `legacy_connect` variant 生效**;**仅 status ∈ {ok, warn} 时落盘**。
status=fail 时**只写** probe-results artifact,**不写**
`materials/runtime-evidence.md`(spec correction)。

写入路径:`experiments/<id>/materials/runtime-evidence.md`(单一文件;
v0.6 MVP 不分 runtime/harness/cloud 三份)。文件**覆盖**(不 append)。

Evidence 文件必含字段(per Kun correction):

- `probe_id`
- `variant_id`(或 variants covered 列表)
- `status`
- `captured_at` (UTC ISO timestamp)
- checks performed(runtime_source / harness_package / start_command 的
  status 各报一行)
- smoke command(若有)
- smoke exit code
- truncated stdout / stderr(各 ≤1KB)
- **limitations** 段必含 "this is supplied runtime evidence captured at
  probe time, not cloud attestation"

对 materialized variant 指定 `--write-evidence` → no-op + stderr warning
("materialized variant 已有 strong 路径,不需要 materials 证据")。

V0.4 evidence 推断下次跑会自动 pick up (`_detect_materials_evidence` 扫
materials/runtime-evidence.md), legacy_connect weak → medium。

---

## 8. Snapshot / evidence interaction

### 8.1 v0.6 MVP:**snapshot 字段不动**

snapshot schema 保持 v0.5 状态(`runtime_source` / `harness_patch` /
`harness_package` / `sandbox` / `environment`)。**不**新增 `runtime_probe`
字段。

理由:probe 是 pre-run / 独立 artifact。把 probe 数据 inline 到 snapshot
里会需要"run 时点必须有 probe artifact"的硬绑定(否则 snapshot 字段半
空)。v0.6 MVP 选择**完全解耦**;v0.7+ 再讨论"snapshot 记最近一次 probe_id"
这种弱绑定。

### 8.2 v0.6 MVP:**evidence 规则不动**

`infer_evidence_from_snapshot` 不读 `probe-results/`。

唯一 evidence 链上的影响是**间接的**:`--write-evidence` flag 让 probe
往 `materials/*-evidence.md` 落文件,v0.4 evidence(对 legacy_connect)
已经原生支持这条 channel(`_detect_materials_evidence` 已扫这三个文件)。

```
Probe (v0.6) ─[--write-evidence]→ materials/*-evidence.md ─[v0.4 evidence]→ legacy_connect weak→medium
```

### 8.3 v0.6 不动的部分

- snapshot.runtime_source / harness_patch / harness_package 字段
- `infer_evidence_from_snapshot` / `_compute_base_evidence` /
  `_apply_package_overlay` 逻辑
- score / compare math
- compare report 渲染(`## Evidence` section 仍按 v0.5 规则)

---

## 9. CLI impact

### 9.1 Decision analysis

| | A. `ahl probe` only | B. Integrate into `ahl review` only | C. Both (minimal) |
|---|---|---|---|
| 产品价值 | 高 — clear 命令语义 | 中 — 用户已熟悉 review 但 review 多了 side-effect | **高 — 显式 probe + review 顺手看到** |
| 用户清晰度 | 高 — `ahl probe` 单一职责 | 低 — review 既报 draft 状态又跑 probe,混乱 | **高 — probe 跑 / review 显示** |
| 实现复杂度 | 低 — 1 个新命令 + workflow.probe() | 中 — review 路径要支持 conditional probe + report | **低 — 1 个新命令 + review 加 1 行 read-only 显示** |
| Scope creep 风险 | 低 | 中 — review 入口被污染 | **低 — review 仍是 read-only,只多查 1 个文件** |
| 跟 v0.5 package 流兼容 | 完全兼容 | review 路径已是只读;改成会跑 probe 破坏既有约定 | **完全兼容** |

### 9.2 Recommendation: **Option C minimal**(per Kun 偏好)

- **新加** `ahl probe <experiment>` —— 唯一新 CLI 命令。
  - `--command "<smoke>"`(可选,legacy_connect variant 用)
  - `--write-evidence`(可选,legacy_connect variant 用,写
    `materials/*-evidence.md`)
  - 退出码:全部 status=ok / warn 退出 0;任一 fail 退出 1
    (不阻塞 — 用户可以选择忽略 fail 继续 `ahl run`,但 exit code 让
    CI 集成可见)
- **`ahl review <experiment>` 加 1 行 display**(若
  `experiments/<id>/probe-results/` 有任何 artifact):
  ```
  Last probe: probe-20260601-100000 (2026-06-01 10:00 UTC) · 3/3 ok
  ```
  review **不**自动跑 probe。**不**改 review 现有的"未起草 / 解析失败 /
  校验提醒"四类信号。

**CLI 命令总数变化:13 → 14**(`init / walkthrough / connect / new / show /
cases / rubric / simulator / harnesses / run / score / compare / review /
**probe**`)。这是 v0.4 / v0.5 之后**第一个**新 CLI,**严格 justified**:
probe 是 pre-run 独立动作,有自己的成功/失败语义,集成进现有命令会破坏单一
职责。

---

## 10. Error handling

Probe 是 **best-effort 信息收集**,never fatal。

| 场景 | 行为 |
|---|---|
| variant runtime_source 不在 runtime-sources.md | status=fail,reason "runtime_source ref 解析失败"(同 workflow.run preflight) |
| local_path source 目录不存在 | status=fail,reason "source path 不存在: <path>" |
| local_path source 不可读 | status=fail,reason "permission denied" |
| git_repo URL 不可访问(网络错误) | status=fail,reason "git ls-remote failed: <err>" |
| git_repo ref 不存在 | status=fail,reason "ref <ref> not in remote" |
| 手动 git binary 缺失 | status=fail,reason "git binary 不在 PATH" |
| harness_package 引用不存在 | status=fail,reason "package <ref> 不存在;可用: ..." |
| package payload 文件缺失 | status=fail,reason "payload 文件不存在: <list>" |
| runtime_compatibility 不匹配 | status=fail,reason "runtime type X 不在 package compat 列表" |
| start_command 双方都缺 | status=fail,reason "start_command unavailable" |
| `--command` smoke 退出非零 | status=warn(不 fail;smoke 命令失败可能是 user environment 问题),reason "smoke exited <code>" |
| `--command` smoke 超时(默认 30s) | status=warn,reason "smoke timed out" |
| `--write-evidence` + materialized variant | status=ok + warning printed("--write-evidence is no-op for materialized variants") |
| `experiments/<id>/probe-results/` 目录写失败(IO / permission) | hard fail probe(整个 ahl probe 抛 WorkflowError) |
| ahl probe 在没有任何 variants 的实验上跑 | hard fail("no variants to probe") |

**不**抛 traceback;所有错误翻成 `status=fail` + reason string + 仍写入
probe artifact 让用户能看见。

---

## 11. Backward compatibility

| 来源 | v0.6 行为 |
|---|---|
| 没跑过 probe 的 experiment(无 `probe-results/`) | `ahl run` / `ahl review` 行为完全等价 v0.5。review 不打 "Last probe" 行。 |
| v0.5 snapshot(无 `runtime_probe` 字段) | 不动,evidence 规则不变。 |
| v0.4 snapshot + v0.4 score JSON | 不动。 |
| v0.4 / v0.5 既有 327 + 76 = 403 tests + v0.5 E2E 2 = 405 tests | 必全部继续通过(regression gate)。 |
| 既有 `materials/*-evidence.md`(用户手写的) | 不动;probe `--write-evidence` 仅在 status=ok 时**追加 / overwrite**(spec §15 决定覆盖语义)。 |
| 既有 13 个 CLI 命令 | 行为不变;仅 review 多打 1 行(若 probe artifact 存在)。 |
| `ahl --help` 输出 | 加 `probe` 一行,其它不动。 |

---

## 12. Error cases (vs §10 happy path)

错误标识:

| ID | 触发 | 行为 |
|---|---|---|
| ERR-PROBE-1 | ahl probe 在不存在的实验 | WorkflowError "找不到实验" |
| ERR-PROBE-2 | ahl probe 实验无 variants | WorkflowError "no variants to probe" |
| ERR-PROBE-3 | `--write-evidence` flag 但 variant 全部 materialized | warning(不 fail);no materials file written |
| ERR-PROBE-4 | probe artifact 写失败 | WorkflowError "probe artifact 写失败: <io error>" |
| ERR-PROBE-5 | `--command` smoke 命令 traversal(包含 `..` / 绝对路径外部) | 不校验 — 这是 user-supplied command,user 责任。spec §14 红线声明 |

---

## 13. Tests required

按 6 组规划:

### Group A — per-source-type probe (~12 tests)
- local_path: ok / source dir missing / source dir unreadable / matches snapshot / drifted from snapshot
- git_repo: ok / repo unreachable / ref missing / git binary missing
- legacy_connect: basic probe (connect.md parse + start_command) / with smoke / without smoke
- packaged variant: package ok / manifest missing / payload missing / runtime_compat mismatch

### Group B — artifact write (~5 tests)
- probe-results/<probe_id>/<variant_id>.json schema
- multiple probes accumulate (probe_id timestamps unique)
- artifact write failure → WorkflowError
- per-variant artifact independence
- forward-slash relative paths in artifact

### Group C — `--write-evidence` flag (~6 tests)
- legacy_connect + ok + flag → writes materials/runtime-evidence.md
- legacy_connect + ok + flag + existing evidence file → overwrites (or appends? — locked in spec §15)
- materialized + flag → no-op + warning printed
- mixed variants + flag → only legacy gets evidence written
- flag without ok status → no write
- write failure → WorkflowError

### Group D — review integration (~4 tests)
- review with no probe artifact → no "Last probe" line; existing 4-tier signals unchanged
- review with recent probe → shows status + timestamp
- review uses **latest** probe (sorted by probe_id timestamp)
- review never triggers probe (verify subprocess not spawned)

### Group E — CLI redlines (~4 tests)
- `ahl --help` shows exactly 14 subcommands (adds `probe`)
- probe never modifies source / sandbox / package files (snapshot of paths before vs after probe)
- probe is read-only on snapshot/evidence (verify snapshot files unchanged across probe runs)
- no implicit probe in `ahl run` (verify probe-results unchanged after run)

### Group F — backward compat (~4 tests)
- experiment without probe-results/ → `ahl run` / `ahl score` / `ahl compare` identical to v0.5
- v0.5 snapshot loaded by probe-aware compare → unchanged
- 405 existing tests must all pass
- v0.4 materials/*-evidence.md still works (probe doesn't change v0.4 channel)

### Group G — E2E (~2 tests)
- `ahl probe` on experiment with V1 (local_path) + V2 (packaged) → both ok, artifact written, review shows status
- `ahl probe --command "echo hello"` on legacy variant + `--write-evidence` → materials/runtime-evidence.md written, next compare shows V evidence upgraded to medium

**Total: ~37 new tests**。Baseline 405 → ~442。

---

## 14. Implementation plan

### 14.1 New files (4)

| Path | Est lines | Purpose |
|---|---|---|
| `src/agent_harness_lab/probe.py` | ~300 | per-source-type probe + artifact writer + `--write-evidence` writer |
| `docs/runtime-probe-mvp.md` | ~600 | this spec (already in this PR's diff) |
| `tests/test_probe.py` | ~500 | Groups A/B/C/E unit tests |
| `tests/test_probe_integration.py` | ~350 | Groups D/F/G integration + E2E |

### 14.2 Modified files (8)

| Path | Est ± | Change |
|---|---|---|
| `src/agent_harness_lab/cli.py` | +30 / -0 | `cmd_probe` + subparser; review adds 1-line probe display (conditional) |
| `src/agent_harness_lab/workflow.py` | +60 / -0 | `probe()` orchestration: load variants + per-variant dispatch to probe.py |
| `src/agent_harness_lab/review.py` (or `workflow.review`) | +10 / -0 | read latest probe artifact if exists; render display line |
| `docs/file-formats.md` | +40 / -0 | `probe-results/<probe_id>/<variant_id>.json` schema |
| `docs/product-walkthrough.md` | +10 / -0 | Step 3 / 4 mention optional probe |
| `docs/evidence-aware-result.md` | +15 / -0 | mention `--write-evidence` as new way to upgrade legacy_connect to medium |
| `docs/runtime-materialization.md` | +5 / -0 | mention probe is pre-run inspection, distinct from materialize |
| `CHANGELOG.md` | +8 / -0 | [Unreleased] / Added bullets |

### 14.3 Estimated diff

- New: ~1750 lines (4 files,含本 spec)
- Modified: ~178 lines (8 files)
- **Total ~1900 lines added across 12 files**。规模 ≈ v0.5。

### 14.4 Commit split

**2 commits**(沿用 v0.5 节奏):

- **C1**: `feat(probe): add runtime probe MVP (local_path / git_repo / legacy / packaged)`
  - probe.py(probe per source type + artifact write,不含 `--write-evidence`)
  - cli.py 加 cmd_probe(不含 review 集成)
  - workflow.py 加 probe() orchestration
  - test_probe.py Groups A/B
  - docs/runtime-probe-mvp.md(本 spec)
  - docs/file-formats.md probe-results schema

- **C2**: `feat(probe): integrate --write-evidence + review display + E2E`
  - probe.py 加 `--write-evidence` 通道
  - cli.py review 加 1 行 display
  - workflow.review 读 probe artifact
  - test_probe_integration.py + E2E tests
  - docs 更新(walkthrough + evidence-aware-result + runtime-materialization)
  - CHANGELOG bullets

### 14.5 Spec first?

**Yes**(本步)。本 spec 是 C1 GO 条件。

### 14.6 Review bundle

每个 commit 自带 review bundle,沿用 v0.5 模板。

---

## 15. Stability commitment & locked design choices

锁的字段(future-version backward compat 硬约束):

- `probe-results/<probe_id>/<variant_id>.json` 字段(§7.1)的顶层 key 稳定:
  `probe_id / variant_id / experiment / captured_at / status / runtime_source_state /
  package_state / start_command_available / start_command_source / optional_smoke /
  reasons`。
- `status` 枚举:`ok / warn / fail / skip`。
- `probe_id` 格式:`probe-YYYYMMDD-HHMMSS`(UTC)。
- `--write-evidence` flag 默认行为:
  - 仅 legacy_connect variant 触发
  - **覆盖** materials/<file>.md(不 append)—— 简单 + reproducible;
    用户若要 append,应在 probe 之间手工合并
- CLI 命令名固定为 `ahl probe`(future 不重命名)。
- `ahl review` probe 显示行格式:`Last probe: <probe_id> (<UTC timestamp>) ·
  <n>/<total> <status>`。

未来允许扩展(不破坏 v0.6 字段):
- 加 snapshot.runtime_probe 字段(v0.7+ 弱绑定)
- 加 evidence rule:probe `status=ok` 主动 promote materialized variant
  (v0.7+)
- 加新 source type 的 probe 实现(docker_image / remote_api 等)
- 加 `ahl probe --variant V2` 单 variant flag(选择性 probe)

不允许(将打破 v0.6 contract):
- 改 `probe_id` 格式
- 改 `status` 枚举值
- 改 `--write-evidence` 覆盖 vs append 行为
- 改 review display 行格式(允许加新行,但 "Last probe:" 那行格式锁定)

---

## 16. Locked decisions (Kun GO,锁定 for v0.6 implementation)

| # | Decision | Locked value |
|---|---|---|
| 1 | Smoke command timeout | **30 seconds default**;CLI flag `--timeout <sec>` 覆盖;仅作用于 smoke command 执行 |
| 2 | `--write-evidence` target | **`experiments/<id>/materials/runtime-evidence.md`** 单一文件;仅 status ∈ {ok, warn} 时写;status=fail 时**不**写 |
| 3 | Probe artifact cleanup | **不自动清理**;**不**加 `--keep-last N` flag(v0.6 范围) |
| 4 | Exit code | 全部 variant 是 ok/warn → exit 0;任一 variant 是 fail → exit 1;probe failure **不阻塞** future `ahl run`(advisory only) |
| 5 | Smoke output truncation | **stdout ≤1KB · stderr ≤1KB**(UTF-8 bytes);超出 truncate + 标记 `(truncated)`;**不存** full raw output |

Plus the `--write-evidence` correction(spec §7.4):写入文件必含 probe_id /
variant_id / status / captured_at / checks performed / smoke command /
exit code / truncated outputs / limitations(含 "supplied runtime evidence,
not cloud attestation" 字样)。

这 6 项已 lock,C1 实现直接按此 spec。

---

## 17. Redlines (consolidated)

| Redline | Honored by design |
|---|---|
| No Auto | ✅ probe is single-shot inspection, no autonomous behavior |
| No registry / remote distribution | ✅ probe doesn't download (except user-supplied `--command`) |
| No cloud attestation built-in | ✅ cloud state via user-supplied `--command` only |
| No mutation of runtime source / sandbox / config | ✅ probe is read-only |
| No change to v0.5 package install | ✅ probe calls parse_manifest / discover_packages only;
  doesn't touch install_package_payload |
| No scoring / comparator math change | ✅ score / compare untouched |
| Probe never required | ✅ opt-in via explicit `ahl probe` invocation |
| No repo visibility change | ✅ unrelated to spec |
| No new CLI beyond `probe` | ✅ review gains read-only display only |
| No v0.5 snapshot schema change | ✅ snapshot.runtime_probe deferred to v0.7+ |
| No v0.4 evidence rule change | ✅ probe affects evidence via existing materials/*-evidence.md channel only |
| No tag / release / branch deletion | ✅ unrelated to spec |
| Probe can't be attack vector | ✅ probe is read-only on filesystem; user `--command` is user's responsibility (documented warning) |
| No background daemon | ✅ probe is single invocation |
| No auto-discovery / spider | ✅ probe only acts on variants declared in experiment |

---

## 18. What this spec does NOT change (snapshot)

For absolute clarity:

- `results/snapshots/<run_id>/<variant_id>.json` schema **unchanged** in v0.6.
- `results/run-*.json` schema **unchanged**.
- `results/score-*.json` `evidence` block **unchanged**.
- `results/compare-*.md` rendering **unchanged**.
- CLI subcommand behavior **unchanged** (except review gaining one
  conditional display line; probe is brand new).
- 405 v0.5 tests pass without modification.
