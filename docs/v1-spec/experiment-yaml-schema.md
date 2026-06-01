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
   `human_annotation`, `llm_judge`, `benchmark`.
2. **Evaluator Instance** — experiment-local configured evaluator
   (`evaluation.evaluators`): binds a method to a concrete `script` (benchmark) or
   `rubric` (llm_judge / human_annotation).
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
  tracks:
    - id: skill-artifact
      question: "Did the harness produce a usable skill artifact?"
      evaluators: [artifact_exists, skill_quality, human_skill_review]
      evidence: [artifacts, traces, raw]
```

Allowed evaluator methods: `human_annotation`, `llm_judge`, `benchmark`.
Allowed track evidence types: `traces`, `raw`, `artifacts`, `snapshots`, `scores`,
`inspections`, `issues`.

Review rules: evaluator `id` unique; evaluator `method` known; track `id` unique;
each `track.evaluators` entry must reference an existing evaluator id; each
`track.evidence` entry must be a known evidence type; **no evaluators (and no
`methods` shorthand) → ERROR**; **no tracks → WARN**.

Backward-compatible shorthand (still accepted, but `evaluators` + `tracks` is preferred):

```yaml
evaluation:
  root: evaluation/
  methods:
    - type: llm_judge
```

## 14a. simulator (optional)

Drives the user side of cases. Scaffolded as `single_turn`.

```yaml
simulator:
  type: single_turn          # send each case input once (Auto v1)
# or:
#   type: script
#   script: cases/simulator.py
# or:
#   type: role_play
#   actor: ceo
#   max_turns: 6
#   policy: cases/simulator.md
```

Allowed types: `single_turn`, `script`, `role_play`. Review: unknown type → ERROR;
`script` requires `script:`; `role_play` requires `actor:` + `policy:` (`max_turns`
int if present); `role_play` under Auto Mode → WARN (not auto-run in v1).

## 14b. objective + optimization (Auto Optimize — schema/review only)

These describe **Auto Optimize**, the second Auto Mode layer. v1 ships the
**schema + review boundary only** — the optimization loop (generate / run /
evaluate / promote Candidate Harnesses) is NOT implemented; `enabled: true`
produces an honest WARN, not execution.

```yaml
objective:
  primary_track: skill-artifact        # must be a defined evaluation.tracks id
  success_criteria: "a usable skill artifact on >= 80% of cases"
  optimize_for: maximize               # maximize | minimize

optimization:
  enabled: false                       # true → Auto Optimize would run (not built → WARN)
  editable_surface:                    # what a Candidate Harness may change
    - harnesses/B/                     # MUST be harness-controlled (under harnesses/)
  protected_surface:                   # never changed by Auto (defaults below are always protected)
    - goal.md
    - cases/
    - evaluation/
    - objective
    - conclusion.md
  stop_conditions:                     # REQUIRED when enabled: true
    - max_rounds: 5
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
- `optimization.enabled: true` → WARN (the Auto Optimize loop is not implemented).

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
report.html requested but renderer unavailable
human review required but not documented
snapshots requested but no snapshot collection configured
```
