# Evidence-Aware Result · v0.4 Spec

> 这份 spec 描述 v0.4 evidence-aware result 的契约 —— 把 v0.3.0 已经持久化
> 的 runtime snapshot 事实读出来,作为 keep/discard 决策的依据 surface 到
> score JSON 和 compare report 里。
>
> Status: target v0.4.0,branch `v0.4.0-evidence-aware-result`。
> Date: 2026-05-25。
>
> 本文是 `product-walkthrough.md` **Step 8 (inspect evidence)** 的
> depth-detail。还没读 walkthrough 的从
> [`product-walkthrough.md`](product-walkthrough.md) 起。可运行 sample:
> [`examples/sample-workspace/`](../examples/sample-workspace/) — 跑完后
> `compare-*.md` 顶部 `## Evidence` section 是 v0.4 evidence 链的产物。
>
> **User-facing companion**: [`evidence-guide.md`](evidence-guide.md) ——
> 这份 spec 是实现合同(level 推断规则、JSON schema、graceful 降级路径);
> evidence-guide 是用户层解读手册(每档什么时候可信、weak → medium 怎么
> 升、worked examples、AHL 不证明什么)。两份互补 —— 如果只读一份,新用户
> 先读 evidence-guide,改 code 的时候再读这份。

---

## 0. Purpose

v0.3.0 Runtime Materialization M1 per (run, variant) 落了一份 snapshot,
含 runtime source type、`source_dir_hash`、`patch_hash`、`commit_sha`
等可复现指纹。v0.4 把这些事实读出来,推断 evidence level 并标到 score
JSON 和 compare report 里。**runtime 行为零变化 —— evidence 是解读,
不是采集**。

---

## 1. Non-goals

明确不做的事:

- **不**改 `results/run-*.json` schema —— 它仍是 raw fact layer,
  v0.3.0 加的 `snapshot_id` 已经够用。
- **不**改 scoring math、comparison math、winner selection。
- **不**因 evidence level block 任何 run / score / compare 流程。
- **不**解析 `materials/*-evidence.md` 的内容 —— 只检 existence。
- **不**默认创建 evidence 文件。
- **不**加新 CLI 命令。
- **不**动 runtime materialization / snapshot persistence / adapter 代码。

---

## 2. Evidence levels

四个枚举,定义见 §3 推断规则。

| Level | 含义 |
|---|---|
| `strong` | Snapshot 完整可复现:materialized runtime 含必填 hash。 |
| `medium` | materialized runtime 缺部分指纹,**或** legacy_connect 含至少一份 materials evidence 文件。 |
| `weak` | legacy_connect 不含任何 materials evidence 文件。 |
| `unknown` | Snapshot 文件缺失 / 损坏,或 `runtime_source.type` 不识别。 |

---

## 3. Inference rules

Pure function `infer_evidence_from_snapshot(snapshot_dict, materials_dir) → dict`。
输入是 `results/snapshots/<run_id>/<variant_id>.json` 解码后的 dict
(或 None) + `experiments/<id>/materials/` 目录路径 (可能不存在)。

### 3.1 `runtime_source.type = "local_path"`

| 条件 | Level |
|---|---|
| `source_dir_hash` 缺失 | medium |
| `harness_patch` is None (无 patch 声明) | **strong** |
| `harness_patch` 存在 + `patch_hash` 存在 | **strong** |
| `harness_patch` 存在 + `patch_hash` 缺失 | medium |

**关键**:`harness_patch` 不存在 (即 variant 跑的是 raw source 不打 patch)
**不**降级。raw source 跑也是完全可复现。

### 3.2 `runtime_source.type = "git_repo"`

| 条件 | Level |
|---|---|
| `commit_sha` 缺失 **或** `source_dir_hash` 缺失 | medium |
| `harness_patch` is None | **strong** |
| `harness_patch` 存在 + `patch_hash` 存在 | **strong** |
| `harness_patch` 存在 + `patch_hash` 缺失 | medium |

同 §3.1,`harness_patch` 不存在不降级。

### 3.3 `runtime_source.type = "legacy_connect"`

| 条件 | Level |
|---|---|
| `materials/` 下含任一 evidence 文件 | medium |
| 不含任何 evidence 文件 | weak |

Evidence 文件清单 (existence-only,**不**解析内容):

- `materials/runtime-evidence.md`
- `materials/harness-evidence.md`
- `materials/cloud-evidence.md`

`materials_dir` 是 `experiments/<id>/materials/`。该目录不存在
(如 manual 模式) → legacy_connect 仍 weak。

### 3.4 Unknown cases

| 条件 | Level |
|---|---|
| Snapshot 文件缺失 (如 v0.2.x 旧 run) | unknown |
| Snapshot 文件 corrupt (UnicodeDecodeError / JSONDecodeError) | unknown |
| `runtime_source.type` 不在 {local_path, git_repo, legacy_connect} | unknown |

---

## 4. Score result schema

`results/score-*.json` 新增 top-level `evidence` 字段:

```json
{
  "run": "run-20260525-160000.json",
  "rubric": "rubric.md",
  "grader": "本地桩(未接真模型)",
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
      },
      "V2": {
        "level": "weak",
        "runtime_source_type": "legacy_connect",
        "snapshot_id": "legacy",
        "snapshot_available": true,
        "materials_evidence": [],
        "reasons": ["legacy_connect with no materials evidence files"]
      }
    },
    "summary": {
      "levels": {"strong": 1, "medium": 0, "weak": 1, "unknown": 0},
      "warning": "weak/unknown evidence may be behavioral-only or missing metadata; do not treat this as fully reproducible harness comparison",
      "note": null
    }
  }
}
```

`evidence.variants[<vid>]` 字段稳定列表:
- `level` ∈ {strong, medium, weak, unknown}
- `runtime_source_type` (string or null)
- `snapshot_id` (string or null)
- `snapshot_available` (bool)
- `materials_evidence` (list of evidence filenames present)
- `reasons` (list of human-readable strings)

`evidence.summary` 字段:
- `levels` (固定 4 个 key 的 count map)
- `warning` (string or null) — 见 §5 三档策略
- `note` (string or null) — 见 §5 三档策略

---

## 5. Compare report behavior

`results/compare-*.md` 在版本总分段**之前**新增 `## Evidence` section。
内容:

1. Markdown 表格:variant / level / source / snapshot / materials / reasons
2. 之后按下表加 `⚠ <warning>` 或 `ℹ <note>` (若有)

### 5.1 三档 warning 策略 (per Kun 调整)

**判断顺序固定:先检查 weak/unknown,再检查 level 是否一致**。所以任何含 weak 或
unknown 的组合(包括全 weak / 全 unknown / weak+medium / unknown+strong 等)
都触发 `⚠ warning`,不退化成 `ℹ note`,不退化成"无提示"。

| 条件 (this compare 的 variants) | 输出 |
|---|---|
| 所有 variant 都是 strong,或都是 medium(uniform 且无 weak/unknown) | 只显示 Evidence 表格,**无** warning/note |
| 无 weak/unknown,但 level 不一致 (如 strong + medium) | Evidence 表格 + `ℹ` 提示 "evidence levels differ; comparison is useful but not equally grounded" |
| 任意 variant 是 weak 或 unknown(**包括全 weak / 全 unknown / weak+medium / unknown+strong 等所有混合**) | Evidence 表格 + `⚠` 警告 "weak/unknown evidence may be behavioral-only or missing metadata; do not treat this as fully reproducible harness comparison" |

完整 matrix (Kun adjustment 1 + Blocker 1 fix):

| V1 \ V2 | strong | medium | weak | unknown |
|---|---|---|---|---|
| **strong** | — | ℹ note | ⚠ warning | ⚠ warning |
| **medium** | ℹ note | — | ⚠ warning | ⚠ warning |
| **weak** | ⚠ warning | ⚠ warning | ⚠ warning | ⚠ warning |
| **unknown** | ⚠ warning | ⚠ warning | ⚠ warning | ⚠ warning |

不 block compare,不改 winner / score diff 逻辑。

### 5.2 CLI stdout

`ahl compare` 当前打 `report_text` + 报告文件路径。v0.4 在最后追加
一行 (若 warning 或 note 存在):

- warning: `⚠ <warning> — 见 report 顶部 Evidence 段`
- note (无 warning): `ℹ <note> — 见 report 顶部 Evidence 段`

退出码不变。无 warning/note 时不打。

---

## 6. Old result compatibility

| 来源 | 行为 |
|---|---|
| v0.4+ `score-*.json` 含 `evidence` 字段 | compare 直接读用。 |
| v0.3.x `score-*.json` (无 `evidence`) + run-*.json 可读 | compare 加载 `score.run` 引用的 `run-*.json`,从 filename 推 `run_id`,on-the-fly 重算 evidence。**不** rewrite score JSON。 |
| v0.2.x run record 无 `snapshot_id` 字段 | snapshot 文件定位不到 → evidence level = unknown(per-variant 仍出现在 Evidence section)。 |
| Snapshot JSON 损坏 / 缺失 | 该 variant evidence level = unknown,reasons 含原因。 |
| **run-*.json 缺失 / 损坏 / 文件不可读** (Blocker 2 fix) | **fallback synthesis**:从 score 的 `scores` 数组提取 unique `version_id`,每个 variant 合成一条 unknown 记录(`snapshot_available=false`,reasons = "score result has no evidence metadata and run/snapshot could not be loaded")。**Evidence section 仍出现**,⚠ warning **仍触发**。compare 不 crash 不 block。 |

旧 result 不 crash compare。Recompute / synthesize 是 best-effort,但**只要
score 含至少一条 entry,Evidence section 一定在 compare report 里出现**,user
不会因为 metadata 缺失而错过 weak/unknown 的提醒。

---

## 6.1 v0.6: probe → materials/runtime-evidence.md → v0.4 升级 channel

v0.6 加 `ahl probe --write-evidence`(详见
[`runtime-probe-mvp.md`](runtime-probe-mvp.md))。对 legacy_connect variant
+ probe status ∈ {ok, warn} 时,probe **自动写**
`materials/runtime-evidence.md`,内容含 probe_id / variant_id / status /
captured_at / checks performed / smoke command + truncated stdout/stderr /
limitations。

下次 `ahl score` 推断 evidence 时,`_detect_materials_evidence` 扫到该
文件 → 按 v0.4 §3.3 规则,legacy_connect weak → medium。**v0.4 evidence
推断规则本身不变**;probe 只是把"写 materials evidence"这步从用户手工
变成 `ahl probe --write-evidence` 自动化。

probe status = fail 时**不写** materials 文件(spec §7.4 correction),
避免假证据污染 evidence 链。

---

## 7. What v0.4 does NOT change

- `results/run-*.json` schema 不动 — `snapshot_id` 已 v0.3.0 加好。
- `results/snapshots/*.json` schema 不动 — 已完整。
- `score-*.json` `scores` 数组不动。
- `compare-*.md` `版本总分:` / `维度变化:` / `退化维度:` 段不动。
- 所有 CLI 命令不动 (compare 只多一行 stdout 若有 warning/note)。

---

## 8. Implementation surface

| 文件 | 类型 | 改什么 |
|---|---|---|
| `src/agent_harness_lab/evidence.py` | 新 | pure inference + score/run summarize + warning/note 决策 |
| `src/agent_harness_lab/workflow.py` | 改 | score 写 evidence 段;compare 读或 fallback 重算;`CompareResult` 加 `evidence` 字段 |
| `src/agent_harness_lab/report.py` | 改 | `build_compare_report` 加 `evidence` 参数 + 渲染 Evidence section |
| `src/agent_harness_lab/cli.py` | 改 | `cmd_compare` 末尾若 warning/note 加一行 |
| `docs/file-formats.md` | 改 | score-*.json 的 `evidence` 字段 + compare-*.md 的 Evidence section |
| `docs/product-walkthrough.md` | 改 | Step 8 提一句 evidence level surface |
| `CHANGELOG.md` | 改 | `[Unreleased] / Added` 加一条 bullet。**不**加 `[0.4.0]` heading (release prep 阶段才加) |

---

## 9. Test coverage

- A: evidence inference (12 cases 覆盖 §3 全部规则)
- B: score integration (score JSON 含 evidence;旧 snapshot 缺失不 crash)
- C: compare/report integration (Evidence section 渲染;3 档 warning;compare math 不动)
- D: CLI stdout (weak/unknown 打警告行;全 strong 不打)
- E: 红线 (`ahl new --mode auto` 仍 exit 2;`ahl new copilot` 不默建 evidence 文件;CLI 命令数不变)

---

## 10. Stability commitment

`evidence.summary.levels` 的 4 个 key 名固定。`warning` / `note` 字段为
nullable string。后续版本可扩 `summary` 字段,但以上 key 不动。
