# Harness Design Loop

English | [中文](README_CN.md)

> A command-line tool for AI product research: change your agent, then measure whether the change made it better, worse, or no different.

`hdl` runs experiments. You describe your agent, a goal, a set of test cases, and a rubric; the tool runs each version of the agent through the tests, scores the conversations, and lays the versions side by side so you can see what the change did.

## Why this exists

I am an AI Product Manager. My day job is designing memory, skill, and harness features for AI agents — features where you can't write a PRD on Monday and ship it Friday, because the design surface is in flight and the right answer is unknown when you start.

For months I ran the same loop on my own work: define a goal, build a change, run experiments, look at the data, refine the goal, repeat. The pattern was consistent enough to treat as an architecture, not a workflow. `hdl` is that loop, extracted into a tool.

## What it does

An experiment compares a few **versions** of an agent — `V1`, `V2`, `V3`, one held fixed as the baseline — against the same test set.

- **run** — drive every version through the test set; each test case becomes a multi-turn conversation.
- **score** — grade every conversation against a rubric (dimensions + weights).
- **compare** — lay the versions side by side: total scores, per-dimension deltas vs. the baseline, regressed dimensions.

Each experiment is a self-contained folder — its program, versions, test set, rubric, and results — that you can re-run and re-score.

## Install

Requires Python 3.10+.

```
git clone <repo-url>
cd harness-design-loop
pip install -e .
```

This installs the `hdl` command. If your shell reports `hdl: command not found`, the script directory isn't on your PATH — add it, or run the tool as `python -m harness_design_loop` (on Windows, `py -m harness_design_loop`).

## Quickstart

```
hdl init                     # create connect.md, goal.md, experiments/
# edit connect.md — tell the tool how to reach your agent
hdl new my-experiment        # scaffold experiments/001-my-experiment/
# fill in program.md, rubric.md, versions/, and 测试集/ (test cases)
hdl run 001                  # run every version through the test set
hdl score 001                # score the conversations
hdl compare 001              # compare the versions
```

`examples/` ships a minimal agent for each of the four connection types (in-process library, external CLI, HTTP stateless, HTTP stateful), each with its protocol documented — start by pointing the tool at one of those.

By default `run` and `score` use built-in stubs (a canned simulator and a hash-based grader) — enough to smoke-test the pipeline, not to produce real results. For real runs, pass `--llm` and set the model environment variables (`HDL_SIM_*` for the simulator, `HDL_JUDGE_*` for the grader).

## Commands

`init` · `connect` · `new` · `show` · `cases` · `rubric` · `simulator` · `versions` · `run` · `score` · `compare` · `draft`. Run `hdl --help` or `hdl <command> --help` for details.

## Status

**v1 — a trusted manual loop.** The full `init → run → score → compare` pipeline runs end to end and rejects malformed input up front. The `--llm` path (real simulator + LLM judge) has been run end to end in a local experiment, not only on the built-in stubs; no polished case study is published yet. Known gaps:

- `depends_on` (seeding a case's opening context from a prior case) is parsed and shown, but `run` does not use it yet.
- `run` / `score` default to stubs; real scoring needs `--llm` and API keys.
- Only the "simulated" conversation mode is implemented; replay and scripted modes, the self-iterating run mode, environment snapshots, and noise/trial handling are not built yet.
- No polished case study published yet — treat this as an architecture being proposed.

On the `v2-agent-drafted-lab` branch, `hdl draft` adds the minimal agent-drafted workflow: brief.md → generated program / versions / cases / rubric / simulator → review.md. See `docs/v2-minimal-spec.md` for the implementation slice.

Where v2 and beyond are headed — agents drafting and operating experiments while humans keep the anchors — is laid out in `docs/design-v0.4.1.md`.

## Related Work

**Heuristic Learning** — Jiayi Weng, *Learning Beyond Gradients* (2026): a coding agent improves a software system by editing code — rules, state, tests, memory — rather than training neural-network parameters. `hdl` is a tool for running that kind of loop.

**Karpathy's AutoResearch** (2026) demonstrated an automated research loop on ML training against a fixed objective. `hdl` addresses an adjacent problem — AI *product* research, where the goal itself is under revision. A reference, not a template.

## Author

Built by Kun, an AI Product Manager.
