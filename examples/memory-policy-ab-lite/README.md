# Example: Memory policy A/B (eager injection vs filtered retrieval)

A complete, runnable v1 **flagship** example. An assistant answers user questions from
a mixed **memory store**; two harnesses use that memory differently, and a
deterministic 5-dimension benchmark scores them. Everything is local and deterministic
— no network, no API keys, no LLM.

This is the same experiment that `hlab new --template memory-policy-ab-lite` generates.

## The experiment

- **Harness A — `eager-memory-injection`**: injects every memory item into the answer
  (relevant or not) and guesses when nothing relevant is on file. It leaks and
  hallucinates — the baseline to beat.
- **Harness B — `filtered-memory-retrieval`**: uses only relevant memory, drops
  irrelevant / stale / sensitive memory, and declines instead of inventing.
- **5 cases**: relevant-memory-used, irrelevant-not-leaked, conflicting-handled,
  missing-not-fabricated, sensitive-not-exposed.
- **Benchmark** (`evaluation/benchmarks/evaluate.py`): scores five dimensions per
  (harness, case) — `answer_correctness`, `memory_relevance`, `privacy_leakage`,
  `hallucination`, `conciseness`.
- **Objective**: maximize the `memory-quality` track. An optional `llm_judge` track
  adds an LLM's view when `AHL_JUDGE_*` is configured (otherwise it stays pending —
  never a faked verdict).

## Run it

From this directory (`examples/memory-policy-ab-lite/`):

```bash
PYTHONPATH=../../src python -m agent_harness_lab review   experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab run      experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab report   experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab compare  experiments/demo
PYTHONPATH=../../src python -m agent_harness_lab conclude experiments/demo --winner B \
  --reason "Filtered retrieval cut leakage while keeping task success."
```

> The runtimes call `python3 agent.py`. On Windows without `python3`, change
> `command:` in `experiments/demo/agent-runtimes/runtime-*.yaml` to `py agent.py`.

## What you get

- **Harness comparison** — B beats A on relevance, privacy, and hallucination: B passes
  all 5 cases; A leaks irrelevant/sensitive memory or fabricates on 4 of them.
- `reports/report.md` and `reports/report.html` — the human report (Markdown + a real
  rendered HTML page).
- `reports/compare.json` — a machine-readable A/B summary: per-harness score, pass
  count, issue tags, winner, and a data-driven reason.
- `conclusion.md` — your decision, recorded by `hlab conclude` (not generated for you).

## No API key needed

The objective track is a deterministic benchmark, so the whole path runs offline. The
`llm_judge` track stays **pending** without `AHL_JUDGE_BASE_URL` / `AHL_JUDGE_MODEL` /
`AHL_JUDGE_API_KEY` — a missing key is reported as pending, never as a fabricated score.
