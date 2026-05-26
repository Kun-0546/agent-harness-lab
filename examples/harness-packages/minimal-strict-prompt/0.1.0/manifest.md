---
id: minimal-strict-prompt
version: 0.1.0
runtime_compatibility: [local_path, git_repo]
---

## Description
极简严格 prompt harness。覆盖 `prompts/system.md` + 注入 `HARNESS_STRICT=1`
env + 锁定 start command。任何兼容 local_path / git_repo 的 runtime
source 都能引用 `minimal-strict-prompt@0.1.0` 套用此 harness。

## Payload

files:
  - target: prompts/system.md
    source: payload/system.md
env:
  HARNESS_STRICT: "1"
start_command: python -m agent.run
