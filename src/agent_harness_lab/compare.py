"""hlab compare — summarize an A/B run into reports/compare.json.

Reads the evidence scores that `hlab run` already wrote (the EvaluationRunner output
for the objective's primary track), aggregates each harness's mean score, pass count,
and issue tags, picks the winner, and writes a machine-readable comparison plus a
data-driven reason. It does NOT re-run anything and does NOT draw the human's
conclusion — `hlab conclude` records that.

It reuses report_builder's harness-score aggregation so `compare`, `run`, `status`,
and `report` all agree on who won.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent_harness_lab import report_builder
from agent_harness_lab.experiment_spec import ExperimentSpec


def _aggregate_issues(records: list[dict], harness_id) -> dict[str, int]:
    """Count the optional `issues` tags a benchmark emitted for this harness."""
    counts: dict[str, int] = {}
    for r in records:
        if r.get("harness_id") != harness_id:
            continue
        for tag in (r.get("issues") or []):
            counts[str(tag)] = counts.get(str(tag), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _fmt_score(x) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) else "—"


def _build_reason(harnesses: list[dict], winner, name_of: dict, primary) -> str:
    """A deterministic, data-driven reason — a summary of the numbers, not a value
    judgment (the human's judgment goes in `hlab conclude`)."""
    if not winner:
        if not any(h["total"] for h in harnesses):
            return (f"No per-harness scores on track '{primary}'. Run the experiment "
                    f"first (`hlab run`), then compare.")
        return f"No single winner on track '{primary}' — the harnesses tie."
    w = next((h for h in harnesses if h["id"] == winner), None)
    others = [h for h in harnesses if h["id"] != winner and h["total"]]
    bits = [f"Harness {winner} ({name_of.get(winner, winner)}) leads on '{primary}'"]
    if w and others:
        o = others[0]
        bits.append(f"score {_fmt_score(w['score'])} vs {_fmt_score(o['score'])}")
        bits.append(f"{w['passed']}/{w['total']} vs {o['passed']}/{o['total']} cases passed")
        fewer = [t for t in o["issues"] if o["issues"].get(t, 0) > w["issues"].get(t, 0)]
        if fewer:
            bits.append("fewer " + ", ".join(sorted(fewer)))
    return "; ".join(bits) + "."


def build_comparison(exp_dir: Path, spec: ExperimentSpec) -> dict:
    """Build the comparison dict from the primary track's evidence scores."""
    evidence_dir = Path(exp_dir) / "evidence"
    primary = report_builder._primary_track_id(spec)
    records = report_builder._read_records(evidence_dir, primary)
    hscores = report_builder._harness_scores(records)
    name_of = {h.id: h.name for h in spec.harnesses}
    winner = report_builder._winner(hscores)

    harnesses: list[dict] = []
    for h in spec.harnesses:
        s = hscores.get(h.id)
        if s:
            harnesses.append({
                "id": h.id, "name": h.name,
                "score": round(s["mean"], 4) if s["mean"] is not None else None,
                "passed": s["passed"], "total": s["total"],
                "issues": _aggregate_issues(records, h.id),
            })
        else:
            harnesses.append({"id": h.id, "name": h.name, "score": None,
                              "passed": 0, "total": 0, "issues": {}})

    return {
        "experiment_id": spec.id,
        "primary_track": primary,
        "harnesses": harnesses,
        "winner": winner,
        "winner_name": name_of.get(winner) if winner else None,
        "reason": _build_reason(harnesses, winner, name_of, primary),
        "report_path": "reports/report.md",
        "compare_path": "reports/compare.json",
    }


def write_comparison(exp_dir: Path, spec: ExperimentSpec) -> tuple[Path, dict]:
    """Write reports/compare.json and return (path, data)."""
    data = build_comparison(exp_dir, spec)
    reports_dir = Path(exp_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / "compare.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out, data


def format_summary(data: dict) -> str:
    """Human-facing console summary mirroring compare.json."""
    lines = ["Harness comparison", ""]
    for h in data["harnesses"]:
        lines.append(f"{h['id']} {h['name']}")
        lines.append(f"  score: {_fmt_score(h['score'])}")
        lines.append(f"  passed: {h['passed']}/{h['total']}")
        if h["issues"]:
            lines.append("  issues:")
            for tag, count in h["issues"].items():
                lines.append(f"    - {tag}: {count}")
        else:
            lines.append("  issues: none")
        lines.append("")
    lines.append(f"Winner: {data['winner'] or '(no single winner)'}")
    lines.append(f"Reason: {data['reason']}")
    return "\n".join(lines)
