# Harness Package MVP · v0.5 Spec

> 这份 spec 定义 Agent Harness Lab 的 v0.5 Harness Package MVP —— 让 harness
> variant 从"实验目录里的文件"升级为"可安装、可 hash、可 snapshot 的 runtime
> harness component",支持跨实验复用 harness 设计。
>
> Status: target v0.5.0,branch `v0.5.0-harness-package-mvp`。**spec lock-in
> only — 代码尚未实现**。
> Date: 2026-05-26。
> 上游约束:Kun 5 项 corrections 已并入(install order / 必须 materialized
> runtime / 版本化目录 / evidence 规则 / snapshot 字段名)。
>
> 本文是 `product-walkthrough.md` **Step 5 (design harness variants) +
> Step 7 (run experiment)** 的 depth-detail。还没读 walkthrough 的从
> [`product-walkthrough.md`](product-walkthrough.md) 起。可运行 sample:
> [`examples/sample-workspace/`](../examples/sample-workspace/) — V2 引用
> `concise-prompt@0.1.0` package,跑完后 V2 snapshot 含完整的
> manifest_hash + payload_hash + effective_harness_hash。

---

## 1. Purpose

v0.3.0 Runtime Materialization 让单个实验里的 variant 跑得可复现;v0.4
Evidence-Aware Result 让证据强度被 surface。**v0.5 解决"harness 不能跨实验
复用"的痛点**:今天 prompts / config / start_command 写在
`experiments/<id>/harnesses/V*.md` 的 `## Patch` 段里,换一个实验就要复制
粘贴。Harness Package 把这一坨抽出来,变成 workspace 根目录下的
**版本化、可 hash、可 install** 的资产,任何实验的 variant 都能引用。

核心一句话:

> 一个 harness package 是一份打包好的 harness payload(files + env +
> start_command),由 workspace 内多个 experiment 的 variant 共享、按 id@version
> 引用、install 到 materialized sandbox 中,并在 snapshot 里留下指纹。

---

## 2. Non-goals (redlines)

v0.5 MVP **不做**:

- 不实现 **registry** —— package id 解析只在 workspace 本地扫
  `harness-packages/`,无任何 URL / API / discovery 机制。
- 不实现 **remote package distribution** —— manifest 不带任何下载 URL,
  无 fetch / cache / lock 逻辑。
- 不实现 **Auto mode** —— 不引入 autonomous iteration / approval gate。
- 不实现 **Runtime Probe** —— 不从 runtime 主动抓任何东西。
- 不实现 **cloud / runtime attestation** —— evidence 仍是 facts-of-snapshot 推断。
- 不改 **scoring / comparison math** —— `grader.py` / `comparator.py` 不动。
- **不把 cases / rubric / simulator 打进 package** —— 它们属于 Experiment Layer,
  package 只装 Harness Layer。`runtime_compatibility` 字段也只允许 runtime
  source types。
- **不加新 CLI 命令** —— 全部能力通过现有 `ahl run` / `ahl harnesses` /
  `ahl review` 的 file-format 支持暴露。
- **不破坏 v0.4 evidence** —— 变体无 package 时 evidence 推断完全等价 v0.4;
  变体有 package 时仅扩展 §13 的规则,**不**反向修改 v0.4 contract。

---

## 3. Directory layout

新增 workspace 根目录:`harness-packages/`,**版本化双层目录**。

```
<workspace>/
├── harness-packages/                            # NEW v0.5
│   └── <package-id>/
│       └── <version>/
│           ├── manifest.md
│           └── payload/
│               ├── <file-1>
│               └── ...
├── experiments/<id>/harnesses/V*.md             # existing,新增可选 frontmatter
├── runtime-sources.md                            # existing,不变
└── connect.md                                    # existing,legacy 不变
```

约束:

- `<package-id>` kebab-case,workspace-unique。**path 上的 id 必须等于
  manifest.id**(parser 强制校验,不一致抛 ValueError)。
- `<version>` SemVer 字符串(`MAJOR.MINOR.PATCH`,可带 pre-release 后缀如
  `0.1.0-alpha`)。**path 上的 version 必须等于 manifest.version**(同上)。
- 同一个 `<package-id>` 下可有多个 `<version>` 子目录(MVP 不阻止;variant
  按 id@version pin)。
- `payload/` 必须存在(可空,代表"只设 env 或只改 start_command 的纯配置
  package")。
- 不允许同一 `harness-packages/<id>/<version>/` 路径出现两次 manifest.md
  (filesystem 保证;扫描时若发现奇怪情况抛 ValueError)。

---

## 4. Variant frontmatter field

`experiments/<id>/harnesses/V*.md` 新增**可选** frontmatter 字段
`harness_package`:

```yaml
---
id: V2
基线: 否
runtime_source: openmanus-main
harness_package: minimal-strict-prompt@0.1.0
---
```

规则:

- **`<id>@<version>` 是必需格式**。bare `<id>`(不带 `@version`)在 v0.5 视为
  **invalid**,preflight 抛 `WorkflowError`(避免未来 "latest" 语义的隐式
  漂移,v0.5 强制 explicit pin = reproducibility 保底)。
- 不写 `harness_package:` 字段 → variant 完全沿用 v0.4 行为(snapshot 里
  `harness_package: null`)。
- **`harness_package` 需要 `runtime_source` 同时存在**(per Correction 2)。
  legacy 路径(无 runtime_source / 走 connect.md)+ `harness_package` 视为
  invalid configuration,preflight 抛 `WorkflowError`。

---

## 5. Manifest schema

`harness-packages/<id>/<version>/manifest.md`:

```markdown
---
id: minimal-strict-prompt
version: 0.1.0
runtime_compatibility: [local_path, git_repo]
---

## Description
极简严格 prompt harness。覆盖 prompts/system.md + 注入 strict env。

## Payload

files:
  - target: prompts/system.md
    source: payload/system.md
env:
  HARNESS_STRICT: "1"
start_command: python -m agent.run
```

Frontmatter 字段(全部必填):

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | string (kebab-case) | package id,workspace-unique;**必须**等于 path 上的 `<package-id>` |
| `version` | SemVer string | 当前版本号;**必须**等于 path 上的 `<version>` |
| `runtime_compatibility` | list of string | 允许的 runtime source types。v0.5 范围 ∈ {`local_path`, `git_repo`}。未来扩展 `docker_image` 等保持 forward-compat:列表里出现未识别 type 不抛错,**但 variant 实际 runtime_source.type 不在该列表 → preflight 抛 WorkflowError**。**不允许出现 `legacy_connect`** —— manifest parser 拒绝,避免误导用户把 package 用在 legacy 上 |

Body 段:

- `## Description` —— free-form 文本(描述这个 package 干什么),parser
  不强制内容,但段必须存在(空 description 抛 ValueError)。
- `## Payload` —— **schema 完全镜像 V\*.md 的 `## Patch` 段**(files / env /
  start_command),好处:用户已知的 mental model;parser 可复用
  `patch.parse_patch` 内部逻辑(refactor 出共享 helper)。详见 §6。

未识别的 frontmatter 字段 → ValueError(参考 `runtime_source.py` 白名单
模式)。

---

## 6. Payload schema (`## Payload` 段)

复用现有 `## Patch` 的 YAML-like 受控结构:

```yaml
files:
  - target: prompts/system.md            # 相对 sandbox root 的目标路径
    source: payload/system.md            # 相对 manifest 所在目录的源文件路径
env:
  HARNESS_STRICT: "1"                    # value 必须 string(避免类型歧义)
start_command: python -m agent.run       # 可选 — 见 §10 conflict rules
```

字段规则:

- `files[].target`: 相对 sandbox root 的路径。**path traversal 防御**:
  install 时 `_safe_target_path(sandbox_dir, target)` → 越出抛
  `RuntimeError`。
- `files[].source`: 相对 manifest 所在目录(`harness-packages/<id>/<version>/`)
  的路径,**必须**位于 `payload/` 下。parser 时
  `_safe_payload_source_path(pkg_dir, source)` → 越出抛 `ValueError`。
  原因:防止 manifest 引用 workspace 其它位置的文件(只允许 self-contained
  payload)。
- `env`: 可选;key-value 都是 string。
- `start_command`: 可选。manifest 可省略 start_command;**冲突解析见 §10**。
- 不写 `files` / `env` / `start_command` 任一段 → 视作空(空 list / 空 dict
  / None)。但**三者全空** → manifest parser 抛 ValueError(package 没有任何
  effect,无意义)。

---

## 7. Resolution rules

`workflow.run` preflight 阶段(`runtime-sources.md` 校验之后)做 package
resolution:

1. **扫 `harness-packages/`**(不存在 → 空 dict,所有 variant 必须不引用
   package;若有 variant 引用了 → §15 ERR-RESOLV-1):
   ```
   harness-packages/<id>/<version>/manifest.md
   ```
   每个 manifest 解析为 `Manifest{id, version, runtime_compatibility,
   description, payload}` 对象。
2. **校验 manifest 完整性**:
   - `manifest.id == <id from path>`(否则 §15 ERR-MANIFEST-1)
   - `manifest.version == <version from path>`(否则 §15 ERR-MANIFEST-2)
   - `manifest.runtime_compatibility` 非空且不含 `legacy_connect`(否则
     §15 ERR-MANIFEST-3)
3. **构造 `packages: dict[(id, version)] → Manifest`** 索引。
4. **遍历所有 variant**:
   - 若 variant 无 `harness_package:` → skip。
   - 若 variant `harness_package:` 写了但格式非 `<id>@<version>` → §15
     ERR-VARIANT-1。
   - 若 variant 引用的 `<id>@<version>` 不在 packages 索引 → §15
     ERR-RESOLV-1。
   - 若 variant 引用了 package 但 variant.runtime_source 为 None → §15
     ERR-VARIANT-2(per Correction 2)。
   - 若 variant.runtime_source 对应的 `RuntimeSource.type` 不在
     `manifest.runtime_compatibility` → §15 ERR-COMPAT-1(per Correction 2 +
     §8)。
5. **构造 `(variant_id) → Manifest` 映射**,传入 `MaterializeContext` 给
   adapter。

resolution 失败任一条 → 抛 `WorkflowError`,run 提前 fail,不进 materialize。

---

## 8. Runtime compatibility rules (per Correction 2)

**`harness_package` 仅在 materialized runtime 上工作**:

- 允许的 `runtime_source.type`(v0.5):`local_path`, `git_repo`。
- 不允许:`legacy_connect`(无 sandbox,无法 install 文件);任何
  `harness_package` + legacy_connect 组合 → ERR-COMPAT-2 / ERR-VARIANT-2。
- 不允许:variant 无 `runtime_source` + 有 `harness_package` →
  ERR-VARIANT-2。
- 未来扩展:`docker_image` / `remote_api` / `dev_agent` 出现在 manifest
  `runtime_compatibility` 时,parser 不报错(forward-compat),但 v0.5 没
  实现对应 adapter,真去用会在 adapter dispatch 阶段抛
  `NotImplementedError`(已经是 v0.3 的既有行为)。

理由(per Kun Correction 2):

> Harness Package MVP installs files into the sandbox. legacy_connect does
> not provide a reproducible installable sandbox.

defense-in-depth:即使 preflight 因 bug 漏掉,evidence 层也不会把
legacy_connect + package 评为 strong(见 §13)。

---

## 9. Install order (per Correction 1, FIXED)

`workflow.run` per (variant, run) 的 lifecycle:

```
1. adapter.materialize(version, ctx)             # source → sandbox
2. install_package_payload(sandbox, manifest)    # NEW v0.5 — only if variant has harness_package
3. apply_patch(version.patch, sandbox)           # existing — variant ## Patch
4. build_snapshot(version, ctx, adapter, sandbox, manifest)   # extended in v0.5
5. adapter.start(sandbox)
6. run cases
7. adapter.teardown(sandbox, cleanup=flag)
```

固定步骤 1 → 2 → 3 → 4:

- **package install 在 patch 之前**。理由:variant patch 是 per-experiment
  细化,设计意图是覆盖 package defaults。所以 patch 后落盘,patch
  胜出。
- 步骤 2 在 variant 无 `harness_package` 时 skip(snapshot 里
  `harness_package: null`)。
- 步骤 3 在 variant 无 `## Patch` 段时 skip(已是 v0.3 行为)。
- 步骤 4 始终执行;snapshot 是证据链,write 失败 → hard fail run(已是
  v0.3 行为)。
- `install_order` 字段在 snapshot 里固定为 `["package", "patch"]`(v0.5
  范围)。

**禁止**任何其他顺序(per Correction 1):不允许 patch 先 package 后、不允许
package 内联到 patch 步骤里、不允许 conditional 跳序。

---

## 10. Conflict resolution (per Correction 1)

variant `## Patch` **完全覆盖** package payload 的冲突项。

| 维度 | Package 单独存在 | Patch 单独存在 | 都存在 (冲突) |
|---|---|---|---|
| 同 `target` 文件 | 写 package 内容 | 写 patch 内容 | **patch 写在 package 之上 → 最终 = patch 内容** |
| 同 env key | 设 package value | 设 patch value | **patch.env 覆盖 package.env(per-key)** |
| `start_command` | 用 manifest.start_command | 用 patch.start_command | **patch.start_command 胜出**(若 patch.start_command 非空) |

特殊情况:

- variant 有 package 但**没** `## Patch` 段 + manifest 也没 start_command →
  ERR-START-CMD(§15);v0.5 不假设默认。
- variant 有 package(manifest start_command 存在)但 patch start_command
  空 → 用 manifest.start_command。
- variant 有 package 且有 patch,patch.start_command 空,manifest
  start_command 也空 → ERR-START-CMD。
- env 合并算法:`merged = {**package_env, **patch_env}`(Python dict
  unpack 语义,后者覆盖)。

实现层:`install_package_payload` 只负责把 payload 文件铺到 sandbox + 准备
package_env 字典 + 暴露 manifest.start_command。后续 `apply_patch` 复用现有
逻辑覆盖文件。env 合并 + start_command resolution 在 adapter.start 前由
workflow 一次性完成(单一职责)。

---

## 11. Hashing rules (per Correction 5)

三类 hash,**全 sha256**,**deterministic**(同样输入 → 同样输出):

### 11.1 `manifest_hash`

定义:对 `manifest.md` 文件的 **raw bytes** 算 sha256。

```python
manifest_hash = "sha256:" + sha256(manifest_path.read_bytes()).hexdigest()
```

理由:manifest 是 package 的契约;任何字符变化(包括描述措辞)都应触发
hash 变更,让 snapshot 真实记录"这一次跑用的是哪一份 manifest"。

### 11.2 `payload_hash`

定义:package payload 的 **deterministic content fingerprint**。算法复用
`patch.compute_patch_hash` 的思路:

```
input = sorted([(target, file_sha256) for file in payload.files])
      + json.dumps(payload.env, sort_keys=True)
      + payload.start_command or ""
payload_hash = sha256(canonical_concat(input))
```

不包含 manifest 元数据(id/version/description/runtime_compatibility)——
只反映 "实际要 install 进 sandbox 的东西的指纹"。

### 11.3 `effective_harness_hash`

定义:**package + patch 都应用到 sandbox 后,harness-controlled 文件的实际
内容 hash**。这是"实际跑了什么"的 ground truth。

scope(designed to be focused, not "all sandbox files"):
- 仅覆盖 `union(package.payload.files[].target, variant.patch.files[].target)`
  这些 target_paths
- 对每个 target 在 sandbox 中的实际文件算 sha256
- 加上 `merged_env`(package+patch 合并后的 dict,sort_keys)+
  `effective_start_command`
- 同样 sorted + canonical concat

```
input = sorted([(target, sha256(sandbox/target)) for target in union_targets])
      + json.dumps(merged_env, sort_keys=True)
      + effective_start_command
effective_harness_hash = sha256(canonical_concat(input))
```

理由:
- 单文件复盖序的可见结果(patch 覆盖了 package 同名文件 → effective hash
  反映的是 patch 内容)。
- 不含 sandbox 里其它文件(runtime source 自带的代码)—— 那是 runtime_source
  的 source_dir_hash 已经管的事,不重复。
- 用户能从 effective_harness_hash 反查:"这一次实际生效的 harness 是
  什么"。

### 11.4 Open question 备录

§16 / §17 期开发时需要 finalize:`union_targets` 是否包含 patch 写入但 package
没有的 target(答:是;union 是 union)。需要 unit test 覆盖各种 overlap 情形。

---

## 12. Snapshot schema (per Correction 5)

`results/snapshots/<run_id>/<variant_id>.json` 新增 top-level **可选**字段
`harness_package`(variant 无 package → `null`):

### 12.1 Variant with package (materialized + package)

```json
{
  "snapshot_id": "snap-run-20260601-100000-V2",
  "run_id": "run-20260601-100000",
  "variant_id": "V2",
  "experiment": "001-greedy-explorer",
  "created_at": "2026-06-01T10:00:00Z",

  "runtime_source": {
    "type": "git_repo",
    "name": "openmanus-main",
    "url": "https://github.com/.../openmanus.git",
    "ref": "main",
    "commit_sha": "abc123...",
    "source_dir_hash": "sha256:<pre-patch raw>"
  },

  "harness_package": {
    "id": "minimal-strict-prompt",
    "version": "0.1.0",
    "ref": "minimal-strict-prompt@0.1.0",
    "manifest_path": "harness-packages/minimal-strict-prompt/0.1.0/manifest.md",
    "manifest_hash": "sha256:<manifest.md bytes>",
    "payload_hash": "sha256:<payload files+env+start_cmd>",
    "effective_harness_hash": "sha256:<sandbox state after install+patch>",
    "install_order": ["package", "patch"]
  },

  "harness_patch": {
    "applied": [
      {"target_path": "prompts/system.md",
       "source_path": "patches/V2/system.md",
       "hash": "sha256:..."}
    ],
    "env": {"HARNESS_MAX_DEPTH": "5"},
    "start_command": "python -m openmanus.agent",
    "patch_hash": "sha256:..."
  },

  "sandbox": {
    "type": "git_clone",
    "path": "sandbox/run-20260601-100000/V2",
    "start_command": "python -m openmanus.agent"
  },

  "environment": {...}
}
```

### 12.2 Variant with package + no `## Patch`

`harness_patch: null`(已是 v0.3 行为);`harness_package` 块如上。

### 12.3 Variant without package

`harness_package: null`(显式 null,跟 v0.3 的 `harness_patch: null` 风格
统一)。其余字段不变。

### 12.4 Legacy path

legacy_connect 路径(无 runtime_source)在 §8 已禁与 package 共存。snapshot
里 `harness_package: null`,其余字段同 v0.3。

### 12.5 字段稳定性

- `harness_package.{id, version, ref}` —— 文本字段,稳定。
- `harness_package.manifest_path` —— **相对 workspace root** 的路径
  (不是绝对路径,reproducible across machines)。
- `harness_package.{manifest_hash, payload_hash, effective_harness_hash}`
  —— `sha256:<hex>` 字符串,稳定。
- `harness_package.install_order` —— v0.5 固定 `["package", "patch"]`;
  字段长期保留,允许未来新值。

---

## 13. Evidence interaction (per Correction 4)

v0.4 evidence 规则**保持不变**;v0.5 仅扩展"variant 有 package"的情形。

### 13.1 No package (variant 无 harness_package)

完全沿用 v0.4 §3 规则,不动。snapshot 里 `harness_package: null` →
evidence 推断不读这字段。

### 13.2 With package (variant 有 harness_package)

新规则(per Correction 4):

| 条件 | Level |
|---|---|
| runtime_source 满足 v0.4 §3.1/§3.2 strong 条件 **AND** `harness_package.{manifest_hash, payload_hash, effective_harness_hash}` **全非空** | **strong**(reasons 加 "harness_package `<id>@<version>` fully fingerprinted") |
| runtime_source 满足 v0.4 strong 条件 **AND** harness_package 三个 hash 任一缺失 | **medium**(reason: `"materialized runtime but incomplete harness package fingerprint"`) |
| runtime_source 不满足 v0.4 strong(materialized 但部分指纹缺) | **medium**(沿用 v0.4 reason)+ 额外 reason 提 package 状态 |
| `runtime_source.type == "legacy_connect"` AND harness_package 非空 | **defensive unknown**(reason: `"package present on legacy_connect — preflight should have rejected this"`)—— 正常情况 §7 preflight 已 hard fail,本分支只是 evidence 层 defense-in-depth,**绝不**升 strong |

显式 redline(Kun):
- Package 出现**不允许**把 legacy_connect 升 medium 或 strong。
- Package 缺指纹**只能 downgrade**(strong → medium),不能 upgrade。

### 13.3 不动的部分

- `materials/*-evidence.md` 升 legacy_connect 到 medium 的逻辑 → 不动。
- weak / unknown 触发 warning 的逻辑 → 不动(spec
  `evidence-aware-result.md` §5.1)。
- `evidence.summary` 三档 warning/note 决策 → 不动。
- 旧 snapshot(v0.3.x / v0.4.x,无 `harness_package` 字段)→ 推断完全
  等价 v0.4(读不到字段 = null = no package)。

---

## 14. Backward compatibility

| 来源 | v0.5 行为 |
|---|---|
| v0.4 snapshot(无 `harness_package` 字段) | 推断时视作 null;evidence 不变。 |
| v0.4 score JSON(无 `evidence.variants[*].harness_package`) | unchanged;evidence schema 不强制 per-variant 出现 harness_package 子段(仅 snapshot 出)。 |
| v0.4 variant(无 `harness_package:` frontmatter) | 完全等价 v0.4 行为;snapshot 里 `harness_package: null`。 |
| v0.4 experiment without `harness-packages/` dir | OK,空 packages 索引;若任何 variant 引用了 package → ERR-RESOLV-1。 |
| v0.4 score/compare flow | 不变(`score` / `compare` / `report.build_compare_report` 不需要新参数;`harness_package` 是 snapshot-only) |
| v0.4 327 个 existing tests | 必须全部继续通过(regression gate)。 |

向后兼容是**硬契约**:`feat(harness-package)` 不允许破任何 v0.4 行为。

---

## 15. Error cases

错误标识 + 触发条件 + 抛错类型 + 用户消息要点:

| ID | 触发 | 抛错 | 用户消息要点 |
|---|---|---|---|
| ERR-MANIFEST-1 | manifest.id ≠ path id | `ValueError` → `WorkflowError` | `manifest id "..." 跟目录 "..." 不一致;路径 = 真理` |
| ERR-MANIFEST-2 | manifest.version ≠ path version | `ValueError` → `WorkflowError` | `manifest version "..." 跟目录 "..." 不一致` |
| ERR-MANIFEST-3 | runtime_compatibility 空 / 含 legacy_connect | `ValueError` → `WorkflowError` | `runtime_compatibility 不能为空或含 legacy_connect(MVP 仅支持 local_path / git_repo)` |
| ERR-MANIFEST-4 | 三段全空(无 files / 无 env / 无 start_command) | `ValueError` → `WorkflowError` | `package 没有任何 effect(files/env/start_command 全空)` |
| ERR-MANIFEST-5 | unknown frontmatter field | `ValueError` → `WorkflowError` | `manifest 含未知字段:...` |
| ERR-MANIFEST-6 | path traversal in payload source | `ValueError` → `WorkflowError` | `package payload source 越出 payload/ 目录:...` |
| ERR-VARIANT-1 | variant `harness_package` 字段格式非 `<id>@<version>` | `WorkflowError` | `variant X 的 harness_package 必须是 <id>@<version> 格式(v0.5 不接受 bare id)` |
| ERR-VARIANT-2 | variant 有 harness_package 但无 runtime_source(或 legacy 路径) | `WorkflowError` | `variant X 用 harness_package 必须同时指定 runtime_source(legacy connect 不支持 package install)` |
| ERR-RESOLV-1 | variant 引用 `<id>@<version>` 不在 harness-packages/ 索引 | `WorkflowError` | `variant X 引用的 package "<id>@<version>" 不存在;可用:...` |
| ERR-COMPAT-1 | variant runtime_source.type ∉ manifest.runtime_compatibility | `WorkflowError` | `package "<id>@<version>" runtime_compatibility = [...] 不含 variant 的 runtime_source.type = "..."` |
| ERR-COMPAT-2 | (defensive) package 在 legacy_connect 上 | `WorkflowError` | 同 ERR-VARIANT-2 |
| ERR-INSTALL-1 | install 时 target path traversal | `RuntimeError` → `WorkflowError` | `package payload target 越出 sandbox:...` |
| ERR-INSTALL-2 | install 时 payload source 文件不存在 | `FileNotFoundError` → `WorkflowError` | `package payload source 不存在:...` |
| ERR-START-CMD | package + patch 都不提供 start_command,manifest 也没 | `WorkflowError` | `variant X:必须由 package manifest 或 variant ## Patch 至少一方提供 start_command` |

所有错误**preflight 触发 → 在 `apply_patch` 之前** fail,不污染 sandbox。

---

## 16. Tests required

按 8 组规划,目标 **~50 新测试**(252 → 327 v0.4 → ~377 v0.5 baseline):

### Group A — Manifest parse (~10)
- 有效 manifest 全字段 → 加载成功
- 缺 id / version / runtime_compatibility / Description 段 → ERR-MANIFEST-*
- runtime_compatibility 含 legacy_connect → ERR-MANIFEST-3
- runtime_compatibility 含未知 type(如 docker_image)→ OK(forward-compat,
  不抛错;仅在 variant 实际用时若不匹配抛)
- unknown frontmatter 字段 → ERR-MANIFEST-5
- duplicate id@version(同一 path 二次写入)→ filesystem 保证;不写专门
  test
- manifest.id ≠ path id → ERR-MANIFEST-1
- manifest.version ≠ path version → ERR-MANIFEST-2
- 三段全空 → ERR-MANIFEST-4
- payload source path traversal → ERR-MANIFEST-6

### Group B — Hash stability (~8)
- 同 manifest bytes → 同 manifest_hash
- 同 payload(文件+env+start_cmd)→ 同 payload_hash
- file content 变 → payload_hash 变
- env key/value 变 → payload_hash 变
- start_command 变 → payload_hash 变
- file 顺序不影响(deterministic sort)
- 同 (package+patch)+ 同 sandbox 起始 → 同 effective_harness_hash
- effective_harness_hash 反映 patch 对 package 同名文件的覆盖

### Group C — Install / apply (~10)
- variant only package(no patch)→ payload 落 sandbox + env 生效 +
  start_command 用 manifest
- variant package + patch:patch override package 同名文件 → 文件最终 = patch
  内容
- variant package + patch:patch.env 覆盖 package.env(per-key)
- variant package + patch:patch.start_command 覆盖 manifest start_command
- variant package(manifest 无 start_command) + patch(无 start_command)
  → ERR-START-CMD
- variant package + patch:env 合并算法 verify
- package payload target_path traversal → ERR-INSTALL-1
- package payload source 缺失 → ERR-INSTALL-2
- package install 后 sandbox 文件权限 / chmod 处理(Windows .git read-only
  类似)
- install_order 始终为 ["package", "patch"](v0.5 固定)

### Group D — Resolution (~7)
- workspace 无 harness-packages/ + variant 引用 → ERR-RESOLV-1
- variant 引用不存在的 id@version → ERR-RESOLV-1
- variant 引用 bare id(无 @version)→ ERR-VARIANT-1
- variant 有 package 但无 runtime_source → ERR-VARIANT-2
- variant 在 legacy connect 路径 + package → ERR-VARIANT-2 (defensive
  ERR-COMPAT-2)
- variant runtime_source.type 不在 manifest.runtime_compatibility →
  ERR-COMPAT-1
- 多 variant 引用同一 package(应该 OK,共享 install)

### Group E — Snapshot integration (~6)
- snapshot `harness_package` block 字段完整(id/version/ref/manifest_path/
  manifest_hash/payload_hash/effective_harness_hash/install_order)
- 无 package variant → `harness_package: null`
- snapshot.manifest_path 是相对 workspace root 的路径(reproducible)
- effective_harness_hash 包含 patch + package union targets
- install_order 字段值固定 `["package", "patch"]`
- snapshot JSON serializable

### Group F — Evidence integration (per Correction 4) (~7)
- variant package + materialized strong + 三 hash 齐 → **strong**(v0.4
  rule extended)
- variant package + materialized strong + 缺 manifest_hash → **medium**
  (reason "incomplete harness package fingerprint")
- variant package + materialized strong + 缺 payload_hash → medium
- variant package + materialized strong + 缺 effective_harness_hash → medium
- variant package + materialized medium(v0.4 medium 条件)→ stays medium,
  额外 reason 提 package
- variant no package(v0.4 strong)→ unchanged strong
- defensive: snapshot 显式 legacy_connect + harness_package non-null →
  **unknown** with "preflight should have rejected this" reason(永不
  升 strong)

### Group G — Backward compatibility (~5)
- v0.4 snapshot(无 harness_package 字段)→ 推断成功,行为等价 v0.4
- v0.4 variant(无 harness_package frontmatter)→ snapshot 里
  `harness_package: null`
- workspace 没 harness-packages/ + 所有 variant 无 ref → 327 v0.4 tests
  全过(regression gate,实际跑 pytest 验证)
- v0.4 score JSON old 文件 + compare 重算 → evidence 一致
- old experiment 直接升级到 v0.5,无 source 改动 → run/score/compare 仍跑通

### Group H — Redlines (~3)
- `ahl --help` 13 subcommands 不变(meta-test)
- evidence.py / harness_package.py 无外部依赖(stdlib only)
- no network call in test suite(sanity: subprocess 调用清单 review)

**总计**:~56 new tests。327 → ~383(预估)。

---

## 17. Implementation plan

### 17.1 文件清单

**新建 (5)**:

| 路径 | 估行 | 作用 |
|---|---|---|
| `src/agent_harness_lab/harness_package.py` | ~280 | `Manifest` dataclass + `parse_manifest` + `compute_manifest_hash` + `compute_payload_hash` + `compute_effective_harness_hash` + `install_package_payload` + `_safe_payload_source_path` |
| `tests/test_harness_package.py` | ~500 | Groups A + B + D + H |
| `tests/test_harness_package_integration.py` | ~350 | Groups C + E + F + G end-to-end |
| `examples/harness-packages/minimal-strict-prompt/0.1.0/{manifest.md, payload/system.md}` | ~30 | Reference example |
| `(本文件)` `docs/harness-package-mvp.md` | ~450 | spec (此份;**已存在,本步唯一交付**) |

**修改 (8)**:

| 路径 | 估 ± | 改动 |
|---|---|---|
| `src/agent_harness_lab/version.py` | +15 / -0 | parse `harness_package:` frontmatter field;`Version.harness_package: str \| None` |
| `src/agent_harness_lab/workflow.py` | +40 / -2 | preflight: 扫 packages + resolve + cross-validate;materialize 后 install 前调 install_package_payload |
| `src/agent_harness_lab/materialize/__init__.py` | +8 / -0 | `MaterializeContext.harness_packages: dict[(id, version)] → Manifest` + `MaterializeContext.variant_packages: dict[variant_id] → Manifest \| None` |
| `src/agent_harness_lab/materialize/local_path.py` | +5 / -0 | start 前合并 env(package + patch),resolve start_command |
| `src/agent_harness_lab/materialize/git_repo.py` | +5 / -0 | 同上 |
| `src/agent_harness_lab/snapshot.py` | +40 / -2 | `build_snapshot` 加 `harness_package` 块计算逻辑(manifest_hash + payload_hash + effective_harness_hash) |
| `src/agent_harness_lab/evidence.py` | +20 / -2 | 读 `harness_package` 字段;§13.2 规则扩展;defensive legacy_connect + package 分支 |
| `docs/file-formats.md` | +80 / -0 | `harness-packages/` schema + V*.md `harness_package:` + snapshot `harness_package` 块 + Evidence schema 扩展 |
| `docs/runtime-materialization.md` | +25 / -2 | package install 嵌入 materialize flow;明确"package 在 patch 之前" |
| `docs/evidence-aware-result.md` | +35 / -2 | §13 evidence interaction 链入;指向本 spec |
| `docs/product-walkthrough.md` | +12 / -1 | Step 5 提 package 选项(`harness_package: id@version`) |
| `docs/roadmap.md` | +3 / -3 | v0.5 [planned] body 细化;release-prep commit 才 [shipped] |
| `CHANGELOG.md` | +5 / -0 | `[Unreleased] / Added` 4 条 bullets |

### 17.2 Diff 估计

- 新文件: ~1610 行(5 个,含本 spec 已计入)
- 改文件: ~+293 / -16(13 个)
- **总计 ~1900 行 added,~16 行 deleted,~18 files touched**(略大于 v0.4)

### 17.3 Commit split

**2 commits 推荐**(沿用 v0.4 节奏):

- **C1**: `feat(harness-package): manifest parser, payload + manifest hashing`
  - 涉及:`harness_package.py`(parser + 2 hash 函数 + payload source 路径
    校验,**不含 install**)·`version.py` 加 frontmatter 字段 ·
    `workflow.py` preflight 加 resolution+validation ·
    `tests/test_harness_package.py` 含 Groups A/B/D/H ·
    `docs/harness-package-mvp.md`(spec 全量)+
    `docs/file-formats.md`(manifest schema 段)
  - 独立可 ship:数据层 + spec + 验证,无 install 行为变化
  - 必须 v0.4 327 tests 全过

- **C2**: `feat(harness-package): install into materialize + snapshot + evidence`
  - 涉及:`harness_package.py` 加 `install_package_payload` +
    `compute_effective_harness_hash` ·
    `materialize/*` 加 install hook + env/start_command 合并 ·
    `snapshot.py` 加 `harness_package` 块 ·
    `evidence.py` §13.2 规则 ·
    `tests/test_harness_package_integration.py` 含 Groups C/E/F/G ·
    `examples/harness-packages/minimal-strict-prompt/` 示例 ·
    余下 docs(`runtime-materialization.md` / `evidence-aware-result.md` /
    `product-walkthrough.md`)+ CHANGELOG bullet
  - 必须 ~377 tests 全过(C1 加的 + C2 加的 + v0.4 327 全过)

### 17.4 Spec first?

**Yes**(本步)。本 spec 是 C1 的 GO 条件;Kun 接受后才开始 C1 编码。

### 17.5 Review bundle structure

每个 commit 自带 review bundle,模板沿用 v0.4:

```
temp/v0.5.0-harness-package-mvp-c1-review/
├── RELEASE_REVIEW_SUMMARY.md
├── CHANGELOG.md (copy)
├── src/{harness_package.py, version.py, workflow.py}
├── docs/{harness-package-mvp.md, file-formats.md}
├── tests/test_harness_package.py
└── samples/{manifest-example.md, validation-errors-snippet.md}

temp/v0.5.0-harness-package-mvp-c2-review/
├── RELEASE_REVIEW_SUMMARY.md
├── src/{harness_package.py (install+hash), materialize/*, snapshot.py, evidence.py}
├── docs/{runtime-materialization.md, evidence-aware-result.md, product-walkthrough.md}
├── tests/test_harness_package_integration.py
├── examples/harness-packages/minimal-strict-prompt/0.1.0/
└── samples/{snapshot-with-package.json, evidence-with-package-snippet.md, compare-report-with-package.md}
```

### 17.6 Release prep

C1+C2 都进 main 后,单独的 release-prep commit:
- `pyproject.toml` 0.4.0 → 0.5.0
- `CHANGELOG.md`:`[Unreleased]` bullets → `[0.5.0] - <date>` 段;link refs
  加 0.5.0
- `docs/roadmap.md`:v0.5 `[planned]` → `[shipped]`(v0.6/v0.9 不动)

后续 tag / release / push 流程沿用 v0.4 standing rules。

---

## 18. Stability commitment

v0.5 锁的字段:

- Variant frontmatter: `harness_package` 字符串,格式 `<id>@<version>`
- Manifest 字段: `id` / `version` / `runtime_compatibility` 必填;
  `## Description` / `## Payload` 段必存(payload 三子段任意组合)
- Snapshot `harness_package` 字段: 8 个 key 列表稳定(§12)
- `install_order` v0.5 固定 `["package", "patch"]`
- evidence 规则: §13.2 表格规则稳定

未来允许扩展:
- 加 `runtime_compatibility` 新 type(docker_image 等)
- 加 manifest 新段(如 `## Dependencies` —— 但仍不引入 registry)
- 加 snapshot 新字段(`install_log` 等),不动现有 8 个

不允许打破:
- 上述任何字段名 / 含义
- evidence 规则的方向性(package 不能 promote weak / legacy_connect)
- install_order 的两步语义(可加新值,不能改前两位的含义)

---

## 19. Open questions (待开发期 finalize)

1. **`effective_harness_hash` 的 union 含义**:patch.target ∪ package.target
   是文件 union;`compute_effective_harness_hash` 处理 patch 写入但 package
   没有的文件 → 写 unit test 锁定。spec 默认:include。
2. **路径分隔符规范化**:`manifest_path` 应统一用 forward slash 还是 OS-native?
   建议 forward slash(Path.as_posix())以保 cross-platform reproducibility。
3. **`runtime_compatibility` 未知 type 行为**:parser 接受(forward-compat),
   variant 实际用时若不匹配抛 ERR-COMPAT-1。需 test 覆盖。
4. **`payload/` 空目录支持**:manifest 三段全空已 ERR-MANIFEST-4;若 payload
   有 env / start_command 但 files 空(无 payload/ 文件)→ OK(payload 目录
   存在但空)。
5. **Manifest description 段必须非空 vs 可空**:本 spec 写"段必须存在",
   描述允许 free-form 空文本;parser 不抛。改 ValueError 与否待定。
6. **多 package per variant**:v0.5 不支持(`harness_package` 是 string,
   不是 list)。未来若需要,字段升级为 list 兼容 string。MVP 限制。

C1 编码前 Kun 确认这些 open question。
