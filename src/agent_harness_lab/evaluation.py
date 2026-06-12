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
  - human_annotation — NO interactive UI. If an annotation file exists, ingest it
                     (`passed` must be a bool; missing or non-bool → `error`);
                     else write a `pending` record (never blocks).
  - llm_judge      — pending without AHL_JUDGE_API_KEY (it never invents a verdict);
                     with AHL_JUDGE_* set it judges each (harness, case) via llm.chat,
                     recording a request failure or unparseable reply as `error`.
                     A multi-turn trace record (v1.1, carries `transcript`) is judged
                     over the WHOLE conversation ([CONVERSATION], expanded turn by
                     turn); single-turn records keep the original prompt byte-for-byte.

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

from agent_harness_lab import llm, user_sim
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

# llm_judge per-request timeout (seconds); default mirrors llm.chat's own 180s.
try:
    _JUDGE_TIMEOUT = float(os.environ.get("AHL_JUDGE_TIMEOUT", "180"))
except ValueError:
    _JUDGE_TIMEOUT = 180.0


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


def _load_traces(evidence_dir: Path,
                 trial: int | None = None) -> dict[str, list[dict]]:
    """Load trace records from evidence/traces/*.jsonl.

    PR5 5a trial read scope: by default (`trial=None`) returns only records from
    the LATEST trial across ALL trace files (the global maximum `trial` value, where
    absent means trial 0). This prevents mixing trials when multiple runtimes' files
    end at different trial heights. Pass `trial=N` to read a specific historical
    trial. This keeps single-trial experiments (trial field absent) behaving
    identically to pre-PR5 — the only records in those files have no `trial` key,
    so they are all at trial 0 and are always returned.

    Fix (defect 4): global latest-trial selection across ALL files first, then
    filter each file to that trial — prevents cross-file trial mixing.
    Fix (defect 8): non-dict lines and string trial values are skipped defensively.
    """
    traces: dict[str, list[dict]] = {}
    tdir = evidence_dir / "traces"
    if not tdir.is_dir():
        return traces

    # collect all records per file first
    raw_per_file: dict[str, list[dict]] = {}
    for p in sorted(tdir.glob("*.jsonl")):
        recs: list[dict] = []
        for ln in _read_text(p).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                continue
            # defect 8: skip non-dict lines silently
            if not isinstance(obj, dict):
                continue
            recs.append(obj)
        raw_per_file[p.stem] = recs

    if trial is None:
        # defect 4: compute global latest trial across ALL files first
        global_max = -1
        for recs in raw_per_file.values():
            for r in recs:
                t = r.get("trial")
                # defect 8: coerce/ignore non-int trial values
                if t is None:
                    t = 0
                elif not isinstance(t, int):
                    try:
                        t = int(t)
                    except (TypeError, ValueError):
                        t = 0
                if t > global_max:
                    global_max = t
        target_trial = max(global_max, 0)
        for stem, recs in raw_per_file.items():
            traces[stem] = [r for r in recs if _trial_of(r) == target_trial]
    else:
        for stem, recs in raw_per_file.items():
            traces[stem] = [r for r in recs if _trial_of(r) == trial]
    return traces


def _trial_of(r: dict) -> int:
    """Return the effective trial number of a trace record (absent field = 0)."""
    t = r.get("trial")
    if t is None:
        return 0
    if isinstance(t, int):
        return t
    try:
        return int(t)
    except (TypeError, ValueError):
        return 0


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Overwrite the file with exactly `records` (trial-scoped callers handle merge)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _write_jsonl_trial_scoped(path: Path, new_records: list[dict],
                               trial: int | None) -> None:
    """Write score records with trial-scoped merge semantics (defect 1d).

    Reads existing records from `path`, drops only those belonging to `trial`
    (so other trials' records are preserved), then appends `new_records`.
    When `trial` is None (single-run / latest default, trial-0 semantics) this
    behaves like a plain overwrite of the whole file — trial-0 records carry no
    `trial` field so there is no prior-trial data to preserve for them (a
    single-trial workflow never gains a trial field).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if trial is None or trial == 0:
        # Simple overwrite: no prior-trial records to preserve for trial 0
        # (trial-0 records have no `trial` field — byte-identity contract).
        # Re-running eval with trial=None replaces all records as before.
        with path.open("w", encoding="utf-8") as f:
            for rec in new_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return
    # trial >= 1: read existing, drop only records of this trial, re-append
    existing: list[dict] = []
    if path.is_file():
        for ln in _read_text(path).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                existing.append(obj)
    kept = [r for r in existing if (r.get("trial") or 0) != trial]
    with path.open("w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for rec in new_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _stamp_trial(rec: dict, trial: int | None) -> dict:
    """Add the `trial` field to a score record iff trial >= 1 (defect 1a contract)."""
    if trial is not None and trial >= 1:
        rec = dict(rec)
        rec["trial"] = trial
    return rec


def _run_benchmark(ev: EvaluatorSpec, track_id: str, exp_dir: Path,
                   eval_root: Path, context: dict, scores_dir: Path,
                   trial: int | None = None) -> EvaluatorOutcome:
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
                records.append(_stamp_trial(rec, trial))
    elif isinstance(parsed, dict) and "passed" in parsed:
        out.status = PASSED if parsed.get("passed") else FAILED
        out.score = parsed.get("score") if isinstance(parsed.get("score"), (int, float)) else None
        out.detail = str(parsed.get("detail", ""))
        records.append(_stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
                        "status": out.status, "score": out.score, "detail": out.detail,
                        "created_by": "EvaluationRunner"}, trial))
    else:
        out.detail = "benchmark JSON must contain `passed` or `records`"
        return out

    records_path = dest / f"{ev.id}.jsonl"
    _write_jsonl_trial_scoped(records_path, records, trial)
    out.records_path = str(records_path)
    return out


def _run_human(ev: EvaluatorSpec, track_id: str, exp_dir: Path,
               eval_root: Path, scores_dir: Path,
               trial: int | None = None) -> EvaluatorOutcome:
    """Ingest a human annotation file if present; else write a pending record.

    Defect 6 (annotation trial binding): annotation files are NOT trial-scoped in
    v1.1 — the human annotates whatever trial they reviewed. When adopting an
    annotation into a specific trial, the score record carries the trial it was
    adopted INTO (per the >= 1 convention). Operators who run `eval --trial N`
    with a stale annotation are annotating about a different trial; this is
    documented behaviour (v1.2 territory to enforce per-trial annotation files).
    """
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
    adopted_into = f" (adopted into trial {trial})" if (trial is not None and trial >= 1) else ""
    if ann is not None:
        try:
            data = json.loads(_read_text(ann))
        except json.JSONDecodeError:
            out.status = ERROR
            out.detail = f"human annotation file is not JSON: {ann}"
        else:
            passed = data.get("passed") if isinstance(data, dict) else None
            if isinstance(passed, bool):
                out.status = PASSED if passed else FAILED
                out.score = data.get("score") if isinstance(data.get("score"), (int, float)) else None
                out.detail = str(data.get("detail", "ingested human annotation")) + adopted_into
            else:
                # honesty contract (same as llm_judge): a score alone is not a
                # verdict — surface ERROR, never a silent FAILED.
                out.status = ERROR
                out.detail = (f'annotation missing boolean "passed": {ann} '
                              '(expected JSON {"passed": bool, "score"?: number, '
                              '"detail"?: string})')
    else:
        out.detail = "awaiting human annotation (no annotation file found)"
    rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
           "status": out.status, "score": out.score, "detail": out.detail,
           "created_by": "EvaluationRunner"}, trial)
    records_path = dest / f"{ev.id}.jsonl"
    _write_jsonl_trial_scoped(records_path, [rec], trial)
    out.records_path = str(records_path)
    return out


# --- llm_judge: real LLM-based judging --------------------------------------
# Reuses the stdlib `llm.chat` client (no new dependency). Config mirrors grader.py:
# AHL_JUDGE_BASE_URL / AHL_JUDGE_MODEL / AHL_JUDGE_API_KEY; AHL_JUDGE_TIMEOUT
# (seconds, default 180) bounds each judge request. Honesty contract:
#   - no AHL_JUDGE_API_KEY        -> PENDING (offline; never a fabricated verdict)
#   - request fails/times out/5xx -> ERROR  (surfaced, not silently pending)
#   - unparseable model reply     -> ERROR  (keeps a raw_response preview)
#   - traces but 0 judgeable units-> ERROR  (no `response` field to judge; the
#                                    script connector records none in v1)

def _judge_config() -> tuple[str, str, str]:
    return (os.environ.get("AHL_JUDGE_BASE_URL", ""),
            os.environ.get("AHL_JUDGE_MODEL", ""),
            os.environ.get("AHL_JUDGE_API_KEY", ""))


def _build_judge_prompt(rubric_text: str, case_input: str, agent_output: str,
                        evidence_summary: str, transcript: list | None = None) -> str:
    """Judge prompt over the v1 evidence model (rubric + one case's evidence).

    Without a transcript the single-turn prompt is byte-for-byte the frozen v1
    shape (pinned by a golden test). A multi-turn record (v1.1) replaces the
    [CASE INPUT]/[AGENT OUTPUT] pair with [CONVERSATION], expanded turn by turn
    — the judging unit becomes the WHOLE conversation, not one reply (schema
    §14 "Multi-turn judging"). Scoring math is unchanged either way."""
    rub = (rubric_text or "").strip() or "(no rubric file — judge general answer quality)"
    if transcript:
        return (
            "You are a strict evaluator. Judge the agent's replies in the "
            "CONVERSATION against the RUBRIC. Judge the conversation as a whole "
            "— every agent turn counts, not just the first. Be conservative: "
            "only 'pass' when the agent's side clearly satisfies the rubric.\n\n"
            f"[RUBRIC]\n{rub}\n\n"
            f"[CONVERSATION]\n{user_sim.transcript_text(transcript)}\n\n"
            f"[EVIDENCE SUMMARY]\n{evidence_summary}\n\n"
            "Reply with ONLY one JSON object and nothing else:\n"
            '{"verdict": "pass" | "fail", "score": <integer 0-100>, "reason": "<one sentence>"}'
        )
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
    import math
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("judge reply contains no JSON object")
    data = json.loads(text[start:end + 1])
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in ("pass", "fail"):
        raise ValueError(f"verdict must be 'pass' or 'fail', got {verdict!r}")
    raw_score = data.get("score")
    score: float | None = None
    if isinstance(raw_score, (int, float)):
        v = float(raw_score)
        if not math.isfinite(v):
            raise ValueError(f"judge score is not finite: {raw_score!r}")
        score = max(0.0, min(100.0, v))
    return verdict, score, str(data.get("reason", "")).strip()


def _run_llm_judge(ev: EvaluatorSpec, track_id: str, exp_dir: Path, eval_root: Path,
                   scores_dir: Path, *, traces: dict[str, list[dict]],
                   cases: list[dict], trial: int | None = None) -> EvaluatorOutcome:
    """Judge each (harness, case) output with a real LLM, per the rubric.

    Offline (no AHL_JUDGE_API_KEY) -> a single PENDING record (the historical, honest
    behavior). Configured -> one record per judged case: verdict pass/fail -> status,
    score -> score, reason -> detail; a failed request or unparseable reply -> ERROR.

    Defect 5: ok:false records are excluded from judging (same as single-turn
    exclusion) — the partial transcript stays in evidence but is not scored as
    if the case completed successfully.
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
        rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": PENDING, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}, trial)
        _write_jsonl_trial_scoped(records_path, [rec], trial)
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, PENDING,
                                detail=detail, records_path=str(records_path))

    case_by_id = {c.get("id"): c for c in cases if isinstance(c, dict)}
    # defect 5: exclude ok:false records from judging (errored cases are evidence;
    # they are not scored as if complete — same parity as single-turn exclusion).
    # one judged unit per (harness, case) — every trace record that has a response
    # AND ok:true (or ok absent, for backwards compatibility with old traces).
    all_with_response = [r for recs in traces.values() for r in recs
                         if isinstance(r, dict) and r.get("response") is not None]
    units = [r for r in all_with_response if r.get("ok") is not False]
    if not units and any(traces.values()):
        # honesty contract: trace records exist but none carries a `response`
        # (the script connector's v1 trace records input/exit_code/ok only) —
        # a configured judge must surface that, not stay silently pending forever.
        detail = ("llm_judge: trace records exist but none carries a `response` "
                  "field — 0 judgeable units (the script connector does not record "
                  "a response in v1)")
        rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": ERROR, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}, trial)
        _write_jsonl_trial_scoped(records_path, [rec], trial)
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, ERROR,
                                detail=detail, records_path=str(records_path))

    records: list[dict] = []
    statuses: list[str] = []
    for r in units:
        cid, hid = r.get("case_id"), r.get("harness_id")
        case_input = r.get("input") or str(case_by_id.get(cid, {}).get("input", ""))
        agent_output = str(r.get("response") or "")
        # multi-turn record (v1.1): judge the whole conversation, not one reply
        _tr = r.get("transcript")
        transcript = _tr if isinstance(_tr, list) and _tr else None
        evidence_summary = f"case_id={cid}, harness_id={hid}, ok={r.get('ok')}"
        rec: dict = {"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
                     "case_id": cid, "harness_id": hid, "created_by": "EvaluationRunner"}
        try:
            raw = llm.chat(base, model, key,
                           _build_judge_prompt(rubric_text, case_input, agent_output,
                                               evidence_summary, transcript=transcript),
                           timeout=_JUDGE_TIMEOUT)
        except Exception as e:  # noqa: BLE001 — request failed/timeout/5xx after retries
            rec.update({"status": ERROR, "score": None,
                        "detail": f"llm_judge request failed: {e}"})
            records.append(_stamp_trial(rec, trial)); statuses.append(ERROR); continue
        try:
            verdict, score, reason = _parse_judge_verdict(raw)
        except (ValueError, json.JSONDecodeError) as e:
            rec.update({"status": ERROR, "score": None,
                        "detail": f"llm_judge: unparseable reply ({e})",
                        "raw_response": raw[:500]})
            records.append(_stamp_trial(rec, trial)); statuses.append(ERROR); continue
        status = PASSED if verdict == "pass" else FAILED
        rec.update({"status": status, "score": score, "detail": reason})
        records.append(_stamp_trial(rec, trial)); statuses.append(status)

    _write_jsonl_trial_scoped(records_path, records, trial)
    return EvaluatorOutcome(track_id, ev.id or "?", ev.method, _aggregate(statuses),
                            detail=f"llm_judge judged {len(records)} case(s)",
                            records_path=str(records_path))


# --- llm_rubric: dimension-weighted LLM scoring --------------------------------
# Ports grader.py's capability into the v1 evaluation stack.
#
# Rubric file format (evaluation/rubrics/<name>.md):
#   A GFM table with pipe-separated columns: Dimension | Weight | Description
#   The header row must use these exact column names (case-insensitive).
#   Example:
#     | Dimension   | Weight | Description                           |
#     |-------------|--------|---------------------------------------|
#     | accuracy    | 0.5    | Is the answer factually correct?      |
#     | conciseness | 0.3    | Is the answer concise and on-point?   |
#     | helpfulness | 0.2    | Does the answer help the user?        |
#
#   - Weights are floats; if they do not sum to 1.0 they are normalised.
#   - Missing or empty table -> review-stage ERROR (rubric_invalid /
#     rubric_missing_dimensions). The review validator left-shifts this catch
#     (experiment_spec.py) so a malformed rubric is caught before any run.
#
# Honesty contract (same as llm_judge):
#   - no AHL_JUDGE_API_KEY            -> PENDING (never fabricate a verdict)
#   - request fails / unparseable     -> ERROR + detail (never silent)
# The scores record's pre-reserved `dimensions` field carries per-dimension
# detail; the standard `score` field carries the weighted total (0–100 scale
# matching llm_judge) so existing aggregation/compare/report work unchanged.

def _parse_weight_cell(cell: str) -> float:
    """Parse a weight cell that may be a plain float or a percent string.

    Accepts:
      "0.5"   → 0.5
      "50%"   → 0.5  (Stack A users write percent-style weights)
      "50.0%" → 0.5
    Returns a float. Raises ValueError if the cell cannot be parsed.
    """
    cell = cell.strip()
    if cell.endswith("%"):
        return float(cell[:-1]) / 100.0
    return float(cell)


def _parse_rubric_table(text: str) -> list[dict]:
    """Parse a GFM dimensions+weights table from a rubric markdown file.

    Returns a list of dicts: [{"name": str, "weight": float, "description": str}, ...]
    Returns an empty list when no valid table is found (caller treats this as
    rubric_invalid). Weights are NOT normalised here — normalisation happens at
    scoring time so review can still flag un-normalised tables in the WARN path.

    Percent-style weights ("50%") are parsed as 0.50 (Stack A users write percents).
    """
    import re
    dimensions: list[dict] = []
    lines = text.splitlines()
    # Find a table header row containing Dimension and Weight columns.
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if not cells:
            continue
        lower = [c.lower() for c in cells]
        if "dimension" not in lower or "weight" not in lower:
            continue
        # found header row; index the column positions
        dim_col = lower.index("dimension")
        weight_col = lower.index("weight")
        desc_col = lower.index("description") if "description" in lower else None
        # skip separator row (e.g. |---|---|---|)
        j = i + 1
        if j < len(lines) and re.match(r"^\s*\|[\s\-\|:]+\|\s*$", lines[j]):
            j += 1
        # parse data rows
        while j < len(lines):
            row = lines[j]
            j += 1
            if "|" not in row:
                break
            parts = [c.strip() for c in row.split("|")]
            # strip empty head/tail from split on leading/trailing |
            if parts and parts[0] == "":
                parts = parts[1:]
            if parts and parts[-1] == "":
                parts = parts[:-1]
            if len(parts) <= max(dim_col, weight_col):
                continue
            name = parts[dim_col].strip()
            if not name:
                continue
            try:
                weight = _parse_weight_cell(parts[weight_col])
            except (ValueError, IndexError):
                continue
            desc = parts[desc_col].strip() if desc_col is not None and desc_col < len(parts) else ""
            dimensions.append({"name": name, "weight": weight, "description": desc})
        break  # process only the first matching table
    return dimensions


def _build_rubric_prompt(dimensions: list[dict], case_input: str, agent_output: str,
                         evidence_summary: str, transcript: list | None = None) -> str:
    """Build the llm_rubric scoring prompt.

    Follows grader.py:60-70's multi-turn judging style: presents the whole
    conversation when a transcript is available, or input/response for single-turn.
    Asks the LLM to score each dimension on a 0-100 scale and return JSON.
    """
    dim_lines = "\n".join(
        f"- {d['name']} (weight {d['weight']}): {d['description']}" for d in dimensions
    )
    names = ", ".join(d["name"] for d in dimensions)
    example = "{" + ", ".join(f'"{d["name"]}": <0-100>' for d in dimensions) + "}"
    if transcript:
        conversation_block = (
            f"[CONVERSATION]\n{user_sim.transcript_text(transcript)}"
        )
    else:
        conversation_block = (
            f"[CASE INPUT]\n{case_input}\n\n"
            f"[AGENT OUTPUT]\n{agent_output}"
        )
    return (
        "You are a strict evaluator. Score the agent's replies against each "
        "rubric dimension below. Judge the WHOLE conversation (every agent turn "
        "counts, not just the first). Be conservative: only give high scores when "
        "the agent clearly satisfies the dimension.\n\n"
        f"[RUBRIC DIMENSIONS]\n{dim_lines}\n\n"
        f"{conversation_block}\n\n"
        f"[EVIDENCE SUMMARY]\n{evidence_summary}\n\n"
        f"Reply with ONLY one JSON object mapping each dimension name to an integer "
        f"score 0-100. Output NOTHING else.\n"
        f"Format: {example}"
    )


def _parse_rubric_verdict(text: str, dimension_names: list[str]) -> dict[str, float]:
    """Extract per-dimension scores from an llm_rubric reply.

    Raises ValueError if no JSON object found, verdict missing dimensions, a
    score is not numeric, or a score is NaN/Infinity (mirrors _parse_judge_verdict).
    NaN must never serialize into scores JSONL.
    """
    import math
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("llm_rubric reply contains no JSON object")
    data = json.loads(text[start:end + 1])
    out: dict[str, float] = {}
    for name in dimension_names:
        if name not in data:
            raise ValueError(f"llm_rubric: reply missing dimension {name!r}")
        raw = data[name]
        try:
            v = float(raw)
        except (TypeError, ValueError) as e:
            raise ValueError(f"llm_rubric: score for {name!r} is not numeric: {raw!r}") from e
        if not math.isfinite(v):
            raise ValueError(f"llm_rubric: score for {name!r} is not finite: {raw!r}")
        out[name] = max(0.0, min(100.0, v))
    return out


def _run_llm_rubric(ev: EvaluatorSpec, track_id: str, exp_dir: Path, eval_root: Path,
                    scores_dir: Path, *, traces: dict[str, list[dict]],
                    cases: list[dict], trial: int | None = None) -> EvaluatorOutcome:
    """Score each (harness, case) with an LLM across rubric dimensions, weighted.

    Offline (no AHL_JUDGE_API_KEY) -> a single PENDING record (same honesty
    contract as llm_judge). Configured -> one record per case: per-dimension
    scores stored in the `dimensions` field; weighted total in `score`.
    Parse or request failures -> ERROR record (never silent).

    Defect 5: ok:false records excluded from scoring (same parity as llm_judge).
    """
    dest = scores_dir / track_id
    dest.mkdir(parents=True, exist_ok=True)
    records_path = dest / f"{ev.id}.jsonl"

    # load and parse the rubric file
    rubric_text = ""
    dimensions: list[dict] = []
    if ev.rubric:
        rp = eval_root / ev.rubric
        if rp.is_file():
            rubric_text = _read_text(rp)
            dimensions = _parse_rubric_table(rubric_text)

    if not dimensions:
        detail = (f"llm_rubric: rubric file has no parseable dimensions table "
                  f"(rubric: {ev.rubric!r}); cannot score")
        rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": ERROR, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}, trial)
        _write_jsonl_trial_scoped(records_path, [rec], trial)
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, ERROR,
                                detail=detail, records_path=str(records_path))

    # Validate and normalise weights.
    raw_weights = {d["name"]: d["weight"] for d in dimensions}
    neg = [k for k, v in raw_weights.items() if v < 0]
    if neg:
        detail = (f"llm_rubric: rubric has negative weight(s) for dimension(s) "
                  f"{neg}; rubric is invalid (rubric_invalid)")
        rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": ERROR, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}, trial)
        _write_jsonl_trial_scoped(records_path, [rec], trial)
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, ERROR,
                                detail=detail, records_path=str(records_path))
    total_w = sum(raw_weights.values())
    if total_w <= 0:
        detail = (f"llm_rubric: rubric weight sum is zero or negative "
                  f"(total={total_w}); rubric is invalid (rubric_invalid)")
        rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": ERROR, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}, trial)
        _write_jsonl_trial_scoped(records_path, [rec], trial)
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, ERROR,
                                detail=detail, records_path=str(records_path))
    weights = {k: v / total_w for k, v in raw_weights.items()}

    base, model, key = _judge_config()
    if not key:
        detail = ("llm_rubric: AHL_JUDGE_API_KEY not set — offline, pending "
                  "(set AHL_JUDGE_BASE_URL / AHL_JUDGE_MODEL / AHL_JUDGE_API_KEY to score)")
        rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": PENDING, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}, trial)
        _write_jsonl_trial_scoped(records_path, [rec], trial)
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, PENDING,
                                detail=detail, records_path=str(records_path))

    case_by_id = {c.get("id"): c for c in cases if isinstance(c, dict)}
    # defect 5: exclude ok:false records (errored cases not scored as complete)
    all_with_response = [r for recs in traces.values() for r in recs
                         if isinstance(r, dict) and r.get("response") is not None]
    units = [r for r in all_with_response if r.get("ok") is not False]
    if not units and any(traces.values()):
        detail = ("llm_rubric: trace records exist but none carries a `response` "
                  "field — 0 scoreable units")
        rec = _stamp_trial({"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
               "status": ERROR, "score": None, "detail": detail,
               "rubric": ev.rubric, "created_by": "EvaluationRunner"}, trial)
        _write_jsonl_trial_scoped(records_path, [rec], trial)
        return EvaluatorOutcome(track_id, ev.id or "?", ev.method, ERROR,
                                detail=detail, records_path=str(records_path))

    dim_names = [d["name"] for d in dimensions]
    records: list[dict] = []
    statuses: list[str] = []
    for r in units:
        cid, hid = r.get("case_id"), r.get("harness_id")
        case_input = r.get("input") or str(case_by_id.get(cid, {}).get("input", ""))
        agent_output = str(r.get("response") or "")
        _tr = r.get("transcript")
        transcript = _tr if isinstance(_tr, list) and _tr else None
        evidence_summary = f"case_id={cid}, harness_id={hid}, ok={r.get('ok')}"
        rec: dict = {"track_id": track_id, "evaluator_id": ev.id, "method": ev.method,
                     "case_id": cid, "harness_id": hid, "rubric": ev.rubric,
                     "created_by": "EvaluationRunner"}
        try:
            raw = llm.chat(base, model, key,
                           _build_rubric_prompt(dimensions, case_input, agent_output,
                                                evidence_summary, transcript=transcript),
                           timeout=_JUDGE_TIMEOUT)
        except Exception as e:  # noqa: BLE001
            rec.update({"status": ERROR, "score": None,
                        "detail": f"llm_rubric request failed: {e}"})
            records.append(_stamp_trial(rec, trial)); statuses.append(ERROR); continue
        try:
            dim_scores = _parse_rubric_verdict(raw, dim_names)
        except (ValueError, json.JSONDecodeError) as e:
            rec.update({"status": ERROR, "score": None,
                        "detail": f"llm_rubric: unparseable reply ({e})",
                        "raw_response": raw[:500]})
            records.append(_stamp_trial(rec, trial)); statuses.append(ERROR); continue
        # weighted total on 0-100 scale (same range as llm_judge score)
        weighted_total = round(sum(dim_scores.get(n, 0.0) * weights.get(n, 0.0)
                                   for n in dim_names), 2)
        rec.update({
            "status": PASSED,  # llm_rubric produces a score, not a pass/fail verdict
            "score": weighted_total,
            "detail": f"llm_rubric scored {len(dim_names)} dimension(s); weighted total {weighted_total}",
            "dimensions": {n: dim_scores[n] for n in dim_names},
        })
        records.append(_stamp_trial(rec, trial)); statuses.append(PASSED)

    _write_jsonl_trial_scoped(records_path, records, trial)
    return EvaluatorOutcome(track_id, ev.id or "?", ev.method, _aggregate(statuses),
                            score=(sum(r.get("score") or 0.0 for r in records
                                       if isinstance(r.get("score"), (int, float))) / len(records)
                                   if records and any(isinstance(r.get("score"), (int, float))
                                                      for r in records) else None),
                            detail=f"llm_rubric scored {len(records)} case(s)",
                            records_path=str(records_path))


class MissingEvidenceError(Exception):
    """Raised by run_evaluation when a requested trial has no trace records.

    Defect 2: eval --trial N for a nonexistent trial must exit 1 with
    HLAB_MISSING_EVIDENCE — never silently evaluate over empty evidence.
    """
    def __init__(self, requested_trial: int) -> None:
        self.requested_trial = requested_trial
        super().__init__(
            f"HLAB_MISSING_EVIDENCE: no trace records found for trial {requested_trial} — "
            f"use `hlab run --trials N` to collect evidence for this trial number"
        )


def run_evaluation(exp_dir: Path, spec: ExperimentSpec, *,
                   evidence_dir: Path | None = None,
                   trial: int | None = None) -> EvaluationResult:
    """Evaluate Auto Run evidence: run each track's evaluators, aggregate, reflect
    the objective's primary track. No tracks → nothing to do (empty result).
    evidence_dir overrides the store (default exp_dir/evidence) for the Auto
    Optimize loop's per-iteration evidence.

    trial: read records from a specific trial (PR5 5a); None = latest trial
    (default). `hlab eval --trial N` passes an explicit trial number.

    Raises MissingEvidenceError (defect 2) when `trial` is explicitly given and
    no trace records exist for that trial — nothing is written in that case."""
    exp_dir = Path(exp_dir).resolve()
    result = EvaluationResult()
    if not spec.tracks:
        return result

    evidence_dir = Path(evidence_dir).resolve() if evidence_dir else exp_dir / "evidence"
    scores_dir = evidence_dir / "scores"
    tracks_dir = scores_dir / "tracks"
    eval_root = (exp_dir / spec.evaluation_root) if spec.evaluation_root else exp_dir
    by_id: dict[str, EvaluatorSpec] = {ev.id: ev for ev in spec.evaluators if ev.id}

    traces = _load_traces(evidence_dir, trial=trial)

    # defect 2: if a specific trial was requested and there is no evidence for it,
    # refuse to evaluate over empty evidence — raises; caller writes HLAB_MISSING_EVIDENCE.
    if trial is not None:
        has_any = any(bool(recs) for recs in traces.values())
        if not has_any:
            raise MissingEvidenceError(trial)

    try:
        cases = (load_cases(exp_dir / spec.cases_root, spec.cases_files)
                 if spec.cases_root and spec.cases_files else [])
    except ExperimentSpecError:
        cases = []

    # compute effective_trial for score-record stamping: when trial=None we are
    # evaluating the globally-latest trial; discover that number from the traces
    # so score records get the right trial stamp (>= 1 only).
    if trial is None:
        # infer from traces dict: the trial stamp in any record of this batch
        effective_trial: int | None = None
        for recs in traces.values():
            for r in recs:
                t = r.get("trial")
                if t is not None and isinstance(t, int):
                    effective_trial = t
                    break
            if effective_trial is not None:
                break
        # if effective_trial is None all records are trial-0 (no `trial` field)
        score_trial = effective_trial  # None = trial 0 = no stamp
    else:
        score_trial = trial if trial >= 1 else None

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
                outcomes.append(_run_benchmark(ev, tid, exp_dir, eval_root, context,
                                               scores_dir, trial=score_trial))
            elif ev.method == "human_annotation":
                outcomes.append(_run_human(ev, tid, exp_dir, eval_root, scores_dir,
                                           trial=score_trial))
            elif ev.method == "llm_judge":
                outcomes.append(_run_llm_judge(ev, tid, exp_dir, eval_root, scores_dir,
                                               traces=traces, cases=cases,
                                               trial=score_trial))
            elif ev.method == "llm_rubric":
                outcomes.append(_run_llm_rubric(ev, tid, exp_dir, eval_root, scores_dir,
                                                traces=traces, cases=cases,
                                                trial=score_trial))
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
