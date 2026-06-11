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

from agent_harness_lab import markdown_html
from agent_harness_lab.experiment_spec import (
    ExperimentSpec,
    ExperimentSpecError,
    load_agent_runtime_spec,
    load_cases,
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


def _read_records(evidence_dir: Path, track_id: str | None) -> list[dict]:
    """All per-evaluator score records for a track (across its evaluators)."""
    recs: list[dict] = []
    if not track_id:
        return recs
    d = evidence_dir / "scores" / track_id
    if d.is_dir():
        for p in sorted(d.glob("*.jsonl")):
            recs.extend(_read_jsonl(p))
    return recs


def _harness_scores(records: list[dict]) -> dict[str, dict]:
    """Group benchmark records by harness_id → {passed, total, mean}."""
    out: dict[str, dict] = {}
    for r in records:
        hid = r.get("harness_id")
        if hid is None:
            continue
        s = out.setdefault(hid, {"passed": 0, "total": 0, "_sum": 0.0, "_n": 0})
        s["total"] += 1
        if r.get("status") == "passed" or r.get("passed") is True:
            s["passed"] += 1
        if isinstance(r.get("score"), (int, float)):
            s["_sum"] += float(r["score"])
            s["_n"] += 1
    for s in out.values():
        s["mean"] = (s["_sum"] / s["_n"]) if s["_n"] else None
    return out


def _winner(hscores: dict[str, dict]) -> str | None:
    """The harness strictly ahead by mean score then pass rate; None on tie/empty."""
    if not hscores:
        return None

    def rank(hid):
        s = hscores[hid]
        mean = s["mean"] if s["mean"] is not None else -1.0
        rate = (s["passed"] / s["total"]) if s["total"] else 0.0
        return (mean, rate)

    ordered = sorted(hscores, key=rank, reverse=True)
    if len(ordered) == 1 or rank(ordered[0]) > rank(ordered[1]):
        return ordered[0]
    return None


def _primary_track_id(spec: ExperimentSpec) -> str | None:
    if spec.objective and spec.objective.primary_track:
        return spec.objective.primary_track
    return spec.tracks[0].id if spec.tracks else None


def _load_cases_safe(exp_dir: Path, spec: ExperimentSpec) -> list[dict]:
    try:
        if spec.cases_root and spec.cases_files:
            return load_cases(exp_dir / spec.cases_root, spec.cases_files)
    except ExperimentSpecError:
        pass
    return []


def comparative_summary(exp_dir: Path, spec: ExperimentSpec) -> dict | None:
    """For a multi-harness A/B benchmark run, the comparative verdict; else None.

    Shared by `hlab run` / `hlab status` so their summaries match the report — a
    multi-harness run is a COMPARISON with a winner, not a "failed" track. Returns
    {primary, winner, winner_name, best_passed, best_total, objective_met} or None
    when fewer than two harnesses have per-harness scores.
    """
    evidence_dir = Path(exp_dir) / "evidence"
    primary = _primary_track_id(spec)
    hscores = _harness_scores(_read_records(evidence_dir, primary))
    if len(hscores) < 2:
        return None
    winner = _winner(hscores)
    name_of = {h.id: h.name for h in spec.harnesses}
    out: dict = {"primary": primary, "winner": winner,
                 "winner_name": (name_of.get(winner, winner) if winner else None),
                 "objective_met": False}
    if winner:
        s = hscores[winner]
        out["best_passed"], out["best_total"] = s["passed"], s["total"]
        out["objective_met"] = bool(s["total"] and s["passed"] == s["total"])
    return out


def _build_markdown(exp_dir: Path, spec: ExperimentSpec) -> str:
    evidence_dir = exp_dir / "evidence"
    tracks_dir = evidence_dir / "scores" / "tracks"
    primary = _primary_track_id(spec)
    records = _read_records(evidence_dir, primary)
    hscores = _harness_scores(records)
    name_of = {h.id: h.name for h in spec.harnesses}
    winner = _winner(hscores)
    is_comparative = len(hscores) >= 2  # multi-harness A/B → a comparison, not pass/fail
    cases = _load_cases_safe(exp_dir, spec)
    L: list[str] = []
    L.append(f"# Experiment Report: {spec.id or '(unset)'}")
    L.append("")
    L.append(f"- **Question:** {spec.question or '(unset)'}")
    L.append(f"- **Status:** {spec.status or '(unset)'}")
    L.append(f"- **Run mode:** {spec.run_mode or '(unset)'}")
    L.append(f"- **Execution mode:** {spec.execution_mode or '(unset)'} "
             f"(state_policy={spec.state_policy or '(unset)'})")
    L.append("")

    # ---- Harness comparison (the A/B headline) ----
    L.append("## Harness comparison")
    if hscores:
        L.append(f"Per-harness result on the **`{primary}`** benchmark track:")
        L.append("")
        L.append("| Harness | Name | Cases passed | Mean score |")
        L.append("|---|---|---|---|")
        for h in spec.harnesses:
            s = hscores.get(h.id)
            if s:
                mean = f"{s['mean']:.2f}" if s["mean"] is not None else "—"
                L.append(f"| `{h.id}` | {h.name} | {s['passed']}/{s['total']} | {mean} |")
            else:
                L.append(f"| `{h.id}` | {h.name} | — | — |")
        L.append("")
        if winner:
            L.append(f"**Winner (by `{primary}`): `{winner}` — {name_of.get(winner, winner)}.**")
            for h in spec.harnesses:
                if h.id == winner or h.id not in hscores:
                    continue
                reason = next((r.get("detail") for r in records
                               if r.get("harness_id") == h.id and r.get("status") != "passed"
                               and r.get("detail")), None)
                if reason:
                    L.append(f"- `{h.id}` ({h.name}) fell short — e.g. {reason}.")
        else:
            L.append(f"**No single winner on `{primary}` — the harnesses tie.**")
    else:
        L.append("- No per-harness benchmark scores were produced "
                 "(no benchmark evaluator emitted per-harness records).")
    L.append("")

    # ---- Cases ----
    L.append("## Cases")
    if cases:
        for c in cases:
            cid = c.get("id", "(case)")
            inp = c.get("input", "")
            exp_kw = c.get("expect")
            L.append(f"- `{cid}` — {inp}" + (f"  _(expect: `{exp_kw}`)_" if exp_kw else ""))
    else:
        L.append("- (no cases declared)")
    L.append("")

    # ---- Evidence (per runtime) ----
    L.append("## Evidence")
    if spec.agent_runtimes:
        for r in spec.agent_runtimes:
            tr = _read_jsonl(evidence_dir / "traces" / f"{r.id}.jsonl")
            raw_dir = evidence_dir / "raw" / r.id
            n_raw = len(list(raw_dir.glob("*.out"))) if raw_dir.is_dir() else 0
            art_dir = evidence_dir / "artifacts" / r.id
            n_art = len([p for p in art_dir.rglob("*") if p.is_file()]) if art_dir.is_dir() else 0
            L.append(f"- `{r.id}` (harness `{r.harness}`, connector "
                     f"{_connector_type(exp_dir, r)}): {len(tr)} trace(s), "
                     f"{n_raw} raw output(s), {n_art} artifact file(s)")
    else:
        L.append("- (no agent runtimes)")
    L.append("")

    # ---- Artifacts ----
    L.append("## Artifacts")
    any_art = False
    for r in spec.agent_runtimes:
        art_dir = evidence_dir / "artifacts" / r.id
        files = sorted(p for p in art_dir.rglob("*") if p.is_file()) if art_dir.is_dir() else []
        if files:
            any_art = True
            sample = files[0].relative_to(evidence_dir).as_posix()
            L.append(f"- `{r.id}` (harness `{r.harness}`): {len(files)} file(s) collected "
                     f"— e.g. `{sample}`")
    if not any_art:
        L.append("- No artifacts collected.")
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
            tid = d.get("track_id")
            q = f" — {d.get('question')}" if d.get("question") else ""
            if is_comparative and tid == primary:
                # multi-harness A/B: the outcome is a comparison, not a single pass/fail
                if winner:
                    L.append(f"- **{tid}**: comparative — winner `{winner}` "
                             f"({name_of.get(winner, winner)}){q}")
                else:
                    L.append(f"- **{tid}**: comparative — no single winner{q}")
                L.append("    - per-harness scores; see **Harness comparison** above")
            else:
                L.append(f"- **{tid}**: {status}{q}")
                for e in d.get("evaluators", []):
                    L.append(f"    - `{e.get('evaluator_id')}` ({e.get('method')}): "
                             f"{e.get('status')}" + (f" score={e.get('score')}" if e.get("score") is not None else ""))
    if any_pending:
        L.append("")
        L.append("> Some tracks are **pending**: `human_annotation` evaluators await an "
                 "annotation file, and `llm_judge` evaluators are pending unless "
                 "`AHL_JUDGE_*` is configured (a missing key is reported as pending — the "
                 "judge never invents a verdict). Their verdicts are not final.")
    L.append("")

    # ---- Methodology (how the numbers above were produced; plain text only) ----
    L.append("## Methodology")
    if spec.tracks:
        method_of = {e.id: e.method for e in spec.evaluators if isinstance(e.id, str)}
        for tr in spec.tracks:
            evs = ", ".join(f"`{ref}` ({method_of.get(ref) or 'unknown'})"
                            for ref in tr.evaluators) or "(no evaluators)"
            L.append(f"- Track `{tr.id}` — evaluators: {evs}")
    else:
        L.append("- No evaluation tracks configured.")
    L.append("- **Status meanings:** `passed` / `failed` are real evaluator verdicts; "
             "`pending` means the evaluator did not run (a human annotation not yet "
             "recorded, or `llm_judge` without `AHL_JUDGE_*` configured); `error` means "
             "the evaluator could not produce a usable verdict — it is never counted "
             "as a score.")
    L.append("- **Score semantics:** `benchmark` scores come from the script's stdout "
             "JSON (the scale is benchmark-defined; the shipped benchmarks use 0-1); "
             "`llm_judge` scores are 0-100 as returned by the judge model; "
             "`human_annotation` scores are read verbatim from the annotation file.")
    L.append("")

    # Objective
    L.append("## Objective")
    if spec.objective and spec.objective.primary_track:
        obj = spec.objective
        L.append(f"- **Primary track:** `{obj.primary_track}`")
        if obj.success_criteria:
            L.append(f"- **Success criteria:** {obj.success_criteria}")
        if obj.optimize_for:
            L.append(f"- **Optimize for:** {obj.optimize_for}")
        if is_comparative and winner:
            # A/B: report a comparison with a clear winner — never a "failed" track.
            ws = hscores[winner]
            L.append("- **Track result:** comparative")
            L.append(f"- **Winner:** `{winner}` — {name_of.get(winner, winner)}")
            L.append(f"- **Best harness passed:** {ws['passed']}/{ws['total']}")
            others = [h.id for h in spec.harnesses if h.id in hscores and h.id != winner]
            for hid in others:
                s = hscores[hid]
                label = "Baseline passed" if len(others) == 1 else f"`{hid}` passed"
                L.append(f"- **{label}:** {s['passed']}/{s['total']}")
            if ws["total"] and ws["passed"] == ws["total"]:
                L.append("- **Objective met:** yes, because the best harness satisfies the objective")
            elif ws["passed"]:
                L.append(f"- **Objective partially met:** the best harness satisfies the objective "
                         f"on {ws['passed']}/{ws['total']} cases")
            else:
                L.append("- **Objective not met:** no harness satisfies the objective")
        elif winner and hscores.get(winner):
            s = hscores[winner]
            if s["total"] and s["passed"] == s["total"]:
                L.append(f"- **Objective met:** yes — harness `{winner}` "
                         f"({name_of.get(winner, winner)}) passed {s['passed']}/{s['total']}.")
            elif s["passed"]:
                L.append(f"- **Objective partially met:** harness `{winner}` passed "
                         f"{s['passed']}/{s['total']}.")
            else:
                L.append("- **Objective not met:** no case passed.")
        else:
            agg = tracks_dir / f"{obj.primary_track}.json"
            st = "(no score)"
            if agg.is_file():
                try:
                    st = json.loads(agg.read_text(encoding="utf-8")).get("status", st)
                except (OSError, json.JSONDecodeError):
                    pass
            L.append(f"- **Primary track status:** {st}")
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
    L.append("- `llm_judge` evaluators call a real LLM only when `AHL_JUDGE_BASE_URL` / "
             "`AHL_JUDGE_MODEL` / `AHL_JUDGE_API_KEY` are set; otherwise they are pending "
             "(the judge never invents a score).")
    L.append("- `human_annotation` requires an annotation file; absent it stays pending.")
    L.append("- Executable connectors are `local_cli` / `script` only; "
             "`remote_devbox` / `api` / `bridge` are not executed in this phase.")
    L.append("- State policies run at a local-filesystem MVP level.")
    L.append("- Auto Optimize is deterministic / script-based (copy-only or a mutation "
             "script) — not a general AI self-improvement engine.")
    L.append("")

    # Recommendation (data-driven, but never the human's final conclusion)
    L.append("## Recommendation")
    if winner and primary:
        L.append(f"Based on the `{primary}` benchmark track, Harness `{winner}` "
                 f"({name_of.get(winner, winner)}) is stronger for this objective. A human "
                 f"reviewer should inspect the evidence and decide whether to adopt it in "
                 f"`conclusion.md`.")
    else:
        L.append("The benchmark did not single out a stronger harness. A human reviewer "
                 "should inspect the evidence and record a decision in `conclusion.md`.")
    L.append("")
    conclusion = exp_dir / "conclusion.md"
    if conclusion.is_file():
        L.append("A `conclusion.md` exists — confirm it reflects the evidence above.")
    else:
        L.append("This report does **not** draw the conclusion for you. Write your decision "
                 "in `conclusion.md` (Decision / Rationale / Evidence relied on / Evidence not "
                 "trusted / Next step).")
    L.append("")
    return "\n".join(L)


def build_report(exp_dir: Path, spec: ExperimentSpec) -> Path:
    """Write reports/report.md (+ report.html if `html` is in reports.formats).

    Returns the .md path. report.html is a real, self-contained Markdown render of
    the same report.md (stdlib renderer; no external dependency) — content is escaped,
    so evidence text cannot inject markup."""
    exp_dir = Path(exp_dir).resolve()
    reports_dir = exp_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    md = _build_markdown(exp_dir, spec)
    md_path = reports_dir / "report.md"
    md_path.write_text(md, encoding="utf-8")
    if "html" in (spec.report_formats or []):
        rendered = markdown_html.render(md, title=f"Report: {spec.id or 'experiment'}")
        (reports_dir / "report.html").write_text(rendered, encoding="utf-8")
    return md_path
