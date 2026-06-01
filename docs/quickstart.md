# Quickstart

Run a real v1 experiment end to end in a couple of minutes. Everything here is
local and deterministic — no network, no API keys, no LLM.

## Prerequisites

- Python 3.10+
- PyYAML (installed automatically by `pip install -e .`)
- A `python3` on your PATH for the example runtimes (on Windows without `python3`,
  edit the example's `command:` to `py agent.py` or `python agent.py`).

```bash
pip install -e .          # provides the `hlab` command (and `python -m agent_harness_lab`)
```

## The command surface

```text
hlab init <dir>            initialize a workspace (goal.md, evaluation-methods/, experiments/)
hlab new <name>            scaffold an experiment (--mode copilot|auto, --execution ab|...)
hlab review <experiment>   validate experiment.yaml before running (PASS / WARN / ERROR)
hlab run <experiment>      Copilot: render agent-task.md · Auto: drive runtimes + collect evidence
hlab status <experiment>   show status + evidence/evaluation state
hlab report <experiment>   build reports/report.md from the evidence
```

`hlab <cmd>` and `python -m agent_harness_lab <cmd>` are equivalent.

## Run the Auto Run example

A single `local_cli` harness driven over two cases, with a benchmark evaluator.

```bash
cd examples/auto-run-local-cli-lite
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

`run` dispatches both cases, collects evidence, then runs evaluation + inspection:

```text
experiments/demo/evidence/
├── traces/runtime-a.jsonl          # one record per case
├── raw/runtime-a/{c1,c2}.{out,err}
├── artifacts/runtime-a/<case>/produced/out.txt
├── scores/quality/e1.jsonl         # benchmark verdict
├── scores/tracks/quality.json      # aggregated track status (passed)
└── issues.jsonl                    # empty on the happy path
```

`report` writes `experiments/demo/reports/report.md`. (`review` prints a
`conclusion_missing` WARN — that is expected; you write `conclusion.md` once you've
read the report.)

## Run the Auto Optimize example (bounded, deterministic)

The bounded `candidate → evaluate → promote` loop in its simplest copy-only form.

```bash
cd examples/auto-optimize-copy-lite
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

Copy-only candidates are exact copies of the incumbent, so none can beat it — you
get **2 iterations, 0 promotions, stopped by `max_iterations`**:

```text
experiments/demo/optimization/
├── history.jsonl                       # one record per iteration
└── iterations/iter-00N/
    ├── iter-00N.json
    └── evidence/                       # that iteration's traces / raw / scores / issues
```

To make a loop that actually improves the harness, add a `mutation_script` under
`optimization:` — it may edit only the **editable surface** (the harness); touching
the protected surface (cases / evaluation / objective / goal) rolls the candidate back.

`review` emits an `optimization_bounded_only` WARN: the loop runs, but it is
deterministic (copy-only / script-based), **not** LLM-driven or autonomous.

## Where the contracts live

- CLI: [`docs/v1-spec/cli.md`](v1-spec/cli.md)
- experiment.yaml schema: [`docs/v1-spec/experiment-yaml-schema.md`](v1-spec/experiment-yaml-schema.md)
- execution model (Copilot / Auto Run / Auto Optimize, connectors, state policies):
  [`docs/v1-spec/execution-model.md`](v1-spec/execution-model.md)
- experiment structure: [`docs/v1-spec/experiment-structure.md`](v1-spec/experiment-structure.md)
