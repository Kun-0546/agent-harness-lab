"""v1 workspace / experiment scaffolding (templates + directory creation).

Public term is `harness` throughout. `hlab init` builds the workspace;
`hlab new` builds an experiment tree whose experiment.yaml is a valid minimal
spec that reviews with no ERROR (Auto Mode with a not-yet-implemented state
policy may WARN).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_harness_lab.experiment_spec import make_experiment_id

# --- workspace-level templates ----------------------------------------------

GOAL_TEMPLATE = """# Goal — <one-line long-term goal>

Workspace-level goal. It stays valid across many experiments.

## 1. Target agent

<Which agent does this workspace try to improve? Its role and typical use.>

## 2. Behavior to improve

<Which behaviors are unsatisfactory? Write them as real case types.>

## 3. Current baseline

<What is the comparison point today? e.g. a prompt version, a commit, a
production version, a manual process.>

## 4. Harness hypotheses

<Which harness layer do you think should change first, and why?
A harness is any design unit that changes how an agent runs: skill, memory
mechanism, context strategy, agent configuration, runtime patch, tool/plugin
setup, prompt bundle, execution script, runtime constraint.>

## 5. Success criteria

<What would count as success for this workspace?>

## 6. Red lines

<Which dimensions must not regress? e.g. safety, factuality, latency, cost.>
"""

EVAL_METHOD_HUMAN_ANNOTATION = """# Evaluation method: human_annotation

How humans judge experiment results.

## When to use
- Quality is subjective or hard to specify mechanically.
- A small number of high-value cases warrant careful human reading.

## Procedure
<How a human reviews a transcript/artifact and records a verdict.>

## Output
<Where annotations are written, e.g. evidence/inspections/.>
"""

EVAL_METHOD_LLM_JUDGE = """# Evaluation method: llm_judge

An LLM scores outputs against a rubric.

## Inputs
- A rubric (evaluation/rubrics/<name>.md): dimensions + weights.
- The canonical transcript and/or artifacts.

## Anti-inflation discipline
- 5-6 is the baseline; 8+ requires concrete, quoted evidence.
- Abstract praise without evidence caps at 6.

## Output
- Per-dimension scores -> evidence/scores/.
"""

EVAL_METHOD_BENCHMARK = """# Evaluation method: benchmark

A deterministic, scriptable check (pass/fail or task-success metrics).

## When to use
- Objective, reproducible criteria (e.g. did the produced artifact build/run).

## Output
- Benchmark results -> evidence/scores/.
"""

# --- experiment-level templates ----------------------------------------------

EXPERIMENT_MD_TEMPLATE = """# Experiment — {id}

Human-readable experiment plan. `experiment.yaml` is the machine source of
truth; this file is where you think the experiment through in prose. Each
section is a question to answer, not a placeholder to leave blank.

## Why are we running this experiment?
<The question in one or two sentences. What decision will the result inform?
Tie it to a real behavior you want to change, not a vanity metric.>

## Which long-term goal does it serve?
<Which part of goal.md this advances. (experiment.yaml `goal_ref` points to it.)>

## Which harnesses are compared?
One line per harness describing the design difference; mark the baseline.
Full detail goes in each harnesses/<id>/README.md.
  A: <what A is>  (baseline?)
  B: <what B changes vs A>

## Which Agent Runtimes are used?
<Which real runtime each harness runs in (see agent-runtimes/). Same runtime for
both isolates the harness as the only variable; different runtimes means you are
also comparing environments — say which and why.>

## Which cases are run?
<What inputs exercise the behavior difference (see cases/cases.jsonl). If every
case makes A and B behave the same, the experiment has no signal — choose cases
that can actually separate them.>

## How is evaluation designed?
<How good/bad is judged, decided before the run (see evaluation/evaluation.md):
which of human_annotation / llm_judge / benchmark, and against what rubric.>

## What evidence must be collected?
<What the run must capture to be trustworthy (see `collection` in
experiment.yaml): traces, raw output, produced artifacts, scores.>

## What requires human review?
<Which judgments you will not delegate: rubric calibration, the final
conclusion, any red-line dimension that must not regress.>

## When should the result be considered invalid or weak?
<Name, up front, the conditions that would make you distrust the result: empty
output, fake precision, contaminated state, too few cases, judge disagreement,
runtime mismatch. These map to `inspection.issue_checks` in experiment.yaml.>
"""

# {id}, {question}, {run_mode}, {execution_mode}, {state_policy} filled by new_experiment().
# id is quoted so digit-only / YAML-reserved ids (007, 2026, yes, null) stay strings.
EXPERIMENT_YAML_TEMPLATE = """id: "{id}"
status: draft

goal_ref: ../../goal.md
question: "{question}"

run:
  mode: {run_mode}

execution:
  mode: {execution_mode}
  state_policy: {state_policy}

harnesses:
  - id: A
    name: harness-a
    path: harnesses/A/
  - id: B
    name: harness-b
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

# How the user side of multi-turn cases is driven. single_turn (Auto v1) sends
# each case input once. Other types: script (cases/simulator.py) and role_play
# (actor + policy) — see docs.
simulator:
  type: single_turn

evaluation:
  root: evaluation/
  # Evaluators are experiment-local configured evaluators built from a workspace
  # Evaluation Method (see ../../evaluation-methods/). script/rubric are relative
  # to evaluation.root.
  evaluators:
    - id: artifact_exists
      method: benchmark
      script: benchmarks/check_artifact_exists.py
    - id: skill_quality
      method: llm_judge
      rubric: rubrics/skill_quality.md
    - id: human_skill_review
      method: human_annotation
      rubric: rubrics/human_skill_review.md
  # Tracks are experiment-local groupings of evaluators + the evidence each needs.
  # Tracks do not replace evidence; the run must still write evidence/.
  tracks:
    - id: skill-artifact
      question: "Did the harness produce a usable skill artifact?"
      evaluators:
        - artifact_exists
        - skill_quality
        - human_skill_review
      evidence:
        - artifacts
        - traces
        - raw

collection:
  traces: true
  raw: true
  artifacts: true
  snapshots: false
  scores: true

inspection:
  artifact_review: true
  skill_review: false
  memory_review: false
  context_review: false
  issue_checks:
    - missing_artifact
    - empty_output
    - case_failure

reports:
  formats:
    - md
"""

AGENT_RUNTIME_TEMPLATE = """# Agent Runtime spec for "{runtime_id}".
# An Agent Runtime is the real environment the tested agent runs in. This file
# tells AHL how to drive it and what artifacts it may produce. Connector
# EXECUTION is implemented in a later phase (Auto Mode); `hlab review` validates
# the connector `type` (and, in Auto Mode, that it is supported).

id: {runtime_id}

connector:
  # Copilot Mode default is `manual` (an external agent drives the runtime).
  # Auto Mode v1 supports `local_cli` and `script`. `remote_devbox` / `api` /
  # `bridge` may be declared but are NOT executed in v1.
  type: {connector_type}

  # Used by local_cli / script (Auto Mode). For `manual`, an external agent runs
  # the runtime and these fields are ignored.
  command: "python run_agent.py"
  working_dir: "./{runtime_id}"      # resolved relative to the experiment dir
  input_mode: stdin_json             # one JSON object per line on stdin/stdout
  timeout: 60                        # per-turn seconds before a connector failure

# Artifacts the runtime may produce. Declare only WHAT (id / kind / glob /
# required); AHL's EvidenceCollector archives them under evidence/artifacts/ —
# you do NOT specify a destination path here. `glob` is relative to
# connector.working_dir; `required: true` means a missing artifact later becomes
# an evidence issue.
artifacts:
  collect:
    - id: generated_skill
      kind: skill
      glob: "outputs/skill/**"
      required: true
"""

HARNESS_README_TEMPLATE = """# Harness {hid}

A harness is any design unit that changes how the agent runs, behaves, or
performs (prompt bundle, skill, memory mechanism, config, runtime patch,
tool/plugin setup, execution script, runtime constraint). Fill in the five
sections below so a reader knows exactly what this harness is and how it runs.

## What this harness changes
<One or two sentences. What is different about this harness compared with the
others? If this is the baseline / reference, say so explicitly.>

## Source / config / prompt / skill location
<Where the harness material actually lives: files in this directory, a path
inside the Agent Runtime, a specific prompt or skill file, a config key, a
patch. Be concrete enough that someone else could find it.>

## How it is applied to the Agent Runtime
<How does this harness get into the runtime listed in experiment.yaml? e.g.
copied into the runtime working_dir, set via an env var or config key, applied
as a patch, loaded as a skill. (Auto Mode applies this automatically in a later
phase; describe the intended application now.)>

## Expected artifacts
<What running this harness should produce: a created skill folder, a generated
file, a memory write, etc. These are what evidence/artifacts/ will hold and what
inspection will look for — so be specific about paths/names.>

## Known risks / failure modes
<What could make a run with this harness invalid or misleading? e.g. empty
output, fake precision (numbers reported with no real output), path drift,
contaminated/leaked state, nondeterminism.>
"""

CASES_JSONL_SEED = (
    '{"id": "case-001", "input": "Replace with the first case input.", '
    '"tags": ["example"]}\n'
)

EVALUATION_MD_TEMPLATE = """# Evaluation design

How results of this experiment are judged. Evaluation is designed *before* the
run, so the bar is set independently of the outputs. v1 models evaluation in
three layers (see `experiment.yaml: evaluation`).

## 1. Evaluation Methods (workspace level)
Reusable method recipes live in `../../evaluation-methods/`:
- **human_annotation** — a human reads transcripts/artifacts and records a verdict.
- **llm_judge** — an LLM scores outputs against a rubric; keep an anti-inflation
  discipline (a high score needs quoted evidence).
- **benchmark** — a deterministic, scriptable check (pass/fail or task-success).

## 2. Evaluators (this experiment)
Configured instances under `evaluation.evaluators` — each binds a method to a
concrete `script` (benchmark) or `rubric` (llm_judge / human_annotation). Fill in
the referenced files under `benchmarks/` and `rubrics/`. `hlab review` warns if a
referenced script/rubric is missing, and warns if human_annotation is used but
this file is absent.

## 3. Tracks (this experiment)
`evaluation.tracks` group evaluators around a question and name the evidence each
needs (traces / raw / artifacts / snapshots / scores / inspections / issues).
Tracks are experiment-local and do NOT replace evidence — the run must still
write evidence/.

## What counts as a weak or invalid result
<Name the conditions that make a result untrustworthy for THIS experiment.
Line them up with the `inspection.issue_checks` in experiment.yaml.>
"""

BENCHMARK_SEED_TEMPLATE = '''"""Benchmark evaluator: artifact_exists (placeholder).

A benchmark is a deterministic, scriptable check (pass/fail or a metric). This
runs at the Evaluation phase (later) over collected evidence under evidence/ and
records a score. Replace the body with the real check.
"""
# TODO: inspect evidence/artifacts/ for the expected skill artifact and decide
# pass/fail, then write a score record under evidence/scores/.
'''

RUBRIC_SKILL_QUALITY_TEMPLATE = """# Rubric: skill_quality (llm_judge)

Score the produced skill artifact against these dimensions. 5-6 is baseline; 8+
needs concrete, quoted evidence from the artifact/trace.

- **Usability** (weight: ?) — can the skill be used as-is? <top vs bottom>
- **Correctness** (weight: ?) — does it do what it claims? <top vs bottom>
- **Reusability** (weight: ?) — is it generic enough to reuse? <top vs bottom>
"""

RUBRIC_HUMAN_SKILL_REVIEW_TEMPLATE = """# Rubric: human_skill_review (human_annotation)

A human reads the produced skill + its trace and records a verdict. Use for the
judgments you will not delegate.

- What to read: evidence/artifacts/<runtime>/, evidence/traces/<runtime>.jsonl
- Verdict to record: <accept / revise / reject> + one-line rationale
- Record under: evidence/inspections/
"""

CONCLUSION_MD_TEMPLATE = """# Conclusion — {id}

Human final conclusion. Fill this in after reading reports/report.md and the
evidence under evidence/.

## Human conclusion
<Your conclusion, in plain language: what did this experiment actually show?>

## Rationale
<Why you reached that conclusion.>

## Evidence relied on
<Which evidence you trusted and used: specific traces / scores / artifacts /
inspections. Point to files under evidence/.>

## Evidence not trusted
<Which evidence you discounted, and why: weak reproducibility, fake precision
(numbers reported on empty output), contaminated/leaked state, missing
artifacts, judge disagreement, too few cases, etc.>

## Next step
<What to run or change next — keep this harness, drop it, iterate, or change
the experiment design.>
"""

# --- builders ----------------------------------------------------------------

_EVIDENCE_SUBDIRS = ("traces", "raw", "artifacts", "snapshots", "scores", "inspections")
# default state policy per execution mode (longitudinal accumulates state;
# replay re-evaluates existing evidence; ab/sequential isolate each run)
_STATE_POLICY_BY_EXECUTION = {
    "ab": "isolated", "sequential": "isolated",
    "longitudinal": "cumulative", "replay": "replay",
}


@dataclass
class InitResult:
    root: Path
    created: list[str]


def init_workspace(root: Path) -> InitResult:
    """Create the v1 workspace: goal.md + evaluation-methods/ + experiments/ + .hlab/.
    Idempotent: existing files are left untouched."""
    created: list[str] = []

    def _write(rel: str, content: str) -> None:
        p = root / rel
        if p.exists():
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        created.append(rel)

    def _mkdir(rel: str, keep: bool = False) -> None:
        p = root / rel
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(rel + "/")
        if keep and p.is_dir() and not any(p.iterdir()):
            (p / ".gitkeep").write_text("", encoding="utf-8")

    _write("goal.md", GOAL_TEMPLATE)
    _write("evaluation-methods/human_annotation.md", EVAL_METHOD_HUMAN_ANNOTATION)
    _write("evaluation-methods/llm_judge.md", EVAL_METHOD_LLM_JUDGE)
    _write("evaluation-methods/benchmark.md", EVAL_METHOD_BENCHMARK)
    _mkdir("experiments")            # will hold experiment subdirs; no .gitkeep
    _mkdir(".hlab", keep=True)       # workspace marker / reserved tool-state dir
    return InitResult(root, created)


@dataclass
class NewResult:
    experiment_dir: Path
    experiment_id: str
    created: list[str]


def new_experiment(root: Path, name: str, run_mode: str = "copilot",
                   execution_mode: str = "ab", question: str | None = None) -> NewResult:
    """Create experiments/<name>/ with a valid v1 tree that reviews with no ERROR.

    The directory name is the normalized (kebab-case) id, so dir == id.
    Raises ValueError if the name has no usable [a-z0-9], FileExistsError if the
    experiment already exists.
    """
    exp_id = make_experiment_id(name)
    if not exp_id:
        raise ValueError(
            f"experiment name must contain ASCII letters or digits (a-z, 0-9); got {name!r}")
    # the id IS the directory name (so the on-disk dir and the experiment.yaml
    # id never diverge, and path separators / '.'/'..' in the name cannot escape)
    exp_dir = root / "experiments" / exp_id
    if exp_dir.exists():
        raise FileExistsError(f"experiment already exists: experiments/{exp_id}")
    created: list[str] = []

    def _write(rel: str, content: str) -> None:
        p = exp_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        created.append(rel)

    def _mkdir(rel: str) -> None:
        p = exp_dir / rel
        p.mkdir(parents=True, exist_ok=True)
        created.append(rel + "/")
        if not any(p.iterdir()):  # keep empty scaffolded dirs under version control
            (p / ".gitkeep").write_text("", encoding="utf-8")

    q = question or f"<one-line question for experiment {exp_id}>"
    state_policy = _STATE_POLICY_BY_EXECUTION.get(execution_mode, "isolated")
    _write("experiment.md", EXPERIMENT_MD_TEMPLATE.format(id=exp_id))
    _write("experiment.yaml", EXPERIMENT_YAML_TEMPLATE.format(
        id=exp_id, question=q, run_mode=run_mode, execution_mode=execution_mode,
        state_policy=state_policy))
    # harnesses A / B
    _write("harnesses/A/README.md", HARNESS_README_TEMPLATE.format(hid="A"))
    _write("harnesses/B/README.md", HARNESS_README_TEMPLATE.format(hid="B"))
    # agent runtimes: Copilot Mode → manual (external agent drives it);
    # Auto Mode → local_cli (a v1-supported connector). Never default to
    # remote_devbox/api/bridge.
    connector_type = "manual" if run_mode == "copilot" else "local_cli"
    _write("agent-runtimes/runtime-a.yaml",
           AGENT_RUNTIME_TEMPLATE.format(runtime_id="runtime-a", connector_type=connector_type))
    _write("agent-runtimes/runtime-b.yaml",
           AGENT_RUNTIME_TEMPLATE.format(runtime_id="runtime-b", connector_type=connector_type))
    # cases
    _write("cases/cases.jsonl", CASES_JSONL_SEED)
    _mkdir("cases/datasets")
    # evaluation (three layers: methods at workspace level; evaluators + tracks here).
    # Write the files the scaffold's evaluators reference so a fresh experiment
    # reviews with no missing-ref warning.
    _write("evaluation/evaluation.md", EVALUATION_MD_TEMPLATE)
    _write("evaluation/benchmarks/check_artifact_exists.py", BENCHMARK_SEED_TEMPLATE)
    _write("evaluation/rubrics/skill_quality.md", RUBRIC_SKILL_QUALITY_TEMPLATE)
    _write("evaluation/rubrics/human_skill_review.md", RUBRIC_HUMAN_SKILL_REVIEW_TEMPLATE)
    _mkdir("evaluation/graders")
    # evidence store
    for sub in _EVIDENCE_SUBDIRS:
        _mkdir(f"evidence/{sub}")
    _write("evidence/issues.jsonl", "")
    # reports + conclusion
    _mkdir("reports")
    _write("conclusion.md", CONCLUSION_MD_TEMPLATE.format(id=exp_id))
    return NewResult(exp_dir, exp_id, created)
