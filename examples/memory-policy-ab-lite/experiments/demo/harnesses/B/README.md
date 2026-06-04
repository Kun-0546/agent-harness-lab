# Harness B — filtered-memory-retrieval

## What this harness changes
Uses only memory tagged relevant; drops irrelevant / stale / sensitive memory; declines
instead of inventing an answer; notes when sensitive details were withheld.

## Source / config
harnesses/B/agent.py — a deterministic local_cli agent.

## How it is applied
Run directly as the Agent Runtime `runtime-b` (connector local_cli, `python3 agent.py`).

## Expected artifacts
produced/answer.txt — the answer for the last case.

## Known risks / failure modes
Recall loss: by filtering aggressively it could drop a memory that was actually
relevant. The cases test that it still answers the relevant ones.
