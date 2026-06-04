# Harness A — eager-memory-injection

## What this harness changes
The baseline (worst-practice) memory policy: inject every memory item into the answer
regardless of relevance or sensitivity, and guess confidently when no relevant memory
exists.

## Source / config
harnesses/A/agent.py — a deterministic local_cli agent.

## How it is applied
Run directly as the Agent Runtime `runtime-a` (connector local_cli, `python3 agent.py`).

## Expected artifacts
produced/answer.txt — the answer for the last case.

## Known risks / failure modes
Leaks irrelevant and sensitive memory; asserts stale facts; fabricates when memory is
missing. That is the point — it is the baseline B must beat.
