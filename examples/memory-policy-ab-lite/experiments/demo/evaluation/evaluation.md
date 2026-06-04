# Evaluation design — memory policy A/B

Evaluation is fixed before the run so the bar is independent of the outputs.

## 1. Evaluation Methods (workspace level)
- **benchmark** — deterministic, scriptable scoring (the primary, no-key path here).
- **llm_judge** — an LLM scores against rubrics/memory_policy.md (optional; needs
  AHL_JUDGE_BASE_URL / AHL_JUDGE_MODEL / AHL_JUDGE_API_KEY, else pending).

## 2. Evaluators (this experiment)
- `memory_policy` (benchmark) -> evaluation/benchmarks/evaluate.py
- `memory_judge` (llm_judge)  -> evaluation/rubrics/memory_policy.md

## 3. Tracks
- `memory-quality` (objective primary) — the benchmark; decides the winner with no
  API key required.
- `judge-review` — the llm_judge; pending unless AHL_JUDGE_* is configured.

## What counts as a weak or invalid result
A tie on `memory-quality`, empty agent responses, or a benchmark that fails to
separate eager vs filtered policies.
