# goal · FAQ-bot conciseness

## 目标 agent

A simple FAQ-bot that responds to user questions about a fictional product
(password resets, refund policies, etc.).

## 想改善的行为

Default responses are verbose — the bot explains too much when a short
direct answer would do. Real users want to scan the answer and move on.

Two concrete failure cases:
- "How do I reset my password?" → returns 3 paragraphs of context before
  the actual step
- "What is your refund policy?" → restates the question, then the policy

## 当前 baseline

V1 baseline = tiny-runtime's default system prompt:
`DEFAULT verbose prompt: explain everything in detail`

## Harness 层假设

The harness layer that most directly controls verbosity is the **system
prompt**. Changing the system prompt from "explain everything in detail"
to a stricter, more concise instruction should shorten responses without
losing correctness — and it should be testable via A/B compare on the
same case set.

## 成功标准

- V2 (with `concise-prompt` package) produces measurably different
  responses to the same cases (shorter, more direct)
- Stub grader registers a non-trivial total-score delta between V1 and V2
- Snapshot for V2 carries a complete `harness_package` block (manifest_hash
  + payload_hash + effective_harness_hash) — proving the package install
  was reproducible

## 红线

- Do not lose correctness for the sake of concision
- Do not change the API protocol the agent speaks (stdin JSON in / stdout
  JSON out)
