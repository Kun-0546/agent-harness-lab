# Harness Design Loop

> A two-loop architecture for AI product research. Inner loop runs at agent speed. Outer loop runs on PM judgment.
>
> Built from PM work. Not ported from ML.

`hdl` is a command-line tool. You write a goal; a coding agent runs experiments that test changes against it; you read the results and revise the goal. Two loops, two clocks.

---

## Why this exists

I am an AI Product Manager. My day job is designing memory, skill, and harness features for AI agents — the kind of feature where you can't write a PRD on Monday and ship it on Friday, because the design surface is in flight and the right answer is unknown when you start.

For the past several months I have been running a research loop on my own work: define a goal, build a feature, run experiments, look at the data, refine the goal, repeat. The pattern was consistent enough that I started treating it as an architecture, not a workflow. This repo is that architecture, extracted into a tool I can hand to other AI PMs.

This is the first public release. It is production-tested only by me, on my own work. I built it for myself first.

## What it does

`hdl` runs two nested loops for AI product research.

**Inner loop — the experiment.** You stand up an experiment: a few **versions** of the agent (`V1`, `V2`, `V3` — one held fixed as the baseline), a test set, and a scorer. The coding agent runs every version through the test set, scores the conversations, and compares them into a report. The whole experiment — program, versions, eval, results, verdict — is one self-contained, reproducible record.

**Outer loop — the goal.** You read the comparison report and decide the next move: accept a change, drop it, or redesign it; or step up a layer and revise the test set, the scorer, or `goal.md` itself. The inner loop optimizes a change under a fixed goal. The outer loop optimizes the goal.

**Two modes, for how much the PM stays in the loop.** In **human-judged** mode the coding agent only runs experiments; the PM designs each one and makes every call. In **self-iterating** mode the coding agent runs the whole cycle on its own — design a change, run, judge it by the rules written into the program, design the next — for many rounds, with the PM tending only `goal.md` and the program. A *handoff rule* sits between the modes: it tells the agent when to stop and hand back to the PM.

There is no "winner." Plenty of experiments conclude "this change didn't clear the noise" or "mixed result" — and that is a valid finding. The unit of work is the reproducible experiment record, not a promoted artifact.

**One scope line.** `hdl` reads agents; it does not write to them. When a verdict says a change is worth keeping, actually applying it to your production agent is something you do outside the tool.

## The architecture

```
   goal.md  ·  meta-goal / operational goal / eval suite
        │                                          ▲
        │  OUTER LOOP — PM revises the goal         │
        ▼                                          │
   ┌─────────────────────────────────────────┐     │
   │  versions   V1 · V2 · V3                 │     │
   │  (one held fixed as the baseline)        │     │
   │       │                                  │     │
   │       ▼      INNER LOOP — coding agent    │     │
   │  run ──► score ──► compare                │     │
   └────────────────────┬─────────────────────┘     │
                         ▼                           │
                 comparison report ──► PM verdict ───┘
                                       (revises a version,
                                        the experiment, or the goal)
```

The inner loop runs an experiment under a fixed goal. The outer loop reads the comparison report and revises something — a single version, the experiment setup, or the goal itself. In human-judged mode the PM owns the outer loop; in self-iterating mode the coding agent drives part of it too, by the rules in the program.

## Usage

```
$ hdl new memory-rule-v2
  built experiment: 001-memory-rule-v2
    program.md   — experiment brief: hypothesis + declarations
    rubric.md    — scoring dimensions + weights
    测试集/      — test cases
    versions/    — versions under test

$ hdl show 001       # read and lint the program
$ hdl cases 001      # read and lint the test set
$ hdl rubric 001     # read and lint the rubric
$ hdl versions 001   # read and lint the versions
```

Today `hdl` scaffolds an experiment and lints its files — it is the authoring front end. The run/score/compare engine is the next piece to build; until it lands, the running, scoring and comparing are done by hand, or by the coding agent, against the files `hdl` validates.

## The goal specification

`goal.md` separates three things, on purpose:

- **Meta-goal** — qualitative; what you actually want. Not optimized against directly.
- **Operational goal** — verifiable; what the agent optimizes. A proxy.
- **Eval suite** — how the operational goal is measured. This is the goal-level definition; each experiment builds its own test set and scorer from it.

The split exists because the operational goal is a proxy, and proxies get gamed. Keeping the meta-goal visible and separate is the explicit defense against Goodhart's law — and that is the outer loop's job: catch the gap between "the metric went up" and "the thing I wanted got better."

## Status

| | |
|---|---|
| Stage | Pre-MVP — authoring CLI works; run/score/compare engine not built |
| Form | Open-source CLI tool |
| Tested | Not yet — no real case study |
| Case study | In preparation (see below) |

**On evidence.** "I ran this" is a claim, not proof. Before the first public release I owe a real case study: a feature or skill I optimized with Harness Design Loop, before and after, with the experiment records and a real comparison report. Until that ships, treat this as an architecture I am proposing — not a result I am reporting.

## Related Work

**Heuristic Learning** — Jiayi Weng, *Learning Beyond Gradients* (2026). Weng names the paradigm Harness Design Loop operates in: a coding agent improves a software system by editing *code* — rules, state, tests, memory — instead of training neural-network parameters. It shares Deep RL's state–action–feedback–update loop, but the update mechanism is direct code edits and the feedback is multi-channel (tests, logs, replays, human input). Harness Design Loop's inner loop *is* an HL loop: the artifact under optimization is a Heuristic System, and the keep-or-discard rule is its combined update-and-feedback mechanism. Weng also names the failure modes the outer loop exists to catch — "new rules break old scenarios," "tests become exploitable," "patches accumulate beyond maintenance capacity." Where Weng describes the paradigm, Harness Design Loop is one tool for running it — with a PM in an outer loop optimizing the goal itself.

**Karpathy's AutoResearch** (2026) demonstrated an automated research loop on ML training, against a fixed objective — validation loss. Harness Design Loop borrows its two-role structure — a researcher and a coding agent — but plays a different game: it compares versions side by side rather than iterating a single file, and the goal itself is under revision, so Goodhart risk dominates. AutoResearch is a reference, not a template.

## Author

Built by Kun, an AI Product Manager.
