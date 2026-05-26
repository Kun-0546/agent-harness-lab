# Evidence Examples

Reference templates for user-supplied `materials/*-evidence.md` files.

These are **examples** — not committed inside any experiment, not
auto-installed, and not parsed by AHL. You copy one of them into your
own experiment's `materials/` directory, edit for your situation, and
the file's *existence* upgrades a legacy `connect.md` variant's
evidence level from `weak` to `medium`.

For the full reasoning about what evidence does and doesn't prove,
read [`docs/evidence-guide.md`](../../docs/evidence-guide.md). The
short version:

- AHL never parses these files' content. Existence-only.
- Supplied evidence cannot reach `strong`. Materialized runtimes
  (`runtime-sources.md` with `local_path` / `git_repo`) are the only
  path to `strong`.
- Supplied evidence is **not** cloud attestation — it is a note to
  your future self about what *you* believe was installed.

## Files in this directory

| File | Use when |
|---|---|
| [`runtime-evidence.md`](runtime-evidence.md) | The agent is an already-running local process and you want to record what runtime AHL was actually talking to. |
| [`harness-evidence.md`](harness-evidence.md) | You want to document which harness (memory file, skill set, plugin list, soul file) was loaded inside the running agent. |
| [`cloud-evidence.md`](cloud-evidence.md) | The agent is a managed cloud deployment and you want to record deployment id, configuration version, and capture-time state. |

You can drop one, two, or all three into a single experiment's
`materials/` directory. Each one independently triggers the `weak →
medium` upgrade (any file is sufficient).

## Why these aren't shipped inside `examples/sample-workspace/`

The sample workspace at `examples/sample-workspace/` demonstrates the
**materialized** product flow (`runtime_source: local-tiny`). Its V1
and V2 variants land at `strong` evidence without any
`materials/*-evidence.md` files — that's the point of the
materialization path.

Putting evidence examples inside the sample workspace would:

- Trip the sample workspace cleanliness assertion in
  `tests/test_sample_workspace_e2e.py` (`materials/*-evidence.md` are
  treated as generated, not committed, artifacts).
- Suggest that the sample workspace's `strong` evidence depends on
  supplied attestation, which is the opposite of what materialization
  provides.

So evidence examples live one directory up, free of that confusion.

## When you adapt these for your experiment

1. Copy the file you need into
   `experiments/<your-id>/materials/<filename>.md`.
2. Replace placeholder values with your real attestation.
3. Be honest. AHL doesn't parse contents, but the file is the record
   *you* will read when reviewing the run six months from now.
4. Re-run `ahl score` or `ahl compare`. The variant's evidence level
   should land at `medium`.

If you find yourself wanting evidence to upgrade past `medium`, the
answer is to **materialize the runtime** (declare it in
`runtime-sources.md` and let AHL copy / clone + snapshot it), not to
write more evidence files.
