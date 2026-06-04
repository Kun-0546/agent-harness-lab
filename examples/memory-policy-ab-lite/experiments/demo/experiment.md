# Experiment — demo

## Why are we running this experiment?
To decide whether a filtered memory-retrieval policy (B) is a real improvement over
eager memory injection (A) for an assistant that answers from a mixed memory store.

## Which long-term goal does it serve?
goal.md — a memory policy that helps without leaking.

## Which harnesses are compared?
  A: eager-memory-injection — injects all memory, guesses when nothing fits (baseline)
  B: filtered-memory-retrieval — uses only relevant memory, declines otherwise

## Which Agent Runtimes are used?
Both are local_cli agents (`python3 agent.py`) under agent-runtimes/. Same contract,
different policy — so the harness is the only variable.

## Which cases are run?
Five cases that separate the policies (cases/cases.jsonl): relevant-memory-used,
irrelevant-not-leaked, conflicting-handled, missing-not-fabricated,
sensitive-not-exposed.

## How is evaluation designed?
A deterministic benchmark (evaluation/benchmarks/evaluate.py) scores five dimensions
per (harness, case): answer_correctness, memory_relevance, privacy_leakage,
hallucination, conciseness. An optional llm_judge track adds an LLM's view when
AHL_JUDGE_* env vars are set (otherwise it stays pending — never a fake verdict).

## What evidence must be collected?
Traces, raw output, the produced answer artifact, and scores.

## What requires human review?
The final conclusion (recorded with `hlab conclude`) and any privacy red-line call.

## When should the result be considered invalid or weak?
Empty responses, a benchmark that does not separate the harnesses, or a tie.
