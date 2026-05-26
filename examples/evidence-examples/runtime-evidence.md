# runtime-evidence

> **Template** — copy to `experiments/<your-experiment>/materials/runtime-evidence.md`
> and edit. The file's *existence* upgrades a legacy `connect.md` variant from
> `weak` to `medium` evidence. AHL never parses this content.
>
> Honest about what this file is: **a note from you to future you about what
> runtime AHL was actually talking to.** Not cloud attestation, not a
> compliance artifact, not parsed.

## What was checked

The local Python process exposed via the `connect.md` `外部命令行` adapter
was confirmed to be the long-running coding-assistant agent at the
documented path (`/Users/example/code/coding-agent/`), not a stale
process or sibling executable.

Verified items:
- Process command line matched `connect.md` `命令:` field.
- Process working directory matched the expected agent install root.
- Process environment contained the harness-relevant variables
  (`AGENT_PROFILE=production`, `AGENT_MEMORY_PATH=...`).
- Tool / dependency versions in the install root matched what the
  experiment assumes (e.g., specific `requirements.txt`).

## Who / what supplied this

- **Supplier**: Kun (manually, via shell inspection — `ps`, `lsof`, `env`).
- **Workstation**: macOS 14.4 development laptop, hostname `<host>`.
- No automated tooling produced this file.

## When was it captured

- **Captured at**: 2026-06-01 14:32:00 PDT (local clock).
- **AHL run timestamp**: 2026-06-01 14:35:18 PDT (the next `ahl run` after
  capture; record the actual run ID once it exists, e.g.
  `run-20260601-213518`).
- Best practice: capture this immediately before or after the `ahl run`,
  not days apart. The longer the gap, the weaker the attestation.

## What this evidence can support

- Upgrading the variant from `weak → medium` in v0.4 evidence inference
  (file existence triggers the upgrade).
- A future read of the compare report ("right, the runtime at the time of
  this run was the production-profile process with memory at X").
- A starting point for a deeper investigation if the result is
  surprising.

## What this evidence cannot prove

- That the process described above was actually running at the moment of
  the AHL run (process state may have shifted between capture and run).
- That the harness configuration loaded by the process matches what the
  config file on disk says — runtime overrides, env vars, hot reloads
  could differ.
- That subsequent runs in the same experiment also hit the same process
  (long-running processes can be restarted with different config).
- Anything cryptographic. This is plaintext markdown, no signature, no
  hash chain.

## Limitations

- **Existence-only**: AHL reads this file's filename but never its
  content. Editing the file does not re-trigger evidence reinference —
  only the existence of the file at the time `ahl score` / `ahl compare`
  runs matters.
- **Ceiling at medium**: supplied evidence in legacy_connect path
  cannot reach `strong` regardless of how thorough this file is.
  `strong` requires materialized runtime via `runtime-sources.md`.
- **Honor system**: AHL trusts you. If the claims here are wrong or
  outdated, the `medium` label will be misleading. This file is a
  contract with your future self, not with a verifier.
- **Local context only**: this template is for local long-running
  processes. For cloud deployments, use `cloud-evidence.md` instead
  (similar shape, different framing).
