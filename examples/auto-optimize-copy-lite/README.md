# Example: Auto Optimize (copy-only)

The smallest end-to-end **Auto Mode → Auto Optimize** example. It runs the bounded
`candidate → evaluate → promote` loop in its simplest deterministic form:
**copy-only**. Each candidate is an exact copy of the incumbent (no LLM, no
`mutation_script`), so none can beat it — the loop runs to `max_iterations` and
records its history. Everything is local and deterministic.

## Layout

```
auto-optimize-copy-lite/
├── goal.md
├── evaluation-methods/benchmark.md
└── experiments/demo/
    ├── experiment.yaml                       # optimization.enabled: true, max_iterations: 2
    ├── cases/cases.jsonl                     # 1 case
    ├── agent-runtimes/runtime-a.yaml         # local_cli → python3 agent.py
    ├── harnesses/base/agent.py               # echoes "BASE:..." (never passes the benchmark)
    └── evaluation/benchmarks/needs_good.py   # benchmark: pass iff a response contains "GOOD"
```

## Run it

From this directory (`examples/auto-optimize-copy-lite/`):

```bash
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

> Needs `python3` on PATH (else edit `command:` in
> `experiments/demo/agent-runtimes/runtime-a.yaml`).

## What you get after `run`

```
experiments/demo/
├── harnesses/
│   ├── incumbent/                 # the surviving harness (unchanged — copy-only never promotes)
│   └── candidates/iter-00N/       # each iteration's candidate copy
└── optimization/
    ├── history.jsonl              # one record per iteration (status, score, promoted, reason)
    └── iterations/iter-00N/
        ├── iter-00N.json          # per-iteration record
        └── evidence/              # that iteration's traces / raw / artifacts / scores / issues
```

Because it is copy-only, you should see **2 iterations, 0 promotions, stopped by
`max_iterations`**, and each iteration's `primary_status` is `failed` (the base never
emits `GOOD`). That is the honest, expected result.

## Making it actually improve

Add a `mutation_script` to `optimization:` in `experiment.yaml`. The script is run
as `python <script> <incumbent_dir> <candidate_dir> <iteration> <objective.json>` and
may edit only the **editable surface** (here `harnesses/base`); touching the protected
surface (cases / evaluation / objective / goal) rolls the candidate back. A candidate
that makes the benchmark pass (and adds no blocking issue) is promoted to incumbent.
