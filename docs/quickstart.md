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

## Run the Auto Run example (A/B: verbose vs concise)

Two harnesses answer the same FAQ cases; a deterministic benchmark scores each on
correctness + conciseness; the report compares them and names a winner.

```bash
cd examples/auto-run-local-cli-lite
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

`run` dispatches 3 cases × 2 harnesses, collects evidence, then runs evaluation +
inspection. The benchmark passes an answer only if it contains the required key term,
stays within the length budget, and uses minimal filler — so **`verbose baseline` (A)
fails every case and `concise alternative` (B) passes every case**.

Open `experiments/demo/reports/report.md` to read, end to end:

```text
Harness comparison   A (verbose baseline)    0/3   score 0.00
                     B (concise alternative) 3/3   score 1.00   <- Winner
Cases                the 3 FAQ questions and their key terms
Evidence             per harness: traces / raw / artifacts
Artifacts            the produced/answer.txt collected for each
Issues               none on the happy path
Objective            met by the best harness (B)
Recommendation       B is stronger; a human decides in conclusion.md
```

(`review` prints a `conclusion_missing` WARN — expected; you write `conclusion.md`
after reading the report. The `quality` track aggregates to `failed` because not every
harness passes — normal for an A/B run; the per-harness comparison is the signal.)

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
