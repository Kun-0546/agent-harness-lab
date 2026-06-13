# Agent Harness Lab

English | [中文](README.zh-CN.md)

A workbench for designing, running, and evaluating **agent harness experiments**. A
*harness* is everything that wraps an agent runtime and shapes its behavior — the
prompt, the tool configuration, the memory rules, the workflow. Change a harness, run
it over a fixed set of cases against a real Agent Runtime, and collect reproducible
evidence of whether the change helped.

> **Status: v1, stable (`1.1.0`).** The sections below state what is
> implemented today and what is not. This document prioritizes accuracy over polish —
> the product narrative will be developed further, but the README will never claim
> more than the code does.
>
> **Changelog:** [GitHub Releases](https://github.com/Kun-0546/agent-harness-lab/releases)
> is the canonical changelog. There is no `CHANGELOG.md` file — release notes live on
> each release.

## What AHL is

An experiment is one `experiment.yaml`: a goal, one or more harnesses, a set of cases,
an evaluation, and (optionally) an optimization objective. AHL runs each harness
through the cases against a real runtime, writes an auditable evidence tree (traces,
raw output, artifacts, scores, issues), runs inspection and evaluation, and builds a
report.

The first-class object is the **harness**, not the agent. AHL is not a universal
agent framework — it drives runtimes you already have through a small, explicit
connector contract, and keeps the focus on the structure that wraps the agent.

## Why it is not just an eval runner

A plain eval runner scores model outputs. AHL is built around three things an eval
runner usually isn't:

- **The harness is the unit of change.** The structure is goal → harnesses → cases →
  evaluation → (optional) optimization. Experiments compare harnesses (and, in the
  optimization loop, an Incumbent against a Candidate) — not just models.
- **Evidence discipline.** Every run persists a structured evidence tree and an
  `issues.jsonl`; inspection and evaluation are separate, explicit steps. A pending or
  unrun step is reported as pending — never fabricated into a conclusion.
- **A bounded optimization loop.** AHL can run a candidate → evaluate → promote loop
  over the harness within a protected/editable surface — see the honest scope below.

This grew out of one workflow. The author is an AI product manager designing memory,
skill, and harness features for agents — features where you cannot write a PRD on
Monday and ship it Friday, because the design surface is in flight and the right
answer is unknown when you start. The loop (define a goal, change the harness, run
experiments, read the evidence, refine the goal, repeat) was consistent enough to
treat as an architecture. AHL is that loop, extracted into a tool.

## Modes

### Copilot Mode (`run.mode: copilot`)

AHL prepares the experiment and renders an `agent-task.md`; an external coding agent
(Claude Code / Codex / Cursor) executes the runtime-specific steps and writes
evidence, which AHL then validates, inspects, evaluates, and reports. AHL provides the
structure, the checks, and the evidence discipline — not the execution.

### Auto Mode (`run.mode: auto`)

AHL drives the runtime itself through a connector and collects evidence. Auto Mode has
two layers:

- **Auto Run** — dispatch each case to the runtime through a connector, collect
  evidence, inspect it, and evaluate it. Implemented.
- **Auto Optimize** — a **bounded, deterministic** candidate → evaluate → promote loop
  over the harness: copy the incumbent to a candidate, optionally mutate it via a user
  `mutation_script`, enforce the editable/protected-surface boundary (a touched
  protected file is rolled back), run + inspect + evaluate the candidate, then promote
  or reject it by the promotion policy, stopping on `stop_conditions`. Candidate
  generation is copy-only or your own deterministic script. **Not implemented:**
  LLM-based mutation, fully autonomous optimization, remote/distributed optimization,
  and any general self-improvement engine.

## What is implemented (and what is not)

| Area | Implemented in v1 | Not implemented |
|------|-------------------|-----------------|
| Run modes | Copilot, Auto | — |
| Auto layers | Auto Run; **bounded/deterministic** Auto Optimize (copy-only + `mutation_script`; **single_turn only** — multi-turn simulator inside the optimize loop is rejected at review) | LLM-based mutation; fully autonomous, remote/distributed optimization; general self-improvement engine |
| Connectors | `local_cli`, `script` | `remote_devbox`, `api`, `bridge`, `manual` — declarable but **not executed** (rejected by review) |
| Evaluation | `benchmark` (deterministic script); `llm_judge` (**real LLM judging** when `AHL_JUDGE_BASE_URL` / `AHL_JUDGE_MODEL` / `AHL_JUDGE_API_KEY` are set; any OpenAI-compatible endpoint — Anthropic etc. via a compatible gateway; **pending** without a key — never a fabricated verdict); `human_annotation` (ingests an annotation file, else **pending**); `llm_rubric` (v1.1 — dimension-weighted LLM scoring: a rubric markdown table declares named dimensions + weights; per-dimension scores and weighted total stored in score records; same `AHL_JUDGE_*` config as `llm_judge`; no key → **pending**) | streaming / multi-model judging; per-provider protocols (no `AHL_JUDGE_PROVIDER`) |
| Multi-turn simulators (v1.1) | Three types: `role_play` (an LLM plays the user from a four-section policy card; needs `AHL_SIM_*`; no key → `simulator_unconfigured` error, never a fabricated follow-up); `scripted` (deterministic playbook — zero LLM calls, zero keys); `script` (external program decides each user turn — fully custom logic). `single_turn` is still the default and is frozen. Auto Optimize supports `single_turn` only | — |
| Multi-trial | `execution.trials: N` repeats the run N times (append-by-default evidence); `hlab run --trials N` per-run override; `hlab run --fresh` starts clean; `hlab eval --trial N` evaluates a historical trial; compare emits mean/stddev/win_rate across trials | — |
| State policies | `isolated`, `reset` (executed) | `cumulative`, `snapshot_branch`, `replay` — declarable → WARN, not executed |
| Reporting | `reports/report.md` + a real `reports/report.html` (stdlib renderer, no dependency); `compare` → `reports/compare.json`; `conclude` → `conclusion.md` | hosted dashboard; HTML charts |
| Output | evidence tree (traces / raw / artifacts / scores / inspections / issues) | — |
| Runtime source pinning (v1.1) | Experiments can pin runtimes to a source (`local_path` / `git_repo` / `harness_package`) with an optional patch, producing snapshot evidence (`evidence/snapshots/<runtime_id>.json` with source_dir_hash / commit_sha / patch_hash) that drives the `strong` evidence tier in compare reports; `hlab review` runs a read-only source health check (existence, reachability, fingerprint) and emits reconcilable fingerprints for comparison against the post-run snapshot | — |

If a step is pending or unrun, AHL says so in `review`, `status`, and the report.

## Not in scope (by design)

- **No hosted dashboard / web UI** — AHL writes files you read locally.
- **No autonomous self-improvement** — Auto Optimize is a bounded, deterministic loop.
- **No remote connector completion** — `remote_devbox` / `api` / `bridge` are declarable
  but not executed.
- **Not an enterprise Agent-Eval platform** — it is a single-user, local workbench.

## Quickstart

```bash
pip install -e .          # provides `hlab` (and `python -m agent_harness_lab`)
```

Generate a complete, runnable A/B experiment and drive the whole path — local,
deterministic, **no network, no API key**:

```bash
hlab init
hlab new memory-policy-ab --template memory-policy-ab-lite
hlab review   experiments/memory-policy-ab
hlab run      experiments/memory-policy-ab     # drive both harnesses, collect evidence, evaluate
hlab report   experiments/memory-policy-ab     # -> reports/report.md + reports/report.html
hlab compare  experiments/memory-policy-ab     # -> reports/compare.json (winner: B)
hlab conclude experiments/memory-policy-ab --winner B \
  --reason "Filtered retrieval cut leakage while keeping task success."
```

The deterministic benchmark decides the winner with **no API key**. `llm_judge` adds an
LLM's view only when `AHL_JUDGE_BASE_URL` / `AHL_JUDGE_MODEL` / `AHL_JUDGE_API_KEY` are set
— without a key it stays **pending**, never a fabricated score. `report` writes both
`report.md` and a rendered `report.html`.

Shipped examples (browse or run): [`examples/`](examples/) — including the flagship
[`memory-policy-ab-lite`](examples/memory-policy-ab-lite/). Full walk-through:
[`docs/quickstart.md`](docs/quickstart.md).

## Command surface

```text
hlab init                   initialize a workspace (goal.md, evaluation-methods/, experiments/)
hlab new <name>             scaffold an experiment; --template <name> for a complete runnable one
hlab review <experiment>    validate experiment.yaml before running (PASS / WARN / ERROR)
hlab run <experiment>       Copilot: render agent-task.md · Auto: run + collect + inspect + evaluate
hlab eval <experiment>      re-run all evaluation tracks against existing evidence (scores recomputed;
                            evidence read-only — traces/raw/issues never modified; enables
                            human_annotation backflow: run → pending → write annotation → eval → scored)
hlab status <experiment>    show status + evidence / evaluation state
hlab report <experiment>    build reports/report.md (+ report.html) from the evidence
hlab compare <experiment>   summarize the A/B result into reports/compare.json
hlab conclude <experiment>  record your decision as conclusion.md (--winner, --reason)
```

`hlab <cmd>` and `python -m agent_harness_lab <cmd>` are equivalent.

Every command honors one exit-code contract (so a loop or a script can gate on it):

| Exit code | Meaning |
|-----------|---------|
| `0` | success — pending evaluations (no judge key / no annotation yet), *failed* evaluations ("the answer is a failure" is a legitimate result), and warn/info-level issues do **not** fail a run |
| `1` | configuration or preflight error |
| `2` | not implemented in v1 |
| `3` | runtime failure — any error-severity issue, or any evaluation track in `error`; a machine-readable `HLAB_*` error code goes to stderr |

> **Breaking change in 1.0.0 (introduced in rc2):** runtime failures used to exit `0`; they now exit
> `3`. See the [release notes](https://github.com/Kun-0546/agent-harness-lab/releases)
> for migration guidance. The full contract (per-command artifacts, `HLAB_*` error
> codes, re-entrancy) is specified in [`docs/v1-spec/cli.md`](docs/v1-spec/cli.md).

`ahl` (the retired v0.x stack) no longer runs: its workspace format is **not**
compatible with `hlab`, and old `ahl` commands do not map 1:1 onto the v1 surface.
Start fresh with `hlab init`; the migration guide
([`docs/migrating-from-ahl.md`](docs/migrating-from-ahl.md)) maps each old `ahl`
file onto its v1 equivalent.

## Specification

The authoritative v1 contracts live in [`docs/v1-spec/`](docs/v1-spec/):

- [`product-definition.md`](docs/v1-spec/product-definition.md) — what AHL is and its core objects
- [`experiment-structure.md`](docs/v1-spec/experiment-structure.md) — the on-disk layout
- [`experiment-yaml-schema.md`](docs/v1-spec/experiment-yaml-schema.md) — every `experiment.yaml` field
- [`execution-model.md`](docs/v1-spec/execution-model.md) — modes, connectors, state policies, Auto Optimize
- [`cli.md`](docs/v1-spec/cli.md) — the command surface

## Requirements

Python **3.10–3.12** and a single dependency, **PyYAML**. Runs locally; the core
workflow and the shipped examples need no network.

> **Python 3.13 is not yet supported.** A reviewer reported an intermittent test-suite
> hang on 3.13.5 that we could not reproduce or fix with confidence, so 3.13 is pinned
> out (`requires-python = ">=3.10,<3.13"`) until it is resolved. Use a 3.10–3.12 interpreter.

```bash
git clone https://github.com/Kun-0546/agent-harness-lab.git
cd agent-harness-lab
pip install -e .
```

If your shell reports `hlab: command not found`, the script directory isn't on your
PATH — add it, or run `python -m agent_harness_lab` (`py -m agent_harness_lab` on
Windows).

## Author

Built by Kun, an AI Product Manager.

## License

MIT.
