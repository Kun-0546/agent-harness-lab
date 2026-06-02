# Examples

Runnable v1 examples. Each is a self-contained workspace; everything is local and
deterministic — no network, no API keys, no LLM. See
[`../docs/quickstart.md`](../docs/quickstart.md) for the full walk-through.

| Example | Mode | What it shows |
|---------|------|---------------|
| [`auto-run-local-cli-lite/`](auto-run-local-cli-lite/) | Auto Run | drive a `local_cli` harness over cases → evidence → evaluation → report |
| [`auto-optimize-copy-lite/`](auto-optimize-copy-lite/) | Auto Optimize | the bounded, deterministic candidate → evaluate → promote loop (copy-only) |

Run any example from its own directory:

```bash
cd examples/auto-run-local-cli-lite
PYTHONPATH=../../src python -m agent_harness_lab review experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run    experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report experiments/demo
```

(The examples' runtimes call `python3 agent.py`; on Windows without `python3`, edit
`command:` in each `experiments/demo/agent-runtimes/runtime-*.yaml`.)
