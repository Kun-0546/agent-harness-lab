# Agent Harness Lab v1 Product Definition

## 1. One-line Definition

Agent Harness Lab helps humans and agents turn a question about real Agent capability into a controlled, evidence-backed, reproducible harness experiment and conclusion record.

Core flow:

```text
goal → experiment → harness → agent runtime → case → evaluation → evidence → conclusion
```

## 2. What AHL Is

AHL is an open-source project for running goal-driven harness experiments on real Agent Runtimes.

It is designed to compare different harnesses under controlled experimental conditions.

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

## 3. What AHL Is Not

AHL is not:

```text
a generic model eval platform
a leaderboard benchmark runner
a free-form meta-agent
a markdown-only workflow template
a scorer-only tool
a dashboard-first hosted product
```

AHL should not expose every internal operation as a human-facing CLI command.

## 4. Core User Roles

### Human

The human owns:

```text
goal
experiment review
evaluation review
evidence judgment
conclusion
```

The human mainly reads:

```text
goal.md
experiment.md
reports/report.md or reports/report.html
conclusion.md
```

### Execution Agent

The execution agent may be:

```text
Claude Code
Codex
Cursor Agent
AHL AutoRunner
```

It handles:

```text
connecting Agent Runtime
running cases
collecting traces/raw/artifacts/snapshots
triggering evaluation
recording issues
preparing report material
```

### AHL

AHL owns:

```text
experiment archive
experiment.yaml parsing
agent-task.md rendering
review checks
Copilot/Auto run control
evidence organization
inspection
evaluation
report generation
conclusion context preservation
```

## 5. Run Modes

AHL v1 supports:

```text
Copilot Mode
Auto Mode
```

### Copilot Mode

AHL generates a clear agent-facing task. An external agent such as Claude Code performs runtime-specific execution.

### Auto Mode

AHL connects to Agent Runtime through limited connectors and runs cases automatically.

v1 required connectors:

```text
local_cli
script
```

Optional connector:

```text
remote_devbox
```

## 6. v1 Success Criteria

AHL v1 is successful if it can:

```text
create a clear experiment archive
parse experiment.yaml
generate Copilot agent-task.md
run Auto Mode via local_cli/script connectors
collect evidence into standard directories
run basic evaluation/inspection
generate report.md
support at least one runnable example
```
