"""Inspector — completeness checks over an Auto Run's evidence.

Runs after Auto Run + EvaluationRunner. Reads experiment.yaml + evidence/{traces,
raw,artifacts,scores} and records machine-readable issues, MERGING into (not
duplicating) evidence/issues.jsonl and writing a summary to
evidence/inspections/inspection.json.

Checks added by the Inspector (connector_failure / case_failure / empty_output /
missing_artifact are already written by the AutoRunner — we dedupe against them):
  missing_trace    — a runtime produced fewer traces than there are cases
  missing_score    — a configured track has no aggregated score, or it errored
  runtime_mismatch — a trace's runtime/harness is not in the experiment's mapping
  path_drift       — an artifacts.collect glob escapes the runtime working dir
                     (absolute or contains '..') → would collect outside evidence/

Severity: error (connector_failure / case_failure / missing REQUIRED artifact);
warn (missing_trace / missing_score / missing optional artifact / path_drift /
runtime_mismatch); info (a track legitimately pending human/llm review).

Dedup is deterministic: keyed by (type, runtime_id, case_id, track_id). Re-running
overwrites issues.jsonl from the AutoRunner's fresh set + the same detections, so
identical records never accumulate across runs.
"""
from __future__ import annotations

import json
import ntpath
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from agent_harness_lab.auto import _case_id
from agent_harness_lab.experiment_spec import (
    ExperimentSpec,
    ExperimentSpecError,
    load_agent_runtime_spec,
    load_cases,
)

ERROR, WARN, INFO = "error", "warn", "info"


@dataclass
class InspectionResult:
    issues: list[dict] = field(default_factory=list)   # full merged set
    added: list[dict] = field(default_factory=list)    # only what the Inspector added
    inspection_path: Path | None = None

    @property
    def issue_total(self) -> int:
        return len(self.issues)

    def check_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.added:
            out[i["type"]] = out.get(i["type"], 0) + 1
        return out

    def severity_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.issues:
            sev = i.get("severity", ERROR)
            out[sev] = out.get(sev, 0) + 1
        return out


def _key(i: dict) -> tuple:
    return (i.get("type"), i.get("runtime_id"), i.get("case_id"), i.get("track_id"))


def _read_issues(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _read_traces(traces_dir: Path, runtime_id: str) -> list[dict]:
    p = traces_dir / f"{runtime_id}.jsonl"
    if not p.is_file():
        return []
    recs: list[dict] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                recs.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return recs


def _glob_escapes(pattern: str) -> bool:
    """A glob that would collect from OUTSIDE the runtime working dir: absolute
    (POSIX or Windows/drive/UNC) or containing a '..' segment."""
    if not isinstance(pattern, str) or not pattern:
        return False
    if posixpath.isabs(pattern) or ntpath.isabs(pattern):
        return True
    parts = pattern.replace("\\", "/").split("/")
    return ".." in parts


def run_inspection(exp_dir: Path, spec: ExperimentSpec, *,
                   evidence_dir: Path | None = None) -> InspectionResult:
    exp_dir = Path(exp_dir).resolve()
    evidence_dir = Path(evidence_dir).resolve() if evidence_dir else exp_dir / "evidence"
    traces_dir = evidence_dir / "traces"
    artifacts_dir = evidence_dir / "artifacts"
    scores_tracks = evidence_dir / "scores" / "tracks"
    issues_path = evidence_dir / "issues.jsonl"

    existing = _read_issues(issues_path)
    seen = {_key(i) for i in existing}
    added: list[dict] = []

    def add(type_: str, message: str, severity: str, *, runtime_id=None,
            case_id=None, harness_id=None, track_id=None, evidence_ref=None) -> None:
        rec = {"type": type_, "severity": severity, "message": message,
               "runtime_id": runtime_id, "case_id": case_id, "harness_id": harness_id,
               "track_id": track_id, "evidence_ref": evidence_ref, "created_by": "Inspector"}
        k = _key(rec)
        if k in seen:
            return
        seen.add(k)
        added.append(rec)

    try:
        cases = (load_cases(exp_dir / spec.cases_root, spec.cases_files)
                 if spec.cases_root and spec.cases_files else [])
    except ExperimentSpecError:
        cases = []
    n_cases = len(cases)
    rt_harness = {r.id: r.harness for r in spec.agent_runtimes}

    # connector_failure already recorded for these runtimes → don't also flag missing_trace
    failed_rt = {i.get("runtime_id") for i in existing if i.get("type") == "connector_failure"}

    for rt_ref in spec.agent_runtimes:
        recs = _read_traces(traces_dir, rt_ref.id)
        # missing_trace: fewer traces than cases, unless a connector_failure explains it
        if n_cases and len(recs) < n_cases and rt_ref.id not in failed_rt:
            add("missing_trace",
                f"runtime {rt_ref.id}: {len(recs)} trace(s) for {n_cases} case(s)",
                WARN, runtime_id=rt_ref.id, harness_id=rt_ref.harness,
                evidence_ref=f"evidence/traces/{rt_ref.id}.jsonl")
        # runtime_mismatch: a trace points at a runtime/harness not in the mapping
        for r in recs:
            tr_rt, tr_h = r.get("runtime_id"), r.get("harness_id")
            if tr_rt is not None and tr_rt not in rt_harness:
                add("runtime_mismatch",
                    f"trace runtime_id {tr_rt!r} is not a declared agent runtime",
                    WARN, runtime_id=tr_rt, case_id=r.get("case_id"))
            elif tr_h is not None and rt_harness.get(tr_rt) not in (None, tr_h):
                add("runtime_mismatch",
                    f"runtime {tr_rt}: trace harness {tr_h!r} != declared {rt_harness.get(tr_rt)!r}",
                    WARN, runtime_id=tr_rt, case_id=r.get("case_id"), harness_id=tr_h)
        # path_drift + missing_artifact need the runtime's artifact rules
        rt = None
        if isinstance(rt_ref.spec, str) and rt_ref.spec:
            sp = exp_dir / rt_ref.spec
            if sp.is_file():
                try:
                    rt = load_agent_runtime_spec(sp)
                except ExperimentSpecError:
                    rt = None
        rules = rt.artifacts if rt else []
        # path_drift: an artifacts.collect glob escapes the working dir
        for rule in rules:
            if isinstance(rule, dict) and _glob_escapes(rule.get("glob")):
                add("path_drift",
                    f"runtime {rt_ref.id}: artifact glob {rule.get('glob')!r} "
                    f"escapes the working dir",
                    WARN, runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        # missing_artifact: a required rule with an empty per-case artifacts dir
        # (a standalone/replay backstop; AutoRunner also writes this during a live
        # run — deduped). Skipped for runtimes with a connector_failure.
        has_required = any(isinstance(r, dict) and r.get("required") for r in rules)
        if has_required and rt_ref.id not in failed_rt:
            for idx, case in enumerate(cases):
                cid = _case_id(case, idx)
                case_art = artifacts_dir / rt_ref.id / cid
                produced = case_art.is_dir() and any(p.is_file() for p in case_art.rglob("*"))
                if not produced:
                    add("missing_artifact",
                        f"runtime {rt_ref.id} case {cid}: required artifact(s) produced no files",
                        ERROR, runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness,
                        evidence_ref=f"evidence/artifacts/{rt_ref.id}/{cid}/")

    # missing_score / pending review per configured track
    for tr in spec.tracks:
        tid = tr.id or "track"
        agg = scores_tracks / f"{tid}.json"
        if not agg.is_file():
            add("missing_score", f"track {tid}: no aggregated score "
                f"(evidence/scores/tracks/{tid}.json missing)",
                WARN, track_id=tid, evidence_ref=f"evidence/scores/tracks/{tid}.json")
            continue
        try:
            status = json.loads(agg.read_text(encoding="utf-8")).get("status")
        except (OSError, json.JSONDecodeError):
            status = None
        if status == "error":
            add("missing_score", f"track {tid}: evaluation errored (no usable score)",
                WARN, track_id=tid, evidence_ref=f"evidence/scores/tracks/{tid}.json")
        elif status == "pending":
            add("missing_score", f"track {tid}: evaluation pending (human/llm review not done)",
                INFO, track_id=tid, evidence_ref=f"evidence/scores/tracks/{tid}.json")

    # merge: keep existing (AutoRunner) records, append deduped Inspector records,
    # renumber sequentially for a stable issues.jsonl
    merged = existing + added
    for n, rec in enumerate(merged, start=1):
        rec["id"] = f"issue-{n:03d}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with issues_path.open("w", encoding="utf-8") as f:
        for rec in merged:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    insp_dir = evidence_dir / "inspections"
    insp_dir.mkdir(parents=True, exist_ok=True)
    insp_path = insp_dir / "inspection.json"
    result = InspectionResult(issues=merged, added=added, inspection_path=insp_path)
    summary = {"experiment_id": spec.id, "issues_total": len(merged),
               "added_by_inspector": len(added), "checks": result.check_counts(),
               "by_severity": result.severity_counts(), "created_by": "Inspector"}
    insp_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
