# Execution Model

## 1. Overview

AHL v1 supports two run modes:

```text
Copilot Mode
Auto Mode
```

Run Mode answers:

```text
Who executes the experiment?
```

Execution Mode answers:

```text
How is the experiment organized?
```

## 2. Run Modes

### 2.1 Copilot Mode

AHL prepares the experiment and delegates runtime-specific execution to an external agent.

Flow:

```text
read experiment.yaml
validate experiment structure
render agent-task.md
external agent executes runtime-specific steps
external agent writes evidence/
AHL validates evidence
AHL runs evaluation/inspection
AHL builds reports
```

Copilot Mode is not purely manual.

It provides structure, checks, and evidence discipline.

### 2.2 Auto Mode

Auto Mode has **two layers**. v1 implements only the first.

**Auto Run (implemented).** Given an already-defined experiment, AHL runs each
case through `local_cli` / `script` connectors and collects evidence:

```text
read experiment.yaml
load Agent Runtime specs
load cases
dispatch cases (single_turn)
run connector (local_cli stdin_json IPC, or per-case script)
collect evidence/traces, evidence/raw, evidence/artifacts (artifacts.collect globs)
write evidence/issues.jsonl (connector_failure / case_failure / missing_artifact / empty_output)
```

`hlab run` (run.mode=auto) does Auto Run today and **exits 0**.

**Auto Optimize (NOT implemented — schema/review boundary only).** Given a goal,
`objective`, `evaluation`, and an editable surface, AHL would iteratively generate
/ modify Candidate Harnesses, run experiments, evaluate evidence, promote/reject
candidates, and stop on the objective or a stop condition. v1 validates the
`objective` / `optimization` schema and the editable/protected-surface boundary,
and WARNs that the loop is not implemented — it does not generate, run, evaluate,
or promote anything. (Inspectors, EvaluationRunner, ReportBuilder, and the
mutation/optimization engine are later phases.)

Auto Mode v1 required connectors:

```text
local_cli
script
```

Optional:

```text
remote_devbox
```

## 3. Execution Modes

Allowed execution modes:

```text
ab
sequential
longitudinal
replay
```

### ab

Compare two or more harnesses on the same cases.

### sequential

Run harnesses or versions in sequence.

### longitudinal

Run cases across accumulated state.

Used for memory/evolution experiments.

### replay

Run evaluation/reporting on existing evidence without rerunning Agent Runtime.

## 4. State Policies

Allowed state policies:

```text
isolated
reset
cumulative
snapshot_branch
replay
```

Auto Mode v1 must support:

```text
isolated
reset
```

Cumulative and snapshot_branch may be represented before fully implemented.

## 5. Core Runtime Objects

```text
RunPlan
AgentRuntimeConnector
AutoRunner
CaseDispatcher
EvidenceCollector
Inspector
EvaluationRunner
ReportBuilder
```

## 6. AgentRuntimeConnector Interface

Conceptual interface:

```python
class AgentRuntimeConnector:
    def check(self) -> CheckResult:
        pass

    def start(self) -> None:
        pass

    def run_case(self, case: Case) -> RunResult:
        pass

    def collect(self, result: RunResult, target: EvidenceStore) -> None:
        pass

    def stop(self) -> None:
        pass
```

## 7. local_cli Connector

Runs a local command.

Example runtime spec:

```yaml
id: runtime-a
connector:
  type: local_cli
  command: "python run_agent.py"
  working_dir: "./runtime-a"
  input_mode: stdin_json
```

Minimum behavior:

```text
start process
send case input
capture stdout/stderr
write raw output
write trace record
collect declared artifacts
```

## 8. script Connector

Runs a user-provided script per case.

Example:

```yaml
id: runtime-a
connector:
  type: script
  command: "python scripts/run_case.py --case {case_file} --out {output_dir}"
```

Minimum behavior:

```text
render command
execute command
capture exit code
collect output directory
write issue on failure
```

## 9. Evidence Collection

Auto Mode must write:

```text
evidence/traces/
evidence/raw/
evidence/artifacts/
evidence/snapshots/
evidence/scores/
evidence/inspections/
evidence/issues.jsonl
```

## 10. Inspectors

v1 inspectors:

```text
ArtifactInspector
TraceInspector
IssueInspector
```

### ArtifactInspector

Checks:

```text
expected artifacts exist
files are non-empty
artifact paths match expected roots
```

### TraceInspector

Checks:

```text
trace exists
case ids are present
runtime ids are present
error fields are captured
```

### IssueInspector

Normalizes issue records to `evidence/issues.jsonl`.

## 11. Issue Record Format

Example:

```json
{
  "id": "issue-001",
  "case_id": "case-001",
  "runtime_id": "runtime-a",
  "harness_id": "A",
  "type": "missing_artifact",
  "severity": "error",
  "message": "Expected skill artifact was not found.",
  "evidence_ref": "evidence/artifacts/runtime-a/case-001/",
  "created_by": "ArtifactInspector"
}
```

Allowed severity:

```text
info
warning
error
fatal
```

## 12. Status Transitions

```text
draft → ready → running → collected → evaluated → reported → concluded
```

Failure path:

```text
running → invalid
collected → invalid
evaluated → invalid
```

## 13. MVP Boundary

Auto Mode v1 should not attempt to solve universal agent orchestration.

Required:

```text
local_cli connector
script connector
case dispatch
evidence collection
basic inspectors
basic report generation
```

Not required:

```text
universal remote devbox management
all agent framework adapters
role-play simulator automation
semantic memory/context inspection
dashboard
```
