# Agent Harness Lab · Evidence Guide

> User-facing companion to [`evidence-aware-result.md`](evidence-aware-result.md)
> (v0.4 spec) and the package-overlay extension in
> [`harness-package-mvp.md`](harness-package-mvp.md) §13.
>
> Audience: someone reading a `compare-*.md` Evidence section who wants to
> understand what "strong / medium / weak / unknown" means and what they can
> do about it. If you want the implementation contract, read the spec. If you
> want to interpret a result and decide keep / discard / next, read this.
>
> Status: depth-detail for [`product-walkthrough.md`](product-walkthrough.md)
> Step 8 (inspect evidence). Date: 2026-05-26.

---

## 1. Why evidence exists in AHL

AHL compares harness variants on the same cases and reports per-variant scores.
The scores are produced by a grader running over conversations the agent
produced. **That is enough to rank variants, but not enough to tell you why
the rank is what it is.** Two failure modes are common:

- A variant got `+0.4` on a dimension, but **the variant didn't actually
  receive the patch you thought it received** — the runtime quietly fell
  back to the global config, or the cloud deployment still pointed at an
  older harness. The score is real; the attribution is wrong.
- A variant got `-1.2` on a dimension, and the change *was* applied as
  intended — but you don't know whether the regression is from your change
  or from the runtime drifting between when you ran V1 and when you ran V2.

Evidence is the **third column** in every result: alongside *who won* (score)
and *what the win was made of* (per-dimension delta), it tells you **how
confidently AHL can attribute the result to the harness you wrote**.

The levels (`strong / medium / weak / unknown`) summarize that confidence
in one word, and the reasons explain it in one line. Evidence is **advisory**
— it never blocks a run or a score — but ignoring it turns AHL into a
benchmark tool, not a harness-improvement tool.

---

## 2. The 5 evidence-related artifacts

AHL produces five different artifacts that *contain or carry* evidence
information. New users routinely confuse these. The table fixes that:

| # | Artifact | Where it lives | Who produces it | What it carries |
|---|---|---|---|---|
| 1 | **Snapshot** | `experiments/<id>/results/snapshots/<run_id>/<variant_id>.json` | `ahl run` (every run, every variant) | The raw reproducibility facts: `runtime_source.type`, `source_dir_hash`, `commit_sha`, `patch_hash`, `harness_package` block with 3 fingerprint hashes. Mostly machine-readable. |
| 2 | **Supplied materials evidence** | `experiments/<id>/materials/{runtime,harness,cloud}-evidence.md` | User (or `ahl probe --write-evidence` for legacy variants) | User-authored Markdown attestation of what's actually installed in an external agent. AHL reads file *existence* only — never parses content. |
| 3 | **Probe artifact** | `experiments/<id>/probe-results/<probe_id>/<variant_id>.json` | `ahl probe <experiment>` | Read-only pre-run inspection: runtime accessible? package complete? start command supplied? optional smoke command result. **Does not enter snapshots in v0.6+v0.7.** |
| 4 | **Score evidence** | `experiments/<id>/results/score-*.json` top-level `evidence` block | `ahl score` (derived from snapshot + materials) | The **inferred** per-variant `level` (`strong`/`medium`/`weak`/`unknown`) + machine-readable `reasons`. |
| 5 | **Compare evidence** | `experiments/<id>/results/compare-*.md` `## Evidence` section | `ahl compare` (rendered from score evidence) | Human-readable evidence table that appears **above** the version-totals section. Includes `⚠` / `ℹ` callouts when levels mix. |

How they layer:

```
snapshot (1) + supplied materials (2)
        │
        ▼
   v0.4 inference rules
        │
        ▼
   score evidence (4)
        │
        ▼
   compare evidence (5)

probe artifact (3) — independent advisory channel; affects evidence chain
                     only via the supplied-materials path that
                     --write-evidence writes for legacy variants
```

**One number on a compare report (the level word) is built from snapshot
facts plus, optionally, file-existence checks on `materials/`. Nothing
else.**

---

## 3. The 4 evidence levels

| Level | One-line definition |
|---|---|
| `strong` | AHL materialized the runtime itself and the snapshot is fully fingerprinted. |
| `medium` | Either AHL materialized but a fingerprint is missing, **or** a legacy `connect.md` variant has at least one user-supplied `materials/*-evidence.md` file present. |
| `weak` | Legacy `connect.md` variant with no user-supplied evidence — AHL has only the agent's *behavior*, not its identity. |
| `unknown` | Snapshot file is missing or corrupt, or the `runtime_source.type` is unrecognized. |

### 3.1 `strong`

- The runtime was a `local_path` or `git_repo` source AHL itself materialized
  into a sandbox.
- For `local_path`: snapshot has `runtime_source.source_dir_hash`.
- For `git_repo`: snapshot has `runtime_source.commit_sha` **and**
  `source_dir_hash`.
- If the variant declared a `## Patch` section, snapshot also has
  `harness_patch.patch_hash` (covering the patched files + env +
  start_command). Variants with no patch (raw source) stay strong without
  one — raw source is reproducible by definition.
- If the variant uses a harness package (v0.5), snapshot has the full
  `harness_package` block with `manifest_hash`, `payload_hash`, and
  `effective_harness_hash` all set.

### 3.2 `medium`

Two distinct ways to land here:

- **Materialized runtime with an incomplete fingerprint.** For example, the
  variant uses a harness package but the `effective_harness_hash` is
  missing from the snapshot. The score is still trustworthy, but you
  can't replay the exact harness state from the snapshot alone.
- **Legacy `connect.md` variant with supplied attestation.** Any one of
  `materials/runtime-evidence.md` / `harness-evidence.md` /
  `cloud-evidence.md` exists in the experiment's `materials/` directory.
  AHL counts this as an upgrade from `weak` to `medium` because it
  signals the user *claims* to have evidence of what was installed —
  even though AHL itself never reads the file content.

### 3.3 `weak`

- Variant uses legacy `connect.md` (no `runtime_source` declared).
- No `materials/*-evidence.md` files exist.
- AHL connected to an existing agent, exchanged messages, and recorded
  the conversation. That's it. **It has no proof what's running inside.**
- Common case: you point AHL at a long-running cloud agent and don't
  supply any attestation file. The scores are meaningful (real
  conversations were graded) but the variant comparison is
  behavioral-only. If two `weak` variants disagree, you can't tell
  whether the harness change caused the difference or whether the cloud
  agent silently changed.

### 3.4 `unknown`

- Snapshot file at the expected path doesn't exist, or exists but is
  malformed JSON. (Rare; most often a half-deleted run directory.)
- `runtime_source.type` in the snapshot is something AHL doesn't
  recognize. (Should not happen in v0.7 — only `local_path`, `git_repo`,
  and `legacy_connect` are valid; future runtime source types will
  resolve here until support lands.)
- Always treat `unknown` as "do not use this result for decisions."

---

## 4. How a result becomes strong

A flow chart in words:

```
Did you declare runtime_source: <name> in the variant's frontmatter?
    NO  → legacy_connect path (skip to §5)
    YES → continue

Is runtime_source.type local_path or git_repo?
    NO  → unknown (future source types not yet supported)
    YES → continue

For local_path: does the snapshot have runtime_source.source_dir_hash?
    NO  → medium ("local_path missing source_dir_hash")
    YES → continue

For git_repo: does the snapshot have BOTH commit_sha AND source_dir_hash?
    NO  → medium ("git_repo missing <fields>")
    YES → continue

Did the variant declare a ## Patch section?
    NO  → STRONG ("no harness_patch declared" — raw source is reproducible)
    YES → check patch_hash:
        Missing patch_hash → medium ("harness_patch present but missing patch_hash")
        Present patch_hash → continue

Does the variant declare harness_package: <id>@<version>?
    NO  → STRONG (no overlay)
    YES → check 3 hashes (manifest_hash + payload_hash + effective_harness_hash):
        All 3 present → STRONG ("harness_package <ref> fully fingerprinted")
        Any 1 missing → DOWNGRADE to medium ("incomplete fingerprint")
```

**Short version:** Use `runtime-sources.md` instead of `connect.md`. Use
proper `## Patch` or `harness_package` declarations. Don't hand-edit
snapshot files. That's it.

If you see `medium` on a materialized variant and the reason cites a
missing hash, run `ahl probe <experiment>` to see what AHL currently
knows about the runtime + package state; the probe artifact often
explains the missing piece.

---

## 5. How supplied materials upgrade weak → medium

This rule applies to **legacy `connect.md` variants only** (no
`runtime_source` declared).

`weak` happens when AHL connects to an existing agent and can only observe
its behavior. The agent's actual configuration — system prompt, installed
plugins, memory state, deployment id — is opaque. To pull the variant out
of `weak`, **drop a file under `experiments/<id>/materials/`** with one of
three filenames:

- `runtime-evidence.md` — attestation of the agent's runtime state
  (e.g., process commands, environment variables, working directory).
- `harness-evidence.md` — attestation of which harness is loaded
  (e.g., `memory.md` content hash, plugin list, soul file path).
- `cloud-evidence.md` — attestation of a remotely deployed agent
  (e.g., deployment id, console screenshot description, debug-log
  excerpts).

**File existence is what counts.** AHL never parses these files'
content. Touching an empty `materials/runtime-evidence.md` is enough
to flip `weak → medium` per the v0.4 rules. The honor system is
intentional — see §6 for why AHL deliberately refuses to verify these.

For legacy variants that ran probe with `ahl probe --write-evidence`,
AHL itself writes `materials/runtime-evidence.md` covering checks it
performed (runtime_source / harness_package / start_command status,
optional smoke command output). Materialized variants are skipped with
a stderr warning — they don't need this auto-write path because their
snapshot already proves what ran.

See [`examples/evidence-examples/`](../examples/evidence-examples/) for
worked example files you can copy as a starting template.

---

## 6. Why supplied evidence is NOT cloud attestation

This is the most important honest disclosure in this guide.

When you author `materials/cloud-evidence.md` for a cloud-deployed agent,
you are **telling AHL** what's running on the cloud. AHL has no way to
verify the claim. There is no cryptographic signature, no API call back
to the cloud provider, no trust chain. You write the file; AHL reads
the filename and upgrades the level.

**This is by design.** AHL is a workbench for harness design, not a
compliance tool. The evidence channel exists to let *you* record what
*you* know about an external runtime, so that two months later you can
reread the compare report and remember why you trusted (or didn't trust)
the result. It is a note to your future self, not a certificate to a
third party.

Specifically, supplied evidence — including `cloud-evidence.md` — does
**not**:

- Prove the agent in the cloud at the time of run was actually configured
  the way the file claims.
- Survive any audit that asks "show me a chain of custody from the
  attestation file to the running agent."
- Upgrade beyond `medium`. Supplied evidence alone **never** reaches
  `strong`. `strong` requires AHL to have materialized the runtime
  itself.
- Get re-parsed if you change the file. AHL detects existence on each
  `ahl score` / `ahl compare` invocation. Older score JSON files
  embedded the evidence inferred at the time they were written.

If you need real cloud attestation (signed deployment manifests,
runtime introspection APIs), that is a separate problem from what AHL
solves. v0.7 / v0.8 do not implement it; see §10 below.

---

## 7. How harness packages affect evidence

v0.5 added the `harness_package: <id>@<version>` frontmatter field on
variants. When present, AHL installs the package's payload into the
sandbox **before** applying the variant's `## Patch`, and records a
`harness_package` block in the snapshot containing three hashes
(`manifest_hash`, `payload_hash`, `effective_harness_hash`) plus
`install_order` and `manifest_path`.

The evidence overlay on top of the v0.4 base rules:

| Base level | Package present? | All 3 hashes? | Result level | Reason added |
|---|---|---|---|---|
| `strong` (materialized) | no | — | `strong` | (no extra reason) |
| `strong` (materialized) | yes | yes | `strong` | `harness_package <ref> fully fingerprinted` |
| `strong` (materialized) | yes | any missing | `medium` ↓ | `materialized runtime but incomplete harness package fingerprint (missing: <fields>)` |
| `medium` / `weak` | yes | — | unchanged | `harness_package <ref> present` (additive) |
| `legacy_connect` | yes | — | `unknown` (defensive) | `package present on legacy_connect — preflight should have rejected this` |

**Key implications:**

- Adding a package can **downgrade** strong → medium if any of the 3
  hashes is missing. This is a feature: it surfaces "the package
  install path produced something we couldn't fingerprint, don't trust
  this run as fully reproducible."
- Adding a package can **never upgrade** a base medium/weak variant.
  The base path's missing reproducibility (no source_dir_hash, no
  commit_sha, no materials evidence) is the limiting factor.
- The legacy_connect + package combination is **defensive unknown**.
  Preflight (`harness_package.py`) rejects this configuration; the
  defensive case here only triggers if a snapshot is hand-edited or
  comes from a future version that allowed it.

Sample-workspace's V2 demonstrates the strong + fully-fingerprinted
case: V2 uses `concise-prompt@0.1.0`, both `payload_hash` and
`effective_harness_hash` are computed, snapshot stays strong, compare
report's reason column reads
`harness_package concise-prompt@0.1.0 fully fingerprinted`.

---

## 8. How runtime probe relates to evidence

`ahl probe <experiment>` (v0.6) is a **separate, independent inspection
command**. It does not run the experiment, does not create a sandbox,
does not modify source, and does not write into snapshots.

What probe does:

- For each variant: check `runtime_source` accessibility, `harness_package`
  manifest + payload completeness, `start_command` derivability, and
  (optional) a user-supplied smoke command.
- Write per-variant artifacts to
  `experiments/<id>/probe-results/<probe_id>/<variant_id>.json`.
- Exit non-zero if any variant probes `fail` — **advisory**; does not
  block `ahl run`.

How probe touches the evidence chain:

- **Materialized variants** (`local_path` / `git_repo`): probe results
  are pure advisory. They surface "if you ran this right now, here's
  what AHL would see," but the snapshot from the next `ahl run` is the
  authoritative evidence — it doesn't reference the probe.
- **Legacy `connect.md` variants**: `ahl probe --write-evidence` writes
  `materials/runtime-evidence.md` from the probe checks (status ∈
  {ok, warn} only — never on fail). The v0.4 evidence inference then
  detects the file's existence and upgrades the variant from `weak →
  medium` on the next score/compare.

**What probe is NOT (in v0.6 / v0.7 / v0.8):**

- Probe results are **not** bound into snapshots. A snapshot does not
  cite the probe id that preceded it.
- Probe does **not** change v0.4 inference rules. It only feeds the
  existing `materials/*-evidence.md` channel for legacy variants.
- Probe is **not** required. It is a pre-run sanity check; you can run
  `ahl run` without ever running `ahl probe`.

Stronger probe ↔ snapshot binding (recording the latest probe id +
status into each snapshot) is deferred to v0.9+ per
[`docs/roadmap.md`](roadmap.md). Until then, treat probe as an
advisory tool that may improve legacy-variant evidence and a debugging
aid for materialized variants.

---

## 9. Worked examples

Each example shows the variant configuration → snapshot fields
produced → resulting evidence level. All four are realistic; the first
is the sample-workspace canonical case.

### 9.1 Local materialized runtime, no package (sample-workspace V1)

Variant `V1`:

```yaml
---
id: V1
基线: 是
runtime_source: local-tiny
---

## Patch
start_command: python agent.py
```

Snapshot writes:

```json
{
  "runtime_source": {
    "type": "local_path",
    "source_dir_hash": "sha256:..."
  },
  "harness_patch": {
    "patch_hash": "sha256:..."
  },
  "harness_package": null
}
```

Inference:

- `runtime_source.type` = `local_path` → §3.1 path.
- `source_dir_hash` present → not the missing-hash branch.
- `harness_patch` present + `patch_hash` present → **strong**.
- No package → no overlay applied.

**Result: `strong`, reason `local_path with source_dir_hash and patch_hash`.**

### 9.2 Legacy `connect.md` with supplied runtime evidence

Setup:

- `connect.md` at workspace root pointing at a long-running local agent.
- Variant `V1.md` has no `runtime_source:` frontmatter field.
- User authored `experiments/<id>/materials/runtime-evidence.md`
  documenting the agent's process id, working directory, env vars
  (see `examples/evidence-examples/runtime-evidence.md`).

Snapshot writes:

```json
{
  "runtime_source": {"type": "legacy_connect", "connect_md_hash": "sha256:..."},
  "harness_patch": null,
  "harness_package": null
}
```

Inference:

- `runtime_source.type` = `legacy_connect` → §3.3 path.
- `_detect_materials_evidence(materials_dir)` finds
  `runtime-evidence.md` → upgrade.

**Result: `medium`, reason
`legacy_connect with materials evidence: runtime-evidence.md`.**

Without the materials file the result would be `weak`.

### 9.3 Packaged harness variant (sample-workspace V2)

Variant `V2`:

```yaml
---
id: V2
基线: 否
runtime_source: local-tiny
harness_package: concise-prompt@0.1.0
---
```

Snapshot writes:

```json
{
  "runtime_source": {"type": "local_path", "source_dir_hash": "sha256:..."},
  "harness_patch": {"applied": [], "env": {}, "start_command": null, "patch_hash": "sha256:..."},
  "harness_package": {
    "ref": "concise-prompt@0.1.0",
    "manifest_hash": "sha256:...",
    "payload_hash": "sha256:...",
    "effective_harness_hash": "sha256:...",
    "install_order": ["package", "patch"]
  }
}
```

Inference:

- Base: `local_path` + `source_dir_hash` present + `patch_hash` present →
  **strong**.
- Overlay: package present, all 3 hashes present → strong, additive
  reason.

**Result: `strong`, reasons
`local_path with source_dir_hash and patch_hash` +
`harness_package concise-prompt@0.1.0 fully fingerprinted`.**

If `effective_harness_hash` was missing from the snapshot, the overlay
would downgrade to `medium`.

### 9.4 Cloud / external runtime with only supplied evidence

Setup:

- Agent is a managed cloud deployment behind an HTTP API.
- `connect.md` declares the HTTP endpoint as `HTTP有状态` type.
- Variant `V1.md` has no `runtime_source:` (legacy path).
- User authored `experiments/<id>/materials/cloud-evidence.md`
  documenting the deployment id, configuration excerpt, and capture
  timestamp (see `examples/evidence-examples/cloud-evidence.md`).

Snapshot writes:

```json
{
  "runtime_source": {"type": "legacy_connect", "connect_md_hash": "sha256:..."},
  "harness_patch": null,
  "harness_package": null
}
```

Inference:

- `runtime_source.type` = `legacy_connect` → §3.3 path.
- `_detect_materials_evidence(materials_dir)` finds `cloud-evidence.md`.

**Result: `medium`, reason
`legacy_connect with materials evidence: cloud-evidence.md`.**

Critically: this is **the ceiling**. Supplied evidence cannot reach
`strong` regardless of how thorough the attestation is. See §6.

---

## 10. What AHL still does not prove

Evidence levels describe what AHL *can* assert from the snapshot +
materials chain. Equally important: what AHL **cannot** assert, even at
`strong`:

- **The grader judged correctly.** Evidence is about reproducibility of
  the run, not correctness of the score. A `strong` variant with a
  miscalibrated `rubric.md` produces a misleading score with high
  confidence in the run itself. Calibration is separate work (deferred
  to v0.9+ per roadmap).
- **The cases triggered the right behavior.** A `strong` run can still
  be uninformative if every case landed in the same trivial codepath.
  Evidence doesn't critique experiment design.
- **The agent's training data, model weights, or API-side behavior is
  reproducible.** Calling the same LLM API at two different timestamps
  may produce different outputs even at temperature 0; AHL records
  what was *configured*, not what the model *did internally*.
- **Cloud-side state matches what you supplied.** See §6. Supplied
  evidence is honor-system metadata; AHL has no programmatic channel
  to verify it.
- **Future re-runs will produce identical scores.** Even with `strong`
  evidence on both V1 and V2, replaying the experiment six months
  later requires (a) the runtime source still being reachable at the
  recorded path / commit, (b) the LLM API still behaving consistently,
  (c) the case set still being relevant. AHL preserves the *recipe*;
  it can't guarantee the *kitchen* hasn't changed.
- **Noise vs. signal.** Each variant × case combination is a single
  trial in v0.7 / v0.8. A `+0.4` delta could be a real harness effect
  or sampling noise. Multi-trial statistics is a separate, planned
  workstream.

The bottom line: evidence makes attribution honest, not omniscient. Use
it to triage which results to act on and which to investigate further.

---

## Cross-references

- [`product-walkthrough.md`](product-walkthrough.md) — Step 8 (inspect
  evidence) sits at the 9-step product flow level.
- [`evidence-aware-result.md`](evidence-aware-result.md) — v0.4 spec
  contract (implementation-facing).
- [`harness-package-mvp.md`](harness-package-mvp.md) §13 — v0.5
  evidence overlay rules.
- [`runtime-probe-mvp.md`](runtime-probe-mvp.md) — v0.6 probe contract
  and `--write-evidence` rules.
- [`file-formats.md`](file-formats.md) — full schema reference for
  snapshot JSON, score JSON, materials evidence files.
- [`../examples/evidence-examples/`](../examples/evidence-examples/) —
  reference templates for `runtime-evidence.md`,
  `harness-evidence.md`, `cloud-evidence.md`.
- [`../examples/sample-workspace/`](../examples/sample-workspace/) —
  canonical runnable example producing a real compare-*.md with an
  Evidence section showing two `strong` variants.
