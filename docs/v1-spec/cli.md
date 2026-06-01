# CLI Design

## 1. Command Name

Use:

```text
hlab
```

Project name remains:

```text
Agent Harness Lab
```

## 2. MVP Commands

```text
hlab init
hlab new
hlab review
hlab run
hlab status
hlab report
```

## 3. hlab init

Creates workspace.

Usage:

```bash
hlab init
```

Output:

```text
goal.md
evaluation-methods/
  human_annotation.md
  llm_judge.md
  benchmark.md
experiments/
.hlab/
```

## 4. hlab new

Creates experiment.

Usage:

```bash
hlab new <experiment-name>
```

Output:

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

Optional flags:

```bash
hlab new skill-creator-ab --mode auto --execution ab
hlab new memory-comparison --mode copilot --execution longitudinal
```

## 5. hlab review

Reviews experiment before run.

Usage:

```bash
hlab review experiments/<name>
```

Checks:

```text
experiment.yaml exists and parses
harnesses exist
Agent Runtime specs exist
cases exist
evaluation exists
collection settings are valid
Auto Mode connector is supported
report formats are supported
```

Output levels:

```text
PASS
WARN
ERROR
```

## 6. hlab run

Runs or prepares experiment.

Usage:

```bash
hlab run experiments/<name>
```

Behavior depends on `run.mode`.

### Copilot Mode

```text
generate agent-task.md
print next instruction for external agent
do not connect runtime directly
```

### Auto Mode

```text
load connectors
dispatch cases
collect evidence
run inspectors
run evaluation if configured
update status
```

## 7. hlab status

Shows experiment status.

Usage:

```bash
hlab status experiments/<name>
```

Output:

```text
experiment id
status
run mode
execution mode
harness count
case count
evidence summary
issues summary
report status
conclusion status
```

## 8. hlab report

Generates reports.

Usage:

```bash
hlab report experiments/<name>
```

Default output:

```text
reports/report.md
```

Optional output:

```text
reports/report.html
```

## 9. Commands Not Public in MVP

Do not expose these as top-level human commands in MVP:

```text
hlab harvest-artifacts
hlab validate-evidence
hlab build-trace-snapshot
hlab preflight-runtime
hlab run-grader
hlab collect-logs
```

They may exist as internal functions, debug commands, or agent-facing runbook steps.

## 10. Backward Compatibility

If old commands exist, migration should provide friendly errors.

Example:

```text
The `ahl` command has been replaced by `hlab`.
Please use: hlab <command>
```

Do not silently run old semantics when meaning changed.
