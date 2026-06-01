# Evaluation method: benchmark

A `benchmark` evaluator runs a deterministic script over the collected evidence and
prints a JSON verdict `{"passed", "score", "detail"}`. The script receives a context
JSON (experiment id + requested evidence such as `traces`) as its only argument. No
network, no human, no LLM.

This example's script (`experiments/demo/evaluation/benchmarks/needs_good.py`) passes
only if a trace response contains `GOOD`. The copy-only base emits `BASE:` and never
passes — that is intentional, so the loop runs to its stop condition without promoting.
