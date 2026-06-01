"""ReportBuilder — generate reports/report.md from an experiment's evidence.

`hlab report` calls build_report(). It reads experiment.yaml + the evidence store
(traces / raw / artifacts / scores / issues / inspections) and the optional Auto
Optimize history, and writes a human-facing reports/report.md (+ a minimal
report.html if `html` is in reports.formats).

Honesty rules (do NOT oversell):
  - if a track's evaluation is pending (human/llm not executed) → say "pending";
  - llm_judge runs as an offline stub → its scores are pending, stated plainly;
  - if the Auto Optimize loop did not run → say "not run";
  - it never fabricates a conclusion and never writes conclusion.md — it only
    points the human at the next step.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent_harness_lab.experiment_spec import (
    ExperimentSpec,
    ExperimentSpecError,
    load_agent_runtime_spec,
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def _trace_counts(evidence_dir: Path) -> tuple[int, int]:
    tdir = evidence_dir / "traces"
    runtimes = total = 0
    if tdir.is_dir():
        for p in sorted(tdir.glob("*.jsonl")):
            recs = _read_jsonl(p)
            if recs:
                runtimes += 1
                total += len(recs)
    return runtimes, total


def _evidence_present(evidence_dir: Path, sub: str) -> bool:
    d = evidence_dir / sub
    return d.is_dir() and any(f.name != ".gitkeep" for f in d.rglob("*") if f.is_file())


def _connector_type(exp_dir: Path, rt_ref) -> str:
    if isinstance(rt_ref.spec, str) and rt_ref.spec:
        sp = exp_dir / rt_ref.spec
        if sp.is_file():
            try:
                return load_agent_runtime_spec(sp).connector_type or "?"
            except ExperimentSpecError:
                return "(unreadable)"
        return "(missing spec)"
    return "?"


def _build_markdown(exp_dir: Path, spec: ExperimentSpec) -> str:
    evidence_dir = exp_dir / "evidence"
    L: list[str] = []
    L.append(f"# Experiment Report: {spec.id or '(unset)'}")
    L.append("")
    L.append(f"- **Question:** {spec.question or '(unset)'}")
    L.append(f"- **Status:** {spec.status or '(unset)'}")
    L.append(f"- **Run mode:** {spec.run_mode or '(unset)'}")
    L.append(f"- **Execution mode:** {spec.execution_mode or '(unset)'} "
             f"(state_policy={spec.state_policy or '(unset)'})")
    L.append("")

    L.append("## Harnesses")
    if spec.harnesses:
        for h in spec.harnesses:
            L.append(f"- `{h.id}` = {h.name} ({h.path})")
    else:
        L.append("- (none)")
    L.append("")

    L.append("## Agent runtimes")
    if spec.agent_runtimes:
        for r in spec.agent_runtimes:
            L.append(f"- `{r.id}` → harness `{r.harness}` (connector: {_connector_type(exp_dir, r)})")
    else:
        L.append("- (none)")
    L.append("")

    runtimes, traces = _trace_counts(evidence_dir)
    L.append("## Cases & evidence")
    L.append(f"- **Traces:** {traces} record(s) across {runtimes} runtime(s)")
    L.append(f"- **raw:** {'present' if _evidence_present(evidence_dir, 'raw') else 'none'}")
    L.append(f"- **artifacts:** {'present' if _evidence_present(evidence_dir, 'artifacts') else 'none'}")
    L.append(f"- **scores:** {'present' if _evidence_present(evidence_dir, 'scores') else 'none'}")
    L.append("")

    # Issues
    issues = _read_jsonl(evidence_dir / "issues.jsonl")
    L.append("## Issues")
    if issues:
        by_sev: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for i in issues:
            by_sev[i.get("severity", "error")] = by_sev.get(i.get("severity", "error"), 0) + 1
            by_type[i.get("type", "?")] = by_type.get(i.get("type", "?"), 0) + 1
        L.append(f"- **Total:** {len(issues)}")
        L.append(f"- **By severity:** " + ", ".join(f"{k}: {v}" for k, v in sorted(by_sev.items())))
        L.append(f"- **By type:** " + ", ".join(f"{k}: {v}" for k, v in sorted(by_type.items())))
        L.append("")
        for i in issues:
            loc = " ".join(x for x in (i.get("runtime_id"), i.get("case_id"), i.get("track_id")) if x)
            L.append(f"  - [{i.get('severity', 'error')}] {i.get('type')}"
                     f"{(' (' + loc + ')') if loc else ''}: {i.get('message', '')}")
    else:
        L.append("- none recorded")
    L.append("")

    # Evaluation
    tracks_dir = evidence_dir / "scores" / "tracks"
    L.append("## Evaluation")
    track_files = sorted(tracks_dir.glob("*.json")) if tracks_dir.is_dir() else []
    any_pending = False
    if not spec.tracks:
        L.append("- No evaluation tracks configured — nothing was evaluated.")
    elif not track_files:
        L.append("- Tracks are configured but no scores were produced "
                 "(EvaluationRunner did not run, or produced no output).")
    else:
        for p in track_files:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            status = d.get("status")
            any_pending = any_pending or status == "pending"
            q = f" — {d.get('question')}" if d.get("question") else ""
            L.append(f"- **{d.get('track_id')}**: {status}{q}")
            for e in d.get("evaluators", []):
                L.append(f"    - `{e.get('evaluator_id')}` ({e.get('method')}): "
                         f"{e.get('status')}" + (f" score={e.get('score')}" if e.get("score") is not None else ""))
    if any_pending:
        L.append("")
        L.append("> Some tracks are **pending**: `human_annotation` evaluators await an "
                 "annotation file and `llm_judge` evaluators run as an **offline stub "
                 "(no LLM call)** in this phase. Their verdicts are not final.")
    L.append("")

    # Objective
    L.append("## Objective")
    if spec.objective and spec.objective.primary_track:
        obj = spec.objective
        prim_status = "(no score)"
        agg = tracks_dir / f"{obj.primary_track}.json"
        if agg.is_file():
            try:
                prim_status = json.loads(agg.read_text(encoding="utf-8")).get("status", "(no score)")
            except (OSError, json.JSONDecodeError):
                pass
        L.append(f"- **Primary track:** `{obj.primary_track}` → **{prim_status}**")
        if obj.success_criteria:
            L.append(f"- **Success criteria:** {obj.success_criteria}")
        if obj.optimize_for:
            L.append(f"- **Optimize for:** {obj.optimize_for}")
    else:
        L.append("- No objective defined.")
    L.append("")

    # Auto Optimize
    L.append("## Auto Optimize")
    history = _read_jsonl(exp_dir / "optimization" / "history.jsonl")
    if spec.optimization and spec.optimization.enabled:
        if history:
            promoted = sum(1 for h in history if h.get("promoted"))
            L.append(f"- Loop ran: {len(history)} iteration(s), {promoted} promotion(s).")
            for h in history:
                L.append(f"    - iter {h.get('iteration')}: "
                         f"{'PROMOTED' if h.get('promoted') else 'rejected'} "
                         f"({h.get('reason', '')})")
        else:
            L.append("- Auto Optimize is **enabled** but the loop produced no history "
                     "(`optimization/history.jsonl` absent) — **not run** in this report.")
    elif spec.optimization:
        L.append("- Auto Optimize is declared but **disabled** (`optimization.enabled: false`).")
    else:
        L.append("- No Auto Optimize configuration.")
    L.append("")

    # Known limitations (honest, phase-accurate)
    L.append("## Known limitations")
    L.append("- `llm_judge` evaluators are an **offline stub** — no external LLM is called; "
             "their scores are pending.")
    L.append("- `human_annotation` requires an annotation file; absent it stays pending.")
    L.append("- Executable connectors are `local_cli` / `script` only; "
             "`remote_devbox` / `api` / `bridge` are not executed in this phase.")
    L.append("- State policies run at a local-filesystem MVP level.")
    L.append("- Auto Optimize is deterministic / script-based (copy-only or a mutation "
             "script) — not a general AI self-improvement engine.")
    L.append("")

    # Next step (never fabricate a conclusion)
    L.append("## Next step")
    conclusion = exp_dir / "conclusion.md"
    if conclusion.is_file():
        L.append("- A `conclusion.md` exists — confirm it reflects the evidence above.")
    else:
        L.append("- Write your decision in `conclusion.md` "
                 "(Human conclusion / Rationale / Evidence relied on / Evidence not trusted / "
                 "Next step). This report does **not** draw a conclusion for you.")
    L.append("")
    return "\n".join(L)


def build_report(exp_dir: Path, spec: ExperimentSpec) -> Path:
    """Write reports/report.md (+ minimal report.html if requested). Returns the .md path."""
    exp_dir = Path(exp_dir).resolve()
    reports_dir = exp_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    md = _build_markdown(exp_dir, spec)
    md_path = reports_dir / "report.md"
    md_path.write_text(md, encoding="utf-8")
    if "html" in (spec.report_formats or []):
        # Minimal, honest render: the markdown verbatim inside a <pre> block. Not a
        # full Markdown→HTML renderer (review WARNs that one is unavailable).
        esc = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = (f"<!doctype html><html><head><meta charset=\"utf-8\">"
                f"<title>Report: {spec.id or ''}</title></head>"
                f"<body><pre>{esc}</pre></body></html>\n")
        (reports_dir / "report.html").write_text(html, encoding="utf-8")
    return md_path
