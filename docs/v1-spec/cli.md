# CLI Design

## 1. Command Name

Use:

```text
hlab
```

Project name remains:

```text
Agent Harness Lab
```

## 2. Object Model and Command Surface

`hlab` has exactly two objects: the **workspace** and the **experiment**.
`hlab init` creates the workspace; every other command acts on one experiment
directory (`experiments/<name>` — addressable as a path or a bare name).

Nine public commands, grouped by experiment-loop stage:

```text
prepare           hlab init
                  hlab new
gate & execute    hlab review
                  hlab run
                  hlab eval
                  hlab status
conclude          hlab report
                  hlab compare
                  hlab conclude
```

`hlab <cmd>` and `python -m agent_harness_lab <cmd>` are equivalent.

## 3. The Loop Contract

The first consumer of this CLI is an agent driving the experiment loop. Every
command therefore signs four contracts: an **exit code** (§3.1), **machine-readable
artifacts** at documented paths (§3.2), **named error codes** on stderr (§3.3),
and a **re-entrancy promise** (§3.4).

### 3.1 Exit codes

One contract for all commands:

| Exit code | Meaning |
|-----------|---------|
| `0` | success |
| `1` | configuration or preflight error (experiment not found, broken `experiment.yaml`, review `ERROR` verdict, bad flag value, internal error) |
| `2` | not implemented in v1 (`run` with a `run.mode` that is neither `copilot` nor `auto`) |
| `3` | runtime failure (Auto Mode `run` only — see below) |

`run` exits `3` when, after evidence collection + evaluation + inspection, either:

- any issue with `severity: error` exists in the judged `issues.jsonl`
  (e.g. `connector_failure`, `case_failure`, `empty_output`, a missing
  **required** artifact), or
- any evaluation track aggregates to `status: error`.

Exempt by contract — these stay exit `0`:

- **pending** evaluation tracks (no `AHL_JUDGE_API_KEY` for `llm_judge`, no
  annotation file yet for `human_annotation`);
- **failed** evaluation tracks — "the experiment's answer is a failure" is a
  legitimate experiment result, not a tool failure;
- warn/info-level issues.

In an Auto Optimize run, exit `3` is judged on the **final incumbent's** evidence
(the last promoted iteration's evidence; with zero promotions, the last iteration
that actually ran) — never the union of all iterations.

> **Changed in `1.0.0rc2` (breaking):** runtime failures used to exit `0`.
> Scripts that gated on `hlab run` exiting non-zero only for config errors must
> now treat `3` as "ran, but the evidence shows a runtime failure".

### 3.2 Machine-readable artifacts

Every verb that produces output leaves it at a documented path, relative to the
experiment directory (workspace-relative for `init`):

| Command | Artifacts |
|---------|-----------|
| `init` | `goal.md`, `evaluation-methods/*.md`, `experiments/`, `.hlab/` |
| `new` | `experiments/<id>/` tree: `experiment.yaml` (machine source of truth), `experiment.md`, `harnesses/`, `agent-runtimes/`, `cases/cases.jsonl`, `evaluation/`, `evidence/`, `reports/`, `conclusion.md` |
| `review` | none — verdict on stdout, gate on the exit code |
| `run` (Copilot) | `agent-task.md` |
| `run` (Auto Run) | `evidence/traces/<runtime_id>.jsonl`, `evidence/raw/<runtime_id>/<case_id>.{out,err}`, `evidence/artifacts/`, `evidence/snapshots/<runtime_id>.json` (written for each runtime that declares `source:`), `evidence/scores/<track_id>/<evaluator_id>.jsonl`, `evidence/scores/tracks/<track_id>.json`, `evidence/issues.jsonl`, `evidence/inspections/inspection.json`; `sandbox/<runtime_id>/` (materialized runtime tree — preserved across trials, wiped by `--fresh`) |
| `run` (Auto Optimize) | `optimization/history.jsonl`, `optimization/iterations/iter-NNN.json`, `optimization/iterations/iter-NNN/evidence/` (same layout as Auto Run), `harnesses/candidates/iter-NNN/` (candidate copies) |
| `eval` | `evidence/scores/<track_id>/<evaluator_id>.jsonl`, `evidence/scores/tracks/<track_id>.json` (evidence/traces/, evidence/raw/, evidence/issues.jsonl are **read-only** inputs — never modified) |
| `status` | none — read-only summary on stdout |
| `report` | `reports/report.md`; plus `reports/report.html` when `html` is in `reports.formats` |
| `compare` | `reports/compare.json` |
| `conclude` | `conclusion.md` |

### 3.3 Named error codes (`HLAB_*`)

The exit code routes a loop gate; the named error code lets an agent write a
branch; the prose is for the human. On a runtime failure (`exit 3`), `run`
prints one stderr line per code, prefixed `HLAB_<NAME>: `.

Complete v1 list:

| Code | Trigger | Detail in the message | Where to look |
|------|---------|----------------------|---------------|
| `HLAB_RUNTIME_FAILURE` | ≥ 1 issue with `severity: error` in the judged evidence | issue count + per-type counts (e.g. `connector_failure=2, empty_output=1`) | the referenced `issues.jsonl` |
| `HLAB_EVAL_ERROR` | ≥ 1 evaluation track with `status: error` | track count + sorted track ids | the referenced `scores/tracks/` |
| `HLAB_MISSING_EVIDENCE` | `eval` called when evidence/ dir is absent, has zero trace records, OR `--trial N` is given but no trace records exist for trial N | what is missing (no evidence dir / zero trace records / missing trial) | the experiment directory |

`HLAB_RUNTIME_FAILURE` and `HLAB_EVAL_ERROR` may both appear on the same `run`; the
exit code is `3` in either case. `HLAB_MISSING_EVIDENCE` exits `1` (preflight class).
No other `HLAB_*` codes exist in v1; new codes enter through this table only.

### 3.4 Re-entrancy

| Command | Promise |
|---------|---------|
| `init` | idempotent — creates only the missing pieces, never overwrites |
| `new` | refuses an existing `experiments/<id>` (exit `1`) — never overwrites |
| `review`, `status` | read-only, idempotent |
| `run` (Copilot) | re-render overwrites `agent-task.md` — idempotent |
| `run` (Auto Run) | **append-by-default** (v1.1 PR5): a re-run appends trace records as a new trial number; old evidence is immutable. `--fresh` is the only sanctioned wipe (starts a clean trial-0 run). `issues.jsonl` accumulates per-trial (append), trial >= 1 records carry a `trial` field; exit-code judges THIS invocation's in-memory issues, not the full historical file. |
| `run` (Auto Optimize) | a re-run rewrites `optimization/history.jsonl` and re-numbers iterations from `iter-001` |
| `eval` | **idempotent for deterministic tracks** (benchmark, human_annotation) — same evidence → same scores. `llm_judge` and `llm_rubric` are the documented exceptions: each call with a configured key may produce different scores (model non-determinism). `eval --trial N` with no evidence for trial N exits `1` (HLAB_MISSING_EVIDENCE) and writes nothing. Annotation files are not trial-scoped in v1.1: the human annotates the trial they reviewed; recomputing a different trial N with a stale annotation carries trial N in the score record but the annotation may not match. |
| `report`, `compare`, `conclude` | deterministic overwrite of their artifact — idempotent over identical evidence |

## 4. hlab init

Creates the workspace in the current directory.

Usage:

```bash
hlab init
```

Output:

```text
goal.md
evaluation-methods/
  human_annotation.md
  llm_judge.md
  benchmark.md
experiments/
.hlab/
```

Exit codes: `0` created (or already complete); `1` a workspace member exists as
a file where a directory is required (nothing is scaffolded).

## 5. hlab new

Creates the experiment `experiments/<name>/`.

Usage:

```bash
hlab new <experiment-name>
```

Output:

```text
experiments/<name>/experiment.md
experiments/<name>/experiment.yaml
experiments/<name>/harnesses/
experiments/<name>/agent-runtimes/
experiments/<name>/cases/
experiments/<name>/evaluation/
experiments/<name>/evidence/
experiments/<name>/reports/
experiments/<name>/conclusion.md
```

Optional flags:

```bash
hlab new skill-creator-ab --mode auto --execution ab
hlab new memory-comparison --mode copilot --execution longitudinal
hlab new faq-ab --mode auto --question "Does a concise prompt beat a verbose one?"
hlab new memory-policy-ab --template memory-policy-ab-lite
```

- `--mode copilot|auto` (default `copilot`); with `auto`, the scaffold writes a
  runnable placeholder echo agent under `harnesses/` so the first `run` works
  out of the box (its output carries a visible `PLACEHOLDER` marker).
- `--execution ab|sequential|longitudinal|replay` (default `ab`).
- `--question TEXT` — the one-line experiment question, written into
  `experiment.yaml`; without it a `<placeholder>` is scaffolded and `hlab review`
  warns. Ignored (with a notice) when combined with `--template`.
- `--template NAME` — scaffold a complete, runnable experiment from a built-in
  template.

Exit codes: `0` created; `1` no workspace, unknown template, unusable name, or
the experiment already exists.

## 6. hlab review

Gates an experiment before run: validates `experiment.yaml` and the structure
around it.

Usage:

```bash
hlab review experiments/<name>
```

### Phase 1 — static validation

```text
experiment.yaml exists and parses
harnesses exist
Agent Runtime specs exist
cases exist
evaluation exists
collection settings are valid
Auto Mode connector is supported
Auto Mode working_dir exists (local_cli / script)
question is not a <placeholder>
report formats are supported
```

### Phase 2 — source health checks (PR8)

When any Agent Runtime declares a `source:` section, `hlab review` runs a
**read-only** health check on each such runtime immediately after static
validation:

| Source type | Checks performed | Fingerprint emitted |
|-------------|------------------|---------------------|
| `local_path` | source directory exists, is a directory, is readable; patch file `source:` entries exist | `source_dir_hash` (sha256 of directory tree, same function as materialize) |
| `git_repo` | `git ls-remote` reachability + ref resolved (no clone; timeout 30 s) | resolved remote SHA of the ref |
| `harness_package` | package directory exists, is a directory; `expected_fingerprint` matches if declared | `manifest_hash` + `dir_hash` |

**Read-only guarantee**: the health check never creates a sandbox, never clones
a repository, never installs a package, and never writes to `evidence/` or
`sandbox/`. It is always safe to re-run `hlab review` without side effects.

**Severity**: all source health check failures are `ERROR` — they will prevent
a run from succeeding. An unreachable `git_repo` remote is `ERROR` (not `WARN`)
because review's job is to gate a run that WILL clone; an unreachable remote
at review time predicts a clone failure at run time. The error message notes
that network issues may be transient.

**Phase 1 review error codes** (static validation, selected):

| Code | Level | Condition |
|------|-------|-----------|
| `optimize_multiturn_unsupported` | ERROR | `optimization.enabled: true` + a multi-turn simulator declared |
| `optimize_source_unsupported` | ERROR | `optimization.enabled: true` + any Agent Runtime declares `source:` — optimize mutates harness files but source sandboxes are rebuilt per-invocation, so mutations would be lost |
| `simulator_connector_unsupported` | ERROR | a multi-turn simulator declared + an Agent Runtime with connector type `script` — the script connector spawns a fresh process per case and has no turn IPC; use `local_cli` |

(Full list: see `experiment-yaml-schema.md §14a` and §18.)

**issue codes** (`probe_*` prefix):

| Code | Condition |
|------|-----------|
| `probe_source_missing` | `local_path` / `harness_package` source directory does not exist |
| `probe_source_not_dir` | source path is not a directory |
| `probe_source_unreadable` | source directory exists but cannot be listed (permission) |
| `probe_source_hash_skipped` | `local_path` directory exceeds the 256 MiB size cap; existence confirmed but `source_dir_hash` not computed (WARN) |
| `probe_source_hash_failed` | `source_dir_hash` computation raised an OS error (WARN) |
| `probe_patch_source_missing` | a `patch.files[].source` file referenced in the source spec does not exist |
| `probe_git_missing` | `git` binary not found in PATH |
| `probe_git_url_missing` | `source.url` is absent for a `git_repo` source |
| `probe_git_unreachable` | `git ls-remote` failed (non-zero exit, timeout, or OS error) |
| `probe_git_ref_missing` | `git ls-remote` succeeded but returned empty output (ref not found) |
| `probe_git_ref_unverifiable` | `source.ref` is a commit SHA (7–40 hex chars) — WARN; `ls-remote` cannot verify individual commit reachability |
| `probe_fingerprint_mismatch` | `harness_package` fingerprint does not match `expected_fingerprint` |

**Output**: when source health checks run, a compact per-runtime table is
printed after the verdict items:

```text
source health checks:
  rt-a  type=local_path  target=/path/to/src  [PASS]  fingerprint: sha256:abc123...
  rt-b  type=git_repo    target=https://...@main  [PASS]  fingerprint: <sha>
```

### Reconciling review vs snapshot

The fingerprints emitted in the `source health checks` section are computed
with the **same functions** that `materialize_v1` uses during a run, so you
can compare them against `evidence/snapshots/<runtime_id>.json` after a run:

| Source type | Review emits | Snapshot field |
|-------------|-------------|----------------|
| `local_path` | `source_dir_hash` (pre-patch) | `runtime_source.source_dir_hash` |
| `git_repo` | resolved remote SHA of the ref | `runtime_source.commit_sha` |
| `harness_package` | `manifest_hash` + `dir_hash` | `runtime_source.source_dir_hash` + `harness_package.manifest_hash` |

This closes the roadmap's deferred probe↔snapshot binding item (previously
noted in `temp/v0.10.0-planning.md:417`); see also `execution-model.md §16`.

### Output levels

```text
PASS
WARN
ERROR
```

Exit codes: `0` PASS or WARN (the experiment may run); `1` experiment not found,
or ERROR (must be fixed before `run`).

## 7. hlab run

Runs or prepares the experiment. Behavior depends on `run.mode`. A review
`ERROR` blocks the run (exit `1`, nothing generated); a `WARN` is surfaced but
does not block.

Usage:

```bash
hlab run experiments/<name>
hlab run experiments/<name> --trials N    # override execution.trials for this invocation
hlab run experiments/<name> --fresh       # wipe evidence/ before running (sanctioned destruction)
```

Optional flags (v1.1):

```text
--trials N   override execution.trials for this invocation (positive integer);
             recorded in evidence/run-metadata.json when it differs from the
             config value
--fresh      wipe evidence/ before running — the ONLY sanctioned destruction;
             starts a clean trial-0 run; without --fresh, a re-run appends as
             a new trial (evidence is immutable by default)
```

### Copilot Mode

```text
generate agent-task.md
print next instruction for external agent
do not connect runtime directly
```

### Auto Mode

```text
load connectors
run N trials (execution.trials, or --trials override)
  per trial: dispatch cases, collect evidence (appended to same files)
run evaluation on the latest trial's records
run inspectors (merge issues)
judge the exit-code contract (§3.1)
```

With `optimization.enabled`, Auto Mode runs the bounded candidate → evaluate →
promote loop instead; the exit-code judgement applies to the final incumbent's
evidence (§3.1).

Exit codes: `0` / `1` / `2` / `3` — the full table in §3.1. This is the only
command that can exit `2` or `3`.

## 8. hlab status

Shows experiment status. Read-only.

Usage:

```bash
hlab status experiments/<name>
```

Output:

```text
experiment id
status
question
run mode
execution mode (+ state_policy)
harness count + harnesses
agent runtimes (runtime → harness, connector type)
case count
collection / inspection settings
evidence summary
evaluation per-track status
issues summary
report status
conclusion status
next-step hint
```

Exit codes: `0`; `1` experiment or `experiment.yaml` not found / unparseable.

## 9. hlab report

Generates reports from the collected evidence. Pending evaluations and an unrun
Auto Optimize loop are reported as pending — never fabricated into a conclusion.

Usage:

```bash
hlab report experiments/<name>
```

Default output:

```text
reports/report.md
```

Plus, when `html` is in `reports.formats` (the default scaffold includes it):

```text
reports/report.html
```

Exit codes: `0`; `1` experiment not found, review ERROR, or unparseable yaml.

## 10. hlab compare

Summarizes the A/B result into machine-readable JSON and prints a human summary.

Usage:

```bash
hlab compare experiments/<name>
```

Output:

```text
reports/compare.json
```

Exit codes: `0`; `1` experiment not found, review ERROR, or unparseable yaml.

## 11. hlab conclude

Records the **human's** decision — not a generated verdict.

Usage:

```bash
hlab conclude experiments/<name> --winner B --reason "Filtered retrieval cut leakage."
```

Output:

```text
conclusion.md
```

Exit codes: `0`; `1` experiment or `experiment.yaml` not found / unparseable.

## 12. hlab eval

Re-runs all evaluation tracks against the **existing** evidence. Evidence
(traces / raw / issues) is the immutable first-order artifact; scores are
recomputable derivatives.

Optional flags (v1.1 PR5):

```bash
hlab eval experiments/<name> --trial N   # re-evaluate a specific historical trial N
                                          # default: latest trial
```

Re-runs all evaluation tracks against the **existing** evidence. Evidence
(traces / raw / issues) is the immutable first-order artifact; scores are
recomputable derivatives. `eval` never touches the evidence — it only rewrites
`scores/` and `scores/tracks/`.

Usage:

```bash
hlab eval experiments/<name>
```

**human_annotation backflow**: the flow `run` (missing annotation → pending) →
human writes annotation file alongside traces → `hlab eval` adopts it and scores.
This fixes the deadlock where annotations had no command to adopt them and
re-running `run` would destroy the traces the annotations refer to.

Artifact paths (written):

```text
evidence/scores/<track_id>/<evaluator_id>.jsonl
evidence/scores/tracks/<track_id>.json
```

Artifact paths (read-only inputs — never modified):

```text
evidence/traces/
evidence/raw/
evidence/issues.jsonl
```

Exit codes:

| Code | Condition |
|------|-----------|
| `0` | success — includes pending tracks (no key configured is not a failure) and failed tracks (a failed experiment answer is a legitimate result) |
| `1` | experiment not found / unparseable `experiment.yaml` / missing evidence (no evidence dir or zero trace records; `HLAB_MISSING_EVIDENCE` on stderr) |
| `3` | any evaluation track lands in `status: error` after recompute (`HLAB_EVAL_ERROR` on stderr pointing at `scores/tracks/`) |

Named error codes:

| Code | Trigger |
|------|---------|
| `HLAB_MISSING_EVIDENCE` | evidence/ dir absent or has zero trace records |
| `HLAB_EVAL_ERROR` | ≥ 1 track with `status: error` after recompute |

Re-entrancy: idempotent for deterministic tracks (benchmark, human_annotation).
`llm_judge` and `llm_rubric` are the documented exceptions — each call may return
different scores because the model is non-deterministic.

Multi-turn awareness: `eval` evaluates multi-turn traces identically to `run`'s
inline evaluation — the transcript-aware judge prompt (`[CONVERSATION]` expansion)
is used when a trace record carries a `transcript` field.

## 13. Surface Growth Rules

The top-level verbs are the stages of the experiment loop. The surface grew from
eight to **nine commands** in v1.1 via the spec-explicit channel: the v1.1 spec
(`temp/v1.1-multiturn-eval-spec.md` §PR4 + §总约束) explicitly authorized `eval`
— nothing enters the verb surface casually.

New object families must enter as **noun namespaces**, and the noun must match
the experiment directory name it operates on (`cases`, `evaluation`,
`evidence`, …). The directory layout is the vocabulary; the CLI never invents a
second one.

For users coming from a generic eval-infrastructure background, the hlab
directories map onto the common concepts:

| hlab directory | Common eval-infrastructure concept |
|----------------|-----------------------------------|
| `cases/` | datasets |
| `evaluation/` | graders |
| `evidence/traces/` | trace |
| `evidence/snapshots/` | package |

## 14. Commands Not Public in v1

Do not expose these as top-level human commands:

```text
hlab harvest-artifacts
hlab validate-evidence
hlab build-trace-snapshot
hlab preflight-runtime
hlab run-grader
hlab collect-logs
```

They may exist as internal functions, debug commands, or agent-facing runbook steps.

## 15. Backward Compatibility

The retired `ahl` command is an honest stop, not a shim. It does not run old
semantics (meaning changed in v1), and it does not pretend the old arguments map
onto `hlab` — the two stacks' workspace formats are **not** compatible, and old
`ahl` commands do not map 1:1 onto the v1 surface.

`ahl <anything>` prints that explanation, points at the README's "Command
surface" section and at the migration guide
([`../migrating-from-ahl.md`](../migrating-from-ahl.md)), and exits `1`.

Do not silently run old semantics when meaning changed.
