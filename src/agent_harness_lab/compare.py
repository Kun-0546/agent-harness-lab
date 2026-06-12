"""hlab compare — summarize an A/B run into reports/compare.json.

Reads the evidence scores that `hlab run` already wrote (the EvaluationRunner output
for the objective's primary track), aggregates each harness's mean score, pass count,
and issue tags, picks the winner, and writes a machine-readable comparison plus a
data-driven reason. It does NOT re-run anything and does NOT draw the human's
conclusion — `hlab conclude` records that.

It reuses report_builder's harness-score aggregation so `compare`, `run`, `status`,
and `report` all agree on who won.

PR5 5b: when multiple trials exist in the trace files, emits the configured
aggregation stats (mean/stddev/min_max/median/win_rate) per metric across trials,
and states the trial count in the output. Single-trial experiments: output unchanged.
"""
from __future__ import annotations

import json
import statistics as _stats
from pathlib import Path

from agent_harness_lab import report_builder
from agent_harness_lab.experiment_spec import AGGREGATION_DEFAULT, ExperimentSpec


def _trial_count(evidence_dir: Path) -> int:
    """Return the number of distinct trials found in evidence/traces/."""
    tdir = evidence_dir / "traces"
    if not tdir.is_dir():
        return 0
    max_trial = -1
    for p in tdir.glob("*.jsonl"):
        try:
            for ln in p.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                t = rec.get("trial") if isinstance(rec, dict) else None
                t = t if isinstance(t, int) else 0
                if t > max_trial:
                    max_trial = t
        except OSError:
            continue
    return max_trial + 1 if max_trial >= 0 else 0


def _score_trial_count(evidence_dir: Path, track_id: str | None) -> int:
    """Return the number of distinct trials found in score records for a track.

    Defect 1e: trial_count in compare.json must be derived from scores actually
    present (per-trial scoring), not from traces. This prevents overstating the
    count when only some trials were scored.
    """
    if not track_id:
        return 0
    d = evidence_dir / "scores" / track_id
    if not d.is_dir():
        return 0
    max_trial = -1
    for p in sorted(d.glob("*.jsonl")):
        try:
            for ln in p.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                t = rec.get("trial")
                t = t if isinstance(t, int) else 0
                if t > max_trial:
                    max_trial = t
        except OSError:
            continue
    return max_trial + 1 if max_trial >= 0 else 0


def _per_trial_harness_scores(evidence_dir: Path, primary: str | None,
                               n_trials: int) -> dict[str, list[dict]]:
    """For each trial 0..n_trials-1, return {harness_id: score_dict}.

    Defect 1e: reads score records (which now carry trial fields from per-trial
    evaluation) rather than traces. This gives real per-trial score vectors for
    aggregation statistics.
    """
    result: dict[str, list[dict]] = {}  # harness_id -> list of per-trial score dicts
    for t in range(n_trials):
        recs = report_builder._read_records_trial(evidence_dir, primary, t)
        hscores = report_builder._harness_scores(recs)
        for hid, s in hscores.items():
            result.setdefault(hid, []).append(s)
    return result


def _compute_agg_stats(values: list[float], methods: list[str]) -> dict:
    """Compute the configured aggregation stats for a list of float values."""
    out: dict = {}
    if not values:
        return out
    if "mean" in methods:
        out["mean"] = round(sum(values) / len(values), 4)
    if "stddev" in methods:
        out["stddev"] = round(_stats.pstdev(values), 4) if len(values) > 1 else 0.0
    if "min_max" in methods:
        out["min"] = round(min(values), 4)
        out["max"] = round(max(values), 4)
    if "median" in methods:
        out["median"] = round(_stats.median(values), 4)
    return out


def _win_rate(harness_id: str, other_id: str,
              per_trial_scores: dict[str, list[dict]]) -> dict:
    """Fraction of trials where harness_id beats other_id (by mean score then pass rate).

    win_rate semantics: for each trial, compare the two harnesses by their mean
    score; if equal, compare pass rate. Ties (both metrics equal) count as neither
    winning. Returns {"wins": N, "losses": M, "ties": K, "rate": float} for
    harness_id vs other_id.
    """
    a_scores = per_trial_scores.get(harness_id, [])
    b_scores = per_trial_scores.get(other_id, [])
    n = min(len(a_scores), len(b_scores))
    wins = losses = ties = 0
    for i in range(n):
        a, b = a_scores[i], b_scores[i]
        am = a.get("mean") if a.get("mean") is not None else -1.0
        bm = b.get("mean") if b.get("mean") is not None else -1.0
        if am != bm:
            if am > bm:
                wins += 1
            else:
                losses += 1
        else:
            ar = (a["passed"] / a["total"]) if a.get("total") else 0.0
            br = (b["passed"] / b.get("total", 1)) if b.get("total") else 0.0
            if ar != br:
                if ar > br:
                    wins += 1
                else:
                    losses += 1
            else:
                ties += 1
    rate = round(wins / n, 4) if n else 0.0
    return {"wins": wins, "losses": losses, "ties": ties, "rate": rate}


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
    """Build the comparison dict from the primary track's evidence scores.

    PR5 5b: when multiple trials are present, adds `trial_count` and
    `aggregation_stats` (mean/stddev/min_max/median/win_rate across trials) to the
    output per the configured `execution.aggregation`. Single-trial output is
    unchanged (no extra fields to avoid noise)."""
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

    result: dict = {
        "experiment_id": spec.id,
        "primary_track": primary,
        "harnesses": harnesses,
        "winner": winner,
        "winner_name": name_of.get(winner) if winner else None,
        "reason": _build_reason(harnesses, winner, name_of, primary),
        "report_path": "reports/report.md",
        "compare_path": "reports/compare.json",
    }

    # PR5 5b: multi-trial aggregation stats — use score-based count (defect 1e).
    # trial_count derived from scores actually present, not from traces, to avoid
    # overstating when only some trials have been scored.
    n_trials = _score_trial_count(evidence_dir, primary)
    if n_trials > 1:
        result["trial_count"] = n_trials
        agg_methods = list(spec.aggregation) if spec.aggregation else list(AGGREGATION_DEFAULT)
        per_trial = _per_trial_harness_scores(evidence_dir, primary, n_trials)
        agg_stats: dict[str, dict] = {}
        for h in spec.harnesses:
            hid = h.id
            trial_scores = per_trial.get(hid, [])
            means = [s["mean"] for s in trial_scores if s.get("mean") is not None]
            per_h: dict = {}
            per_h["score"] = _compute_agg_stats(means, agg_methods)
            if "win_rate" in agg_methods:
                others = [oh.id for oh in spec.harnesses if oh.id != hid and oh.id in per_trial]
                for other_id in others:
                    wr = _win_rate(hid, other_id, per_trial)
                    per_h.setdefault("win_rate_vs", {})[other_id] = wr
            agg_stats[hid] = per_h
        result["aggregation_stats"] = agg_stats

    return result


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
