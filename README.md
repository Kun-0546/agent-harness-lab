# Agent Harness Lab

English | [中文](README.zh-CN.md)

A workbench for designing, running, and evaluating **agent harness experiments**. A
*harness* is everything that wraps an agent runtime and shapes its behavior — the
prompt, the tool configuration, the memory rules, the workflow. Change a harness, run
it over a fixed set of cases against a real Agent Runtime, and collect reproducible
evidence of whether the change helped.

> **Status: v1, pre-release (`1.0.0.dev0`).** The sections below state what is
> implemented today and what is not. This draft prioritizes accuracy over polish —
> the product narrative will be developed further, but the README will never claim
> more than the code does.

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
| Auto layers | Auto Run; **bounded/deterministic** Auto Optimize (copy-only + `mutation_script`) | LLM-based mutation; fully autonomous, remote/distributed optimization; general self-improvement engine |
| Connectors | `local_cli`, `script` | `remote_devbox`, `api`, `bridge`, `manual` — declarable but **not executed** (rejected by review) |
| Evaluation | `benchmark` (runs a deterministic script) | — |
| Evaluation (honest stubs) | `human_annotation` (ingests an annotation file if present, else **pending**); `llm_judge` (**offline stub → always pending**; no model is called) | real LLM-based judging |
| State policies | `isolated`, `reset` (executed) | `cumulative`, `snapshot_branch`, `replay` — declarable → WARN, not executed |
| Output | evidence tree (traces / raw / artifacts / scores / inspections / issues), `reports/report.md` | — |

If a step is pending or unrun, AHL says so in `review`, `status`, and the report.

## Quickstart

```bash
pip install -e .          # provides `hlab` (and `python -m agent_harness_lab`)
```

Run a shipped example end to end — local, deterministic, no network, no API keys:

```bash
cd examples/auto-run-local-cli-lite
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

Full walk-through, including the Auto Optimize example:
[`docs/quickstart.md`](docs/quickstart.md). Both examples: [`examples/`](examples/).

## Command surface

```text
hlab init <dir>            initialize a workspace (goal.md, evaluation-methods/, experiments/)
hlab new <name>            scaffold an experiment (--mode copilot|auto, --execution ab|sequential|...)
hlab review <experiment>   validate experiment.yaml before running (PASS / WARN / ERROR)
hlab run <experiment>      Copilot: render agent-task.md · Auto: run + collect + inspect + evaluate
hlab status <experiment>   show status + evidence / evaluation state
hlab report <experiment>   build reports/report.md from the evidence
```

`hlab <cmd>` and `python -m agent_harness_lab <cmd>` are equivalent. `ahl` remains as a
legacy redirect that points you at `hlab`.

## Specification

The authoritative v1 contracts live in [`docs/v1-spec/`](docs/v1-spec/):

- [`product-definition.md`](docs/v1-spec/product-definition.md) — what AHL is and its core objects
- [`experiment-structure.md`](docs/v1-spec/experiment-structure.md) — the on-disk layout
- [`experiment-yaml-schema.md`](docs/v1-spec/experiment-yaml-schema.md) — every `experiment.yaml` field
- [`execution-model.md`](docs/v1-spec/execution-model.md) — modes, connectors, state policies, Auto Optimize
- [`cli.md`](docs/v1-spec/cli.md) — the command surface

## Requirements

Python 3.10+ and a single dependency, **PyYAML**. Runs locally; the core workflow and
the shipped examples need no network.

```bash
git clone https://github.com/Kun-0546/agent-harness-lab.git
cd agent-harness-lab
pip install -e .
```

If your shell reports `hlab: command not found`, the script directory isn't on your
PATH — add it, or run `python -m agent_harness_lab` (`py -m agent_harness_lab` on
Windows).

## Related work

- **Heuristic Learning** — Jiayi Weng, *Learning Beyond Gradients* (2026): a coding
  agent improves a software system by editing code — rules, state, tests, memory —
  rather than training network parameters. AHL is a tool for running that kind of loop.
- **Karpathy's AutoResearch** (2026) demonstrated an automated research loop on ML
  training against a fixed objective. AHL addresses an adjacent problem — AI *product*
  research, where the goal itself is under revision. A reference, not a template.

## Author

Built by Kun, an AI Product Manager.

## License

MIT.
