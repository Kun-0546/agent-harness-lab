# harness-evidence

> **Template** — copy to `experiments/<your-experiment>/materials/harness-evidence.md`
> and edit. The file's *existence* upgrades a legacy `connect.md` variant from
> `weak` to `medium` evidence. AHL never parses this content.
>
> Use this when the harness (system prompt / memory / skills / plugins /
> soul file) lives inside the running agent's workspace and you can describe
> what's loaded, but AHL itself isn't installing it via
> `runtime-sources.md` materialization.

## What was checked

The harness loaded by the long-running agent was confirmed to match the
intended version for this experiment:

- **System prompt**: `~/.config/coding-agent/system.md`
  - SHA-256: `4c8a91d3b...` (computed via `shasum -a 256`)
  - Last modified: 2026-05-30 16:22:00 PDT
- **Memory file**: `~/.config/coding-agent/memory.md`
  - SHA-256: `9f12bb47c...`
  - Last modified: 2026-05-28 09:14:00 PDT
- **Skill directory**: `~/.config/coding-agent/skills/`
  - Files: `code-review.md`, `test-generation.md`, `refactoring.md`
  - Combined directory hash: `sha256:1a2b3c4d...`
- **Plugin list** (from the agent's `/plugins list` introspection
  command output): `code-search`, `git-helper`, `repl`. No others.

## Who / what supplied this

- **Supplier**: Kun (manually, via shell + `shasum` + the agent's own
  introspection commands).
- The agent provided plugin/skill list via its built-in `/plugins list`
  and `/skills list` commands; the rest came from filesystem inspection.

## When was it captured

- **Captured at**: 2026-06-01 14:28:00 PDT.
- **AHL run timestamp**: 2026-06-01 14:35:18 PDT (≈7 minutes after
  capture; replace with your actual run id, e.g. `run-20260601-213518`).
- The harness on disk did not change between capture and run (verified
  by re-running `shasum -a 256 ~/.config/coding-agent/*.md` immediately
  after the AHL run).

## What this evidence can support

- Upgrading the variant from `weak → medium` (existence triggers the
  rule).
- A reviewer's question "which version of the system prompt was loaded
  for this run?" — the SHA above answers it for the on-disk state at
  capture time.
- Distinguishing two variants of the same `connect.md` adapter where
  the only difference is the harness loaded inside the running agent
  (e.g., V1 = baseline `system.md`, V2 = experimental `system.md`).

## What this evidence cannot prove

- That the agent's *runtime state* matches what's on disk. The agent
  may have loaded these files at startup and then mutated them in
  memory (in-memory edits, hot reloads, runtime overrides). Filesystem
  hashes describe disk state, not process state.
- That no other harness component is also active (system prompts in
  env vars, plugins loaded by side-effect of running a tool, etc.).
- That the agent's `/plugins list` and `/skills list` are accurate —
  these are the agent's self-report, which the agent could in principle
  be misreporting.
- Cryptographic chain of custody. Plain markdown + plaintext hashes.

## Limitations

- **Existence-only**: AHL reads this file's filename but never its
  content. The SHAs above are for *your* later review, not for AHL.
- **Ceiling at medium**: legacy_connect + supplied evidence cannot
  reach `strong`. If you need `strong`, switch the variant to a
  `runtime_source: <local_path>` declaration so AHL itself can copy +
  hash the harness directory and apply patches inside a sandbox.
- **Hash snapshots are point-in-time**: re-capture before each
  experiment iteration. A stale `harness-evidence.md` from three weeks
  ago is worse than no file — it implies a precision the run no longer
  has.
- **No automated re-check**: if the harness on disk changes between
  this file and the next AHL run, nothing flags it. The honor system
  applies here too.
