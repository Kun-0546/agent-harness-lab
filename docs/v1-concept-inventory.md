# v1 Concept Inventory (internal engineering note)

> Internal note, not public positioning. Purpose: every **public** v1 concept
> must have a clear user-facing purpose, a place it appears, code that reads or
> validates it, and — if not executed yet — a named future phase. Concepts that
> cannot pass this bar are removed from the public surface or kept internal.
>
> Status legend: **MVP** = part of the Phase 1 public surface and validated now ·
> **MVP (config)** = declared + validated now, executed in a later phase ·
> **stretch/reserved** = recognized but not surfaced/executed in Phase 1.

## 1. Public concepts (kept)

| Concept | User-facing definition | Appears in | Read / validated by | Executed by (phase) | Status |
|---|---|---|---|---|---|
| **goal** | The workspace-level long-term objective: which agent, what behavior to improve. | `goal.md`; `experiment.yaml: goal_ref`; `experiment.md` | `scaffold.init_workspace` writes it; `validate_spec` warns if `goal_ref` target is missing | Human-authored; never executed | MVP |
| **experiment** | One comparison of harnesses against the goal; a directory under `experiments/`. | `experiments/<name>/`; `experiment.md` (human); `experiment.yaml` (machine) | `parse_experiment_yaml` → `ExperimentSpec`; `review_experiment` | `run`/`status`/`report` operate on it | MVP |
| **harness** | The core public object — any design unit that changes how an agent runs (prompt, skill, memory, config, runtime patch, tool setup, script, constraint). | `harnesses/<id>/`; `experiment.yaml: harnesses[]`; `harnesses/<id>/README.md` | `HarnessRef` (id/name/path); harness `path` existence validated | Applied to runtime by AutoRunner | MVP (config) |
| **Agent Runtime** | The real environment the tested agent runs in. | `agent-runtimes/*.yaml`; `experiment.yaml: agent_runtimes[]` | `AgentRuntimeRef` (id/harness/spec); spec-file existence + connector type validated; harness cross-ref checked | Connectors execute (Auto Mode) | MVP (config) |
| **case** | An executable input to the runtime. | `cases/cases.jsonl`; `experiment.yaml: cases.{root,files}` | `cases.root`/`files` existence validated; `load_cases` parses JSONL (used by `status`) | Dispatched to runtime (Auto Mode) | MVP (config) |
| **evaluation** | How results are judged, in three layers: workspace **Evaluation Methods** (`evaluation-methods/`), experiment **evaluators** (configured instances), experiment **tracks** (groupings of evaluators + evidence). | `evaluation/`; `experiment.yaml: evaluation.{root, evaluators, tracks}` (legacy `methods` shorthand kept) | `evaluation.root` existence; evaluator id-unique + method enum + script/rubric refs; track id-unique + evaluator refs + evidence-type enum; no evaluators → ERROR, no tracks → WARN | `EvaluationRunner` (Evaluation phase) | MVP (design + validation); execution stretch |
| **evidence** | The store of actual run outputs. | `evidence/…` + `issues.jsonl`; `experiment.yaml: collection` | `collection` shape-validated; **values drive review coherence warnings** and are **reflected by `hlab status`**; `status` lists which evidence subdirs are non-empty | `EvidenceCollector` (`auto.py`) writes traces/raw/artifacts/issues.jsonl in Auto Mode | MVP (layout + Auto-Mode population); evaluation-scores population stretch |
| **inspection** | Automated checks over collected evidence. | `experiment.yaml: inspection` (review flags + `issue_checks`) | shape-validated; **cross-checked against `collection` in review** (e.g. a check whose evidence is disabled → WARN); **reflected by `hlab status`** | `Inspector` runs the checks (Auto Mode) | MVP (config takes effect); execution stretch |
| **issue** | A machine-readable evidence problem (e.g. `missing_artifact`, `empty_output`, `path_drift`, `runtime_mismatch`, `connector_failure`). | `evidence/issues.jsonl`; `experiment.yaml: inspection.issue_checks` | `issue_checks` enum validated; empty `issues.jsonl` scaffolded; `status` counts lines | `IssueInspector` writes typed records (Auto Mode) | MVP (file + enum); population stretch |
| **report** | Generated human-facing summary of an experiment. | `reports/report.md` (+ `report.html`); `experiment.yaml: reports.formats` | `reports.formats` enum validated; `html` → WARN (renderer unavailable) | `ReportBuilder` (Report phase) | MVP (config); `hlab report` is an explicit exit-2 stub now |
| **conclusion** | The human final conclusion + next step. | `conclusion.md` | existence → WARN if missing | Human-authored | MVP |
| **Copilot Mode** | AHL prepares the experiment and delegates runtime execution to an external coding agent. | `experiment.yaml: run.mode=copilot`; `hlab run` → `agent-task.md` | `run.mode` enum validated; `hlab run` renders `agent-task.md` (review-gated; ERROR refuses) | `CopilotTaskRenderer` (`copilot.py`) — implemented | MVP; `hlab run` (copilot) generates `agent-task.md` and exits 0 |
| **Auto Mode / Auto Run** | AHL runs an already-defined experiment's cases against runtimes through connectors. | `experiment.yaml: run.mode=auto`; agent-runtime `connector` | `run.mode` enum validated; Auto connector gate (`local_cli`/`script`); Auto state-policy note | `AutoRunner` (`auto.py`) — implemented | MVP; `hlab run` (auto) dispatches cases + writes evidence, exit 0 |
| **Auto Optimize** | The second Auto layer: iteratively generate/run/evaluate/promote Candidate Harnesses toward an objective. (Roles: Candidate / Incumbent Harness — not `variant`.) | `experiment.yaml: objective`, `optimization` | schema + review boundary validated (editable must be harness-controlled, never protected; stop_conditions required when enabled; promotion_policy refs known tracks/issues; `enabled:true` → WARN) | optimization loop — **NOT implemented** | schema/review only; loop + mutation engine stretch |
| **connector** | How a runtime is driven: `local_cli`/`script` (Auto v1), `manual` (Copilot default); `remote_devbox`/`api`/`bridge` declarable, not executed in v1. | `agent-runtimes/*.yaml: connector.type` (or top-level `type`) | `connector_type` enum; Auto Mode accepts only `local_cli`/`script` (Auto+manual/remote/api/bridge → ERROR); Copilot+manual allowed | Connector impls (Auto phase) | MVP (config); `local_cli`/`script`/`manual` relevant, others stretch |
| **artifact collection** | What artifacts a runtime may produce; declared as WHAT (id/kind/glob/required), not WHERE. | `agent-runtimes/*.yaml: artifacts.collect[]` | id-unique + `glob` present validated; no `source`/`target` (EvidenceCollector decides the path) | `EvidenceCollector` (`auto.py`) archives per-case matches under `evidence/artifacts/<rt>/<case>/` in Auto Mode | MVP (config + render + Auto-Mode harvesting) |
| **state_policy** | How agent state carries across cases: `isolated`/`reset` (Auto v1), `cumulative`/`snapshot_branch`/`replay` declarable. Every value has explicit review semantics. | `experiment.yaml: execution.state_policy` | enum; reset(auto)→pending WARN; cumulative/snapshot_branch/replay(auto)→unimplemented WARN; snapshot_branch+no snapshots→WARN; replay+no evidence→WARN | Enforced by AutoRunner (Auto phase) | MVP (config + semantics); execution stretch |
| **simulator** | Drives the user side of multi-turn cases: `single_turn` (Auto v1), `script`, `role_play` (Copilot/stretch). | `experiment.yaml: simulator.{type,…}`; scaffolded as `single_turn` | `simulator.type` enum; required fields per type; `role_play` under Auto → WARN (not auto-run); rendered in agent-task.md | AutoRunner / Copilot agent (later) | MVP (config + render); script/role_play execution stretch |

## 2. Concepts removed from the public surface, or kept internal only

| Old / candidate concept | Disposition | Replacement / rationale |
|---|---|---|
| **variant** | **Removed from public surface.** | Public object is **harness**. `variant`/`version_id` survive only in retained internal v0.10 modules (e.g. `version.py`), never in v1 scaffolded files or CLI output. |
| **program.md** | **Removed from public surface.** | Replaced by `experiment.yaml` (machine source of truth) + `experiment.md` (human plan). Internal `program.py` parser retained for later-phase reuse. |
| **decision.md / "Decision"** | **Removed.** | Replaced by `conclusion.md` with sections *Human conclusion / Rationale / Evidence relied on / Evidence not trusted / Next step*. |
| **hdl** | **Removed entirely.** | No entry point. `ahl` retained only as a temporary redirect to `hlab`. |
| **harness-packages** | **Not a v1 public concept.** | Not scaffolded, not in CLI, not in templates, not in `experiment.yaml`. Internal `harness_package.py` + its unit tests retained for now; may be removed in a later phase. |

## 3. Notes
- **No inert content.** Every `experiment.yaml` field has a Phase-1 effect — it
  is validated, its value changes review/status output, or it is reflected by
  `hlab status`. Specifically: `collection`/`inspection` are shape-validated,
  their *values* drive review coherence warnings (an inspection check whose
  evidence is disabled by `collection` → WARN), and both are printed by
  `hlab status`; harness `name` and runtime `connector` type are shown by
  `hlab status`; unknown keys WARN wherever they appear — at the **top level**,
  nested under `run`/`execution`/`cases`/`evaluation`/`reports`/`collection`/
  `inspection`, and inside `harnesses`/`agent_runtimes` entries; a dangling
  `goal_ref` WARNs; list-typed fields given a scalar, and non-mapping
  `collection`/`inspection`, ERROR. Nothing is read and silently ignored.
- **Experiment id uniqueness** (schema §4 "unique within workspace") is enforced
  by `hlab new` — the id IS the directory name, so a duplicate id collides and
  errors. `hlab review` is single-experiment in scope and does not scan siblings,
  so a hand-edited duplicate id across two dirs is not caught (accepted Phase-1
  limitation).
- `hlab run` in **Copilot Mode** renders `agent-task.md` (from `experiment.yaml`
  + `experiment.md`) and exits 0 — review-gated, a review ERROR refuses generation.
  `hlab run` in **Auto Mode** and `hlab report` return **exit code 2** and
  explicitly state that no run/evidence/report was produced (see `docs/v1-phase1-status.md`).
