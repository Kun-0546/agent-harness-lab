# Example: Auto Run over a `local_cli` runtime

The smallest end-to-end **Auto Mode → Auto Run** example. AHL drives one harness
(`base-echo`) over two cases through the `local_cli` connector, collects evidence,
runs a benchmark evaluator, and builds a report. Everything is local and
deterministic — no network, no API keys, no LLM.

## Layout

```
auto-run-local-cli-lite/
├── goal.md
├── evaluation-methods/benchmark.md
└── experiments/demo/
    ├── experiment.yaml                  # run.mode: auto, one harness, benchmark track
    ├── cases/cases.jsonl                # 2 cases
    ├── agent-runtimes/runtime-a.yaml    # local_cli → python3 agent.py
    ├── harnesses/base/agent.py          # deterministic echo + writes produced/out.txt
    └── evaluation/benchmarks/score.py   # benchmark: pass iff every trace is ok
```

## Run it

From this directory (`examples/auto-run-local-cli-lite/`):

```bash
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

> The runtime command is `python3 agent.py`. If `python3` is not on your PATH
> (e.g. some Windows setups), change `command:` in
> `experiments/demo/agent-runtimes/runtime-a.yaml` to `py agent.py` or
> `python agent.py`.

## What you get after `run`

```
experiments/demo/evidence/
├── traces/runtime-a.jsonl          # one record per case (input, response, ok)
├── raw/runtime-a/{c1,c2}.{out,err} # raw stdout/stderr per case
├── artifacts/runtime-a/<case>/produced/out.txt
├── scores/quality/e1.jsonl         # benchmark verdict (EvaluationRunner)
├── scores/tracks/quality.json      # aggregated track status
└── issues.jsonl                    # connector/case/artifact issues (empty on happy path)
```

And after `report`: `experiments/demo/reports/report.md`.

This is a single-harness baseline. To turn it into a real A/B comparison, add a
second harness under `harnesses/` and a second `agent_runtimes` entry pointing at it.
