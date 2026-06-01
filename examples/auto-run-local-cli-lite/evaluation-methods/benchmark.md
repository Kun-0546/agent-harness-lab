# Evaluation method: benchmark

A `benchmark` evaluator runs a deterministic script over the collected evidence and
emits a pass/fail + score. The script receives a context JSON as its only argument
(experiment id + the requested evidence, e.g. `traces`) and prints a JSON verdict
`{"passed": bool, "score": number, "detail": str}` to stdout. No network, no human,
no LLM — fully reproducible.

This example's script: `experiments/demo/evaluation/benchmarks/score.py`.
