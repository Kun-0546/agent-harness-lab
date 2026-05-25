# Agent Harness Lab

English | [中文](README_CN.md)

> A workbench for humans and coding agents to design, test, and improve the **runtime harnesses** that shape agent behavior.

Change a harness — a prompt, a tool config, a memory rule, a workflow — then measure whether the change made the agent better, worse, or no different. `ahl` runs experiments: you describe a goal, a set of harness variants, a set of test cases, and a rubric; the tool drives each variant through the cases, scores the conversations, and lays the variants side by side so you can see what the change did.

## Why this exists

I am an AI Product Manager. My day job is designing memory, skill, and harness features for AI agents — features where you can't write a PRD on Monday and ship it Friday, because the design surface is in flight and the right answer is unknown when you start.

For months I ran the same loop on my own work: define a goal, build a change, run experiments, look at the data, refine the goal, repeat. The pattern was consistent enough to treat as an architecture, not a workflow. `ahl` is that loop, extracted into a tool — but with a sharper claim than "evaluate agents": this tool's first-class object is the **harness** that wraps the agent, not the agent itself. See [`docs/product-definition.md`](docs/product-definition.md) for the full framing.

## What it does

An experiment compares a few **harness variants** of an agent — `V1`, `V2`, `V3`, one held fixed as the baseline — against the same set of cases.

- **run** — drive every variant through the cases; each case becomes a multi-turn conversation.
- **score** — grade every conversation against a rubric (dimensions + weights).
- **compare** — lay the variants side by side: total scores, per-dimension deltas vs. the baseline, regressed dimensions.

Each experiment is a self-contained folder — its program, harness variants, cases, rubric, and results — that you can re-run and re-score.

## Three product modes

`ahl` exposes three modes (setup mode flow detailed in [`docs/product-walkthrough.md`](docs/product-walkthrough.md)):

- **Manual** — you design harness variants and the experiment; `ahl` validates, runs, scores, compares. **v1, done.**
- **Co-pilot** — the **default AI-guided experiment-setup mode**: an external coding agent (Claude Code / Cursor / Codex) collaborates with you through conversation to maintain `brief.md` and `materials/`, and to generate or complete the experiment files (program / rubric / cases / harnesses). **v2-minimal, implemented.**
- **Auto** — agents iterate harnesses inside rules, budgets, and approval gates; escalate to you on anomalies. **Future mode.** Runtime Materialization M1 has shipped in v0.3.0 (`local_path` + `git_repo`; see [`docs/runtime-materialization.md`](docs/runtime-materialization.md) and [`docs/runtime-materialization-m1-spec.md`](docs/runtime-materialization-m1-spec.md)); Auto mode itself still depends on calibration + approval gates (M2+).

## Install

Requires Python 3.10+.

```
git clone <repo-url>
cd agent-harness-lab
pip install -e .
```

This installs the `ahl` command. If your shell reports `ahl: command not found`, the script directory isn't on your PATH — add it, or run the tool as `python -m agent_harness_lab` (on Windows, `py -m agent_harness_lab`).

## Quickstart

```
# 1. Init workspace
ahl init                     # creates goal.md + experiments/

# 2. Define goal
# edit goal.md — what behavior do you want to improve?

# 3. See the product flow
ahl walkthrough              # 9 steps: goal → mode → runtime → ... → decide
                             # full doc: docs/product-walkthrough.md

# 4. Declare runtime — pick one:
#    already-running agent     → create connect.md (legacy)
#    local source / Git repo   → create runtime-sources.md

# 5. Create experiment (setup mode: copilot default / manual / auto)
ahl new my-experiment                      # default: --mode copilot
                                           #   → brief.md + materials/README.md + cases/ + harnesses/
#  or: ahl new my-experiment --mode manual # full skeleton (program/rubric/simulator), you fill it
#  or: ahl new my-experiment --mode auto   # not implemented yet (M2+)

# 6. Run, score, compare
ahl run 001 ; ahl score 001 ; ahl compare 001
```

`examples/` ships a minimal agent for each of the four connection types (in-process library, external CLI, HTTP stateless, HTTP stateful), each with its protocol documented — start by pointing the tool at one of those.

By default `run` and `score` use built-in stubs (a canned simulator and a hash-based grader) — enough to smoke-test the pipeline, not to produce real results. For real runs, pass `--llm` and set the model environment variables (`AHL_SIM_*` for the simulator, `AHL_JUDGE_*` for the grader).

## Commands

`init` · `walkthrough` · `connect` · `new` · `show` · `cases` · `rubric` · `simulator` · `harnesses` · `run` · `score` · `compare` · `review`. Run `ahl --help` or `ahl <command> --help` for details.

## Status

**v1 — a trusted Manual loop.** The full `init → run → score → compare` pipeline runs end to end and rejects malformed input up front. The `--llm` path (real simulator + LLM judge) has been run end to end in a local experiment, not only on the built-in stubs; no polished case study is published yet. Known gaps:

- `depends_on` (seeding a case's opening context from a prior case) is parsed and shown, but `run` does not use it yet.
- `run` / `score` default to stubs; real scoring needs `--llm` and API keys.
- Only the "simulated" conversation mode is implemented; replay and scripted modes, the Auto mode (with calibration and approval gates), and noise/trial handling are not built yet.
- No polished case study published yet — treat this as an architecture being proposed.

In Co-pilot mode (`ahl new <name> --mode copilot`, default), AHL creates `brief.md` (a working sheet for the coding agent) plus `materials/README.md` (a shared workspace for reference material). An **external coding agent** (Claude Code / Cursor / Codex) then collaborates with you — drafting `program.md` / `harnesses/` / `cases/` / `rubric.md` / `simulator.md` from `goal.md` + `brief.md` + `materials/`, and helping you maintain `brief.md` and organize `materials/` through conversation; `ahl` itself does not call a model. `ahl review` then produces an auditable `review.md` (permissive — marks any missing piece as "未起草"). The old `ahl draft` command is merged into `ahl new --mode copilot`. See [`docs/product-walkthrough.md`](docs/product-walkthrough.md) for the current setup-mode flow.

Making each run reproducible against a specific harness × runtime — Runtime Materialization — has shipped its M1 in v0.3.0 (`local_path` + `git_repo` + snapshot persistence + `--cleanup-sandboxes`). See [`docs/runtime-materialization.md`](docs/runtime-materialization.md) and [`docs/runtime-materialization-m1-spec.md`](docs/runtime-materialization-m1-spec.md). Replay/scripted modes, Auto, approval gates, and calibration are still future work.

## History

This project began as **HDL / Harness Design Loop**. It is now renamed to **Agent Harness Lab** to make explicit what the first-class object actually is. HDL remains as a historical codename in commit history, old branches, and the v1 design docs (`docs/design-v0.3.md` / `docs/design-v0.4.1.md`).

## Related Work

**Heuristic Learning** — Jiayi Weng, *Learning Beyond Gradients* (2026): a coding agent improves a software system by editing code — rules, state, tests, memory — rather than training neural-network parameters. `ahl` is a tool for running that kind of loop.

**Karpathy's AutoResearch** (2026) demonstrated an automated research loop on ML training against a fixed objective. `ahl` addresses an adjacent problem — AI *product* research, where the goal itself is under revision. A reference, not a template.

## Author

Built by Kun, an AI Product Manager.
