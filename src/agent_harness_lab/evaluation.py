"""EvaluationRunner — judge an Auto Run's evidence with the experiment's evaluators.

Three-layer model (see docs/v1-spec): workspace **Evaluation Methods** →
experiment **Evaluator Instances** (`evaluation.evaluators[]`) → **Evaluation
Tracks** (`evaluation.tracks[]`, each grouping evaluator ids + expected evidence).
`run_evaluation()` executes every evaluator referenced by a track and aggregates a
per-track status, then reflects the objective's primary track.

Bounded by design:
  - benchmark      — runs `evaluator.script` (under evaluation.root) with a JSON
                     context file as argv[1]; the script prints JSON to stdout
                     ({"passed": bool, "score"?, "detail"?} or {"records": [...]}).
                     Run with file-redirected stdout + proc.wait(timeout) + a
                     process-group sweep (same hardening as the script connector),
                     so a misbehaving evaluator can never hang or orphan.
  - human_annotation — NO interactive UI. If an annotation file exists, ingest it;
                     else write a `pending` record (never blocks).
  - llm_judge      — pending without AHL_JUDGE_API_KEY (it never invents a verdict);
                     with AHL_JUDGE_* set it judges each (harness, case) via llm.chat,
                     recording a request failure or unparseable reply as `error`.

Outputs:
  evidence/scores/<track_id>/<evaluator_id>.jsonl   per-evaluator score records
  evidence/scores/tracks/<track_id>.json            aggregated track status
Track / evaluator status ∈ {passed, failed, pending, error}.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_harness_lab import llm
from agent_harness_lab.agentconn import _POSIX, _pgid_of
from agent_harness_lab.auto import _read_text, _sweep_group
from agent_harness_lab.experiment_spec import (
    EvaluatorSpec,
    ExperimentSpec,
    ExperimentSpecError,
    load_cases,
)

PASSED, FAILED, PENDING, ERROR = "passed", "failed", "pending", "error"
# track status precedence (worst-first): a hard error dominates, then a definite
# failure, then an incomplete (pending) judgement, else all-passed.
_PRECEDENCE = (ERROR, FAILED, PENDING, PASSED)

try:
    _EVAL_TIMEOUT = float(os.environ.get("AHL_EVAL_TIMEOUT", "60"))
except ValueError:
    _EVAL_TIMEOUT = 60.0


@dataclass
class EvaluatorOutcome:
    track_id: str
    evaluator_id: str
    method: str | None
    status: str
    score: float | None = None
    detail: str = ""
    records_path: str | None = None


@dataclass
class TrackOutcome:
    track_id: str
    question: str | None
    status: str
    evaluators: list[EvaluatorOutcome] = field(default_factory=list)
    path: str | None = None


@dataclass
class EvaluationResult:
    tracks: list[TrackOutcome] = field(default_factory=list)
    objective_track: str | None = None
    objective_status: str | None = None
    ran: bool = False  # True if at least one track was evaluated

    def status_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in self.tracks:
            out[t.status] = out.get(t.status, 0) + 1
        return out


def _aggregate(statuses: list[str]) -> str:
    """Worst status wins (error > failed > pending > passed). Empty → pending."""
    if not statuses:
        return PENDING
    for s in _PRECEDENCE:
        if s in statuses:
            return s
    return PENDING


def _load_traces(evidence_dir: Path) -> dict[str, list[dict]]:
    traces: dict[str, list[dict]] = {}
    tdir = evidence_dir / "traces"
    if not tdir.is_dir():
        return traces
    for p in sorted(tdir.glob("*.jsonl")):
        recs: list[dict] = []
        for ln in _read_text(p).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                recs.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        traces[p.stem] = recs
    return traces


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _run_benchmark(ev: EvaluatorSpec, track_id: str, exp_dir: Path,
                   eval_root: Path, context: dict, scores_dir: Path) -> EvaluatorOutcome:
    """Run a benchmark evaluator script and turn its JSON stdout into records."""
    out = EvaluatorOutcome(track_id, ev.id or "?", ev.method, ERROR)
    if not ev.script:
        out.detail = "benchmark evaluator has no `script`"
        return out
    script_path = (eval_root / ev.script).resolve()
    if not script_path.is_file():
        out.detail = f"benchmark script not found: {ev.script}"
        return out

    dest = scores_dir / track_id
    dest.mkdir(parents=True, exist_ok=True)
    ctx_path = dest / f"{ev.id}.context.json"
    ctx_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    so_path, se_path = dest / f"{ev.id}.stdout.txt", dest / f"{ev.id}.stderr.txt"

    timed_out = False
    with open(so_path, "w", encoding="utf-8") as fo, open(se_path, "w", encoding="utf-8") as fe:
        proc = subprocess.Popen(
            [sys.executable, str(script_path), str(ctx_path)],
            shell=False, cwd=str(exp_dir),
            stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
            text=True, encoding="utf-8", close_fds=True, start_new_session=_POSIX,
        )
        pgid = _pgid_of(proc)
        try:
            proc.wait(timeout=_EVAL_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
    _sweep_group(proc, pgid)
    stdout, stderr = _read_text(so_path), _read_text(se_path)

    if timed_out:
        out.detail = f"benchmark script timed out after {_EVAL_TIMEOUT:g}s"
        return out
    if proc.returncode != 0:
        out.detail = f"benchmark script exited {proc.returncode}: {stderr.strip()[:200]}"
        return out
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        out.detail = f"benchmark script stdout is not JSON: {stdout.strip()[:200]}"
        return out

    records: list[dict] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("records"), list):
        per = parsed["records"]
        passed = bool(per) and all(bool(r.get("passed")) for r in per if isinstance(r, dict))
        scores = [r.get("score") for r in per if isinstance(r, dict) and isinstance(r.get("score"), (int, float))]
        out.status = PASSED if passed else FAILED
        out.score = (sum(scores) / len(scores)) if scores else None
        for r in per:
            if isinstance(r, dict):
                rec = {"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
                       "status": PASSED if r.get("passed") else FAILED,
                       "score": r.get("score"), "detail": str(r.get("detail", "")),
                       "case_id": r.get("case_id"), "harness_id": r.get("harness_id"),
                       "created_by": "EvaluationRunner"}
                # additive + backward-compatible: a benchmark MAY emit per-(harness,case)
                # `dimensions` (dict) and/or `issues` (list) for richer `hlab compare`;
                # benchmarks that don't emit them are unaffected.
                for opt in ("dimensions", "issues"):
                    if opt in r:
                        rec[opt] = r[opt]
                records.append(rec)
    elif isinstance(parsed, dict) and "passed" in parsed:
        out.status = PASSED if parsed.get("passed") else FAILED
        out.score = parsed.get("score") if isinstance(parsed.get("score"), (int, float)) else None
        out.detail = str(parsed.get("detail", ""))
        records.append({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
                        "status": out.status, "score": out.score, "detail": out.detail,
                        "created_by": "EvaluationRunner"})
    else:
        out.detail = "benchmark JSON must contain `passed` or `records`"
        return out

    records_path = dest / f"{ev.id}.jsonl"
    _write_jsonl(records_path, records)
    out.records_path = str(records_path)
    return out


def _run_human(ev: EvaluatorSpec, track_id: str, exp_dir: Path,
               eval_root: Path, scores_dir: Path) -> EvaluatorOutcome:
    """Ingest a human annotation file if present; else write a pending record."""
    out = EvaluatorOutcome(track_id, ev.id or "?", ev.method, PENDING)
    dest = scores_dir / track_id
    dest.mkdir(parents=True, exist_ok=True)
    # annotation location: evaluator.raw['annotation'] (rel to eval root) or a
    # conventional evidence/scores/<track>/<evaluator>.annotation.json drop-in.
    ann_rel = ev.raw.get("annotation") if isinstance(ev.raw, dict) else None
    candidates = []
    if isinstance(ann_rel, str) and ann_rel:
        candidates.append((eval_root / ann_rel).resolve())
    candidates.append(dest / f"{ev.id}.annotation.json")
    ann = next((c for c in candidates if c.is_file()), None)
    if ann is not None:
        try:
            data = json.loads(_read_text(ann))
            out.status = PASSED if data.get("passed") else FAILED
            out.score = data.get("score") if isinstance(data.get("score"), (int, float)) else None
            out.detail = str(data.get("detail", "ingested human annotation"))
        except json.JSONDecodeError:
            out.status = ERROR
            out.detail = f"human annotation file is not JSON: {ann}"
    else:
        out.detail = "awaiting human annotation (no annotation file found)"
    rec = {"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
           "status": out.status, "score": out.score, "detail": out.detail,
           "created_by": "EvaluationRunner"}
    records_path = dest / f"{ev.id}.jsonl"
    _write_jsonl(records_path, [rec])
    out.records_path = str(records_path)
    return out


# --- llm_judge: real LLM-based judging --------------------------------------
# Reuses the stdlib `llm.chat` client (no new dependency). Config mirrors grader.py:
# AHL_JUDGE_BASE_URL / AHL_JUDGE_MODEL / AHL_JUDGE_API_KEY. Honesty contract:
#   - no AHL_JUDGE_API_KEY        -> PENDING (offline; never a fabricated verdict)
#   - request fails/times out/5xx -> ERROR  (surfaced, not silently pending)
#   - unparseable model reply     -> ERROR  (keeps a raw_response preview)

def _judge_config() -> tuple[str, str, str]:
    return (os.environ.get("AHL_JUDGE_BASE_URL", ""),
            os.environ.get("AHL_JUDGE_MODEL", ""),
            os.environ.get("AHL_JUDGE_API_KEY", ""))


def _build_judge_prompt(rubric_text: str, case_input: str, agent_output: str,
                        evidence_summary: str) -> str:
    """Judge prompt over the v1 evidence model (rubric + one case's input/output)."""
    rub = (rubric_text or "").strip() or "(no rubric file — judge general answer quality)"
    return (
        "You are a strict evaluator. Judge the agent's OUTPUT for the given CASE "
        "against the RUBRIC. Be conservative: only 'pass' when the output clearly "
        "satisfies the rubric.\n\n"
        f"[RUBRIC]\n{rub}\n\n"
        f"[CASE INPUT]\n{case_input}\n\n"
        f"[AGENT OUTPUT]\n{agent_output}\n\n"
        f"[EVIDENCE SUMMARY]\n{evidence_summary}\n\n"
        "Reply with ONLY one JSON object and nothing else:\n"
        '{"verdict": "pass" | "fail", "score": <integer 0-100>, "reason": "<one sentence>"}'
    )


def _parse_judge_verdict(text: str) -> tuple[str, float | None, str]:
    """Extract (verdict, score, reason) from a judge reply. Raises ValueError if the
    reply has no usable JSON object or no valid verdict."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("judge reply contains no JSON object")
    data = json.loads(text[start:end + 1])
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in ("pass", "fail"):
        raise ValueError(f"verdict must be 'pass' or 'fail', got {verdict!r}")
    raw_score = data.get("score")
    score = max(0.0, min(100.0, float(raw_score))) if isinstance(raw_score, (int, float)) else None
    return verdict, score, str(data.get("reason", "")).strip()


def _run_llm_judge(ev: EvaluatorSpec, track_id: str, exp_dir: Path, eval_root: Path,
                   scores_dir: Path, *, traces: dict[str, list[dict]],
                   cases: list[dict]) -> EvaluatorOutcome:
    """Judge each (harness, case) output with a real LLM, per the rubric.

    Offline (no AHL_JUDGE_API_KEY) -> a single PENDING record (the historical, honest
    behavior). Configured -> one record per judged case: verdict pass/fail -> status,
    score -> score, reason -> detail; a failed request or unparseable reply -> ERROR.
    """
    dest = scores_dir / track_id
    dest.mkdir(parents=True, exist_ok=True)
    records_path = dest / f"{ev.id}.jsonl"

    rubric_text = ""
    if ev.rubric:
        rp = eval_root / ev.rubric
        if rp.is_file():
            rubric_text = _read_text(rp)

    base, model, key = _judge_config()
    if not key:
        # offline -> pending; never fabricate a verdict
        detail = ("llm_judge: AHL_JUDGE_API_KEY not set — offline, pending "
                  "(set AHL_JUDGE_BASE_URL / AHL_JUDGE_MODEL / AHL_JUDGE_API_KEY to judge)")
        rec = {"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": PENDING, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}
        _write_jsonl(records_path, [rec])
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, PENDING,
                                detail=detail, records_path=str(records_path))

    case_by_id = {c.get("id"): c for c in cases if isinstance(c, dict)}
    # one judged unit per (harness, case) — every trace record that has a response
    units = [r for recs in traces.values() for r in recs
             if isinstance(r, dict) and r.get("response") is not None]

    records: list[dict] = []
    statuses: list[str] = []
    for r in units:
        cid, hid = r.get("case_id"), r.get("harness_id")
        case_input = r.get("input") or str(case_by_id.get(cid, {}).get("input", ""))
        agent_output = str(r.get("response") or "")
        evidence_summary = f"case_id={cid}, harness_id={hid}, ok={r.get('ok')}"
        rec: dict = {"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
                     "case_id": cid, "harness_id": hid, "created_by": "EvaluationRunner"}
        try:
            raw = llm.chat(base, model, key,
                           _build_judge_prompt(rubric_text, case_input, agent_output,
                                               evidence_summary))
        except Exception as e:  # noqa: BLE001 — request failed/timeout/5xx after retries
            rec.update({"status": ERROR, "score": None,
                        "detail": f"llm_judge request failed: {e}"})
            records.append(rec); statuses.append(ERROR); continue
        try:
            verdict, score, reason = _parse_judge_verdict(raw)
        except (ValueError, json.JSONDecodeError) as e:
            rec.update({"status": ERROR, "score": None,
                        "detail": f"llm_judge: unparseable reply ({e})",
                        "raw_response": raw[:500]})
            records.append(rec); statuses.append(ERROR); continue
        status = PASSED if verdict == "pass" else FAILED
        rec.update({"status": status, "score": score, "detail": reason})
        records.append(rec); statuses.append(status)

    _write_jsonl(records_path, records)
    return EvaluatorOutcome(track_id, ev.id or "?", ev.method, _aggregate(statuses),
                            detail=f"llm_judge judged {len(records)} case(s)",
                            records_path=str(records_path))


def run_evaluation(exp_dir: Path, spec: ExperimentSpec, *,
                   evidence_dir: Path | None = None) -> EvaluationResult:
    """Evaluate Auto Run evidence: run each track's evaluators, aggregate, reflect
    the objective's primary track. No tracks → nothing to do (empty result).
    evidence_dir overrides the store (default exp_dir/evidence) for the Auto
    Optimize loop's per-iteration evidence."""
    exp_dir = Path(exp_dir).resolve()
    result = EvaluationResult()
    if not spec.tracks:
        return result

    evidence_dir = Path(evidence_dir).resolve() if evidence_dir else exp_dir / "evidence"
    scores_dir = evidence_dir / "scores"
    tracks_dir = scores_dir / "tracks"
    eval_root = (exp_dir / spec.evaluation_root) if spec.evaluation_root else exp_dir
    by_id: dict[str, EvaluatorSpec] = {ev.id: ev for ev in spec.evaluators if ev.id}

    traces = _load_traces(evidence_dir)
    try:
        cases = (load_cases(exp_dir / spec.cases_root, spec.cases_files)
                 if spec.cases_root and spec.cases_files else [])
    except ExperimentSpecError:
        cases = []

    for tr in spec.tracks:
        tid = tr.id or "track"
        outcomes: list[EvaluatorOutcome] = []
        for ev_id in tr.evaluators:
            ev = by_id.get(ev_id)
            if ev is None:
                outcomes.append(EvaluatorOutcome(tid, ev_id, None, ERROR,
                                                 detail=f"track references unknown evaluator {ev_id!r}"))
                continue
            context = {"experiment_id": spec.id, "track_id": tid, "evaluator_id": ev_id,
                       "method": ev.method, "evidence_dir": str(evidence_dir),
                       "traces": traces, "cases": cases}
            if ev.method == "benchmark":
                outcomes.append(_run_benchmark(ev, tid, exp_dir, eval_root, context, scores_dir))
            elif ev.method == "human_annotation":
                outcomes.append(_run_human(ev, tid, exp_dir, eval_root, scores_dir))
            elif ev.method == "llm_judge":
                outcomes.append(_run_llm_judge(ev, tid, exp_dir, eval_root, scores_dir,
                                               traces=traces, cases=cases))
            else:
                outcomes.append(EvaluatorOutcome(tid, ev_id, ev.method, ERROR,
                                                 detail=f"unknown evaluator method {ev.method!r}"))
        status = _aggregate([o.status for o in outcomes])
        agg = {"track_id": tid, "question": tr.question, "status": status,
               "evaluators": [{"evaluator_id": o.evaluator_id, "method": o.method,
                               "status": o.status, "score": o.score, "detail": o.detail}
                              for o in outcomes],
               "created_by": "EvaluationRunner"}
        tracks_dir.mkdir(parents=True, exist_ok=True)
        agg_path = tracks_dir / f"{tid}.json"
        agg_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
        result.tracks.append(TrackOutcome(tid, tr.question, status, outcomes, str(agg_path)))

    result.ran = bool(result.tracks)
    if spec.objective and spec.objective.primary_track:
        result.objective_track = spec.objective.primary_track
        match = next((t for t in result.tracks if t.track_id == result.objective_track), None)
        result.objective_status = match.status if match else None
    return result
