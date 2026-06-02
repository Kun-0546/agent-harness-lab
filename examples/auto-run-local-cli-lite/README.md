# Example: A/B Auto Run over `local_cli` (verbose vs concise)

A complete, runnable v1 **Auto Run A/B** demo. Two harnesses answer the same FAQ
cases; a deterministic benchmark scores each on **correctness + conciseness**; the
report compares them and names a winner. Everything is local and deterministic — no
network, no API keys, no LLM.

This is **Auto Run** (compare A vs B on fixed cases), not Auto Optimize (which
iterates one harness).

## The experiment

- **Harness A — `verbose baseline`**: answers are correct (they contain the required
  key term) but padded with filler phrases and run long.
- **Harness B — `concise alternative`**: the same correct information, short and direct.
- **3 FAQ cases** (reset password / support hours / cancel), each declaring its
  required key term in `expect`.
- **Benchmark** (`evaluation/benchmarks/concise_faq.py`): a (harness, case) answer
  passes iff it (1) contains the key term, (2) is ≤ 120 characters, and (3) uses at
  most one filler phrase. So A fails on length/filler; B passes on all three.
- **Objective**: maximize the `quality` track.

## Layout

```
auto-run-local-cli-lite/
├── goal.md
├── evaluation-methods/benchmark.md
└── experiments/demo/
    ├── experiment.yaml                     # run.mode: auto, execution.mode: ab, 2 harnesses
    ├── cases/cases.jsonl                   # 3 FAQ cases with `expect` key terms
    ├── agent-runtimes/runtime-a.yaml       # harness A → local_cli (python3 agent.py)
    ├── agent-runtimes/runtime-b.yaml       # harness B → local_cli
    ├── harnesses/A/agent.py                # verbose baseline (correct but bloated)
    ├── harnesses/B/agent.py                # concise alternative (correct and direct)
    └── evaluation/benchmarks/concise_faq.py# correctness + length + filler, per (harness, case)
```

## Run it

From this directory (`examples/auto-run-local-cli-lite/`):

```bash
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

> The runtimes call `python3 agent.py`. On Windows without `python3`, change
> `command:` in `experiments/demo/agent-runtimes/runtime-*.yaml` to `py agent.py`.

## What the report shows

Open `experiments/demo/reports/report.md`:

- **Harness comparison** — `A` (verbose baseline) 0/3, score 0.00 vs `B` (concise
  alternative) 3/3, score 1.00; **winner: B**, with the reason A fell short.
- **Cases** — the three FAQ questions and their key terms.
- **Evidence** — per harness: traces, raw outputs, artifact files.
- **Artifacts** — the `produced/answer.txt` collected for each harness/case.
- **Issues** — none on the happy path (both harnesses produce complete evidence; the
  difference is in the *scores*, not in evidence integrity).
- **Evaluation / Objective** — the `quality` track, and "objective met by the best
  harness (B)". The track aggregates to `failed` because not every harness passes —
  that is expected in an A/B run; the per-harness comparison is the real signal.
- **Recommendation** — that B is stronger, while leaving the final decision to a human
  in `conclusion.md` (the report never writes your conclusion for you).

## Make it your own

Swap the two `harnesses/{A,B}/agent.py` for real runtimes (or point the connectors at
your own command), edit the cases, and adjust the benchmark thresholds in
`evaluation/benchmarks/concise_faq.py`. To compare more than two, add another harness
+ agent-runtime entry.
