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

Eight public commands, grouped by experiment-loop stage:

```text
prepare           hlab init
                  hlab new
gate & execute    hlab review
                  hlab run
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
| `run` (Auto Run) | `evidence/traces/<runtime_id>.jsonl`, `evidence/raw/<runtime_id>/<case_id>.{out,err}`, `evidence/artifacts/`, `evidence/snapshots/`, `evidence/scores/<track_id>/<evaluator_id>.jsonl`, `evidence/scores/tracks/<track_id>.json`, `evidence/issues.jsonl`, `evidence/inspections/inspection.json` |
| `run` (Auto Optimize) | `optimization/history.jsonl`, `optimization/iterations/iter-NNN.json`, `optimization/iterations/iter-NNN/evidence/` (same layout as Auto Run), `harnesses/candidates/iter-NNN/` (candidate copies) |
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

Both lines may appear on the same run; the exit code is `3` in either case.
No other `HLAB_*` codes exist in v1; new codes enter through this table only.

### 3.4 Re-entrancy

| Command | Promise |
|---------|---------|
| `init` | idempotent — creates only the missing pieces, never overwrites |
| `new` | refuses an existing `experiments/<id>` (exit `1`) — never overwrites |
| `review`, `status` | read-only, idempotent |
| `run` (Copilot) | re-render overwrites `agent-task.md` — idempotent |
| `run` (Auto Run) | **a re-run truncates** each runtime's `evidence/traces/<runtime_id>.jsonl` on first write (overwrite-not-append) and rebuilds `issues.jsonl`. Known v1 limitation, honestly stated: v1.1 moves to append / run-scoped evidence semantics |
| `run` (Auto Optimize) | a re-run rewrites `optimization/history.jsonl` and re-numbers iterations from `iter-001` |
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

Checks:

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

Output levels:

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
dispatch cases
collect evidence
run evaluation if configured
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

## 12. Surface Growth Rules

The top-level verbs are the stages of the experiment loop, and that surface is
**frozen at the eight commands above**. v1.1 may add `eval` (+1) through an
explicit spec change — nothing enters the verb surface casually.

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

## 13. Commands Not Public in v1

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

## 14. Backward Compatibility

The retired `ahl` command is an honest stop, not a shim. It does not run old
semantics (meaning changed in v1), and it does not pretend the old arguments map
onto `hlab` — the two stacks' workspace formats are **not** compatible, and old
`ahl` commands do not map 1:1 onto the v1 surface.

`ahl <anything>` prints that explanation, points at the README's "Command
surface" section, and exits `1`. A migration guide (`migrating-from-ahl.md`) is
planned for v1.1.

Do not silently run old semantics when meaning changed.
