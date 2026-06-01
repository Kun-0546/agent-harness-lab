# Claude Code Handoff: Agent Harness Lab v1 Migration Analysis

## 0. Task Status

This is a handoff for Claude Code.

Do **not** start implementation immediately.

Your first task is to inspect the current Agent Harness Lab v0.10.0 repository and produce a migration plan for v1.

The goal is to correct the existing project direction, structure, CLI, schema, and tests so it can become a clean open-source project.

---

## 1. Product Direction

Agent Harness Lab v1 is a project for running **goal-driven harness experiments on real Agent Runtimes**.

The core method is:

```text
goal → experiment → harness → agent runtime → case → evaluation → evidence → conclusion
```

AHL is not just a benchmark runner.

It should help humans and agents design, run, collect evidence for, evaluate, and review experiments that compare different harnesses in real Agent Runtime environments.

---

## 2. Important Terminology

Use these terms consistently.

### 2.1 Harness

`harness` is the core public object.

Do **not** use `variant` as the public-facing term.

A harness is any design unit that changes how an Agent runs, behaves, or performs in an experiment.

Examples:

```text
skill
memory mechanism
context compression strategy
evolution mechanism
agent configuration
runtime patch
tool/plugin setup
prompt/instruction bundle
execution script or runtime constraint
```

### 2.2 Agent Runtime

Use `Agent Runtime` as the public term.

An Agent Runtime is the real environment where the tested Agent runs.

It should answer:

```text
What agent is being tested?
What code version is it?
Where does it run?
How is it connected?
How are cases sent to it?
How are logs and artifacts collected?
What state policy is used?
```

### 2.3 Experiment

An experiment compares one or more harnesses against a goal.

### 2.4 Evaluation

Evaluation defines how results are judged.

Evaluation is designed before execution.

Common evaluation methods:

```text
human_annotation
llm_judge
benchmark
```

### 2.5 Evidence

Evidence is what the run produces.

Examples:

```text
trace
raw log
artifact
snapshot
score
inspection
issue
```

### 2.6 Conclusion

Conclusion is the human-recognized final analysis and next step.

Use `conclusion.md`, not `decision.md`, as the default file name.

---

## 3. New Project Structure

The v1 workspace should be organized like this:

```text
goal.md
evaluation-methods/
  human_annotation.md
  llm_judge.md
  benchmark.md

experiments/
  <experiment-name>/
    experiment.md
    experiment.yaml
    agent-task.md            # generated, optional to commit

    harnesses/
      A/
      B/

    agent-runtimes/
      runtime-a.yaml
      runtime-b.yaml

    cases/
      cases.jsonl
      datasets/
      simulator.md

    evaluation/
      evaluation.md
      rubrics/
      graders/
      benchmarks/

    evidence/
      traces/
      raw/
      artifacts/
      snapshots/
      scores/
      inspections/
      issues.jsonl

    reports/
      report.md
      report.html

    conclusion.md
```

Important notes:

```text
experiment.md: human-readable experiment plan.
experiment.yaml: machine-readable source of truth.
agent-task.md: generated task view for external agents in Copilot Mode.
harnesses/: compared harnesses or references.
agent-runtimes/: Agent Runtime connection/environment specs.
cases/: executable inputs.
evaluation/: scoring, rubric, benchmark, inspection design.
evidence/: actual run evidence.
reports/: generated reports.
conclusion.md: human final conclusion and next-step analysis.
```

---

## 4. CLI Direction

The CLI command should be:

```text
hlab
```

Not `ahl`.

Minimum v1 commands:

```text
hlab init
hlab new
hlab review
hlab run
hlab status
hlab report
```

Expected behavior:

### 4.1 hlab init

Creates:

```text
goal.md
evaluation-methods/
experiments/
.hlab/
```

### 4.2 hlab new

Creates:

```text
experiments/<name>/experiment.md
experiments/<name>/experiment.yaml
experiments/<name>/harnesses/
experiments/<name>/agent-runtimes/
experiments/<name>/cases/
experiments/<name>/evaluation/
experiments/<name>/evidence/
experiments/<name>/reports/
experiments/<name>/conclusion.md
```

### 4.3 hlab review

Checks:

```text
harnesses are defined
Agent Runtime specs exist
cases exist
evaluation exists
collection requirements are complete
Auto Mode connector is available when run.mode=auto
```

### 4.4 hlab run

Uses `run.mode` from `experiment.yaml`.

```text
copilot: generate agent-task.md for Claude Code / Codex / Cursor Agent.
auto: run cases through connector and collect evidence.
```

### 4.5 hlab status

Shows experiment status, missing assets, and evidence state.

### 4.6 hlab report

Generates or refreshes:

```text
reports/report.md
reports/report.html  # optional / stretch goal
```

---

## 5. Run Modes

AHL v1 should support two product modes.

### 5.1 Copilot Mode

In Copilot Mode, AHL does not directly control all Agent Runtimes.

AHL:

```text
reads experiment.yaml
checks experiment.md / harnesses / agent-runtimes / cases / evaluation
generates agent-task.md
hands the task to an external agent such as Claude Code or Codex
expects evidence to be written back to standard locations
runs review/evaluation/report generation
```

Copilot Mode is not pure manual mode.

It is structured human-agent execution.

### 5.2 Auto Mode

Auto Mode is in scope for v1.

In Auto Mode, AHL uses connectors to directly run cases against Agent Runtimes, collect evidence, inspect outputs, run evaluation, and build reports.

Auto Mode v1 should support a limited connector set.

Required:

```text
local_cli
script
```

Optional / stretch:

```text
remote_devbox
```

Not required for v1:

```text
universal connector for every agent framework
full remote execution platform
complex role-play simulator automation
```

---

## 6. Execution Model

AHL v1 should include these technical objects or their equivalents:

```text
ExperimentSpec
HarnessSpec
AgentRuntimeSpec
CaseSet
EvaluationSpec
RunPlan
AgentRuntimeConnector
AutoRunner
CopilotTaskRenderer
EvidenceCollector
EvidenceStore
IssueStore
Inspector
EvaluationRunner
ReportBuilder
ReviewChecker
```

Map them to project files:

```text
experiment.yaml            → ExperimentSpec
harnesses/                 → HarnessSpec
agent-runtimes/            → AgentRuntimeSpec
cases/                     → CaseSet
evaluation/                → EvaluationSpec
run.mode                   → RunPlan
agent-task.md              → CopilotTaskRenderer output
connector                  → AgentRuntimeConnector
evidence/                  → EvidenceStore
evidence/issues.jsonl      → IssueStore
reports/                   → ReportBuilder output
conclusion.md              → human conclusion and next-run context
```

---

## 7. Experiment YAML Direction

`experiment.yaml` is the machine-readable source of truth.

Example:

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

harnesses:
  - id: A
    name: our-skill-creator
    path: harnesses/A/
  - id: B
    name: anthropic-skill-creator
    path: harnesses/B/

agent_runtimes:
  - id: runtime-a
    harness: A
    spec: agent-runtimes/runtime-a.yaml
  - id: runtime-b
    harness: B
    spec: agent-runtimes/runtime-b.yaml

cases:
  root: cases/
  files:
    - cases.jsonl

evaluation:
  root: evaluation/
  methods:
    - type: human_annotation
    - type: llm_judge
    - type: benchmark

collection:
  traces: true
  raw: true
  artifacts: true
  snapshots: false
  scores: true

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

reports:
  formats:
    - md
    - html
```

Your migration plan should identify how close the current code is to this schema and what needs to change.

---

## 8. Evidence Structure

Evidence should use:

```text
evidence/
  traces/
  raw/
  artifacts/
  snapshots/
  scores/
  inspections/
  issues.jsonl
```

Definitions:

```text
traces/: simplified jsonl traces for review and replay.
raw/: raw responses or logs.
artifacts/: skills, memory files, PDFs, spreadsheets, generated outputs.
snapshots/: memory/context/state snapshots.
scores/: grader and benchmark outputs.
inspections/: human or agent review of artifacts/snapshots/traces.
issues.jsonl: machine-readable evidence issues.
```

`issues.jsonl` is not a report.

It records evidence problems such as:

```text
missing artifact
empty output
path drift
runtime mismatch
scorer missed key evidence
fake precision
scenario contamination
model version mismatch
connection check failure
```

---

## 9. What To Do First

Do **not** edit files yet.

First inspect the current repository and produce a migration plan.

Your output should include:

```text
1. Repository inventory
2. Current concept mapping
3. Current CLI mapping
4. Current directory/file mapping
5. Current schema/config mapping
6. Current test coverage mapping
7. Gap analysis against v1 product direction
8. Proposed implementation phases
9. Risk list
10. Open questions
```

---

## 10. Specific Analysis Questions

Answer these specifically:

### 10.1 Naming

Where does the current repo use:

```text
variant
runtime
hdl
ahl
decision
program
scorer
```

What should each become?

Expected direction:

```text
variant → harness
runtime → Agent Runtime where user-facing
ahl/hdl command → hlab command
decision.md → conclusion.md
scorer → evaluation / EvaluationRunner where broader than scoring
```

### 10.2 CLI

What commands exist now?

Which should remain?

Which should be renamed?

Which should become internal/debug?

### 10.3 Directory migration

How does the current experiment directory compare to:

```text
experiment.md
experiment.yaml
harnesses/
agent-runtimes/
cases/
evaluation/
evidence/
reports/
conclusion.md
```

### 10.4 Auto Mode feasibility

Given the current code, how hard is it to support:

```text
local_cli connector
script connector
```

What is the smallest useful Auto Mode implementation?

### 10.5 Copilot Mode

How should `agent-task.md` be generated?

What current code can be reused?

### 10.6 Evidence

How are traces, artifacts, scores, and results currently stored?

What needs to change to support:

```text
evidence/traces/
evidence/raw/
evidence/artifacts/
evidence/snapshots/
evidence/scores/
evidence/inspections/
evidence/issues.jsonl
```

### 10.7 Tests

What tests need to be updated or added?

At minimum, test:

```text
workspace initialization
experiment creation
experiment.yaml parsing
harness loading
Agent Runtime spec loading
review checks
Copilot agent-task generation
Auto local_cli/script execution
EvidenceCollector output
IssueInspector
report generation
example validity
```

---

## 11. Output Format

Write the migration plan as:

```text
docs/migration-from-v0.10.0-to-v1.md
```

The plan should be structured as:

```markdown
# Migration Plan: AHL v0.10.0 → Agent Harness Lab v1

## 1. Executive Summary
## 2. Current Repository Inventory
## 3. Concept Mapping
## 4. CLI Mapping
## 5. Directory and File Mapping
## 6. Schema and Data Model Changes
## 7. Execution Model Changes
## 8. Evidence Model Changes
## 9. Tests to Update or Add
## 10. Implementation Phases
## 11. Risks
## 12. Open Questions
```

Do not implement until the plan is reviewed.

---

## 12. Non-negotiables

Do not violate these:

```text
Do not create a new product architecture unrelated to the existing code.
Do not invent extra public concepts unless required.
Do not expose every internal operation as a human-facing CLI command.
Do not keep variant as the public term.
Do not make AHL only a markdown template generator.
Do not make Auto Mode depend on a universal agent connector.
Do not delete backwards compatibility paths before identifying migration impact.
Do not skip tests.
```

---

## 13. Suggested Implementation Phases After Review

Only after the migration plan is reviewed, implementation may proceed in phases:

```text
Phase 1: Naming and CLI migration to hlab.
Phase 2: New experiment directory structure and templates.
Phase 3: experiment.yaml schema and parser.
Phase 4: Copilot Mode agent-task generation.
Phase 5: EvidenceStore and IssueStore.
Phase 6: Auto Mode local_cli/script connector.
Phase 7: EvaluationRunner and basic Inspector.
Phase 8: ReportBuilder.
Phase 9: Example migration and open-source cleanup.
```
