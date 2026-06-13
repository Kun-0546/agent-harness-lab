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
[PR6] pre-run materialize: for each runtime declaring source:, copy/clone source
      into sandbox/<runtime_id>/ and apply patch before dispatch (see §15)
dispatch cases (single_turn; multi-turn from v1.1 — see §14)
run connector (local_cli stdin_json IPC, or per-case script)
collect evidence/traces, evidence/raw, evidence/artifacts (artifacts.collect globs)
write evidence/issues.jsonl (connector_failure / case_failure / missing_artifact / empty_output)
[PR6] write evidence/snapshots/<runtime_id>.json after successful materialize
```

`hlab run` (run.mode=auto) does Auto Run today. Exit codes: `0` success / `1` config or preflight error / `3` runtime failure (any error-severity issue or evaluation track in `error`) — see [`docs/v1-spec/cli.md`](cli.md) §3.1.

**Auto Optimize (bounded, deterministic loop implemented; not autonomous).** Given a
goal, `objective`, `evaluation`, and an editable surface, AHL runs a bounded loop:
each iteration copies the incumbent harness to a candidate, optionally mutates it via a
user `mutation_script`, enforces the editable/protected-surface boundary (a touched
protected file is rolled back), runs the candidate (Auto Run → Inspector →
EvaluationRunner), then promotes or rejects it by the promotion policy, stopping on
`stop_conditions` (max_iterations / no_improvement) under a safety cap. Candidate
generation is **copy-only or user-script**; it does **not** include LLM-based
mutation, fully autonomous optimization, remote/distributed optimization, or a general
self-improvement engine. Each iteration is recorded in `optimization/history.jsonl` and
`optimization/iterations/iter-NNN/` (per-iteration evidence + record).

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
role-play simulator automation (v1.0 boundary — the v1.1 contract is §14)
semantic memory/context inspection
dashboard
```

## 14. Run / Eval Split and the Evidence Iron Law (v1.1)

### 14a. Semantic iron law

> **Evidence is the immutable first-order artifact. Scores are recomputable derivatives.**

`hlab run` is the **only** command that can modify evidence (traces / raw / issues).
`hlab eval` re-runs all evaluation tracks against the existing evidence and rewrites
`scores/` and `scores/tracks/`, but never touches evidence.

This split enables two things:

1. **Human annotation backflow**: `run` may leave evaluation tracks in `pending` because
   no annotation file exists yet. A human writes an annotation file alongside the traces,
   then calls `hlab eval`. `eval` picks up the annotation and produces a score without
   requiring a re-run (which would destroy the traces the annotations refer to).

2. **Re-scoring without re-running**: when evaluation configuration changes (new rubric,
   upgraded evaluator script, key configured for a previously-offline `llm_judge`), the
   scores can be recomputed without touching the evidence.

### 14b. Idempotency contract

`hlab eval` is **idempotent for deterministic tracks**: benchmark and human_annotation
evaluators produce the same scores given the same evidence. `llm_judge` and `llm_rubric`
are the documented exceptions — the model is non-deterministic, so two `eval` calls on
the same evidence with a configured key may produce different scores.

Running `eval` twice on the same evidence tree:
- benchmark: guaranteed same scores (script is deterministic)
- human_annotation: guaranteed same scores (annotation file is read-only input)
- llm_judge (no key): guaranteed same scores (PENDING)
- llm_judge (with key): may differ (model non-determinism)
- llm_rubric (no key): guaranteed same scores (PENDING)
- llm_rubric (with key): may differ (model non-determinism)

### 14b.1 llm_rubric: fourth evaluation method (v1.1)

`llm_rubric` scores each trace record across multiple named dimensions from a
rubric file, combines them by normalised weight into a 0–100 total, and stores
per-dimension detail in the score record's `dimensions` field. The method is
the v1-native port of Stack A's `grader.py` capability.

**Configuration.** Uses the same `AHL_JUDGE_*` env vars as `llm_judge` (same
judge model). Honesty contract is identical: no key → PENDING (never a
fabricated score); LLM call failure or unparseable reply → ERROR (surfaced,
not silently suppressed). The rubric file must contain a dimensions+weights
table — a missing or malformed table is a review-stage ERROR (`rubric_invalid`
/ `rubric_missing_dimensions`) caught before any run.

**Whole-conversation scoring.** When a trace record carries a `transcript`
(multi-turn execution), the prompt presents the whole conversation (`[CONVERSATION]`
expanded turn by turn) — every agent turn counts, not just the first. Single-turn
records use `[CASE INPUT]` / `[AGENT OUTPUT]`. Scoring math (worst-wins
aggregation, per-record scores, existing `compare` and `report` paths) is unchanged.

**Rubric-guidance caveat.** Scoring the whole conversation changes the comparison
baseline vs scoring only the first turn. An A/B conclusion produced under rubric
version X must NOT be compared against one produced under rubric version Y — the
judging unit and/or criterion changed, so the baselines differ. Revising a rubric
mid-experiment starts a new, incomparable baseline; do not blend scores across
different rubric versions or different rubric口径.

### 14c. Exit-code contract for eval

`eval` exits `3` when any evaluation track lands in `status: error` after the recompute
(`HLAB_EVAL_ERROR` on stderr). Pending tracks and failed tracks exit `0` — identical
semantics to `run`'s evaluation half. Missing evidence exits `1` (`HLAB_MISSING_EVIDENCE`
on stderr — preflight class, not a runtime failure).

**`eval --trial N` with no evidence for that trial**: exits `1` with
`HLAB_MISSING_EVIDENCE` naming the trial. Nothing is written. This prevents fabricated
verdicts from empty evidence (the case where a trial number was requested but never run).

### 14d. Per-trial scoring (v1.1 PR5)

When `execution.trials: N > 1`, `hlab run` evaluates inline after EACH trial with that
trial's number. Score records for trial >= 1 carry an optional `trial` field; trial-0
records have no `trial` field (byte-identity contract, mirrors traces). This means:

- `hlab compare` derives `trial_count` from score records actually present (not from
  traces), so it never overstates the count if only some trials were scored.
- `aggregation_stats` (mean / stddev / win_rate etc.) are computed over real per-trial
  score vectors — stddev is structurally non-zero when scores genuinely vary across trials.
- Per-trial score records are trial-scoped: re-running `eval` for trial N drops only trial
  N's records and re-appends new ones, leaving other trials' records intact.

Latest-trial selection is **global across all trace files**: the highest trial number seen
in any trace file determines the target trial, then all files are filtered to that number.
This prevents cross-file trial mixing when multiple runtimes' files end at different heights.

### 14e. Issues accumulation (v1.1 PR5)

`evidence/issues.jsonl` accumulates across trials (append semantics). Issues for trial >= 1
carry an optional `trial` field (same convention as traces). Trial-0 issues have no `trial`
field. `--fresh` is the only sanctioned wipe.

The exit-code contract for `hlab run` judges only THIS invocation's in-memory issues (all
trials in this one command), not the full accumulated historical file. The Inspector's
deduplication prevents double-counting across re-runs.

### 14f. Errored-case judging (v1.1 PR5)

Trace records with `ok: false` (partial transcript, connector failure, turn error) are
excluded from `llm_judge` and `llm_rubric` judging — exactly the same as single-turn
errored records. The partial transcript persists in evidence (immutability contract) but
is not scored as if the case completed. This ensures scoring parity between single-turn and
multi-turn errored cases.

### 14g. Human annotation trial binding (v1.1)

Annotation files are not trial-scoped in v1.1. The human annotates whatever trial they
reviewed. When `eval --trial N` adopts an annotation, the resulting score record carries
`trial: N` (the trial it was adopted INTO). An operator who runs `eval --trial N` with an
annotation written about a different trial is on notice that the annotation may not match
the evidence. Per-trial annotation files are a v1.2 feature.

## 15. Multi-turn Execution (v1.1)

Status: **v1.1 contract.** v1.0 Auto Mode dispatches `single_turn` only; this
section specifies how Auto Mode drives multi-turn cases from v1.1 on. The
`single_turn` path is frozen: its dispatch, trace records, and evidence layout
stay byte-for-byte identical (pinned by regression tests).

### 14.1 Simulator types

The user side of a multi-turn case is driven by the experiment's `simulator`
(schema: [`experiment-yaml-schema.md`](experiment-yaml-schema.md) §14a). Three
multi-turn types:

```text
role_play   an LLM plays the user, following a designed four-section policy
            card (Persona / Background / Strategy / Stop); needs AHL_SIM_*
scripted    a deterministic playbook of scripted follow-ups — a user-designed
            mock; zero LLM calls, zero keys
script      an external program decides the next user turn (fully custom
            logic, e.g. conditional follow-ups) — protocol in §14.8
```

`single_turn` stays the default and is not a multi-turn type. The simulator
(follow-up strategy or playbook) is a **designable, first-class object** of the
experiment — there is no hardcoded stub.

### 14.2 Session lifecycle: per-case fresh session

When `simulator.type ∈ {role_play, scripted, script}`, Auto Mode starts a
**fresh connector session per case** (the same code path the `reset` state
policy uses). Rationale: a multi-turn conversation requires the agent process
to keep THIS case's context across turns; reusing one process across cases
would let conversation state leak between cases — the single-turn "stateless
per send" assumption does not hold in multi-turn.

Consequently, under multi-turn the isolation unit of `state_policy: isolated`
is redefined as the **case**: isolation means "no state crosses a case
boundary", not "no state inside the case". Single-turn `isolated` semantics
are unchanged. When `AHL_SIM_STUB=1` forces the scripted path (§14.5), session
semantics are unchanged — still a fresh session per case.

Multi-turn dispatch requires a session-capable connector: **`local_cli` only**.
The `script` connector spawns one fresh process per case with no turn IPC, so
it cannot keep a conversation — review rejects the combination with a
`simulator_connector_unsupported` ERROR (left-shifted; `hlab run` blocks at the
gate). If the combination still reaches dispatch (e.g. the runtime spec changed
after review), the run records a `connector_failure` issue and skips that
runtime — an honest failure, never a silent single-turn downgrade.

### 14.3 Turn loop contract

```text
turn 0      send the case input (the opening turn)
turn n > 0  next = simulator(transcript); send next
stop        the simulator returns None ("the user is done"), or the turn
            budget is reached — the loop is capped at max(1, max_turns)
```

- `transcript` is the list of completed turns: `[{turn, user, agent}, ...]`,
  `turn` numbered from 0.
- The loop always executes at least one turn (`max(1, max_turns)` capping).
- If `simulator.max_turns` is omitted, the default is defined by the schema
  (**8** — see [`experiment-yaml-schema.md`](experiment-yaml-schema.md) §14a).

### 14.3a role_play completion: end-token contract

A `role_play` simulator signals that the conversation is complete by returning a
reply that **starts with** one of the two bilingual end tokens:

```text
"结束"   Chinese end token (legacy single-token contract, retained)
"END"    English end token (v1.1 addition — makes English personas usable)
```

The check is: `reply.strip().startswith(token)` for each token in order. The
match is **exact prefix**, **not** case-insensitive: `"end"` does not match
`"END"`. Leading whitespace is stripped before the check; trailing text after the
token is allowed (e.g. `"END — conversation covered."` ends the case). When
either token matches, the simulator returns `None` and the turn loop ends.

The `Stop` section of the policy card provides the "asked enough" criterion in
natural language for the LLM to evaluate; the end-token emission is the
*mechanism* by which it signals that criterion is satisfied. If `max_turns` is
reached the loop also ends regardless of the simulator's return value.

### 14.4 Partial transcript contract

If a turn raises mid-case (connector death, turn timeout, simulator failure),
the turns already collected are **not** discarded: the trace record is written
with the partial `transcript` plus an `error` field, and the raw output
collected so far is kept. Evaluation later sees exactly what happened up to
the failure, never a silently empty case.

### 14.5 role_play without a key (no-key behavior)

`role_play` needs `AHL_SIM_BASE_URL` / `AHL_SIM_MODEL` / `AHL_SIM_API_KEY`
(optional `AHL_SIM_TIMEOUT`, seconds — same shape as the `AHL_JUDGE_*` family).
Without a key, the run records a `simulator_unconfigured` **error**-severity
issue and skips dispatch for that runtime — **never a fabricated follow-up**
(the same honesty contract as `llm_judge`'s no-key `pending`). An
error-severity issue means `hlab run` exits `3`.

Escape hatch: setting `AHL_SIM_STUB=1` forces the run onto the `scripted`
playbook path (deterministic, key-free) so CI and smoke runs can exercise the
multi-turn loop. A forced run's trace records carry `simulator: "scripted"`
plus `forced: true`, so playbook output can never be mistaken for real
LLM-simulated data.

### 14.6 Trace records (additive)

Single-turn trace records are byte-for-byte unchanged. A multi-turn trace
record keeps every single-turn key with remapped semantics — `input` = the
opening turn, `response` = the final agent reply, `ok` = no turn errors and a
non-empty final reply — and adds:

```text
turns        int — number of completed turns
transcript   [{turn, user, agent}, ...]
simulator    "role_play" | "scripted" | "script" (+ forced: true when
             AHL_SIM_STUB redirected the run)
```

`raw/<runtime>/<case>.out` concatenates the turns in order.

Evaluation: `llm_judge` judges a record that carries a `transcript` over the
**whole conversation** instead of the single input/output pair — the judging
unit changes; see the "Multi-turn judging" note in
[`experiment-yaml-schema.md`](experiment-yaml-schema.md) §14.

### 14.7 Auto Optimize boundary

The v1.1 optimization loop supports `single_turn` only. Two combinations are
blocked at review time with an **ERROR**:

1. `optimization.enabled: true` combined with a multi-turn simulator type →
   `optimize_multiturn_unsupported` ERROR. Otherwise an unconfigured simulator
   would fail inside the optimize loop once per iteration.

2. `optimization.enabled: true` combined with any Agent Runtime that declares
   `source:` → `optimize_source_unsupported` ERROR. Optimize mutates harness
   files in-place; source-materialized sandboxes are rebuilt per invocation, so
   mutations would be lost on the next iteration. Both features together produce
   undefined behavior.

Multi-turn and source-based runtimes inside the optimization loop are deferred
past v1.1.

### 14.8 script simulator protocol

`simulator.type: script` runs the experiment's `script:` once **per turn**:



```text
spawn    one subprocess per turn — the script runs with the same Python
         interpreter as benchmark evaluator scripts; cwd = the experiment dir
stdin    {"transcript": [...]}     the turns completed so far ({turn, user, agent})
stdout   {"next": "<message>"}     the next user turn
         {"next": null}            the user is done — end the case
```

The subprocess runs under the script connector's anti-hang hardening: stdin /
stdout / stderr are files (never pipes), the runner waits on the direct child
with a timeout (`AHL_SIM_TIMEOUT`, seconds, default 180), and the whole
process group is swept afterwards — normal exit and timeout alike. The child's
stdio is forced to UTF-8 (`PYTHONIOENCODING`) so the JSON protocol is
encoding-safe on Windows. Any failure — timeout, non-zero exit, non-JSON
stdout, a `next` that is neither string nor null — raises into the
partial-transcript contract (§14.4): the case keeps its collected turns plus
an `error`, later cases still run, and a follow-up is never fabricated. A
missing or undeclared script file makes the simulator unusable: the run
records `simulator_unconfigured` and skips dispatch (§14.5 semantics), and
`hlab review` flags the missing file (`run.mode: auto` → ERROR).

## 16. Multi-trial runs (PR5)

### 16.1 Trial semantics

A **trial** is one complete execution of the run phase (all runtimes × all
cases). Multiple trials reduce variance and make A/B comparisons more
trustworthy.

```text
execution.trials: N   run N times (default 1); part of the experiment design
hlab run --trials N   temporary override for this invocation (recorded in
                      evidence/run-metadata.json when it differs from config)
hlab run --fresh      wipe evidence/ before running — the ONLY sanctioned
                      destruction; starts a clean trial-0 run
```

### 16.2 Append-by-default evidence layout

Without `--fresh`, every `hlab run` appends evidence as a new trial (old
evidence is immutable — same iron law as PR4's read-only evidence contract):

```text
evidence/traces/<runtime>.jsonl
    all trials in the same file
    trial-0 records: no `trial` field (byte-for-byte identical to pre-v1.1)
    trial N ≥ 1: `trial: N` field present

evidence/raw/<runtime>/<case>.out      trial-0 (path unchanged)
evidence/raw/trials/<N>/<rt>/<case>    trial N ≥ 1 raw outputs
```

`--fresh` wipes the entire `evidence/` directory before the first trial and
starts at trial 0. It is a destructive operation; without it, re-runs always
append.

### 16.3 Trial read scope

```text
hlab eval                 re-evaluates the LATEST trial (highest trial number)
hlab eval --trial N       re-evaluates a specific historical trial N
hlab run (inline eval)    runs evaluation on the latest trial after all trials finish
```

Annotation backflow: `hlab eval` (with or without `--trial N`) works on
whichever trial's records match — annotations written for a specific trial's
cases will be picked up when that trial is evaluated.

### 16.4 Cross-trial aggregation

When `n_trials > 1`, `hlab compare` emits per-harness aggregation stats across
trials (configured by `execution.aggregation`):

```text
mean      average score across trials
stddev    population std dev across trials
min_max   min and max score across trials
median    median score across trials
win_rate  fraction of trials where this harness beats the other(s)
```

`win_rate` tie-breaking: per trial, compare by mean score; if equal, by pass
rate; if still equal, it is a tie (counted in neither side's wins). The `rate`
field is `wins / total_trials`.

## §15. Pre-run Materialize (PR6, v1.1)

When an Agent Runtime spec declares a `source:` section, AHL materializes the
runtime's working directory before dispatch:

```
for each runtime with source::
  remove sandbox/<runtime_id>/ if it exists (rebuild-per-invocation)
  local_path  → copytree source.path → sandbox/<runtime_id>/
  git_repo    → git clone source.url → sandbox/<runtime_id>/
                git checkout source.ref
                record commit_sha (rev-parse HEAD)
  harness_package → verify expected_fingerprint (if declared)
                     install package payload → sandbox/<runtime_id>/
  apply source.patch.files (overwrite targets in sandbox)
  merge source.patch.env into connector subprocess env (this runtime only)
  redirect connector.working_dir → sandbox/<runtime_id>/
  write evidence/snapshots/<runtime_id>.json
```

### §15.1 Materialize position in the run lifecycle

Materialize happens **once per `run_auto` call**, before the per-case dispatch
loop. The sandbox is **rebuilt fresh on every invocation** — any pre-existing
`sandbox/<runtime_id>/` is removed before materializing. Within a single invocation
all trial iterations share the sandbox that was materialized at the start of that call.

This means:

- Multi-trial runs (PR5): all trials within one invocation share one materialized
  sandbox — materialize runs once per invocation, not once per trial.
- Consecutive invocations (e.g., running `hlab run` twice): the sandbox is rebuilt
  each time. The snapshot is rewritten on each invocation.
- `--fresh` additionally wipes `evidence/` before materializing — use it to start
  a clean trial-0 run. Without `--fresh`, evidence accumulates (PR5 append semantics)
  but the sandbox is still rebuilt.

Note on Windows: sandbox removal uses `robust_rmtree` (chmod-retry on PermissionError)
to handle read-only files left by `.git/objects`. If sandbox removal fails, the run
aborts with exit 1 before touching evidence (fail-closed).

### §15.2 Sandbox layout

```text
experiments/<id>/sandbox/<runtime_id>/   materialized runtime files
```

The sandbox is preserved across trials as part of the evidence chain.
The only sanctioned way to destroy it is `hlab run --fresh`.

### §15.3 Failure semantics

Any materialize failure (missing source dir, git clone failure, fingerprint
mismatch, patch apply error) is recorded as a `connector_failure` issue with
`severity: error`. The runtime is skipped for dispatch (no cases run against it).
The failure triggers exit 3 via the standard `HLAB_RUNTIME_FAILURE` contract.

A `HLAB_RUNTIME_FAILURE: materialize failed for runtime <id>: <reason>` line is
written to stderr for each failed materialize, consistent with existing error code
conventions.

### §15.4 Snapshot schema

Snapshots written by materialize use the existing v0.4 schema (no schema change).
Key fields:

```json
{
  "snapshot_id": "snap-<runtime_id>",
  "run_id": "<experiment_id>",
  "variant_id": "<runtime_id>",
  "experiment": "<experiment_dir_name>",
  "created_at": "<UTC ISO>",
  "runtime_source": {
    "type": "local_path|git_repo|harness_package",
    "path": "...",
    "source_dir_hash": "sha256:...",
    "commit_sha": "..."          // git_repo only
  },
  "harness_patch": {             // null if no patch declared
    "applied": [...],
    "env": {...},
    "patch_hash": "sha256:..."
  },
  "sandbox": {"type": "copy_dir|git_clone|harness_package", "path": "..."},
  "environment": {"python_version": "...", "os": "...", "captured_at": "..."},
  "harness_package": null
}
```

`evidence.py` consumes this schema as-is to infer evidence strength levels
(`strong / medium / weak / unknown`) — see `evidence.py:infer_evidence_from_snapshot`.

### §15.5 git operations

git operations use a file-redirection pattern: stdout and stderr are directed to
temp files (never pipes), then `Popen.wait(timeout=AHL_GIT_TIMEOUT)` is called.
On `TimeoutExpired` the process and its group are swept (`taskkill /F /T` on
Windows, `os.killpg(SIGKILL)` on POSIX) before raising. This avoids the Windows
deadlock where `subprocess.run(capture_output=True, timeout=N)` can hang because
`communicate()` blocks on the pipe buffer.

Environment: `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, `GIT_ASKPASS=echo`,
`GIT_SSH_COMMAND=ssh -o BatchMode=yes` — credential prompts always get `echo`
output (empty) or BatchMode rejection rather than blocking on a terminal.

Timeout: configurable via `AHL_GIT_TIMEOUT` (default 120s).

A missing `git` binary or unreachable remote fails cleanly with a `RuntimeError`
(not a hang).

## §16. Gate-Stage Source Health Checks (PR8, v1.1)

### §16.1 Position in the experiment loop

`hlab review` is the **gate stage** of the experiment loop (before `hlab run`).
In v1.1, the gate stage runs in two phases:

```text
Phase 1 — static validation:   schema, file references, connector types
Phase 2 — source health checks: read-only inspection of declared source: sections
```

Phase 2 runs only when at least one Agent Runtime declares `source:`. Runtimes
without a `source:` section are unaffected — their review behavior is
byte-identical to pre-v1.1.

### §16.2 Read-only contract

The source health check is **strictly read-only**:

- No sandbox is created under `sandbox/`
- No evidence is written under `evidence/`
- For `git_repo`, only `git ls-remote` is run — no clone
- No package is installed
- No files are mutated

Running `hlab review` any number of times has no side effects on the experiment
directory.

### §16.3 What is checked per source type

| Source type | Checks |
|-------------|--------|
| `local_path` | directory exists; is a directory; readable (iterdir); patch `files[].source` entries exist |
| `git_repo` | `git` binary in PATH; `git ls-remote <url> [ref]` succeeds; ref resolves to a non-empty SHA |
| `harness_package` | directory exists; is a directory; `expected_fingerprint` (if declared) matches actual hashes; patch `files[].source` entries exist |

Patch file existence checks for `local_path` and `harness_package` were deferred
from PR6's `parse_source_spec` (where only schema shape is validated); they land
here in PR8.

### §16.4 probe↔snapshot binding (closes roadmap deferred item)

The fingerprints emitted by the source health check are computed with the
**same functions** that `materialize_v1` uses during `hlab run`:

- `local_path`: `source_dir_hash` via `compute_dir_hash` (hash_utils.py)
- `git_repo`: resolved remote SHA via `git ls-remote` output
- `harness_package`: `manifest_hash` + `dir_hash` via `_verify_harness_package_fingerprint`

This closes the roadmap's deferred probe↔snapshot binding item (previously
noted in `temp/v0.10.0-planning.md:417`): review health-check results are now
reconcilable with run-time snapshot fingerprints in `evidence/snapshots/<rt>.json`.

To reconcile:

```text
hlab review emits            →  evidence/snapshots/<rt>.json after run
---------------------------------------------------------------------
source_dir_hash              →  runtime_source.source_dir_hash
remote SHA (git_repo)        →  runtime_source.commit_sha
manifest_hash (pkg)          →  harness_package.manifest_hash
```

A mismatch after a run indicates the source changed between review and run time
(e.g., a local_path directory was modified, or a git repo was force-pushed).

### §16.5 Performance note

For `local_path` sources, `source_dir_hash` is computed only when the total
source directory size is below 256 MiB. Above this cap, hashing is skipped
with a WARN-level `probe_source_hash_skipped` issue; existence and readability
are still confirmed. The hash is informational for reconciliation — the
existence/readability check is the actual gate.
