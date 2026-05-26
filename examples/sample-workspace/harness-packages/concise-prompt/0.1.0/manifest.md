---
id: concise-prompt
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
极简 FAQ 回答 harness package。覆盖 `prompts/system.md`,让 agent 用
STRICT concise prompt(单句回答)替代 runtime 自带的 DEFAULT verbose
prompt(详细解释)。

任何兼容 `local_path` 的 runtime source(如 `local-tiny`)都能引用
`concise-prompt@0.1.0` 套用此 harness。

## Payload

files:
  - target: prompts/system.md
    source: payload/system.md
start_command: python agent.py
