# Goal — demonstrate the bounded Auto Optimize loop deterministically

This workspace shows the v1 **Auto Optimize** loop in its simplest, fully
deterministic form: **copy-only**. There is no LLM and no mutation — each
candidate is an exact copy of the incumbent, so none can beat it. The point is to
show the loop *mechanics* honestly: per-iteration Auto Run + evaluation, the
promotion decision, the stop condition, and `optimization/history.jsonl`. No
network, no external APIs.

To make a loop that actually improves something, supply a `mutation_script` under
`optimization:` (see `docs/v1-spec/` and `docs/quickstart.md`).
