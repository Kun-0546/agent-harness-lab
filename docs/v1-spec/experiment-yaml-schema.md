# experiment.yaml Schema

## 1. Purpose

`experiment.yaml` is the machine-readable source of truth for an AHL experiment.

It creates `ExperimentSpec`.

AHL should use this file for:

```text
review checks
Copilot agent-task generation
Auto Mode execution
evidence collection
report generation
status tracking
```

## 2. Top-level Fields

```yaml
id: skill-creator-ab
status: draft

goal_ref: ../../goal.md
question: "Compare our skill creator harness with Anthropic skill creator harness on OpenClaw."

run:
  mode: auto

execution:
  mode: ab
  state_policy: isolated

harnesses: []
agent_runtimes: {}
cases: {}
evaluation: {}
collection: {}
inspection: {}
reports: {}
```

## 3. Required Fields

```text
id
status
question
run.mode
execution.mode
harnesses
agent_runtimes
cases.root
evaluation.root
collection
reports.formats
```

## 4. id

Stable experiment identifier.

Rules:

```text
lowercase
kebab-case
unique within workspace
```

Example:

```yaml
id: skill-creator-ab
```

## 5. status

Allowed values:

```text
draft
ready
running
collected
evaluated
reported
concluded
invalid
```

## 6. goal_ref

Relative path to workspace goal.

Example:

```yaml
goal_ref: ../../goal.md
```

## 7. question

Human-readable experiment question.

Example:

```yaml
question: "Compare harness A and harness B on reusable skill creation quality."
```

## 8. run

Defines who executes.

Allowed values:

```text
copilot
auto
```

Example:

```yaml
run:
  mode: copilot
```

## 9. execution

Defines how experiment cases are organized.

Allowed `execution.mode`:

```text
ab
sequential
longitudinal
replay
```

Allowed `state_policy`:

```text
isolated
reset
cumulative
snapshot_branch
replay
```

Example:

```yaml
execution:
  mode: ab
  state_policy: isolated
```

Auto Mode v1 must support:

```text
isolated
reset
```

Other state policies may be expressible before fully implemented. Every value has
explicit review semantics (none is an inert enum):

```text
isolated         each case/harness run is independent — fully supported, no extra config
reset            runtime reused, fresh process before each run (no in-process state carries);
                 IMPLEMENTED in Auto — AutoRunner restarts the local_cli session per case, and
                 the script connector is already a fresh process per case
cumulative       state persists across cases; Auto -> auto_state_policy_unimplemented WARN
snapshot_branch  branch from a shared snapshot; Auto -> auto_state_policy_unimplemented WARN;
                 + collection.snapshots off -> snapshots_not_collected WARN
replay           do not rerun the runtime; evaluate existing evidence; no evidence -> replay_no_evidence WARN
```

Under a multi-turn simulator (v1.1) the isolation unit of `isolated` is the
**case**, not the send — see [`execution-model.md`](execution-model.md) §14.2.
Single-turn semantics are unchanged.

### execution.trials / execution.aggregation (v1.1)

v1.1 adds two optional keys to `execution`. All defaults preserve current
behavior — existing experiments need zero migration.

```yaml
execution:
  mode: ab
  state_policy: isolated
  trials: 3                             # repeat-run count; default 1
  aggregation: [mean, stddev, win_rate] # statistics for compare/report
```

- `trials` — how many times the run is repeated. The repeat count is part of
  the **experiment design**, so it lives in `experiment.yaml`; `hlab run
  --trials N` is only a temporary override, and the override fact is recorded
  in evidence/run-metadata.json when the override differs from the config
  value. A single trial's A/B winner is not a conclusion.
  - Default: `1` (one run). Positive integers only; zero or negative → review
    `bad_trials` ERROR.
- `aggregation` — which statistics the comparison report computes across
  trials; a subset of `mean / stddev / min_max / median / win_rate`, default
  `[mean, stddev, win_rate]`. Reports state the trial count alongside.
  - Unknown entries → review `bad_aggregation` ERROR.

**Re-run semantics (PR5 5a):** without `--fresh`, each `hlab run` appends
evidence as a new trial number (old evidence is immutable, same contract as
PR4's read-only evidence iron law). `hlab run --fresh` wipes evidence/ before
running — the only sanctioned destruction; starts a clean trial-0 run.

**Evidence layout:** trace records in `evidence/traces/<runtime>.jsonl`
accumulate across trials. Trial-0 records carry no `trial` field (byte-for-byte
identical to pre-v1.1 single-trial records). Trial N ≥ 1 records carry
`trial: N`. Raw outputs for trial ≥ 1 go under
`evidence/raw/trials/<N>/<runtime>/` (trial-0 paths are unchanged). Issue
records in `evidence/issues.jsonl` follow the same convention: trial-0 issues
carry no `trial` field; trial N ≥ 1 issues carry `trial: N`. Score records in
`evidence/scores/<track>/<evaluator>.jsonl` are also trial-scoped: trial-0
score records carry no `trial` field; trial N ≥ 1 score records carry `trial: N`.

**Trial read scope:** `hlab eval` and inline evaluation after `hlab run` both
default to the **latest** trial (global maximum across all trace files). `hlab
eval --trial N` re-evaluates a specific historical trial. Requesting a
nonexistent trial exits 1 with `HLAB_MISSING_EVIDENCE` and writes nothing.

**Per-trial scoring:** `hlab run` with `trials: N > 1` evaluates inline after
each trial so that score records exist for every trial. `hlab compare`'s
`trial_count` is derived from score records actually present (not from traces)
to avoid overstating when only some trials were scored. Aggregation stats
(stddev, win_rate) are computed over real per-trial score vectors.

**Cost guardrail:** a multi-turn LLM-simulated run makes on the order of
`runtimes × cases × max_turns × trials` model calls — try a small scale first
(e.g. 1 runtime × 1–3 cases × low max_turns × 2–3 trials to estimate cost
before committing to a full run).

## 10. harnesses

List of compared harnesses.

Example:

```yaml
harnesses:
  - id: A
    name: our-skill-creator
    path: harnesses/A/
  - id: B
    name: anthropic-skill-creator
    path: harnesses/B/
```

Required per harness:

```text
id
name
path
```

## 11. agent_runtimes

List of Agent Runtime bindings.

Example:

```yaml
agent_runtimes:
  - id: runtime-a
    harness: A
    spec: agent-runtimes/runtime-a.yaml
  - id: runtime-b
    harness: B
    spec: agent-runtimes/runtime-b.yaml
```

Required per runtime:

```text
id
harness
spec
```

## 12. Agent Runtime Spec

Each runtime spec declares how AHL drives the runtime and what artifacts it may
produce:

```yaml
id: runtime-a

connector:
  type: local_cli             # Auto v1: local_cli | script. Copilot: manual.
  command: "python run_agent.py"
  working_dir: "./runtime-a"  # relative to the experiment dir
  input_mode: stdin_json      # one JSON object per line on stdin/stdout
  timeout: 60                 # per-turn seconds before a connector failure

artifacts:
  collect:
    - id: generated_skill
      kind: skill
      glob: "outputs/skill/**"   # relative to connector.working_dir
      required: true             # a missing required artifact becomes an evidence issue
```

`input_mode: stdin_json` per-turn contract:

```text
stdin  (per turn):  {"input": "<user text>"}
stdout (per turn):  {"response": "<agent reply>"}
```

Connector types and support boundary:

```text
local_cli                      Auto Mode v1 — supported
script                         Auto Mode v1 — supported
manual                         Copilot Mode (an external agent drives it); Auto + manual -> ERROR
remote_devbox / api / bridge   declarable, reserved (not executed in v1); Auto + these -> ERROR
```

Artifact collection declares WHAT the runtime may produce (`id` / `kind` / `glob`
/ `required`), not WHERE it is stored. AHL's EvidenceCollector archives matches
under `evidence/artifacts/<runtime>/`. There is **no `source`/`target`** in the
runtime spec. `glob` is relative to `connector.working_dir`; artifact ids must be
unique within a runtime.

### 12a. Agent Runtime Spec — `source:` section (PR6, v1.1)

The optional `source:` section declares where AHL should materialize the runtime's
working directory before dispatch. When present, AHL copies/clones the source into
`experiments/<exp>/sandbox/<runtime_id>/` and redirects `connector.working_dir` to
that sandbox for all dispatch. A snapshot is written to `evidence/snapshots/<runtime_id>.json`
recording source fingerprints (source_dir_hash, commit_sha, patch_hash) for
reproducibility evidence. Experiments without `source:` behave byte-identically to
today — all new behavior is opt-in.

#### source.type: local_path

Copy a local directory into the sandbox before dispatch.

```yaml
source:
  type: local_path
  path: ../../shared/my-agent   # relative to experiment dir, or absolute

  # Optional patch applied after copy:
  patch:
    files:
      - target: prompts/system.md      # relative to sandbox root
        source: patches/v2/system.md   # relative to experiment dir
    env:
      MY_PROMPT_VERSION: "v2"
```

Required fields: `path`.
The `patch:` sub-section is optional for all source types.

#### source.type: git_repo

Clone a git repository and check out a ref (branch / tag / commit SHA) into the sandbox.

```yaml
source:
  type: git_repo
  url: https://github.com/org/agent.git
  ref: v1.2.0                  # branch, tag, or full commit SHA

  patch:
    files:
      - target: config/tools.yaml
        source: patches/prod/tools.yaml
    env:
      AGENT_MODE: prod
```

Required fields: `url`, `ref`.
A local `file:///path/to/repo` URL also works (used in tests; no network required).

#### source.type: harness_package

Install a local harness package directory into the sandbox. Optionally verify a
3-hash fingerprint before installing (manifest_hash, payload_hash).

```yaml
source:
  type: harness_package
  path: ../../harness-packages/my-harness/1.0.0

  expected_fingerprint:
    manifest_hash: sha256:<64 hex>
    payload_hash: sha256:<64 hex>

  patch:
    env:
      HP_OVERRIDE: "true"
```

Required fields: `path`.
`expected_fingerprint` is optional but strongly recommended — a hash mismatch
causes a `connector_failure` issue (exit 3) rather than silently running with
a modified package.

#### source: review codes

| Code | Level | Trigger |
|------|-------|---------|
| `runtime_spec_invalid` | ERROR | `source.type` is not `local_path`, `git_repo`, or `harness_package` |
| `runtime_spec_invalid` | ERROR | Required fields missing for the declared `source.type` |
| `runtime_spec_invalid` | ERROR | `source.patch.files` entries missing `target` or `source` |

Existence checks (does the path/URL exist?) are deferred to `hlab review` probe
phase (PR8) — the schema parser validates shape only.

#### patch: env semantics

Env vars declared in `source.patch.env` are applied only to the connector subprocess
for that runtime. They do not affect other runtimes or the parent `hlab` process.

## 13. cases

Example:

```yaml
cases:
  root: cases/
  files:
    - cases.jsonl
```

Case file format should be JSONL.

Minimum fields:

```json
{"id":"case-001","input":"Create a reusable reporting skill.","tags":["skill"]}
```

Recommended fields:

```text
id
input
tags
metadata
expected_artifacts
```

## 14. evaluation

Evaluation has three layers:

1. **Evaluation Method** — workspace-level reusable recipe in `evaluation-methods/`:
   `human_annotation`, `llm_judge`, `benchmark`, `llm_rubric`.
2. **Evaluator Instance** — experiment-local configured evaluator
   (`evaluation.evaluators`): binds a method to a concrete `script` (benchmark) or
   `rubric` (llm_judge / human_annotation / llm_rubric).
3. **Evaluation Track** — experiment-local grouping (`evaluation.tracks`): groups
   evaluators around a question and names the evidence each needs. Tracks are
   experiment-local and do NOT replace evidence.

```yaml
evaluation:
  root: evaluation/
  evaluators:
    - id: artifact_exists
      method: benchmark
      script: benchmarks/check_artifact_exists.py   # relative to evaluation.root
    - id: skill_quality
      method: llm_judge
      rubric: rubrics/skill_quality.md
    - id: human_skill_review
      method: human_annotation
      rubric: rubrics/human_skill_review.md
    - id: multi_dim_quality
      method: llm_rubric
      rubric: rubrics/quality_rubric.md             # must contain a dimensions+weights table
  tracks:
    - id: skill-artifact
      question: "Did the harness produce a usable skill artifact?"
      evaluators: [artifact_exists, skill_quality, human_skill_review, multi_dim_quality]
      evidence: [artifacts, traces, raw]
```

Allowed evaluator methods: `human_annotation`, `llm_judge`, `benchmark`, `llm_rubric`.
Allowed track evidence types: `traces`, `raw`, `artifacts`, `snapshots`, `scores`,
`inspections`, `issues`.

Review rules: evaluator `id` unique; evaluator `method` known; track `id` unique;
each `track.evaluators` entry must reference an existing evaluator id; each
`track.evidence` entry must be a known evidence type; **no evaluators (and no
`methods` shorthand) → ERROR**; **no tracks → WARN**.

**human_annotation annotation JSON contract.** The runner ingests a JSON object
with three fields: `passed` (**required, bool** — the verdict), `score`
(optional, number), `detail` (optional, string). It looks for
`evaluator.annotation` (relative to `evaluation.root`), else the drop-in
`evidence/scores/<track_id>/<evaluator_id>.annotation.json`. No file →
`pending` (never blocks). A file whose `passed` is missing or not a bool →
`error` (a `score` alone is not a verdict), with the file path and the expected
schema in the record's detail.

**llm_judge runtime.** Judging needs `AHL_JUDGE_BASE_URL` / `AHL_JUDGE_MODEL` /
`AHL_JUDGE_API_KEY` (no key → `pending`, never a fabricated verdict); the
OpenAI-compatible `base_url` IS the provider abstraction — Anthropic and other
providers connect through an OpenAI-compatible gateway; there is no
per-provider protocol switch. `AHL_JUDGE_TIMEOUT` (seconds, default 180) bounds
each judge request. The judge scores only trace records that carry a `response`
field; the `script` connector's v1 traces record `input`/`exit_code`/`ok` but
no `response`, so a configured judge over script-connector evidence reports
`error` (trace records exist but 0 judgeable units) instead of staying silently
`pending`.

**Multi-turn judging (v1.1).** When a trace record carries a `transcript`
(multi-turn execution, [`execution-model.md`](execution-model.md) §14), the
judge prompt presents the **whole conversation** — a `[CONVERSATION]` block
expanded turn by turn — instead of the single `[CASE INPUT]`/`[AGENT OUTPUT]`
pair; records without a transcript keep the single-turn prompt byte-for-byte
(pinned by a golden test). Write rubrics for multi-turn experiments against
the entire conversation (consistency across turns, how the agent handles
follow-ups, recovery after a bad answer), not just the first reply: the
judging unit changes from "one reply" to "one conversation", so an A/B
conclusion judged under one unit must not be compared against one judged
under the other. Scoring math (worst-wins aggregation, per-record scores)
is unchanged.

## 14b. llm_rubric — dimension-weighted LLM scoring (v1.1)

`llm_rubric` is the fourth evaluation method. It scores each trace record
across multiple named dimensions using an LLM, combines them by weight into a
single 0–100 total, and stores both the total (`score`) and per-dimension detail
(`dimensions`) in the score record. This is the v1-native port of Stack A's
`grader.py` capability.

**Rubric file format.** The `rubric:` path (relative to `evaluation.root`)
points at a Markdown file that contains a GFM pipe table with three columns:

```markdown
| Dimension   | Weight | Description                               |
|-------------|--------|-------------------------------------------|
| accuracy    | 0.5    | Is the answer factually correct?          |
| conciseness | 0.3    | Is the answer concise and on-point?       |
| helpfulness | 0.2    | Is the answer helpful to the user?        |
```

Column names are case-insensitive. Weights are floats; if they do not sum to
1.0 they are normalised automatically (sum != 1 is accepted at eval time, not
an error). The table must be present and contain at least one parseable row —
a missing or empty table is a review-stage ERROR (`rubric_invalid` /
`rubric_missing_dimensions`).

Place rubric files under `evaluation/rubrics/` by convention (the path is
declared in the evaluator config, so any subdirectory under `evaluation.root`
is valid):

```yaml
evaluation:
  root: evaluation/
  evaluators:
    - id: quality_rubric
      method: llm_rubric
      rubric: rubrics/quality_rubric.md
  tracks:
    - id: quality
      evaluators: [quality_rubric]
      evidence: [traces]
```

**Runtime.** Uses the same `AHL_JUDGE_BASE_URL` / `AHL_JUDGE_MODEL` /
`AHL_JUDGE_API_KEY` / `AHL_JUDGE_TIMEOUT` env vars as `llm_judge`. No key →
`pending` (same honesty contract — never a fabricated score). LLM call failure
or unparseable reply → `error` (with detail and `raw_response` preview in the
score record).

**Score record shape.** The standard `score` field holds the weighted total
(0–100). The pre-reserved `dimensions` field carries per-dimension detail:

```json
{
  "score": 68.0,
  "dimensions": {"accuracy": 80.0, "conciseness": 60.0, "helpfulness": 50.0},
  "status": "passed"
}
```

The `score` field is on the same 0–100 scale as `llm_judge`, so existing
aggregation, `compare`, and `report` logic work unchanged.

**Multi-turn scoring.** When a trace record carries a `transcript`, the prompt
presents the whole conversation in a `[CONVERSATION]` block, expanded turn by
turn (same expansion as `llm_judge` multi-turn judging). Single-turn records
get the `[CASE INPUT]` / `[AGENT OUTPUT]` pair. Changing the rubric between
runs shifts the judging unit — see the caveat below.

**Rubric-guidance caveat.** Multi-turn scoring judges the WHOLE conversation
vs only the first turn, which changes the comparison baseline. An A/B
conclusion scored under rubric version X must not be compared against one
scored under rubric version Y — the criterion changed, so the baseline shifted.
If you revise a rubric mid-experiment or between runs, treat the results as
starting a new baseline; do not blend scores across different rubric versions.

**Review codes.**

| Code | Level | Trigger |
|------|-------|---------|
| `rubric_missing_dimensions` | ERROR | `llm_rubric` evaluator has no `rubric:` field, or `rubric:` is empty |
| `rubric_invalid` | ERROR | The rubric file exists but contains no parseable dimensions+weights table |

Both codes are left-shifted to `hlab review` (caught before any run).

Backward-compatible shorthand (still accepted, but `evaluators` + `tracks` is preferred):

```yaml
evaluation:
  root: evaluation/
  methods:
    - type: llm_judge
```

## 14a. simulator (optional)

Drives the user side of cases. Scaffolded as `single_turn` (send each case
input once — the default; its semantics are frozen). The multi-turn types are
a **v1.1 contract**; their execution semantics (per-case fresh session, turn
loop, partial transcripts, no-key behavior) are specified in
[`execution-model.md`](execution-model.md) §14.

```yaml
simulator:
  type: single_turn            # default: send each case input once
# or (v1.1 multi-turn):
#   type: role_play            # an LLM plays the user from a policy card
#   actor: ceo                 # who the simulated user is (short label)
#   max_turns: 6               # turn budget; defaults to 8 when omitted
#   policy: cases/simulator.md # four-section policy card (below)
# or:
#   type: scripted             # deterministic playbook — a designed mock
#   playbook: cases/playbook.yaml
# or:
#   type: script               # external program decides the next user turn
#   script: cases/simulator.py
```

Allowed types: `single_turn`, `script`, `role_play`, `scripted` (v1.1).

Review rules:

```text
unknown type                          ERROR  (bad_simulator_type)
script   without `script:`            ERROR  (simulator_script_missing)
scripted without `playbook:`          ERROR  (simulator_playbook_missing)
role_play without `actor:`/`policy:`  ERROR  (simulator_field_missing)
max_turns present but not an integer  ERROR  (bad_simulator_max_turns)
policy/playbook/script file missing   run.mode: auto  → ERROR (simulator_*_ref_missing)
                                      run.mode: copilot → WARN
policy card unreadable (I/O error)    WARN   (simulator_policy_unreadable)
policy card missing Persona/Strategy  WARN   (simulator_policy_incomplete)
policy card missing its Stop section  WARN   (simulator_policy_no_stop;
                                             conversation ends only on max_turns)
script connector + multi-turn type    ERROR  (simulator_connector_unsupported;
                                             the script connector spawns a fresh
                                             process per case and has no turn
                                             IPC — use a local_cli connector)
optimization.enabled + multi-turn     ERROR  (optimize_multiturn_unsupported;
                                             v1.1 optimize is single_turn only)
optimization.enabled + source:        ERROR  (optimize_source_unsupported;
                                             optimize mutates harness files;
                                             source sandboxes rebuilt per-run,
                                             so mutations would be lost)
```

The v1.0 `simulator_roleplay_unimplemented` WARN (role_play under Auto Mode)
is removed in v1.1: `role_play` becomes executable by Auto Mode.

### role_play policy card (four designable sections)

The `policy` file is a Markdown card with four H2 sections; section names are
accepted in English or Chinese:

| Section (EN)    | 段名（中文）    | Role |
|-----------------|----------------|------|
| `## Persona`    | `## 人设`       | who the simulated user is |
| `## Background` | `## 背景知识`   | what the user knows / the situation |
| `## Strategy`   | `## 追问策略`   | follow-up strategy — ask for numbers, challenge assumptions, switch scenarios, … (free text guiding the LLM) |
| `## Stop`       | `## 收尾条件`   | the "asked enough" criterion, beyond the `max_turns` budget |

`Persona` and `Strategy` are required for a useful card; a missing `Stop`
section is a review WARN — the conversation then ends only on `max_turns`.

`role_play` execution needs `AHL_SIM_BASE_URL` / `AHL_SIM_MODEL` /
`AHL_SIM_API_KEY` (optional `AHL_SIM_TIMEOUT`, seconds). Without a key the run
records a `simulator_unconfigured` error issue and skips dispatch — never a
fabricated follow-up. `AHL_SIM_STUB=1` forces the `scripted` playbook path for
key-free CI/smoke runs (traces marked `forced: true`). See
[`execution-model.md`](execution-model.md) §14.5.

### scripted playbook

`playbook` points at a YAML file:

```yaml
default:                       # global follow-up sequence, one entry per turn
  - "Can you be more specific? Give a number."
  - "And if the situation changes, how would you adjust?"
per_case:                      # optional per-case override, keyed by case id
  case-001:
    - "What is the rollback plan?"
```

Deterministic: zero LLM calls, zero keys. Follow-ups are sent in order; the
end of the sequence is the stop signal. Conditional logic ("ask only if the
answer lacks a number") does **not** belong in a playbook — use `type: script`
for that.

### script simulator

`script` points at an external program that decides the next user turn — fully
custom logic (conditional follow-ups, stateful probing). One subprocess per
turn: stdin receives `{"transcript": [...]}` (the turns completed so far),
stdout must print `{"next": "<message>"}` or `{"next": null}` (null ends the
case). The script runs with the same Python interpreter as benchmark evaluator
scripts, under the script connector's anti-hang hardening; any failure raises
into the partial-transcript contract instead of fabricating a turn. Full
protocol: [`execution-model.md`](execution-model.md) §14.8.

## 14c. objective + optimization (Auto Optimize — bounded deterministic loop)

These describe **Auto Optimize**, the second Auto Mode layer. v1 implements a
**bounded, deterministic loop**: it generates (copy-only or via a user
`mutation_script`), runs, evaluates, and promotes Candidate Harnesses within
`stop_conditions`, recording `optimization/history.jsonl`. There is **no LLM-driven
or autonomous** mutation; `enabled: true` still emits a WARN to set that expectation.

```yaml
objective:
  primary_track: skill-artifact        # must be a defined evaluation.tracks id
  success_criteria: "a usable skill artifact on >= 80% of cases"
  optimize_for: maximize               # maximize | minimize

optimization:
  enabled: false                       # true → runs the bounded deterministic loop (WARN: not autonomous)
  editable_surface:                    # what a Candidate Harness may change
    - harnesses/B/                     # MUST be harness-controlled (under harnesses/)
  protected_surface:                   # never changed by Auto (defaults below are always protected)
    - goal.md
    - cases/
    - evaluation/
    - objective
    - conclusion.md
  stop_conditions:                     # REQUIRED when enabled: true
    - max_iterations: 5                # honored keys: max_iterations | no_improvement
  promotion_policy:                    # must reference known tracks / issue types
    promote_if_track: skill-artifact
    reject_if_issue: case_failure
```

Review rules:
- `objective.primary_track` must be a defined `evaluation.tracks` id; `optimize_for`
  ∈ {maximize, minimize} (else WARN).
- `optimization.editable_surface` entries must be **harness-controlled** (under
  `harnesses/`) and must **never** target a protected surface (`goal`, `cases`,
  `evaluation`, `objective`, `conclusion` — protected by default) → ERROR otherwise.
- `stop_conditions` is REQUIRED when `optimization.enabled: true` → ERROR otherwise.
- `promotion_policy` values must reference a known evaluation track id or issue type.
- `optimization.enabled: true` → WARN (`optimization_bounded_only`: the bounded
  deterministic loop runs; there is no LLM-driven / autonomous optimization).

Roles in optimization are **Candidate Harness** / **Incumbent Harness** — these are
optimization roles, **not** a return of the old `variant` concept.

## 15. collection

Defines what evidence should be collected.

Example:

```yaml
collection:
  traces: true
  raw: true
  artifacts: true
  snapshots: false
  scores: true
```

## 16. inspection

Defines evidence checks.

Example:

```yaml
inspection:
  artifact_review: true
  skill_review: true
  memory_review: false
  context_review: false
  issue_checks:
    - missing_artifact
    - empty_output
    - path_drift
    - runtime_mismatch
```

v1 execution semantics (honest status of these switches):

- `skill_review` / `memory_review` / `context_review` are **declarable-only** in
  v1: no such review is executed. Declaring one as `true` makes `hlab review`
  WARN `declared but not executed in v1` (`inspection_review_unimplemented`).
- `artifact_review` and `issue_checks` are currently **advisory**: the Inspector
  always runs its fixed check set over the collected evidence regardless of
  these values. They document intent and drive review coherence warnings (e.g.
  an issue check whose evidence `collection` disables); they do not gate which
  checks execute.

Allowed issue checks for v1:

```text
missing_artifact
empty_output
path_drift
runtime_mismatch
missing_trace
missing_score
case_failure
connector_failure
```

## 17. reports

Example:

```yaml
reports:
  formats:
    - md
    - html
```

v1 required:

```text
md
```

v1 optional:

```text
html
```

## 18. Validation Rules

`hlab review` should fail when:

```text
experiment.yaml is invalid YAML
required fields are missing
run.mode is unsupported
execution.mode is unsupported
harness path missing
Agent Runtime spec missing
cases root or files missing
evaluation root missing
Auto Mode uses unsupported connector
```

`hlab review` should warn when:

```text
conclusion.md missing
human review required but not documented
snapshots requested but no snapshot collection configured
```

(`report.html` is rendered by a real stdlib Markdown→HTML renderer, so requesting it no
longer warns.)

## 19. Review Issue Codes — `probe_*` (PR8, source health checks)

When an Agent Runtime declares a `source:` section, `hlab review` runs a
read-only source health check and emits `probe_*`-prefixed issue codes.
See `docs/v1-spec/cli.md §6` (Phase 2) for the full check specification.

| Code | Severity | Condition |
|------|----------|-----------|
| `probe_source_missing` | ERROR | `local_path` / `harness_package` source directory does not exist |
| `probe_source_not_dir` | ERROR | Source path exists but is not a directory |
| `probe_source_unreadable` | ERROR | Source directory exists but cannot be listed (permission error) |
| `probe_source_hash_skipped` | WARN | `local_path` source exceeds the 256 MiB cap; existence confirmed, hash skipped |
| `probe_source_hash_failed` | WARN | `source_dir_hash` computation raised an OS error |
| `probe_patch_source_missing` | ERROR | A `patch.files[].source` file does not exist (check deferred from PR6) |
| `probe_git_missing` | ERROR | `git` binary not found in PATH |
| `probe_git_url_missing` | ERROR | `source.url` absent for a `git_repo` source |
| `probe_git_unreachable` | ERROR | `git ls-remote` failed (bad url, timeout, OS error) |
| `probe_git_ref_missing` | ERROR | `git ls-remote` succeeded but returned empty output (ref not found) |
| `probe_git_ref_unverifiable` | WARN | `source.ref` is a commit SHA (7–40 hex chars) — `ls-remote` cannot verify individual commit reachability; the SHA may be unreachable on the remote |
| `probe_fingerprint_mismatch` | ERROR | `harness_package` fingerprint does not match `expected_fingerprint` |

Experiments with no `source:` sections on any runtime are unaffected — no
`probe_*` codes are ever emitted and review behavior is byte-identical to
pre-v1.1.
