"""experiment.yaml -> ExperimentSpec (v1 machine source of truth).

Parses and validates an experiment's `experiment.yaml` per
`docs/experiment-yaml-schema.md`. Also loads Agent Runtime specs
(`agent-runtimes/*.yaml`) and case sets (`cases/*.jsonl`).

This is v1 surface. It uses the public term `harness` (never `variant`).
The old v0.10 markdown parsers (program.py / version.py / ...) remain
internal and untouched during migration; nothing here imports them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent_harness_lab import mdutil, user_sim

# --- allowed value sets (docs/experiment-yaml-schema.md) ---------------------

STATUS_VALUES = {
    "draft", "ready", "running", "collected",
    "evaluated", "reported", "concluded", "invalid",
}
RUN_MODES = {"copilot", "auto"}
EXECUTION_MODES = {"ab", "sequential", "longitudinal", "replay"}
STATE_POLICIES = {"isolated", "reset", "cumulative", "snapshot_branch", "replay"}
AUTO_V1_STATE_POLICIES = {"isolated", "reset"}
# valid aggregation statistics for execution.aggregation (PR5 5b)
AGGREGATION_VALUES = {"mean", "stddev", "min_max", "median", "win_rate"}
AGGREGATION_DEFAULT = ["mean", "stddev", "win_rate"]
CONNECTOR_TYPES = {"local_cli", "script", "remote_devbox", "api", "bridge", "manual"}
AUTO_V1_CONNECTORS = {"local_cli", "script"}
EVAL_METHODS = {"human_annotation", "llm_judge", "benchmark", "llm_rubric"}
# evidence types an evaluation track may consume (collection keys + the two
# stores that are always written: inspections output and issues.jsonl).
EVIDENCE_TYPES = {
    "traces", "raw", "artifacts", "snapshots", "scores", "inspections", "issues",
}
SIMULATOR_TYPES = {"single_turn", "script", "role_play", "scripted"}
# simulator types that drive a multi-turn conversation (v1.1): per-case fresh
# session, turn loop, partial-transcript contract (execution-model.md §14).
MULTI_TURN_SIMULATOR_TYPES = {"role_play", "scripted", "script"}
# Auto Optimize (schema/validation only here; the loop itself lives in auto_optimize.py):
# surfaces Auto must never modify unless explicitly allowed. Keyed by the leading
# path/name segment (goal.md→goal, cases/→cases, evaluation/→evaluation, etc.).
PROTECTED_SURFACE_DEFAULTS = {"goal", "cases", "evaluation", "objective", "conclusion"}
OPTIMIZE_FOR_VALUES = {"maximize", "minimize"}
ISSUE_CHECKS = {
    "missing_artifact", "empty_output", "path_drift", "runtime_mismatch",
    "missing_trace", "missing_score", "case_failure", "connector_failure",
}
REPORT_FORMATS = {"md", "html"}
# `collection`/`inspection` inner keys: shape-validated now; their semantics are
# consumed by the future EvidenceCollector / Inspector (see
# docs/v1-concept-inventory.md). Unknown keys warn (not silently ignored).
COLLECTION_KEYS = {"traces", "raw", "artifacts", "snapshots", "scores"}
INSPECTION_REVIEW_KEYS = {"artifact_review", "skill_review", "memory_review", "context_review"}
KNOWN_TOPLEVEL = {
    "id", "status", "goal_ref", "question", "run", "execution", "harnesses",
    "agent_runtimes", "cases", "evaluation", "collection", "inspection", "reports",
    "simulator", "objective", "optimization",
}

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\Z")  # \Z not $ — reject a trailing newline
# an unfilled scaffold placeholder question: the whole string is <...> (any mode)
_PLACEHOLDER_QUESTION_RE = re.compile(r"^<.*>$", re.DOTALL)

ERROR = "ERROR"
WARN = "WARN"


class ExperimentSpecError(Exception):
    """Raised when experiment.yaml cannot be read or parsed as a mapping."""


@dataclass
class Problem:
    level: str  # ERROR | WARN
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"[{self.level}] {self.code}: {self.message}"


@dataclass
class HarnessRef:
    id: str
    name: str
    path: str


@dataclass
class AgentRuntimeRef:
    id: str
    harness: str
    spec: str  # relative path to agent-runtimes/*.yaml


@dataclass
class AgentRuntimeSpec:
    """Parsed agent-runtimes/<name>.yaml.

    Accepts both shapes documented in the spec bundle:
      - top-level `type:` (experiment-yaml-schema.md §12)
      - nested `connector: {type: ...}` (execution-model.md §7)

    source: is an optional section declaring where to materialize the runtime from
    before dispatch (PR6). When present, auto.py will copytree/clone/verify into
    sandbox/<rt_id>/ and redirect the connector's working_dir there.
    """
    path: Path
    id: str | None
    connector_type: str | None
    raw: dict[str, Any]
    artifacts: list[dict] = field(default_factory=list)  # artifacts.collect[] rules
    source: "Any | None" = None  # RuntimeSourceSpec | None — parsed from source: section


@dataclass
class EvaluatorSpec:
    """An experiment-local configured evaluator (evaluation.evaluators[])."""
    id: str | None
    method: str | None  # human_annotation | llm_judge | benchmark
    script: str | None = None  # relative to evaluation.root (benchmark)
    rubric: str | None = None  # relative to evaluation.root (llm_judge / human_annotation)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrackSpec:
    """An experiment-local evaluation track: groups evaluators + expected evidence."""
    id: str | None
    question: str | None
    evaluators: list[str] = field(default_factory=list)  # evaluator ids
    evidence: list[str] = field(default_factory=list)     # evidence types
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulatorSpec:
    """How the user side of a multi-turn case is driven (optional)."""
    type: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ObjectiveSpec:
    """Auto Optimize objective: which evaluation track the bounded loop optimizes."""
    primary_track: str | None
    success_criteria: str | None
    optimize_for: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationSpec:
    """Auto Optimize boundary for the bounded, deterministic loop.

    editable_surface = what a candidate harness may change (harness-controlled only).
    protected_surface = what Auto must never change (goal/cases/evaluation/objective/
    conclusion are protected by default)."""
    enabled: bool
    editable_surface: list[str] = field(default_factory=list)
    protected_surface: list[str] = field(default_factory=list)
    stop_conditions: list[Any] = field(default_factory=list)
    promotion_policy: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentSpec:
    path: Path
    id: str | None = None
    status: str | None = None
    goal_ref: str | None = None
    question: str | None = None
    run_mode: str | None = None
    execution_mode: str | None = None
    state_policy: str | None = None
    trials: int = 1                                      # execution.trials (PR5 5b)
    aggregation: list[str] = field(default_factory=lambda: list(AGGREGATION_DEFAULT))
    harnesses: list[HarnessRef] = field(default_factory=list)
    agent_runtimes: list[AgentRuntimeRef] = field(default_factory=list)
    cases_root: str | None = None
    cases_files: list[str] = field(default_factory=list)
    evaluation_root: str | None = None
    evaluation_methods: list[str] = field(default_factory=list)  # backward-compat shorthand
    evaluators: list[EvaluatorSpec] = field(default_factory=list)
    tracks: list[TrackSpec] = field(default_factory=list)
    simulator: SimulatorSpec | None = None
    objective: ObjectiveSpec | None = None
    optimization: OptimizationSpec | None = None
    collection: dict[str, Any] = field(default_factory=dict)
    inspection: dict[str, Any] = field(default_factory=dict)
    report_formats: list[str] = field(default_factory=list)
    malformed_lists: list[str] = field(default_factory=list)
    bad_entries: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


# --- parsing -----------------------------------------------------------------

def _maps_field(value: Any, key: str, malformed: list[str], bad_entries: list[str]) -> list[dict]:
    """Parse a list-of-mappings field (harnesses / agent_runtimes).

    Accepts a list of mappings, or `{}` (empty placeholder per schema §2). A
    scalar or non-empty mapping is recorded as malformed (wrong type); a list
    containing a non-mapping item is recorded in bad_entries. Nothing is
    silently dropped."""
    if value is None:
        return []
    if isinstance(value, dict):
        if not value:
            return []
        malformed.append(key)
        return []
    if not isinstance(value, list):
        malformed.append(key)
        return []
    out: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        elif key not in bad_entries:
            bad_entries.append(key)
    return out


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (but still supports the
    standard YAML `<<: *anchor` merge key).

    PyYAML's default silently keeps the last value, which can hide a real
    footgun (e.g. `mode: copilot` overwritten by a second `mode: auto`)."""


def _no_duplicate_keys(loader, node, deep=False):
    # reject duplicate EXPLICIT keys (before merge expansion); skip `<<` merge
    # keys, which construct_mapping -> flatten_mapping resolves below.
    seen = set()
    for key_node, _value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in seen
        except TypeError as e:
            # complex/unhashable mapping key (e.g. `? [a,b] :`) — stock PyYAML
            # raises here too; surface a clean YAML error, not a crash.
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                "found unhashable key", key_node.start_mark) from e
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"found duplicate key: {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def _load_yaml(text: str, path: Path):
    """Parse YAML with the strict loader. Wraps parse-time failures —
    including RecursionError (deeply nested input; a RuntimeError, not a
    YAMLError) — as ExperimentSpecError so callers never see a raw traceback."""
    try:
        return yaml.load(text, Loader=_StrictLoader)
    except (yaml.YAMLError, RecursionError) as e:
        detail = "input is too deeply nested" if isinstance(e, RecursionError) else str(e)
        raise ExperimentSpecError(f"invalid YAML in {path}: {detail}") from e


def _list_field(container: Any, key: str, label: str, malformed: list[str]) -> list:
    """Return container[key] only if it is a list; record `label` as malformed
    if a non-list scalar was given (prevents char-by-char iteration of a string)."""
    v = container.get(key) if isinstance(container, dict) else None
    if v is None:
        return []
    if isinstance(v, list):
        return v
    malformed.append(label)
    return []


def parse_experiment_yaml(path: Path) -> ExperimentSpec:
    """Read experiment.yaml into an ExperimentSpec. Raises ExperimentSpecError
    if the file is missing, not valid YAML, or not a top-level mapping."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise ExperimentSpecError(f"experiment.yaml not found: {path}") from e
    except UnicodeDecodeError as e:
        raise ExperimentSpecError(f"experiment.yaml is not valid UTF-8: {path} ({e})") from e
    except OSError as e:
        raise ExperimentSpecError(f"cannot read {path}: {e}") from e
    data = _load_yaml(text, path)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ExperimentSpecError(
            f"experiment.yaml must be a mapping at top level, got {type(data).__name__}: {path}")

    run = data.get("run") or {}
    execution = data.get("execution") or {}
    cases = data.get("cases") or {}
    evaluation = data.get("evaluation") or {}
    reports = data.get("reports") or {}

    malformed: list[str] = []
    bad_entries: list[str] = []
    harnesses = [
        HarnessRef(id=h.get("id"), name=h.get("name"), path=h.get("path"))
        for h in _maps_field(data.get("harnesses"), "harnesses", malformed, bad_entries)
    ]
    runtimes = [
        AgentRuntimeRef(id=r.get("id"), harness=r.get("harness"), spec=r.get("spec"))
        for r in _maps_field(data.get("agent_runtimes"), "agent_runtimes", malformed, bad_entries)
    ]

    # evaluation: three layers — `methods` (workspace-level shorthand, backward
    # compatible), `evaluators` (experiment-local configured evaluators), and
    # `tracks` (experiment-local grouping). list-typed fields are guarded so a
    # scalar is reported as malformed, not iterated char-by-char; nothing is
    # silently dropped.
    methods: list[str] = []
    for m in _list_field(evaluation, "methods", "evaluation.methods", malformed):
        if isinstance(m, dict) and isinstance(m.get("type"), str):
            methods.append(m["type"])
        elif isinstance(m, str):
            methods.append(m)
        elif "evaluation.methods" not in bad_entries:
            bad_entries.append("evaluation.methods")  # bare list / unhashable type / malformed item
    evaluators: list[EvaluatorSpec] = []
    for e in _list_field(evaluation, "evaluators", "evaluation.evaluators", malformed):
        if isinstance(e, dict):
            evaluators.append(EvaluatorSpec(
                id=e.get("id"), method=e.get("method"),
                script=e.get("script"), rubric=e.get("rubric"), raw=e))
        elif "evaluation.evaluators" not in bad_entries:
            bad_entries.append("evaluation.evaluators")
    tracks: list[TrackSpec] = []
    for t in _list_field(evaluation, "tracks", "evaluation.tracks", malformed):
        if isinstance(t, dict):
            _tev = t.get("evaluators")
            _tevd = t.get("evidence")
            tracks.append(TrackSpec(
                id=t.get("id"), question=t.get("question"),
                evaluators=[x for x in _tev if isinstance(x, str)] if isinstance(_tev, list) else [],
                evidence=[x for x in _tevd if isinstance(x, str)] if isinstance(_tevd, list) else [],
                raw=t))
        elif "evaluation.tracks" not in bad_entries:
            bad_entries.append("evaluation.tracks")
    # simulator (optional top-level): how the user side of multi-turn cases is driven
    _sim = data.get("simulator")
    simulator = None
    if isinstance(_sim, dict):
        simulator = SimulatorSpec(type=_sim.get("type"), raw=_sim)
    elif _sim is not None:
        bad_entries.append("simulator")
    # objective / optimization (Auto Optimize — schema/validation here; loop runs in auto_optimize.py)
    _obj = data.get("objective")
    objective = None
    if isinstance(_obj, dict):
        objective = ObjectiveSpec(
            primary_track=_obj.get("primary_track"),
            success_criteria=_obj.get("success_criteria"),
            optimize_for=_obj.get("optimize_for"), raw=_obj)
    elif _obj is not None:
        bad_entries.append("objective")
    _opt = data.get("optimization")
    optimization = None
    if isinstance(_opt, dict):
        _es, _ps, _sc = _opt.get("editable_surface"), _opt.get("protected_surface"), _opt.get("stop_conditions")
        optimization = OptimizationSpec(
            enabled=(_opt.get("enabled") is True),
            editable_surface=[x for x in _es if isinstance(x, str)] if isinstance(_es, list) else [],
            protected_surface=[x for x in _ps if isinstance(x, str)] if isinstance(_ps, list) else [],
            stop_conditions=(_sc if isinstance(_sc, list) else ([] if _sc is None else [_sc])),
            promotion_policy=(_opt.get("promotion_policy")
                              if isinstance(_opt.get("promotion_policy"), dict) else None),
            raw=_opt)
    elif _opt is not None:
        bad_entries.append("optimization")
    cases_files = _list_field(cases, "files", "cases.files", malformed)
    report_formats = [str(x) for x in _list_field(reports, "formats", "reports.formats", malformed)]

    # execution.trials / execution.aggregation (PR5 5b)
    _trials_raw = execution.get("trials") if isinstance(execution, dict) else None
    _trials = 1
    if _trials_raw is not None:
        if isinstance(_trials_raw, int) and _trials_raw >= 1:
            _trials = _trials_raw
        # else: validation happens in validate_spec
    _agg_raw = execution.get("aggregation") if isinstance(execution, dict) else None
    _agg: list[str] = list(AGGREGATION_DEFAULT)
    if isinstance(_agg_raw, list):
        _agg = [str(x) for x in _agg_raw]

    return ExperimentSpec(
        path=path,
        id=data.get("id"),
        status=data.get("status"),
        goal_ref=data.get("goal_ref"),
        question=data.get("question"),
        run_mode=(run.get("mode") if isinstance(run, dict) else None),
        execution_mode=(execution.get("mode") if isinstance(execution, dict) else None),
        state_policy=(execution.get("state_policy") if isinstance(execution, dict) else None),
        trials=_trials,
        aggregation=_agg,
        harnesses=harnesses,
        agent_runtimes=runtimes,
        cases_root=(cases.get("root") if isinstance(cases, dict) else None),
        cases_files=cases_files,
        evaluation_root=(evaluation.get("root") if isinstance(evaluation, dict) else None),
        evaluation_methods=methods,
        evaluators=evaluators,
        tracks=tracks,
        simulator=simulator,
        objective=objective,
        optimization=optimization,
        collection=data.get("collection"),  # keep raw: a falsy non-mapping (false/0/[]) must be flagged
        inspection=data.get("inspection"),  # keep raw: a falsy non-mapping (false/0/[]) must be flagged, not coerced
        report_formats=report_formats,
        malformed_lists=malformed,
        bad_entries=bad_entries,
        raw=data,
    )


def load_agent_runtime_spec(path: Path) -> AgentRuntimeSpec:
    """Parse an agent-runtimes/*.yaml. Raises ExperimentSpecError on bad YAML."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ExperimentSpecError(f"agent runtime spec is not valid UTF-8: {path} ({e})") from e
    except OSError as e:
        raise ExperimentSpecError(f"cannot read agent runtime spec {path}: {e}") from e
    data = _load_yaml(text, path) or {}
    if not isinstance(data, dict):
        raise ExperimentSpecError(f"agent runtime spec must be a mapping: {path}")
    connector = data.get("connector")
    ctype = None
    if isinstance(connector, dict):
        ctype = connector.get("type")
    if ctype is None:
        ctype = data.get("type")
    # artifacts.collect[]: declared artifacts the runtime may produce. The user
    # declares WHAT (id/kind/glob/required); EvidenceCollector decides WHERE they
    # are archived under evidence/artifacts/ — no source/target in the spec.
    arts: list[dict] = []
    _a = data.get("artifacts")
    if isinstance(_a, dict) and isinstance(_a.get("collect"), list):
        arts = [x for x in _a["collect"] if isinstance(x, dict)]
    # source: section (PR6 — optional; when present, auto.py materializes before dispatch)
    source_spec = None
    _src = data.get("source")
    if _src is not None:
        from agent_harness_lab.materialize_v1 import parse_source_spec
        try:
            source_spec = parse_source_spec(_src, path)
        except ValueError as e:
            raise ExperimentSpecError(str(e)) from e
    return AgentRuntimeSpec(path=path, id=data.get("id"), connector_type=ctype,
                            raw=data, artifacts=arts, source=source_spec)


def load_cases(cases_root: Path, files: list[str]) -> list[dict]:
    """Read JSONL case files. Raises ExperimentSpecError on bad JSON line.
    Non-string / empty file entries are skipped (validate_spec flags them)."""
    out: list[dict] = []
    for fname in files:
        if not isinstance(fname, str) or not fname.strip():
            continue
        fpath = cases_root / fname
        try:
            text = fpath.read_text(encoding="utf-8")
        except OSError as e:
            raise ExperimentSpecError(f"cannot read case file {fpath}: {e}") from e
        for lineno, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ExperimentSpecError(
                    f"invalid JSONL at {fpath}:{lineno}: {e}") from e
            out.append(rec)
    return out


# --- validation --------------------------------------------------------------

def validate_spec(spec: ExperimentSpec, experiment_dir: Path) -> list[Problem]:
    """Validate an ExperimentSpec against docs/experiment-yaml-schema.md §18.

    Returns a list of Problem(level, code, message). ERROR -> review FAIL,
    WARN -> review WARN. Filesystem checks are resolved relative to
    experiment_dir.
    """
    problems: list[Problem] = []

    def err(code: str, msg: str) -> None:
        problems.append(Problem(ERROR, code, msg))

    def warn(code: str, msg: str) -> None:
        problems.append(Problem(WARN, code, msg))

    # malformed list-typed fields (a scalar where a list is required) — report
    # once per field instead of iterating a string character-by-character.
    for fld in spec.malformed_lists:
        err("bad_list_type", f"`{fld}` in experiment.yaml must be a list")
    malformed = set(spec.malformed_lists)
    bad_entries = set(spec.bad_entries)
    if "harnesses" in bad_entries:
        err("bad_harness_entry",
            "a `harnesses:` entry is not a mapping; each must have id / name / path in experiment.yaml")
    if "agent_runtimes" in bad_entries:
        err("bad_agent_runtime_entry",
            "an `agent_runtimes:` entry is not a mapping; each must have id / harness / spec "
            "in experiment.yaml")
    if "evaluation.methods" in bad_entries:
        err("bad_evaluation_method_entry",
            "an `evaluation.methods` entry is malformed in experiment.yaml; "
            "each must be `{type: <method>}` or a bare method name")
    if "evaluation.evaluators" in bad_entries:
        err("bad_evaluator_entry",
            "an `evaluation.evaluators` entry is not a mapping in experiment.yaml; "
            "each must be `{id, method, script|rubric}`")
    if "evaluation.tracks" in bad_entries:
        err("bad_evaluation_track_entry",
            "an `evaluation.tracks` entry is not a mapping in experiment.yaml; "
            "each must be `{id, evaluators: [...], evidence: [...]}`")
    if "simulator" in bad_entries:
        err("bad_simulator_type",
            "`simulator` in experiment.yaml must be a mapping with a `type:` key")
    if "objective" in bad_entries:
        err("bad_objective_type", "`objective` in experiment.yaml must be a mapping")
    if "optimization" in bad_entries:
        err("bad_optimization_type", "`optimization` in experiment.yaml must be a mapping")

    # unknown top-level keys (consistency with collection/inspection: warn, don't ignore)
    if isinstance(spec.raw, dict):
        for k in spec.raw:
            if k not in KNOWN_TOPLEVEL:
                warn("unknown_toplevel_key",
                     f"`{k}` is not a recognized top-level key in experiment.yaml "
                     f"(recognized: {sorted(KNOWN_TOPLEVEL)}); it will be ignored")

    # unknown NESTED keys — same no-silent-ignore rule as top-level/collection/inspection
    _raw = spec.raw if isinstance(spec.raw, dict) else {}

    def _warn_unknown(section, known, label):
        if isinstance(section, dict):
            for k in section:
                if k not in known:
                    warn("unknown_key",
                         f"`{label}.{k}` is not a recognized key in experiment.yaml; it will be ignored")

    _warn_unknown(_raw.get("run"), {"mode"}, "run")
    _warn_unknown(_raw.get("execution"), {"mode", "state_policy", "trials", "aggregation"}, "execution")
    _warn_unknown(_raw.get("cases"), {"root", "files"}, "cases")
    _warn_unknown(_raw.get("evaluation"), {"root", "methods", "evaluators", "tracks"}, "evaluation")
    _warn_unknown(_raw.get("reports"), {"formats"}, "reports")
    for _i, _h in enumerate(_raw.get("harnesses") or []):
        _warn_unknown(_h, {"id", "name", "path"}, f"harnesses[{_i}]")
    for _i, _rt in enumerate(_raw.get("agent_runtimes") or []):
        _warn_unknown(_rt, {"id", "harness", "spec"}, f"agent_runtimes[{_i}]")
    _eval_for_warn = _raw.get("evaluation")
    if isinstance(_eval_for_warn, dict):
        for _i, _ev in enumerate(_eval_for_warn.get("evaluators") or []):
            _warn_unknown(_ev, {"id", "method", "script", "rubric"}, f"evaluation.evaluators[{_i}]")
        for _i, _tr in enumerate(_eval_for_warn.get("tracks") or []):
            _warn_unknown(_tr, {"id", "question", "evaluators", "evidence"}, f"evaluation.tracks[{_i}]")
    _warn_unknown(_raw.get("simulator"),
                  {"type", "script", "actor", "max_turns", "policy", "playbook"}, "simulator")
    _warn_unknown(_raw.get("objective"),
                  {"primary_track", "success_criteria", "optimize_for"}, "objective")
    _warn_unknown(_raw.get("optimization"),
                  {"enabled", "editable_surface", "protected_surface", "stop_conditions",
                   "promotion_policy"}, "optimization")

    # required scalar fields — must be strings. YAML implicit typing means an
    # unquoted 007 / 0x1f / yes / no parses to int/bool, so type-check explicitly.
    def _missing(v) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    if _missing(spec.id):
        err("missing_id", "set `id:` in experiment.yaml (lowercase kebab-case, e.g. skill-creator-ab)")
    elif not isinstance(spec.id, str):
        err("bad_id", f"`id` in experiment.yaml must be a quoted string; got {spec.id!r} "
                      f"(an unquoted YAML scalar like 007 / yes parses to a number/bool)")
    elif not _KEBAB_RE.match(spec.id):
        err("bad_id", f"`id` in experiment.yaml must be lowercase kebab-case; got {spec.id!r}")
    if _missing(spec.status):
        err("missing_status", f"set `status:` in experiment.yaml (one of {sorted(STATUS_VALUES)})")
    elif not isinstance(spec.status, str) or spec.status not in STATUS_VALUES:
        err("bad_status",
            f"`status` in experiment.yaml is {spec.status!r}; use one of {sorted(STATUS_VALUES)}")
    if _missing(spec.question):
        err("missing_question", "set `question:` in experiment.yaml (the one-line experiment question)")
    elif not isinstance(spec.question, str):
        err("bad_question", "`question` in experiment.yaml must be a string (quote it)")
    elif _PLACEHOLDER_QUESTION_RE.match(spec.question):
        warn("question_placeholder",
             f"`question` in experiment.yaml still looks like an unfilled scaffold "
             f"placeholder ({spec.question!r}); replace it with the real one-line "
             f"experiment question")

    # goal_ref is optional, but if set it must resolve to a file (not silently dead)
    if spec.goal_ref:
        if not isinstance(spec.goal_ref, str):
            warn("goal_ref_not_str", "`goal_ref` must be a string path (quote it); ignoring it")
        else:
            gp = experiment_dir / spec.goal_ref
            if not gp.exists():
                warn("goal_ref_missing",
                     f"`goal_ref` points to '{spec.goal_ref}' which does not exist relative to the "
                     f"experiment dir; create it or fix `goal_ref` in experiment.yaml")
            elif not gp.is_file():
                warn("goal_ref_not_file",
                     f"`goal_ref` '{spec.goal_ref}' is a directory, not the goal file; point it at goal.md")

    # run.mode (run must be a mapping with a mode key)
    raw_run = spec.raw.get("run") if isinstance(spec.raw, dict) else None
    if raw_run is not None and not isinstance(raw_run, dict):
        err("bad_run_type", "`run` in experiment.yaml must be a mapping with a `mode:` key")
    elif not spec.run_mode:
        err("missing_run_mode", f"set `run.mode:` in experiment.yaml (one of {sorted(RUN_MODES)})")
    elif not isinstance(spec.run_mode, str) or spec.run_mode not in RUN_MODES:
        err("bad_run_mode",
            f"`run.mode` in experiment.yaml is {spec.run_mode!r}; use one of {sorted(RUN_MODES)}")

    # execution.mode / state_policy (execution must be a mapping with a mode key)
    raw_exec = spec.raw.get("execution") if isinstance(spec.raw, dict) else None
    if raw_exec is not None and not isinstance(raw_exec, dict):
        err("bad_execution_type",
            "`execution` in experiment.yaml must be a mapping with a `mode:` key")
    elif not spec.execution_mode:
        err("missing_execution_mode",
            f"set `execution.mode:` in experiment.yaml (one of {sorted(EXECUTION_MODES)})")
    elif not isinstance(spec.execution_mode, str) or spec.execution_mode not in EXECUTION_MODES:
        err("bad_execution_mode",
            f"`execution.mode` in experiment.yaml is {spec.execution_mode!r}; "
            f"use one of {sorted(EXECUTION_MODES)}")
    if spec.state_policy and (not isinstance(spec.state_policy, str) or spec.state_policy not in STATE_POLICIES):
        err("bad_state_policy",
            f"`execution.state_policy` in experiment.yaml is {spec.state_policy!r}; "
            f"use one of {sorted(STATE_POLICIES)}")

    # execution.trials / execution.aggregation (PR5 5b)
    _raw_exec = spec.raw.get("execution") if isinstance(spec.raw, dict) else None
    if isinstance(_raw_exec, dict):
        _trials_raw = _raw_exec.get("trials")
        if _trials_raw is not None:
            if not isinstance(_trials_raw, int) or _trials_raw < 1:
                err("bad_trials",
                    f"`execution.trials` must be a positive integer; got {_trials_raw!r}")
        _agg_raw = _raw_exec.get("aggregation")
        if isinstance(_agg_raw, list):
            bad = [x for x in _agg_raw if not isinstance(x, str) or x not in AGGREGATION_VALUES]
            if bad:
                err("bad_aggregation",
                    f"`execution.aggregation` contains unknown entries {bad!r}; "
                    f"valid values: {sorted(AGGREGATION_VALUES)}")

    # harnesses
    if "harnesses" not in malformed and not spec.harnesses:
        err("missing_harnesses",
            "add at least one entry under `harnesses:` in experiment.yaml (id/name/path)")
    for h in spec.harnesses:
        if not h.id or not h.name or not h.path:
            err("bad_harness",
                f"each `harnesses:` entry needs `id`, `name`, and `path` "
                f"(got id={h.id!r}, name={h.name!r}, path={h.path!r})")
            continue
        if not isinstance(h.id, str):
            err("bad_harness", f"harness `id` must be a quoted string in experiment.yaml; got {h.id!r} "
                               f"(an unquoted 1 / on parses to a number/bool)")
            continue
        if not isinstance(h.name, str):
            err("bad_harness", f"harness {h.id}: `name` must be a string; got {h.name!r} (quote it)")
            continue
        if not isinstance(h.path, str):
            err("bad_harness", f"harness {h.id}: `path` must be a string; got {h.path!r} (quote it)")
            continue
        hpath = (experiment_dir / h.path)
        if not hpath.exists():
            err("harness_path_missing",
                f"harness {h.id}: create the directory '{h.path}' under the experiment dir, "
                f"or fix its `path` under `harnesses:` in experiment.yaml")
        elif not hpath.is_dir():
            err("harness_path_not_dir",
                f"harness {h.id}: path '{h.path}' is a file, but a harness path must be a "
                f"directory; fix its `path` under `harnesses:` in experiment.yaml")
    _h_ids = [h.id for h in spec.harnesses if isinstance(h.id, str)]
    _h_dups = sorted({x for x in _h_ids if _h_ids.count(x) > 1})
    if _h_dups:
        err("duplicate_harness_id",
            f"duplicate harness id(s) {_h_dups} in experiment.yaml; each harness needs a unique id")

    # agent runtimes
    if "agent_runtimes" not in malformed and not spec.agent_runtimes:
        err("missing_agent_runtimes",
            "add at least one entry under `agent_runtimes:` in experiment.yaml (id/harness/spec)")
    harness_ids = {h.id for h in spec.harnesses if h.id}
    for r in spec.agent_runtimes:
        if not r.id or not r.spec or not r.harness:
            err("bad_agent_runtime",
                f"each `agent_runtimes:` entry needs `id`, `harness`, and `spec` "
                f"(got id={r.id!r}, harness={r.harness!r}, spec={r.spec!r})")
            continue
        if not isinstance(r.id, str):
            err("bad_agent_runtime", f"agent runtime `id` must be a quoted string; got {r.id!r}")
            continue
        if not isinstance(r.harness, str):
            err("bad_agent_runtime",
                f"agent runtime {r.id}: `harness` reference must be a string; got {r.harness!r}")
            continue
        if not isinstance(r.spec, str):
            err("bad_agent_runtime",
                f"agent runtime {r.id}: `spec` must be a string path; got {r.spec!r} (quote it)")
            continue
        if r.harness and harness_ids and r.harness not in harness_ids:
            err("runtime_harness_unknown",
                f"agent runtime {r.id} references harness {r.harness!r}, which is not declared "
                f"under `harnesses:` in experiment.yaml")
        spec_path = experiment_dir / r.spec
        if not spec_path.exists():
            err("runtime_spec_missing",
                f"agent runtime {r.id}: create the spec file '{r.spec}', "
                f"or fix its `spec` under `agent_runtimes:` in experiment.yaml")
            continue
        if not spec_path.is_file():
            err("runtime_spec_not_file",
                f"agent runtime {r.id}: spec '{r.spec}' is not a file (a directory?); "
                f"point it at a YAML file")
            continue
        try:
            rt = load_agent_runtime_spec(spec_path)
        except ExperimentSpecError as e:
            err("runtime_spec_invalid", str(e))
            continue
        if rt.connector_type and (not isinstance(rt.connector_type, str) or rt.connector_type not in CONNECTOR_TYPES):
            err("bad_connector_type",
                f"agent runtime {r.id} connector type {rt.connector_type!r} "
                f"not in {sorted(CONNECTOR_TYPES)}")
        if not rt.connector_type and spec.run_mode != "auto":
            warn("runtime_no_connector",
                 f"agent runtime {r.id}: spec '{r.spec}' declares no connector type "
                 f"(empty or missing `connector.type`/`type`)")
        # Auto Mode connector support gate (schema §18)
        if spec.run_mode == "auto":
            if not rt.connector_type:
                err("auto_connector_missing",
                    f"Auto Mode requires a connector type on agent runtime {r.id}")
            elif not isinstance(rt.connector_type, str) or rt.connector_type not in AUTO_V1_CONNECTORS:
                err("auto_connector_unsupported",
                    f"Auto Mode v1 supports {sorted(AUTO_V1_CONNECTORS)}; "
                    f"agent runtime {r.id} uses {rt.connector_type!r}")
            else:
                # left-shifted from the runner's run-time check: a missing
                # working_dir would only surface as a connector_failure at run
                # time; catch it at review instead. Auto only — a Copilot flow
                # may legitimately create the directory just before the run.
                _conn = rt.raw.get("connector") if isinstance(rt.raw, dict) else None
                _conn = _conn if isinstance(_conn, dict) else {}
                _wd = _conn.get("working_dir") or (
                    rt.raw.get("working_dir") if isinstance(rt.raw, dict) else None) or "."
                if isinstance(_wd, str) and not (experiment_dir / _wd).is_dir():
                    err("auto_working_dir_missing",
                        f"agent runtime {r.id}: connector working_dir '{_wd}' does not "
                        f"exist relative to the experiment dir; create it or fix "
                        f"`connector.working_dir` in '{r.spec}'")
                # Left-shifted from auto.py run-time check: the script connector
                # is one fresh process per case with no turn IPC — it cannot keep
                # a multi-turn conversation. This combination always fails at run
                # time; reject it at review so users see a clear error earlier.
                if (rt.connector_type == "script"
                        and isinstance(spec.simulator, SimulatorSpec)
                        and isinstance(spec.simulator.type, str)
                        and spec.simulator.type in MULTI_TURN_SIMULATOR_TYPES):
                    err("simulator_connector_unsupported",
                        f"agent runtime {r.id}: connector type 'script' cannot drive a "
                        f"multi-turn simulator (type={spec.simulator.type!r}); the script "
                        f"connector spawns a fresh process per case and has no turn IPC — "
                        f"use a 'local_cli' connector for multi-turn experiments")

        # artifacts.collect[]: user declares what artifacts the runtime may produce;
        # EvidenceCollector (Auto Mode phase) archives them under evidence/artifacts/.
        # Validate id uniqueness + glob presence; do not expose source/target here.
        _arts_block = rt.raw.get("artifacts") if isinstance(rt.raw, dict) else None
        if _arts_block is not None:
            if not isinstance(_arts_block, dict):
                err("bad_artifacts_type",
                    f"agent runtime {r.id}: `artifacts` must be a mapping with a `collect:` list")
            elif _arts_block.get("collect") is not None and not isinstance(_arts_block.get("collect"), list):
                err("bad_artifacts_collect_type",
                    f"agent runtime {r.id}: `artifacts.collect` must be a list of "
                    f"{{id, kind, glob, required}} rules")
            else:
                _aids: list[str] = []
                for art in (_arts_block.get("collect") or []):
                    if not isinstance(art, dict):
                        err("bad_artifact_rule",
                            f"agent runtime {r.id}: each `artifacts.collect` entry must be a "
                            f"mapping with `id` and `glob`")
                        continue
                    _aid, _glob = art.get("id"), art.get("glob")
                    if not isinstance(_aid, str) or not _aid.strip():
                        err("bad_artifact_rule",
                            f"agent runtime {r.id}: an `artifacts.collect` entry needs a string `id`")
                    else:
                        _aids.append(_aid)
                    if not isinstance(_glob, str) or not _glob.strip():
                        err("bad_artifact_glob",
                            f"agent runtime {r.id}: artifact {_aid!r} needs a non-empty `glob` "
                            f"(relative to the connector working_dir)")
                    if ("target" in art or "source" in art) and isinstance(_aid, str) and _aid.strip():
                        warn("artifact_source_target_ignored",
                             f"agent runtime {r.id}: artifact {_aid!r} declares source/target — "
                             f"these are not v1 concepts; declare only id/kind/glob/required "
                             f"(EvidenceCollector decides the evidence/artifacts/ path)")
                _adups = sorted({x for x in _aids if _aids.count(x) > 1})
                if _adups:
                    err("duplicate_artifact_id",
                        f"agent runtime {r.id}: duplicate artifact id(s) {_adups}; "
                        f"each artifact needs a unique id within the runtime")
        # (artifact harvesting now runs in Auto Mode via the EvidenceCollector, so the
        # previous "harvest unimplemented" WARN is gone — it would be false.)

        # source: section (PR6): validate shape only here.
        # load_agent_runtime_spec already ran parse_source_spec and raised
        # ExperimentSpecError for unknown type / missing required fields. Here we
        # surface that error as a review problem (it was already raised as
        # ExperimentSpecError and caught by the outer try/except → runtime_spec_invalid).
        # If load succeeded, rt.source is a RuntimeSourceSpec or None.
        # Existence/reachability/fingerprint checks (including patch file sources)
        # are performed in Phase 2 of review_experiment (reviewer.py:_run_source_health_checks)
        # with probe_* issue codes — see docs/v1-spec/cli.md §6 Phase 2.

    _r_ids = [r.id for r in spec.agent_runtimes if isinstance(r.id, str)]
    _r_dups = sorted({x for x in _r_ids if _r_ids.count(x) > 1})
    if _r_dups:
        err("duplicate_runtime_id",
            f"duplicate agent runtime id(s) {_r_dups} in experiment.yaml; each runtime needs a unique id")

    # Auto Mode state policy support (schema §9: Auto v1 must support isolated/reset)
    if (spec.run_mode == "auto" and isinstance(spec.state_policy, str)
            and spec.state_policy in STATE_POLICIES
            and spec.state_policy not in AUTO_V1_STATE_POLICIES):
        warn("auto_state_policy_unimplemented",
             f"Auto Mode v1 implements {sorted(AUTO_V1_STATE_POLICIES)}; "
             f"`{spec.state_policy}` may be expressible before fully implemented")

    # per-StatePolicy review semantics — every value is handled, none is an inert enum:
    #   isolated        : each case/harness run is independent — fully supported, no extra config.
    #   reset           : runtime reused but reset (fresh process) before each run — IMPLEMENTED
    #                     in Auto Mode (AutoRunner restarts the local_cli session per case; the
    #                     script connector is already a fresh process per case). No WARN needed.
    #   cumulative      : state persists across cases (see auto_state_policy_unimplemented).
    #   snapshot_branch : branch from a shared snapshot (see snapshots_not_collected below).
    #   replay          : do not rerun the runtime; evaluate already-collected evidence.
    _sp = spec.state_policy if isinstance(spec.state_policy, str) and spec.state_policy in STATE_POLICIES else None
    if _sp == "replay" or spec.execution_mode == "replay":
        ev_dir = experiment_dir / "evidence"
        _has_evidence = ev_dir.is_dir() and any(
            d.is_dir() and any(f.name != ".gitkeep" for f in d.iterdir())
            for d in ev_dir.iterdir() if d.is_dir())
        if not _has_evidence:
            warn("replay_no_evidence",
                 "replay reuses existing evidence instead of rerunning the Agent Runtime, "
                 "but no evidence has been collected under evidence/ yet")

    # simulator (optional): how the user side of cases is driven. single_turn is
    # the frozen default; role_play / scripted / script are the v1.1 multi-turn
    # types (execution-model.md §14). A missing policy/playbook/script file is
    # fatal under Auto Mode (the runner would dispatch nothing useful) and a WARN
    # under Copilot (the file may legitimately be authored later).
    if isinstance(spec.simulator, SimulatorSpec):
        st = spec.simulator.type
        sraw = spec.simulator.raw if isinstance(spec.simulator.raw, dict) else {}
        _file_missing = err if spec.run_mode == "auto" else warn
        if not isinstance(st, str) or st not in SIMULATOR_TYPES:
            err("bad_simulator_type",
                f"`simulator.type` {st!r} is unknown; use one of {sorted(SIMULATOR_TYPES)}")
        elif st == "script":
            _scr = sraw.get("script")
            if not isinstance(_scr, str) or not _scr.strip():
                err("simulator_script_missing",
                    "simulator type=script requires a `script:` path in experiment.yaml")
            elif not (experiment_dir / _scr).exists():
                _file_missing("simulator_script_ref_missing",
                              f"simulator `script` '{_scr}' does not exist relative to the "
                              f"experiment dir; create it or fix `simulator.script`")
        elif st == "scripted":
            _pb = sraw.get("playbook")
            if not isinstance(_pb, str) or not _pb.strip():
                err("simulator_playbook_missing",
                    "simulator type=scripted requires a `playbook:` path in experiment.yaml")
            elif not (experiment_dir / _pb).exists():
                _file_missing("simulator_playbook_ref_missing",
                              f"simulator `playbook` '{_pb}' does not exist relative to the "
                              f"experiment dir; create it or fix `simulator.playbook`")
        elif st == "role_play":
            for _f in ("actor", "policy"):
                if not isinstance(sraw.get(_f), str) or not str(sraw.get(_f)).strip():
                    err("simulator_field_missing",
                        f"simulator type=role_play requires a string `{_f}:` in experiment.yaml")
            _pol = sraw.get("policy")
            if isinstance(_pol, str) and _pol:
                _ppath = experiment_dir / _pol
                if not _ppath.exists():
                    _file_missing("simulator_policy_ref_missing",
                                  f"simulator `policy` '{_pol}' does not exist relative to the "
                                  f"experiment dir; create it or fix `simulator.policy`")
                elif _ppath.is_file():
                    # four-section policy card (Persona/Background/Strategy/Stop,
                    # EN/CN section names — schema §14a)
                    try:
                        _card = user_sim.parse_policy_card(_ppath)
                    except (OSError, UnicodeError) as e:
                        _card = None
                        warn("simulator_policy_unreadable",
                             f"simulator `policy` '{_pol}' cannot be read: {e}")
                    if _card is not None:
                        _empty = [n for n, v in (("Persona", _card.persona),
                                                 ("Strategy", _card.strategy))
                                  if not mdutil.is_filled(v)]
                        if _empty:
                            warn("simulator_policy_incomplete",
                                 f"simulator policy card '{_pol}' is missing the "
                                 f"{' / '.join(_empty)} section(s) (## Persona/## 人设, "
                                 f"## Strategy/## 追问策略); the role_play user will be "
                                 f"under-specified")
                        if not mdutil.is_filled(_card.stop):
                            warn("simulator_policy_no_stop",
                                 f"simulator policy card '{_pol}' has no Stop section "
                                 f"(## Stop / ## 收尾条件) — the conversation will end "
                                 f"only on max_turns")
        if (isinstance(st, str) and st in MULTI_TURN_SIMULATOR_TYPES
                and "max_turns" in sraw and not isinstance(sraw.get("max_turns"), int)):
            err("bad_simulator_max_turns",
                "simulator.max_turns must be an integer in experiment.yaml")

    # --- Auto Optimize (objective + optimization): schema/validation only; loop implemented in auto_optimize.py ---
    # v1.1 boundary: the optimize loop supports single_turn only. A multi-turn
    # simulator inside the loop would fail (or call an LLM) once per iteration —
    # undefined behavior, so it is rejected here (execution-model.md §14.7).
    if (isinstance(spec.optimization, OptimizationSpec) and spec.optimization.enabled
            and isinstance(spec.simulator, SimulatorSpec)
            and spec.simulator.type in MULTI_TURN_SIMULATOR_TYPES):
        err("optimize_multiturn_unsupported",
            f"`optimization.enabled: true` supports single_turn only in v1.1; "
            f"simulator type {spec.simulator.type!r} is multi-turn — disable "
            f"optimization or use `simulator.type: single_turn`")

    # Defect 9 (LEFT-SHIFT): Auto Optimize × source — reject at review time.
    # v1.1 scopes optimize to sourceless single_turn only. A runtime declaring
    # source: inside the optimize loop causes materialize to override
    # working_dir_override (the candidate dir), so the optimize iteration runs the
    # pristine sandbox instead of the candidate — promotion decisions on unrelated
    # data. Reject the combination so users see a clear error at review time.
    if (isinstance(spec.optimization, OptimizationSpec) and spec.optimization.enabled):
        _runtimes_with_source = []
        for _rt_ref in spec.agent_runtimes:
            if not isinstance(_rt_ref.spec, str) or not _rt_ref.spec:
                continue
            _sp = experiment_dir / _rt_ref.spec
            if not _sp.is_file():
                continue
            try:
                _rt = load_agent_runtime_spec(_sp)
                if _rt.source is not None:
                    _runtimes_with_source.append(_rt_ref.id or _rt.id or "?")
            except ExperimentSpecError:
                pass
        if _runtimes_with_source:
            err("optimize_source_unsupported",
                f"`optimization.enabled: true` is incompatible with `source:` declarations "
                f"in v1.1 (optimize loop is sourceless single_turn only); "
                f"runtimes with source: {_runtimes_with_source}. "
                f"Remove source: from the optimize experiment or disable optimization "
                f"(execution-model.md §15.1, §14.7)")
    _track_ids = {t.id for t in spec.tracks if isinstance(t.id, str)}
    if isinstance(spec.objective, ObjectiveSpec):
        pt = spec.objective.primary_track
        if isinstance(pt, str) and pt and pt not in _track_ids:
            err("objective_unknown_track",
                f"`objective.primary_track` {pt!r} is not a defined evaluation track; "
                f"define it under `evaluation.tracks`")
        of = spec.objective.optimize_for
        if isinstance(of, str) and of and of not in OPTIMIZE_FOR_VALUES:
            warn("objective_optimize_for_unknown",
                 f"`objective.optimize_for` {of!r} is not one of {sorted(OPTIMIZE_FOR_VALUES)}")
    if isinstance(spec.optimization, OptimizationSpec):
        opt = spec.optimization
        # editable_surface: harness-controlled only, and never the protected surface.
        for e in opt.editable_surface:
            head = e.replace("\\", "/").split("/")[0].split(".")[0]
            if head in PROTECTED_SURFACE_DEFAULTS:
                err("editable_surface_protected",
                    f"`optimization.editable_surface` entry '{e}' targets a protected surface "
                    f"({head}); Auto must not modify goal / cases / evaluation / objective / conclusion")
            elif not e.replace("\\", "/").startswith("harnesses/"):
                err("editable_surface_not_harness",
                    f"`optimization.editable_surface` entry '{e}' must be harness-controlled "
                    f"(under harnesses/)")
        # stop_conditions required when optimization is enabled
        if opt.enabled and not opt.stop_conditions:
            err("missing_stop_conditions",
                "`optimization.enabled: true` requires `optimization.stop_conditions`")
        # promotion_policy must reference known evaluation tracks or issue types
        if isinstance(opt.promotion_policy, dict):
            _known_refs = _track_ids | ISSUE_CHECKS
            for k, v in opt.promotion_policy.items():
                for ref in (v if isinstance(v, list) else [v]):
                    if isinstance(ref, str) and ref and ref not in _known_refs:
                        err("promotion_policy_unknown_ref",
                            f"`optimization.promotion_policy.{k}` references {ref!r}, which is not a "
                            f"known evaluation track or issue type")
        # accurate boundary: the BOUNDED, deterministic loop is implemented (copy-only
        # or a user mutation_script); LLM-driven / autonomous optimization is NOT.
        if opt.enabled:
            warn("optimization_bounded_only",
                 "`optimization.enabled: true` runs the bounded, deterministic Auto Optimize loop "
                 "(copy-only or a user `mutation_script`): it generates, runs, evaluates, and "
                 "promotes candidate harnesses within stop_conditions, writing "
                 "optimization/history.jsonl. It does NOT perform LLM-driven or autonomous "
                 "optimization.")

    # cases
    raw_cases = _raw.get("cases")
    if raw_cases is not None and not isinstance(raw_cases, dict):
        err("bad_cases_type", "`cases` in experiment.yaml must be a mapping with `root:` and `files:`")
    elif not spec.cases_root:
        err("missing_cases_root", "set `cases.root:` in experiment.yaml (e.g. cases/)")
    elif not isinstance(spec.cases_root, str):
        err("bad_cases_root", "`cases.root` in experiment.yaml must be a string path (quote it)")
    else:
        croot = experiment_dir / spec.cases_root
        if not croot.exists():
            err("cases_root_missing",
                f"create the cases directory '{spec.cases_root}' under the experiment dir, "
                f"or fix `cases.root` in experiment.yaml")
        elif not croot.is_dir():
            err("cases_root_not_dir",
                f"`cases.root` '{spec.cases_root}' is a file, but it must be a directory")
        elif "cases.files" in malformed:
            pass  # already reported as bad_list_type
        elif not spec.cases_files:
            err("missing_cases_files",
                "list at least one file under `cases.files` in experiment.yaml (e.g. cases.jsonl)")
        else:
            for cf in spec.cases_files:
                if not isinstance(cf, str) or not cf.strip():
                    err("bad_case_file",
                        "`cases.files` entries must be non-empty filenames in experiment.yaml")
                    continue
                if not (croot / cf).exists():
                    rel = f"{spec.cases_root.rstrip('/')}/{cf}" if spec.cases_root else cf
                    err("case_file_missing",
                        f"create the JSONL case file '{rel}', or fix `cases.files` in experiment.yaml")

    # evaluation
    raw_eval = _raw.get("evaluation")
    if raw_eval is not None and not isinstance(raw_eval, dict):
        err("bad_evaluation_type", "`evaluation` in experiment.yaml must be a mapping with a `root:` key")
    elif not spec.evaluation_root:
        err("missing_evaluation_root", "set `evaluation.root:` in experiment.yaml (e.g. evaluation/)")
    elif not isinstance(spec.evaluation_root, str):
        err("bad_evaluation_root", "`evaluation.root` in experiment.yaml must be a string path (quote it)")
    else:
        eroot = experiment_dir / spec.evaluation_root
        if not eroot.exists():
            err("evaluation_root_missing",
                f"create the evaluation directory '{spec.evaluation_root}' under the experiment dir, "
                f"or fix `evaluation.root` in experiment.yaml")
        elif not eroot.is_dir():
            err("evaluation_root_not_dir",
                f"`evaluation.root` '{spec.evaluation_root}' is a file, but it must be a directory")
    # --- three evaluation layers: methods (shorthand) / evaluators / tracks ---
    # 1) methods shorthand (backward compatible)
    for m in spec.evaluation_methods:
        if not isinstance(m, str) or m not in EVAL_METHODS:
            err("bad_evaluation_method",
                f"evaluation method {m!r} in experiment.yaml is unknown; use one of {sorted(EVAL_METHODS)}")

    # 2) evaluators: unique id, known method, script/rubric refs should resolve
    _eval_root_rel = (spec.evaluation_root if isinstance(spec.evaluation_root, str)
                      and spec.evaluation_root else "evaluation/")
    _ev_ids: list[str] = []
    for ev in spec.evaluators:
        if not isinstance(ev.id, str) or not ev.id.strip():
            err("bad_evaluator",
                f"each `evaluation.evaluators` entry needs a string `id` (got id={ev.id!r})")
            continue
        _ev_ids.append(ev.id)
        if not isinstance(ev.method, str) or ev.method not in EVAL_METHODS:
            err("bad_evaluator_method",
                f"evaluator {ev.id}: `method` {ev.method!r} is unknown; "
                f"use one of {sorted(EVAL_METHODS)}")
        for _key, _val in (("script", ev.script), ("rubric", ev.rubric)):
            if isinstance(_val, str) and _val and not (experiment_dir / _eval_root_rel / _val).exists():
                warn("evaluator_ref_missing",
                     f"evaluator {ev.id}: `{_key}` '{_val}' does not exist under "
                     f"{_eval_root_rel.rstrip('/')}/; create it or fix the evaluator in experiment.yaml")
        # llm_rubric: rubric file is required and must contain a parseable dimensions table.
        if ev.method == "llm_rubric":
            _rub_val = ev.rubric
            if not isinstance(_rub_val, str) or not _rub_val.strip():
                err("rubric_missing_dimensions",
                    f"evaluator {ev.id}: `llm_rubric` requires a `rubric:` path pointing at a "
                    f"rubric markdown file (e.g. rubrics/my_rubric.md under the evaluation root)")
            else:
                _rub_path = experiment_dir / _eval_root_rel / _rub_val
                if _rub_path.is_file():
                    try:
                        _rub_text = _rub_path.read_text(encoding="utf-8")
                        from agent_harness_lab.evaluation import _parse_rubric_table
                        _dims = _parse_rubric_table(_rub_text)
                        if not _dims:
                            err("rubric_invalid",
                                f"evaluator {ev.id}: rubric file '{_rub_val}' has no "
                                f"dimensions+weights table; add a markdown table with columns "
                                f"`Dimension`, `Weight`, `Description` "
                                f"(see docs/v1-spec/experiment-yaml-schema.md §14b)")
                        else:
                            _neg = [d["name"] for d in _dims if d["weight"] < 0]
                            if _neg:
                                err("rubric_invalid",
                                    f"evaluator {ev.id}: rubric file '{_rub_val}' has negative "
                                    f"weight(s) for dimension(s) {_neg}; all weights must be >= 0")
                            else:
                                _wsum = sum(d["weight"] for d in _dims)
                                if _wsum <= 0:
                                    err("rubric_invalid",
                                        f"evaluator {ev.id}: rubric file '{_rub_val}' has an "
                                        f"all-zero weight sum; at least one weight must be > 0")
                                elif abs(_wsum - 1.0) > 0.01:
                                    warn("rubric_weights_normalized",
                                         f"evaluator {ev.id}: rubric file '{_rub_val}' weights "
                                         f"sum to {_wsum:.4g} (not ~1.0); they will be normalised "
                                         f"automatically at scoring time")
                    except Exception as _rub_e:  # noqa: BLE001
                        err("rubric_invalid",
                            f"evaluator {ev.id}: rubric file '{_rub_val}' could not be parsed: "
                            f"{_rub_e}")
    _ev_dups = sorted({x for x in _ev_ids if _ev_ids.count(x) > 1})
    if _ev_dups:
        err("duplicate_evaluator_id",
            f"duplicate evaluator id(s) {_ev_dups} in experiment.yaml; each evaluator needs a unique id")

    # 3) tracks: unique id, reference existing evaluators, known evidence types
    _known_ev_ids = set(_ev_ids)
    _tr_ids: list[str] = []
    for tr in spec.tracks:
        if not isinstance(tr.id, str) or not tr.id.strip():
            err("bad_track", f"each `evaluation.tracks` entry needs a string `id` (got id={tr.id!r})")
            continue
        _tr_ids.append(tr.id)
        if not tr.evaluators:
            warn("track_no_evaluators",
                 f"evaluation track {tr.id} lists no evaluators; it will evaluate nothing")
        for ref in tr.evaluators:
            if ref not in _known_ev_ids:
                err("track_unknown_evaluator",
                    f"evaluation track {tr.id} references evaluator {ref!r}, which is not defined "
                    f"under `evaluation.evaluators` in experiment.yaml")
        for evd in tr.evidence:
            if evd not in EVIDENCE_TYPES:
                err("bad_track_evidence",
                    f"evaluation track {tr.id} lists unknown evidence type {evd!r}; "
                    f"use only {sorted(EVIDENCE_TYPES)}")
    _tr_dups = sorted({x for x in _tr_ids if _tr_ids.count(x) > 1})
    if _tr_dups:
        err("duplicate_track_id",
            f"duplicate evaluation track id(s) {_tr_dups} in experiment.yaml; each track needs a unique id")

    # at least one evaluator (or the methods shorthand) must define how results are judged
    if not spec.evaluators and not spec.evaluation_methods:
        err("no_evaluators",
            "define at least one evaluator under `evaluation.evaluators` in experiment.yaml "
            "(id + method), or use the `evaluation.methods` shorthand")
    # tracks group evaluators for the report; without them grouping is weak (not fatal)
    if not spec.tracks:
        warn("no_evaluation_tracks",
             "no `evaluation.tracks` defined — report/evaluation grouping will be weak; "
             "group evaluators into tracks under `evaluation.tracks` in experiment.yaml")

    # collection: required present; shape-validated (known boolean keys). Its
    # semantics are consumed by the future EvidenceCollector (Auto Mode phase).
    if spec.collection is None or spec.collection == {}:
        err("missing_collection",
            f"add a `collection:` block in experiment.yaml (booleans: {sorted(COLLECTION_KEYS)})")
    elif not isinstance(spec.collection, dict):
        err("bad_collection_type",
            "`collection` in experiment.yaml must be a mapping of booleans, not a list/scalar")
    else:
        for k, v in spec.collection.items():
            if k not in COLLECTION_KEYS:
                warn("unknown_collection_key",
                     f"`collection.{k}` in experiment.yaml is not a recognized key "
                     f"({sorted(COLLECTION_KEYS)}); it will be ignored")
            elif not isinstance(v, bool):
                err("bad_collection_value",
                    f"`collection.{k}` must be true/false in experiment.yaml; got {v!r}")

    # inspection: shape-validated (review flags boolean + issue_checks enum).
    # Consumed by the future Inspector (Auto Mode phase).
    if spec.inspection is not None and not isinstance(spec.inspection, dict):
        err("bad_inspection_type",
            "`inspection` in experiment.yaml must be a mapping, not a list/scalar")
    elif isinstance(spec.inspection, dict):
        for k, v in spec.inspection.items():
            if k == "issue_checks":
                if v is not None and not isinstance(v, list):
                    err("bad_issue_checks_type",
                        "`inspection.issue_checks` in experiment.yaml must be a list of check names")
                else:
                    for ic in (v or []):
                        if not isinstance(ic, str) or ic not in ISSUE_CHECKS:
                            err("bad_issue_check",
                                f"`inspection.issue_checks` has unknown check {ic!r}; "
                                f"use only {sorted(ISSUE_CHECKS)}")
            elif k in INSPECTION_REVIEW_KEYS:
                if not isinstance(v, bool):
                    err("bad_inspection_value",
                        f"`inspection.{k}` must be true/false in experiment.yaml; got {v!r}")
                elif v and k != "artifact_review":
                    # honesty: skill/memory/context review are declarable-only in v1 —
                    # the Inspector runs its fixed checks, never a dedicated <k>.
                    warn("inspection_review_unimplemented",
                         f"`inspection.{k}: true` is declared but not executed in v1 "
                         f"(declarable-only); no {k} will be performed")
            else:
                warn("unknown_inspection_key",
                     f"`inspection.{k}` in experiment.yaml is not a recognized key; "
                     f"recognized: {sorted(INSPECTION_REVIEW_KEYS | {'issue_checks'})}")

    # reports
    raw_reports = _raw.get("reports")
    if raw_reports is not None and not isinstance(raw_reports, dict):
        err("bad_reports_type", "`reports` in experiment.yaml must be a mapping with a `formats:` list")
    elif "reports.formats" in malformed:
        pass  # already reported as bad_list_type
    elif not spec.report_formats:
        err("missing_report_formats",
            f"list at least one format under `reports.formats` in experiment.yaml "
            f"(supported: {sorted(REPORT_FORMATS)}; `md` recommended)")
    for fmt in spec.report_formats:
        if fmt not in REPORT_FORMATS:
            err("bad_report_format",
                f"report format {fmt!r} in experiment.yaml is unknown; use one of {sorted(REPORT_FORMATS)}")
    if (spec.report_formats and "reports.formats" not in malformed
            and "md" not in spec.report_formats):
        warn("report_md_missing",
             "`reports.formats` does not include `md` (the v1-required report format); "
             "add `md` so a machine-required report is produced")

    # collection <-> inspection coherence (the field VALUES take effect now: an
    # inspection that needs evidence which collection disables is flagged here,
    # so these are not inert knobs even before the Auto-Mode collector exists).
    # A collection key that is OFF — explicitly false OR absent — means that
    # evidence won't be produced, so both cases are treated identically here.
    # Coherence only runs when `collection` is a present mapping; when it is
    # missing or the wrong type, the required-field / type ERRORs already cover it.
    if isinstance(spec.collection, dict):
        coll = spec.collection
        insp = spec.inspection if isinstance(spec.inspection, dict) else {}
        if insp.get("artifact_review") and not coll.get("artifacts"):
            warn("collection_inspection_mismatch",
                 "`inspection.artifact_review` is on but `collection.artifacts` is off "
                 "(false or unset) — artifacts won't be collected to review; "
                 "set `collection.artifacts: true` in experiment.yaml")
        _CHECK_NEEDS = {
            "missing_artifact": "artifacts", "path_drift": "artifacts",
            "empty_output": "raw", "missing_trace": "traces", "missing_score": "scores",
        }
        _raw_checks = insp.get("issue_checks")
        declared_checks = ({c for c in _raw_checks if isinstance(c, str)}
                           if isinstance(_raw_checks, list) else set())
        for chk, needed in _CHECK_NEEDS.items():
            if chk in declared_checks and not coll.get(needed):
                warn("issue_check_needs_collection",
                     f"`inspection.issue_checks` includes '{chk}' but `collection.{needed}` is off "
                     f"(false or unset) — there will be no {needed} to check; "
                     f"set `collection.{needed}: true` in experiment.yaml")

    # --- warnings (schema §18) ---
    if not (experiment_dir / "conclusion.md").exists():
        warn("conclusion_missing", "conclusion.md is missing (human conclusion not yet recorded)")
    # report.html is rendered by markdown_html (a real, stdlib renderer) — no WARN.
    _effective_methods = set(spec.evaluation_methods) | {
        ev.method for ev in spec.evaluators if isinstance(ev.method, str)}
    if "human_annotation" in _effective_methods:
        eval_root = spec.evaluation_root if isinstance(spec.evaluation_root, str) and spec.evaluation_root else "evaluation"
        if not (experiment_dir / eval_root / "evaluation.md").exists():
            warn("human_review_undocumented",
                 f"human_annotation evaluation requested but {eval_root.rstrip('/')}/evaluation.md is missing")
    snapshots_on = bool(spec.collection.get("snapshots")) if isinstance(spec.collection, dict) else False
    if spec.state_policy == "snapshot_branch" and not snapshots_on:
        warn("snapshots_not_collected",
             "state_policy=snapshot_branch but collection.snapshots is not enabled")

    return problems


def make_experiment_id(name: str) -> str:
    """Derive a kebab-case experiment id from a free-form name.

    Returns "" when the name has no usable [a-z0-9] characters — the caller
    must reject that rather than fall back to a shared default id (which would
    collapse distinct unicode/punctuation names to the same id)."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s
