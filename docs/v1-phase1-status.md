# v1 Phase 1 status (internal engineering note)

> Internal note, not public positioning. What the v1 `hlab` surface does today.

## Implemented (Phase 1)

- `hlab init` — create the workspace (`goal.md`, `evaluation-methods/`,
  `experiments/`, `.hlab/`). Idempotent.
- `hlab new <name>` — scaffold a full v1 experiment tree with a valid
  `experiment.yaml` that reviews with no ERROR (Auto Mode with a not-yet-
  implemented state policy may WARN). Flags: `--mode {copilot,auto}`,
  `--execution {ab,sequential,longitudinal,replay}`.
- `hlab review experiments/<name>` — validate `experiment.yaml` + structure,
  return **PASS / WARN / ERROR** with actionable messages (which file/path to
  create or which field to edit). Exit 1 on ERROR, else 0.
- `hlab status experiments/<name>` — summarize id / status / question / run
  mode / execution mode / harnesses (id=name) / agent runtimes (→harness,
  connector) / harness count / case count / collection (on/off) / inspection
  (reviews/checks) / evidence / issues / report / conclusion. Exit 0.
- `hlab run experiments/<name>` **in Copilot Mode** (`run.mode: copilot`) —
  reviews first, then renders `agent-task.md` from `experiment.yaml` +
  `experiment.md` (deterministic, overwritten each run) and **exits 0**. The
  output states that agent-task.md was generated, that no Agent Runtime was
  directly executed, and that no evidence was collected yet. A review **ERROR**
  refuses generation (exit 1); `agent-task.md` is **not** the source of truth.
- `hlab run experiments/<name>` **in Auto Mode = Auto Run** (`run.mode: auto`) —
  reviews first, then the AutoRunner dispatches each case (single_turn `cases.jsonl`)
  to each runtime via its connector (`local_cli` reuses the stdin_json IPC; `script`
  runs a per-case command), and the EvidenceCollector writes `evidence/traces/`,
  `evidence/raw/`, `evidence/artifacts/` (from `artifacts.collect` globs) and
  `evidence/issues.jsonl` (connector_failure / case_failure / missing_artifact /
  empty_output). **Exits 0** (the run executed; per-case problems are recorded as
  issues, not exit codes). A review **ERROR** (e.g. Auto + manual) blocks it (exit 1).
  This is **Auto Run only** — Auto Optimize is not implemented (see below).

## NOT implemented yet (later phases) — and how the CLI behaves now

- **Auto Optimize** (the second Auto Mode layer) — NOT implemented. v1 validates the
  `objective` / `optimization` schema + the editable/protected-surface boundary and
  **WARNs** that the loop does not execute; it never generates, runs, evaluates, or
  promotes Candidate Harnesses.
- `hlab report` — does **not** generate a report. Prints to stderr that no
  report was generated and **exits 2**.
- Not built: EvaluationRunner (run evaluators/tracks), Inspector (run
  `inspection.issue_checks`), ReportBuilder (`report.md`/`report.html`), the Auto
  Optimize loop / mutation engine, and Auto state policies beyond `isolated`
  (reset/cumulative/snapshot_branch/replay). (AutoRunner = **Auto Run** +
  `local_cli`/`script` connectors + EvidenceCollector + CopilotTaskRenderer — **done**.)
- Authoritative v1 spec is version-controlled in **`docs/v1-spec/`**.

## Exit-code summary

| command | success | not-implemented-this-phase | error |
|---|---|---|---|
| `init` | 0 | — | 1 (`experiments`/`.hlab` exists as a file) |
| `new` | 0 | — | 1 (dup / no workspace) |
| `review` | 0 (PASS/WARN) | — | 1 (ERROR / not found) |
| `status` | 0 | — | 1 (not found / unreadable) |
| `run` (copilot) | 0 (agent-task.md generated) | — | 1 (review ERROR / not found) |
| `run` (auto) | 0 (cases dispatched, evidence written) | — | 1 (review ERROR / not found) |
| `report` | — | **2** | 1 (review ERROR / not found) |
