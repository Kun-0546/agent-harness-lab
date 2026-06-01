# Migration Plan: AHL v0.10.0 → Agent Harness Lab v1

> Status: **Reviewed & accepted; Phase 1 + Phase-1 hardening + concept-hygiene pass IMPLEMENTED.**
> Current status of what is built vs deferred: `docs/v1-phase1-status.md` (and CHANGELOG [Unreleased]).
> Phases 2+ (AutoRunner / connectors / EvidenceStore / EvaluationRunner / ReportBuilder /
> CopilotTaskRenderer) have NOT started.
> Source of v1 direction: `docs/claude-code-handoff.md` (the v1 design handoff).
> Author: Claude Code. Date: 2026-05-31.
> This plan is written in English (the v1 design and the open-source target are English);
> current Chinese identifiers/fields are quoted verbatim where they exist in code.

---

## 1. Executive Summary

### 1.1 What v1 is

v1 keeps the existing engine and re-frames it as a clean open-source project for **goal-driven
harness experiments on real Agent Runtimes**:

```
goal → experiment → harness → agent runtime → case → evaluation → evidence → conclusion
```

### 1.2 The shape of the change

This is a **re-skin + re-home + one genuinely new capability**, not a rewrite:

| Dimension | v0.10.0 | v1 | Nature |
|---|---|---|---|
| CLI binary | `ahl` (+ `hdl` redirect) | `hlab` | rename |
| Command surface | 14 visible (+2 hidden redirects) | 6 (`init/new/review/run/status/report`) | **collapse** |
| Public object | "Harness Variant" / `variant` / `Version` / `version_id` (V1/V2) | **`harness`** / `HarnessSpec` / harness id (A/B) | rename (non-negotiable) |
| Experiment source of truth | `program.md` (markdown DSL) | `experiment.yaml` (machine) + `experiment.md` (human) | **replace + split** |
| Run model | simulated only; Auto = "not implemented, exit 2" | **Copilot + Auto (local_cli/script) — both in v1 scope** | **new capability** |
| Evidence | `evidence` = inferred 4-level reproducibility *signal* | `evidence/` = a *store* of run outputs + `issues.jsonl` | **rename + new store** |
| Dependencies | `dependencies = []` (stdlib-only) | YAML SoT pressures this invariant | **decision needed** |

### 1.3 The good news (reuse is high)

- **Auto Mode is cheap to stand up.** `agentconn._SandboxCliSession` (subprocess + line-delimited
  JSON IPC, `shell=False`+`shlex.split`, mandatory `cwd`, env override, per-turn timeout +
  kill-on-hang, stderr-tail capture, daemon reader threads) is already a production-grade
  `local_cli` connector. `materialize/local_path.py` wires it end-to-end. The per-variant
  materialize→start→run→teardown lifecycle (`workflow.run` + `runner.run_experiment`) **is** the
  AutoRunner skeleton.
- **`evidence/issues.jsonl` is where the three retained experiments' failure modes finally get a
  home.** `missing_artifact / empty_output / path_drift / runtime_mismatch / fake_precision /
  scenario_contamination / model_version_mismatch` are exactly the cross-bundle traps from the
  <experiment> / skill-creator / evolution archives. `probe.py` already implements 4 of the 9
  `issue_checks` (one fully, three partially).
- **The evaluation/compare/grader/snapshot/hash core is reusable** with rename + path-repoint.

### 1.4 The three hard forks (need a decision before Phase 1 — see §12)

1. **`experiment.yaml` vs stdlib-only.** The repo is `dependencies = []`. `patch.py` proves a
   hand-rolled YAML-*subset* parser works, but it only handles *flat* `files:/env:/start_command:`.
   `experiment.yaml` needs **nested lists-of-maps** (`harnesses[{id,name,path}]`,
   `agent_runtimes[]`, `evaluation.methods[{type}]`, `inspection.issue_checks[]`). Either extend
   the hand-rolled parser substantially or add a YAML dependency (breaking the zero-dep OSS pitch).
2. **Auto Mode supersedes a v0.10 standing redline.** v0.10 explicitly *did not* implement Auto
   Mode / new runtime source types. v1 puts `local_cli`+`script` Auto in scope. This is a conscious
   reversal that must be confirmed.
3. **`harness-packages/` has no home in the v1 workspace layout** — yet it is the single largest
   test cluster (~1,880 test lines). Keep it as an internal reuse mechanism, or drop it?

---

## 2. Current Repository Inventory

### 2.1 Package / build

- `pyproject.toml`: name `agent-harness-lab`, **version `0.10.0`**, `requires-python >=3.10`,
  **`dependencies = []`** (stdlib-only invariant), `[project.scripts] ahl = "agent_harness_lab.cli:main"`
  (a `hdl` legacy redirect entry also exists).
- **Bug to fix during migration:** `src/agent_harness_lab/__init__.py` `__version__ = "0.1.0"` is
  stale vs `pyproject` `0.10.0`. A `status` command that reports version would report wrong.

### 2.2 Source modules (`src/agent_harness_lab/`, 30 `.py` files)

| Module | LoC | Responsibility |
|---|---|---|
| `cli.py` | 757 | argparse entry (`prog="ahl"`), 14 subcommands + 2 hidden redirects; thin wrappers over `workflow.*` |
| `workflow.py` | 875 | Orchestration: `run/score/compare/review/probe` + preflight + 5 result dataclasses |
| `runner.py` | 101 | Per-(variant,case) execution; `run_agent_session` turn loop |
| `agentconn.py` | 288 | `AgentSession` base + 5 session subclasses; `open_session()` 4-type dispatch; **`_SandboxCliSession` = local_cli ancestor** |
| `connect.py` | 45 | `connect.md` parser; `CONNECT_TYPES` (进程内库/外部命令行/HTTP无状态/HTTP有状态) |
| `runtime_source.py` | 131 | `runtime-sources.md` parser (`local_path`/`git_repo`), strict field whitelist |
| `materialize/__init__.py` | 106 | `RuntimeAdapter` Protocol + `Sandbox`/`MaterializeContext` + `adapter_for()` |
| `materialize/local_path.py` | 156 | `LocalPathAdapter` (copytree+patch+`_SandboxCliSession`) |
| `materialize/git_repo.py` | 226 | `GitRepoAdapter` (clone/checkout+patch+`_SandboxCliSession`) |
| `materialize/legacy.py` | 66 | `LegacyAdapter` (wraps `connect.md`) |
| `version.py` | 102 | **Misnamed**: it is the *harness-variant* parser (`Version`, `parse_version`), not a version module |
| `program.py` | 110 | `program.md` markdown-DSL parser (`Program`, declarations) |
| `rubric.py` | 71 | `rubric.md` parser (`Rubric`/`Dimension`, weight validation) |
| `simulator.py` | 97 | `simulator.md` parser + stub/LLM simulator factory |
| `testset.py` | 80 | `cases/<case>.md` parser (`TestCase`); only 模拟 mode implemented |
| `brief.py` | 89 | Copilot `brief.md` parser (dual-vocab v0.9/v0.3.1) |
| `templates.py` | 399 | All `init`/`new` scaffold templates + 9-step walkthrough text |
| `grader.py` | 130 | `stub_grader` + `llm_grader`, `score_run` weighted aggregation |
| `comparator.py` | 119 | `compare_scores` A/B + linear delta math |
| `evidence.py` | 387 | **v0.4 4-level reproducibility-SIGNAL inference** (strong/medium/weak/unknown) |
| `report.py` | 92 | `build_compare_report` markdown (+ `## Evidence` section) |
| `snapshot.py` | 172 | `RuntimeSnapshot` reproducibility fingerprint per (run×variant) |
| `harness_package.py` | 429 | v0.5 installable harness component (`manifest.md`, hashing, payload install) |
| `patch.py` | 208 | `## Patch` parser — **hand-rolled flat YAML-subset**, path-traversal defense |
| `probe.py` | 645 | v0.6 read-only pre-run inspection — **Inspector ancestor** |
| `hash_utils.py` | 56 | `compute_dir_hash` (deterministic, OS-agnostic) |
| `llm.py` | 52 | stdlib `urllib` OpenAI-compatible `chat()` with retry/backoff |
| `mdutil.py` | 54 | `split_sections` / `parse_frontmatter` (`:`/`：`) / `is_filled` |
| `__main__.py` / `__init__.py` | 7 / 3 | `python -m agent_harness_lab` entry; `__version__` (stale) |

### 2.3 CLI surface (from `cli.build_parser`)

- **14 visible:** `init walkthrough connect new show cases rubric simulator harnesses run score compare review probe`
- **2 hidden redirects:** `versions` → "renamed to harnesses", `draft` → "use new --mode copilot"
- **Entry redirect:** `hdl` → "renamed to ahl"
- **Exit-code conventions:** success `0`; not-found / `WorkflowError` / redirects `1`; `new --mode auto` `2`; `probe` `1` only if a variant FAILs (advisory).

### 2.4 Current workspace / file formats (`docs/file-formats.md`)

```
<workspace>/
├── goal.md                      (init)
├── experiments/<NNN-name>/      (new)
│   ├── program.md  rubric.md  simulator.md            (manual mode)
│   ├── brief.md  materials/README.md                  (copilot mode, default)
│   ├── cases/<case>.md          harnesses/<V>.md
│   ├── patches/<vid>/...
│   ├── results/{run-*.json, score-*.json, compare-*.md, snapshots/<run_id>/<vid>.json}
│   ├── probe-results/<probe_id>/<vid>.json
│   └── materials/{runtime,harness,cloud}-evidence.md
├── connect.md                   (optional, legacy)
├── runtime-sources.md           (optional; local_path/git_repo)
├── harness-packages/<id>/<ver>/{manifest.md, payload/}
└── calibration/golden/          (v2.5 stub)
```

### 2.5 Tests (`tests/`, 31 `test_*.py`, ~522 tests, stdlib `unittest`)

Layered: parser/util units · materialize adapters · snapshot · evidence · probe · workflow
orchestration · CLI · doc/RC guards. Subprocess E2E invoke `python -m agent_harness_lab`.
**Hard-coded coupling that will break:** literal `ahl` token, command-count redlines (assert
EXACTLY 13/14 subcommands), `program.md`-as-source-of-truth, `variant`/`version_id`,
`harness-packages/`. Detailed breakage in §9.

---

## 3. Concept Mapping

| v0.10.0 concept (where) | v1 concept | Disposition |
|---|---|---|
| Harness Variant / `variant` / `Version` / `version_id` (V1/V2) (`version.py`, snapshots, results) | **Harness** / `HarnessSpec` / harness id (A/B) | **rename (non-negotiable)** |
| `runtime_source` / `RuntimeSource` / `runtime-sources.md` | **Agent Runtime** / `AgentRuntimeSpec` (`agent-runtimes/*.yaml`) | adapt + make public/per-experiment |
| `program.md` (markdown DSL, source of truth) | `experiment.yaml` (machine SoT) + `experiment.md` (human plan) | **replace + split** |
| `brief.md` (copilot 12-section working doc) | `experiment.md` (human plan) **+ `agent-task.md` (generated)** | adapt + **new** |
| `rubric.md` + `grader`/`scorer`/`score_run` | `evaluation/` + `EvaluationSpec` + `EvaluationRunner` (3 methods) | adapt + **broaden** |
| `evidence` (v0.4 4-level reproducibility SIGNAL, `evidence.py`) | **reproducibility/provenance signal** (an Inspector finding) | **rename (resolve collision)** |
| — (no current store) | **`evidence/` STORE** (traces/raw/artifacts/snapshots/scores/inspections/`issues.jsonl`) | **new** |
| `results/` (run/score/compare/snapshots) | `evidence/` (raw/traces/snapshots/scores) + `reports/` | restructure |
| `keep/discard` / "decision" / `compare` winner | `conclusion.md` (human) | rename |
| `connect.md` 4 types (进程内库/外部命令行/HTTP无/有状态) | `AgentRuntimeConnector` { `local_cli`, `script`, (`remote_devbox` opt) } | adapt + **narrow** |
| `probe` / `probe-results/` | `Inspector` + `issue_checks` → `evidence/inspections/` + `issues.jsonl` | adapt |
| `harness-packages/` + `manifest.md` (v0.5) | (no v1 workspace equivalent) | **decision: keep-internal or drop** |
| `simulator.md` (人设/背景知识/追问策略) | `cases/simulator.md` | keep (move) |
| `materials/{runtime,harness,cloud}-evidence.md` | `evidence/inspections/` attestation input | adapt (path move) |
| `ahl` / `hdl` | `hlab` | rename |

**Naming answers (handoff §10.1):** `variant → harness` (everywhere public); `runtime → Agent
Runtime` (user-facing) / `AgentRuntimeSpec` (code); `ahl`/`hdl` → `hlab`; `decision → conclusion.md`;
`scorer → evaluation / EvaluationRunner`; `program → experiment` (`experiment.yaml`/`experiment.md`).
The module file `version.py` and class `Version` must be renamed to `harness_spec.py` / `HarnessSpec`
(its docstring already flags this as deferred cleanup).

---

## 4. CLI Mapping

**Answer to handoff §10.2.** v1 exposes **6** human-facing commands; everything else becomes an
internal operation invoked by them (honoring non-negotiable "do not expose every internal operation
as a CLI command").

| v0.10 command | v1 disposition | Notes |
|---|---|---|
| `init` | **keep** (`hlab init`) | Rewrite scaffold: `goal.md` + `evaluation-methods/` + `experiments/` + `.hlab/` |
| `new` | **keep** (`hlab new`) | Scaffold full v1 experiment tree; Auto **no longer exits 2**; emit `experiment.md`+`experiment.yaml`; generate `agent-task.md` |
| `review` | **keep** (`hlab review`) | `ReviewChecker`: harnesses/runtimes/cases/evaluation present; collection complete; Auto connector available when `run.mode=auto` |
| `run` | **keep** (`hlab run`) | Reads `run.mode`: `copilot`→render `agent-task.md`; `auto`→connector executes + collects evidence |
| — | **new** `status` | Experiment status, missing assets, evidence state (reads `experiment.yaml` + `evidence/`) |
| — | **new** `report` | Generate/refresh `reports/report.md` (+ `report.html` stretch); **folds in `compare`** |
| `score` | **internal op** | Becomes `EvaluationRunner`; invoked by `run`/`report`, not a top-level command |
| `compare` | **internal op** | Becomes `ReportBuilder` A/B logic under `report` |
| `probe` | **internal op** | Becomes `Inspector`; invoked by `review`/`run`; writes `evidence/inspections/` + `issues.jsonl` |
| `show` / `cases` / `rubric` / `simulator` / `harnesses` | **demote** | Inspect-only helpers → fold into `status` (or a hidden `--debug`); not public commands |
| `connect` | **remove/fold** | Runtime binding moves to `agent-runtimes/*.yaml`; checked by `review` |
| `walkthrough` | **remove** | Becomes help text / README; not a command |
| `versions` (hidden) / `draft` (hidden) | **remove** | Legacy redirects retired |
| `hdl` entry | **rename** | `hlab`; keep an `ahl → hlab` redirect for one release (BC, non-negotiable) |

**Command-count redline reversal:** `test_harness_package_integration` / `test_evidence_integration`
/ `test_probe_integration` currently assert EXACTLY 13/14 subcommands and *forbid*
`package/install/auto/...`. These must be **rewritten** to assert the 6-command surface (see §9).

---

## 5. Directory and File Mapping

**Answer to handoff §10.3.** Current experiment dir → v1 experiment dir:

| v0.10 path | v1 path | Disposition |
|---|---|---|
| `goal.md` | `goal.md` | keep |
| — | `evaluation-methods/{human_annotation,llm_judge,benchmark}.md` | **new** (workspace-level) |
| — | `.hlab/` | **new** (tool state) |
| `experiments/<NNN-name>/` | `experiments/<name>/` | keep (numbering optional) |
| `program.md` | `experiment.yaml` (machine) **+** `experiment.md` (human) | **replace + split** |
| `brief.md` (copilot) | `experiment.md` + generated `agent-task.md` | adapt + new |
| `harnesses/<V>.md` (one md per variant) | `harnesses/<A|B>/` (one dir per harness) | restructure + rename |
| inline `类型`/`配置` / `runtime_source` / `connect.md` | `agent-runtimes/*.yaml` | **extract** runtime binding out of harness |
| `runtime-sources.md` (workspace md) | `experiments/<name>/agent-runtimes/*.yaml` (per-experiment) | adapt + relocate + reformat |
| `cases/<case>.md` (md per case) | `cases/cases.jsonl` (+ `datasets/`) | reformat (md → JSONL, stdlib `json`) |
| `simulator.md` | `cases/simulator.md` | move |
| `rubric.md` | `evaluation/rubrics/` + `evaluation/evaluation.md` | move + extend |
| — | `evaluation/{graders/,benchmarks/}` | new |
| `results/run-*.json` (transcripts) | `evidence/traces/` + `evidence/raw/` | restructure |
| `results/score-*.json` | `evidence/scores/` | move |
| `results/snapshots/<run>/<vid>.json` | `evidence/snapshots/` | move (+ `variant_id`→harness id) |
| `probe-results/<probe_id>/<vid>.json` | `evidence/inspections/` | move |
| — | `evidence/artifacts/` (skills, memory, PDFs, outputs) | **new** |
| — | `evidence/issues.jsonl` | **new** |
| `results/compare-*.md` | `reports/report.md` (+ `report.html`) | move + rename |
| `materials/*-evidence.md` | `evidence/inspections/` (attestation input) | adapt |
| `harness-packages/` (workspace) | (no v1 home) | **decision (§12)** |
| `calibration/golden/` | TBD (keep workspace-level) | carry forward |
| (keep/discard outcome) | `conclusion.md` | new (human) |

**Backwards-compat (non-negotiable):** every experiment on disk today has `program.md` +
`harnesses/V*.md`, not `experiment.yaml`. v1 needs a one-way **migration converter** (or a
deprecated read-path) before any deletion of the `program.md` path.

---

## 6. Schema and Data Model Changes

### 6.1 `experiment.yaml` — the new machine source of truth

Target fields (handoff §7): `id, status, goal_ref, question, run.mode(copilot|auto),
execution{mode:ab, state_policy:isolated}, harnesses[{id,name,path}], agent_runtimes[{id,harness,spec}],
cases{root,files[]}, evaluation{methods[{type}]}, collection{traces,raw,artifacts,snapshots,scores},
inspection{artifact_review,skill_review,memory_review,context_review,issue_checks[]}, reports{formats[]}`.

Mapping from `program.md` declarations (`program.py`):

| `program.md` field | `experiment.yaml` field | Note |
|---|---|---|
| 假设 (assumption) | `question` / `goal_ref` | |
| 声明.对话模式 (模拟/回放/固定) | `run` + `cases`/simulator semantics | |
| 声明.运行模式 (人评/自迭代) | `run.mode` (copilot / auto) | **inference** — needs confirmation (§12) |
| 声明.对比方式 (对基线/线性迭代) | `execution.mode` (ab) / comparison | linear-iteration may need a yaml field |
| 声明.状态 (累积/重置) | `execution.state_policy` (isolated/...) | currently descriptive-only |
| 声明.环境 | `agent_runtimes` | currently descriptive-only |

> **`DECLARATION_STATUS` warning:** half of `program.md` is descriptive-only today (环境/状态/运行模式
> = "暂未接线"). `experiment.yaml` would be the **first real wiring** for these — specifying yaml
> fields whose execution semantics don't yet exist is itself a `fake_precision` risk.

### 6.2 The YAML parsing decision (the central schema fork)

- The repo is **stdlib-only** (`dependencies = []`).
- `patch.py:parse_patch` and `harness_package._parse_payload_section` hand-roll a YAML-*subset*
  parser — but only **flat** `files:/env:/start_command:` with simple `- ` list items.
- `experiment.yaml` requires **nested lists-of-maps** (`harnesses[{id,name,path}]`,
  `agent_runtimes[{id,harness,spec}]`, `evaluation.methods[{type}]`, `inspection.issue_checks[]`).
- **Two options (recommend deciding in Phase 0):**
  - **(A) Extend the hand-rolled parser** into a small dedicated `stdlib yaml-subset` module
    (generalize `parse_frontmatter` + `parse_patch`). Preserves zero-dep OSS positioning; risk =
    fragile at depth (no anchors/multiline/type coercion).
  - **(B) Add PyYAML** as the first dependency. Robust; breaks the `dependencies = []` invariant
    and the "stdlib-only" story.
- **`cases.jsonl` needs no YAML** — stdlib `json` handles JSONL trivially.

### 6.3 Other schema changes

- `harnesses/V*.md` (conflates harness design + runtime binding) → split: harness design →
  `harnesses/<A|B>/`; runtime binding → `agent-runtimes/*.yaml`. Keep the `## Patch` sub-structure
  (`patch.py`) as harness material.
- `cases/<case>.md` (frontmatter `id/type/max_turns/depends_on` + 起始输入/完成标准) →
  `cases.jsonl` records (`opening`→`input`, `criterion`→`expected`/rubric ref). `depends_on` is a
  documented no-op today — decide keep-and-implement or drop (carrying it perpetuates fake-precision).
- `snapshot.RuntimeSnapshot` schema reusable for `evidence/snapshots/` with: (a) path move
  `results/snapshots/` → `evidence/snapshots/`; (b) field `variant_id` → harness id; (c) the
  `snapshot_id` format `"snap-<run_id>-<variant_id>"` is an on-disk contract — renaming breaks
  fingerprint continuity → needs a migration shim, not a silent break.

---

## 7. Execution Model Changes

**Mapping the 17 v1 execution objects (handoff §6) to current code:**

| v1 object | Current ancestor | Disposition | Reuse note |
|---|---|---|---|
| `ExperimentSpec` | `program.py:Program` + scattered fields | **new** (unify) | no single spec object exists today |
| `HarnessSpec` | `version.py:Version` (+`patch.py`) | adapt + rename | split runtime binding out |
| `AgentRuntimeSpec` | `runtime_source.py:RuntimeSource` | adapt | cleanest existing spec parser; flip md→yaml |
| `CaseSet` | `testset.py:TestCase`/`load_testset` | adapt | md → `cases.jsonl` |
| `EvaluationSpec` | `rubric.py` (+ implicit grader choice) | adapt + **broaden** | must cover 3 methods, not just llm_judge |
| `RunPlan` | `MaterializeContext` + `run.mode` | adapt | run_id+experiment_dir+sources context |
| `AgentRuntimeConnector` | `agentconn._SandboxCliSession` (+ `materialize/*`) | **adapt** | **`local_cli` ≈ verbatim**; `script` = thin new |
| `AutoRunner` | `workflow.run` + `runner.run_experiment` lifecycle | adapt | materialize→start→run→teardown reusable |
| `CopilotTaskRenderer` (`agent-task.md`) | — (zero existing code) | **new** | rendered FROM `experiment.yaml` |
| `EvidenceCollector` | `hash_utils` + `snapshot.build_snapshot` | adapt | + capture transcripts/raw/artifacts |
| `EvidenceStore` | `results/` writers + `snapshot.write_snapshot` | adapt | repoint to `evidence/` |
| `IssueStore` (`issues.jsonl`) | — (no JSONL issue log) | **new** | append-only typed issues |
| `Inspector` | `probe.py` | adapt | read-only checks → typed issues |
| `EvaluationRunner` | `grader.py:score_run` + `llm_grader` | adapt + broaden | unify over `methods[]` |
| `ReportBuilder` | `report.py` + `comparator.py` | adapt | **add HTML** output |
| `ReviewChecker` | `workflow.review` + `validate()` pattern | adapt | check vs `experiment.yaml` |
| (LLM client) | `llm.py:chat` | **keep** | stdlib urllib, reuse verbatim |

### 7.1 Auto Mode feasibility (handoff §10.4) — the smallest useful Auto Mode

**LOW effort.** `_SandboxCliSession` already does the right things (shell-safe, cwd, env override,
600 s per-turn timeout + `proc.kill` on hang, stderr tail, daemon reader threads). `LocalPathAdapter`
wires copytree→patch→start. The smallest useful Auto Mode:

> Expose **one** connector = `local_cli`, backed by `_SandboxCliSession` over a `local_path`
> Agent Runtime (the `LocalPathAdapter` pipeline). That alone gives a runnable Auto Mode: copy a
> runtime dir → apply harness patch → launch a local CLI agent over line-JSON → capture transcript
> + snapshot. **No new IPC, no new lifecycle, no universal connector.**

`script` connector = a thin second step: run a user-supplied setup/invoke script via the same
`subprocess.run(shell=False, check=True, capture_output=True)` pattern in `git_repo.py`, reusing the
existing exit-code→error translation. **Its exact contract is unspecified and must be designed**
(§12). `remote_devbox` stays optional/M3.

**Wire-protocol caveat:** the `{"input": ...}` / `{"response": ...}` line-JSON contract is implicit
and unversioned; an Auto `local_cli` agent must speak it exactly or it surfaces only as a 600 s hang
→ kill. v1 should document it (and consider whether it stays the contract — §12).

### 7.2 Copilot Mode (handoff §10.5) — `agent-task.md` generation

- `agent-task.md` is **entirely new** (grep confirms zero `agent-task`/`CopilotTask`/`TaskRenderer`
  matches). It is **rendered from `experiment.yaml`** for an external coding agent.
- Reusable inputs: `brief.py` (12-section copilot working doc → `experiment.md`), `templates.py`
  scaffolds, the existing copilot examples (`examples/copilot-setup-example/`,
  `expected-coding-agent-plan.md`). The render itself is new (string-templating from the parsed
  `ExperimentSpec`).
- **Model distinction to preserve:** today's `brief.md` is human/agent co-edited; `agent-task.md`
  is machine-rendered. Don't lose the co-editable working-doc affordance (§12).

### 7.3 Execution-isolation note

`execution.state_policy: isolated` in `experiment.yaml` may require **per-(harness,case) sandboxes**,
which conflicts with the current **per-variant-materialize-once, cross-case sandbox reuse**
(`runner.run_experiment`). Decide whether isolated forces per-case materialization (§12).

---

## 8. Evidence Model Changes

### 8.1 The terminology collision (must resolve first)

- **v0.4 `evidence`** (`evidence.py`, `report.py` `## Evidence`) = an **inferred reproducibility
  SIGNAL**, 4 levels (strong/medium/weak/unknown), derived from snapshots + `materials/*-evidence.md`
  existence.
- **v1 `evidence/`** = a **STORE** of actual run outputs.

These are different concepts sharing a word. **Recommendation:** rename the v0.4 concept to
**reproducibility level / provenance signal** (an `Inspector` finding, surfaced under
`evidence/inspections/` and in a renamed report section), and reserve `evidence/` for the store.

### 8.2 v1 evidence store layout + ancestors

| `evidence/` subdir | Current ancestor | Disposition |
|---|---|---|
| `traces/` | `results/run-*.json` transcripts | restructure (simplified jsonl) |
| `raw/` | `results/run-*.json` raw / stderr tails | restructure |
| `artifacts/` | — (none) | **new** (skills/memory/PDFs/outputs) |
| `snapshots/` | `results/snapshots/*` (`snapshot.py`) | move + rename field |
| `scores/` | `results/score-*.json` | move |
| `inspections/` | `probe-results/*` + `materials/*-evidence.md` | move |
| `issues.jsonl` | — (none) | **new** (typed append-only) |

### 8.3 `issues.jsonl` — issue types and their ancestors (handoff §8, §10.6)

> **Note (shipped vs analysis):** the table below is the *broad analysis* from
> handoff §8. The **authoritative `inspection.issue_checks` enum that Phase 1
> validates** is the 8-value set in `docs/experiment-yaml-schema.md` §16:
> `missing_artifact, empty_output, path_drift, runtime_mismatch, missing_trace,
> missing_score, case_failure, connector_failure`. The extra analysis names
> here (`fake_precision`, `scenario_contamination`, `model_version_mismatch`,
> `scorer_missed_evidence`, `connection_check_failure`) are candidate future
> checks, not part of the v1 enum.

| Issue type | Ancestor in v0.10 | Build |
|---|---|---|
| `missing_artifact` | `probe._probe_local_path` missing source + `payload_files_missing` | **FULL** — rewire to emit issue |
| `empty_output` | `git ls-remote` empty-stdout check; smoke stdout (not asserted) | **PARTIAL** — add empty-check on traces/raw |
| `path_drift` | `_safe_target_path`/`_safe_source_path` traversal defense (resolve+relative_to) | **PARTIAL** — flip from block to detect |
| `runtime_mismatch` | `runtime_compatibility` check; source-not-found | **PARTIAL** — add declared-vs-observed compare |
| `connection_check_failure` | `_probe_git_repo`/`_execute_smoke` failure; turn-timeout `proc.kill` RuntimeError | **PARTIAL** — persist as structured issue |
| `model_version_mismatch` | (only `snapshot.environment` metadata) | **new** |
| `scorer_missed_evidence` | — | **new** (eval-side) |
| `fake_precision` | — (this is the exact skill-creator trap) | **new** (eval-side) |
| `scenario_contamination` | teardown leaks are silently swallowed today | **new** |

> This is the migration's highest-value addition: `issues.jsonl` operationalizes the failure modes
> the three retained experiments kept hitting (fake-precision on 0-byte outputs, path drift,
> baseline/scenario contamination, silent all-0 runs). `EvidenceCollector` should wrap
> `adapter.start()`/`session.send()` to capture `connection_check_failure`, and the eval path
> (`grader`) should emit `scorer_missed_evidence`/`fake_precision`.

### 8.4 `collection{}` / `inspection{}` config

`experiment.yaml` `collection{traces,raw,artifacts,snapshots,scores}` and
`inspection{artifact_review,skill_review,memory_review,context_review,issue_checks[]}` are **new
machine config** with no current equivalent (today collection is implicit and inspection is the
`probe` aspects). These drive `EvidenceCollector` and `Inspector`.

---

## 9. Tests to Update or Add

**Non-negotiable: do not skip tests.** ~522 tests across 31 files; `unittest`. Strategy: rename,
re-home, rewrite redlines; never delete coverage silently.

### 9.1 What breaks and why

| Test file(s) | Breaks under | Action |
|---|---|---|
| `test_harness_package_integration` / `test_evidence_integration` / `test_probe_integration` | **command-count redlines** (assert 13/14 subcommands) | **rewrite** to assert 6-command `hlab` surface |
| `test_*_e2e` / `test_sample_workspace_e2e` / `test_readme_command_flow` / `test_copilot_templates` | literal **`ahl`** token + `python -m agent_harness_lab` + command anchors | rename `ahl`→`hlab`, repoint module |
| `test_parsers` / `test_e2e` / `test_workflow` / `test_cmd_*` | **`program.md` as source of truth**, `变体`/`version_id`, walkthrough/draft | rewrite to `experiment.yaml` + harness vocab |
| `test_materialize_*` / `test_snapshot` / `test_probe` | `variant_id` / `Version` fixtures; `results/snapshots/` path | rename + repoint to `evidence/snapshots/` |
| `test_evidence` (524) / `test_report` | "evidence" semantic shift; `## Evidence` section rename | **re-home** as reproducibility-signal/Inspector tests |
| `test_runtime_source` | markdown `runtime-sources.md` format | keep validation intent; flip fixture to YAML |
| `test_harness_package*` (845+382+654) | `harness-packages/` not in v1 layout | **decision (§12)** — re-scope or retire |
| `test_cmd_walkthrough` / `test_cmd_draft_redirect` | commands removed | retire |
| `test_release_candidate` / `test_doc_consistency` | CHANGELOG/version/anchor/required-spec lists | update lists, mostly portable |

### 9.2 What is safely reusable

`test_agentconn` (the `local_cli` substrate), `test_hash_utils`, `test_mdutil`, `test_patch`,
`test_comparator` — pure units that survive with at most a rename.

### 9.3 Tests to ADD (handoff §10.7)

`workspace init` · `experiment creation` · **`experiment.yaml` parsing** (`ExperimentSpec`) ·
`harness loading` (`HarnessSpec`) · **`AgentRuntimeSpec` loading** · `review checks` (`ReviewChecker`)
· **`agent-task.md` generation** (`CopilotTaskRenderer`) · **Auto `local_cli`/`script` execution** ·
`EvidenceCollector` output · **`IssueInspector`** (each of the 9 issue types) · `report` generation
(md + html) · **example validity** (v1 sample workspace runs end-to-end).

---

## 10. Implementation Phases

**Phase 0 (NEW — before any code): Decision lock + spec.** Resolve §12 forks (YAML strategy;
Auto-redline reversal; harness-packages disposition; repo/package rename; versioning/branch). Write
the v1 `experiment.yaml` schema spec + connector contract. **Gate: Kun sign-off.**

Then (handoff §13, refined with dependencies):

| Phase | Scope | Depends on | Key risk |
|---|---|---|---|
| 1 | Naming + CLI migration to `hlab` (binary, package?, `variant→harness`, `ahl→hlab` redirect) | P0 | snapshot_id BC; redline tests |
| 2 | New experiment directory structure + templates (`init`/`new` scaffolds) | P1 | program.md BC converter |
| 3 | `experiment.yaml` schema + parser (`ExperimentSpec`) | P0 (YAML decision), P2 | nested YAML parse |
| 4 | Copilot Mode `agent-task.md` generation (`CopilotTaskRenderer`) | P3 | new artifact, no ancestor |
| 5 | `EvidenceStore` + `IssueStore` (`evidence/` + `issues.jsonl`) | P2, P3 | evidence terminology |
| 6 | Auto Mode `local_cli`/`script` connector (`AutoRunner`) | P3, P5 | protocol contract; isolation policy |
| 7 | `EvaluationRunner` + basic `Inspector` (3 methods; 9 issue checks) | P5, P6 | human_annotation/benchmark scoring |
| 8 | `ReportBuilder` (`report.md` + `report.html`) | P5, P7 | HTML output is net-new |
| 9 | Example migration + open-source cleanup (credential/path hygiene; version surface fix; EN docs) | all | hardcoded paths/keys |

Each phase keeps the suite green (incrementally rewriting redlines in lockstep, §9).

---

## 11. Risks

1. **YAML vs stdlib-only.** Nested `experiment.yaml` exceeds the hand-rolled parser's flat capability;
   extending it is fragile, adding PyYAML breaks `dependencies = []`. (§6.2, §12)
2. **Command-count redline breakage.** Three integration suites hard-assert 13/14 subcommands and
   forbid extra commands; the 14→6 collapse fails them until rewritten. (§9.1)
3. **`variant`→`harness` rename touches on-disk contracts.** `snapshot_id` format
   `"snap-<run>-<variant_id>"`, `results/*.json`, and `snapshots/*.json` key on `version_id`;
   rename needs a migration shim (non-negotiable: don't break BC before mapping impact).
4. **Evidence terminology collision.** Shipping the v0.4 reproducibility *signal* and the v1 *store*
   both as "evidence" will confuse users and code. Must rename the signal. (§8.1)
5. **`program.md` → `experiment.yaml` source-of-truth shift.** Every consumer of
   `parse_program().declarations` (`testset.load_testset` reads 对话模式; `workflow` reads run_mode)
   must be rewired; all on-disk experiments need a converter.
6. **Auto Mode reverses a v0.10 redline** and introduces an implicit, unversioned wire protocol.
7. **`harness-packages/` (largest test cluster) has no v1 home** — silent drop loses ~1,880 test
   lines and BC.
8. **Half of `program.md` is descriptive-only** (`DECLARATION_STATUS` 暂未接线). Promoting those to
   `experiment.yaml` fields without real execution semantics is itself `fake_precision`.
9. **Chinese-vocabulary remap is semantic, not cosmetic.** 自迭代→`auto`, 人评→`copilot`,
   模拟/回放/固定, 对基线/线性迭代, 基线 frontmatter, all `validate()` messages — mistranslation
   silently changes behavior.
10. **3-method evaluation gap.** Only `llm_judge` exists; `human_annotation` and `benchmark` runners,
    and a score representation for non-numeric benchmark results, are net-new (compare math assumes
    per-dimension 1–10).
11. **HTML report is net-new** (`report.py` is markdown-only).
12. **Credential/path hygiene for OSS:** stale `__version__="0.1.0"`; (from the broader lineage)
    hardcoded paths/keys in adjacent grader scripts — clean before any public flip.

---

## 12. Open Questions (need a decision before Phase 1)

1. **YAML strategy:** extend the hand-rolled stdlib subset parser, or add PyYAML (first dependency)?
   This gates `ExperimentSpec`/`AgentRuntimeSpec` and the "zero-dep OSS" positioning.
2. **Redline reversals to confirm:** Auto Mode in v1 scope (yes per handoff); 14→6 command surface;
   possible loss of stdlib-only. Which v0.10 standing redlines does v1 consciously supersede?
3. **`harness-packages/`:** keep as an internal reuse mechanism (re-scope its tests) or drop it?
4. **`program.md` backward-compat:** ship a deprecated read-path / one-way converter, or hard-cut at
   a major version? (Non-negotiable: map impact before deleting.)
5. **`agent-task.md`:** one-shot machine-rendered artifact, or co-editable like today's `brief.md`?
   (Determines whether `brief.py`'s dual-vocab parse survives.)
6. **`local_cli` protocol:** keep the `{"input"}`/`{"response"}` line-JSON contract, or define a
   richer (tool-calls/structured-turns) protocol? (Determines verbatim reuse of `_SandboxCliSession`.)
7. **`script` connector contract:** what does it do — setup/build step, or a wrapper invoking a
   non-JSON CLI? (No ancestor; must be designed.)
8. **Isolation:** does `execution.state_policy: isolated` force per-(harness,case) sandboxes
   (vs current cross-case reuse)?
9. **Non-`llm_judge` methods:** how are `benchmark` (pass/fail/task-success) and `human_annotation`
   scored and compared, given `comparator` assumes per-dimension 1–10?
10. **Repo/package rename:** `agent_harness_lab` package → `hlab`? GitHub repo rename? `ahl`→`hlab`
    redirect retention window?
11. **Versioning / branch:** is this a `v1.x` line that breaks the v0.10 OSS-freeze posture? New
    branch + tag strategy? (Repo is PRIVATE; this also intersects the post-v0.10 public-flip GO.)
12. **Linear-iteration compare:** does v1 keep both `对基线`/baseline and `线性迭代`/linear (needs a
    yaml field), or only `execution.mode: ab`?

---

*End of migration plan. This plan was reviewed and accepted; Phase 1 has since been
implemented and hardened (see `docs/v1-phase1-status.md` + CHANGELOG [Unreleased]). Later
phases have not started.*
