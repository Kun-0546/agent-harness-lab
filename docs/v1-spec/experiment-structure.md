# Experiment Structure

## 1. Workspace Structure

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
    agent-task.md

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

## 2. File Responsibilities

### goal.md

Human-authored long-term goal.

### experiment.md

Human-readable experiment description.

It should answer:

```text
Why are we running this experiment?
Which long-term goal does it serve?
Which harnesses are compared?
Which Agent Runtimes are used?
Which cases are run?
How is evaluation designed?
What evidence must be collected?
What requires human review?
When should the result be considered invalid or weak?
```

### experiment.yaml

Machine-readable source of truth.

AHL parses this file to create `ExperimentSpec`.

### agent-task.md

Generated agent-facing execution task.

In Copilot Mode, this is given to Claude Code / Codex / Cursor Agent.

It should not be the source of truth.

### harnesses/

Stores or references the compared harnesses.

A harness can be a directory, config, prompt bundle, skill, memory module, script, or runtime patch.

### agent-runtimes/

Stores Agent Runtime specs.

Each runtime spec should define how to start, connect to, run, and collect outputs from the runtime.

### cases/

Executable inputs.

Minimal case file:

```text
cases/cases.jsonl
```

Optional:

```text
cases/datasets/
cases/simulator.md
cases/playbook.yaml   scripted simulator playbook — scaffolded by `hlab new`;
                      a user-designable mock (default: sequence + per_case overrides)
```

### evaluation/

Experiment-specific evaluation design.

```text
evaluation/evaluation.md
evaluation/rubrics/
evaluation/graders/
evaluation/benchmarks/
```

### evidence/

Runtime outputs and inspection material.

```text
evidence/traces/
evidence/raw/
evidence/artifacts/
evidence/snapshots/
evidence/scores/
evidence/inspections/
evidence/issues.jsonl
```

### reports/

Generated reports.

```text
reports/report.md
reports/report.html
```

### conclusion.md

Human final conclusion and next-step analysis.

## 3. Generated vs Authored

Recommended classification:

```text
Human-authored:
  goal.md
  experiment.md
  conclusion.md

Machine-readable source:
  experiment.yaml
  agent-runtimes/*.yaml
  cases/*.jsonl

Generated:
  agent-task.md
  evidence/*
  reports/*
```

## 4. Minimum Valid Experiment

A minimum valid experiment has:

```text
experiment.md
experiment.yaml
at least one harness
at least one Agent Runtime
at least one case file
evaluation/evaluation.md
evidence/ directory
reports/ directory
```
