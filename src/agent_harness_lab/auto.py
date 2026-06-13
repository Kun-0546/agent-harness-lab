"""Auto Mode — execute cases against Agent Runtimes via connectors, collect evidence.

`hlab run` with `run.mode: auto` calls `run_auto()`. The AutoRunner dispatches each
case (single_turn `cases.jsonl`) to each agent runtime through its connector and the
EvidenceCollector writes evidence:

    evidence/traces/<runtime>.jsonl   one record per case
    evidence/raw/<runtime>/<case>.{out,err}
    evidence/artifacts/<runtime>/<case>/   matches of artifacts.collect[].glob
    evidence/issues.jsonl              connector_failure / case_failure /
                                       missing_artifact / empty_output

v1 connectors:
  - local_cli — reuses agentconn's stdin_json IPC session ({"input":...} -> {"response":...})
  - script    — runs a per-case command (with {case_file} / {output_dir} substitution)

Multi-turn (v1.1): when the experiment declares a multi-turn simulator
(role_play / scripted / script), local_cli cases run a turn loop over a FRESH
session per case (execution-model.md §14) — turn 0 sends the case input, then
simulator(transcript) produces each next user turn until None or max_turns.
The script simulator spawns one subprocess per turn (stdin {"transcript":[...]}
-> stdout {"next": str|null}, §14.8). Single-turn dispatch, trace records, and
evidence layout are byte-for-byte unchanged (pinned by regression tests).

Evaluation and report generation are later phases (EvaluationRunner / ReportBuilder
are NOT run here). Auto + manual/remote_devbox/api/bridge is rejected by `hlab review`
before we get here; if one slips through it is recorded as a connector_failure.
"""
from __future__ import annotations

import glob as _glob
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_harness_lab import user_sim
from agent_harness_lab.agentconn import _POSIX, _pgid_of, _SandboxCliSession
from agent_harness_lab.experiment_spec import (
    MULTI_TURN_SIMULATOR_TYPES,
    ExperimentSpec,
    ExperimentSpecError,
    load_agent_runtime_spec,
    load_cases,
)
from agent_harness_lab.materialize_v1 import (
    MaterializeResult,
    build_and_write_snapshot,
    materialize_runtime,
    robust_rmtree,
)

_EVIDENCE_SUBDIRS = ("traces", "raw", "artifacts", "snapshots", "scores", "inspections")

try:
    _DEFAULT_CONNECTOR_TIMEOUT = float(os.environ.get("AHL_CONNECTOR_TIMEOUT", "60"))
except ValueError:
    _DEFAULT_CONNECTOR_TIMEOUT = 60.0


def _coerce_timeout(value: Any) -> float:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return _DEFAULT_CONNECTOR_TIMEOUT


@dataclass
class AutoRunResult:
    runtimes: int = 0
    cases: int = 0
    dispatched: int = 0
    traces_written: int = 0
    evidence_dir: Path | None = None
    issues: list[dict] = field(default_factory=list)

    def issue_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.issues:
            out[i["type"]] = out.get(i["type"], 0) + 1
        return out


class EvidenceCollector:
    """Writes evidence/* + issues.jsonl for an Auto Mode run.

    Per-trial append semantics (PR5 5a): a re-run appends to the same trace
    JSONL files under a new trial number instead of truncating. Trial 0 records
    carry no `trial` field (byte-identical to pre-PR5 single-trial runs). Trial
    >= 1 records carry `trial: N`. Raw outputs use trial-numbered subdirs for
    trial >= 1, keeping trial-0 paths unchanged.

    Layout:
      evidence/traces/<runtime>.jsonl       all trials — no `trial` field on trial-0
                                            records; `trial: N` on trial N >= 1
      evidence/raw/<runtime>/<case>.out     trial-0 raw (unchanged path)
      evidence/raw/trials/<N>/<rt>/<case>   trial N >= 1 raw outputs

    `--fresh` (`fresh=True` constructor arg) is the only sanctioned destruction:
    it wipes evidence/ and starts a clean trial-0 run.
    """

    def __init__(self, evidence_dir: Path, *, trial: int = 0):
        self.dir = evidence_dir
        self.trial = trial
        for sub in _EVIDENCE_SUBDIRS:
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        self.issues: list[dict] = []
        self._seq = 0
        self._trace_started: set[str] = set()  # used only to detect first write per runtime

    def trace(self, runtime_id: str, record: dict) -> None:
        p = self.dir / "traces" / f"{runtime_id}.jsonl"
        # PR5 5a: always append; trial field written only when >= 1 (byte-identity contract)
        if self.trial >= 1:
            record = dict(record)
            record["trial"] = self.trial
        self._trace_started.add(runtime_id)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def raw(self, runtime_id: str, case_id: str, stdout: str, stderr: str) -> Path:
        # trial-0: keep unchanged path (byte-identity); trial >= 1: use trial subdir
        if self.trial == 0:
            d = self.dir / "raw" / runtime_id
        else:
            d = self.dir / "raw" / "trials" / str(self.trial) / runtime_id
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{case_id}.out").write_text(stdout or "", encoding="utf-8")
        (d / f"{case_id}.err").write_text(stderr or "", encoding="utf-8")
        return d

    def issue(self, type_: str, message: str, *, runtime_id: str | None = None,
              case_id: str | None = None, harness_id: str | None = None,
              evidence_ref: str | None = None, severity: str = "error") -> None:
        self._seq += 1
        rec: dict = {
            "id": f"issue-{self._seq:03d}", "type": type_, "severity": severity,
            "message": message, "runtime_id": runtime_id, "case_id": case_id,
            "harness_id": harness_id, "evidence_ref": evidence_ref,
            "created_by": "AutoRunner",
        }
        # defect 3a: issue records gain optional `trial` field (>= 1 only, same convention)
        if self.trial >= 1:
            rec["trial"] = self.trial
        self.issues.append(rec)

    def collect_artifacts(self, working_dir: Path, rules: list[dict], runtime_id: str,
                          case_id: str, harness_id: str | None,
                          baseline: dict[str, tuple] | None = None) -> int:
        """Copy artifacts.collect[] glob matches THIS case produced under
        evidence/artifacts/<rt>/<case>/. `baseline` is a pre-case snapshot
        {path: (mtime, size)}; only files new or changed since then count, so a
        prior case's stale output in the shared working_dir cannot be re-collected
        or mask a required artifact. A required rule with no NEW match becomes a
        missing_artifact issue. Returns count."""
        baseline = baseline or {}
        dest = self.dir / "artifacts" / runtime_id / case_id
        collected = 0
        for rule in rules or []:
            if not isinstance(rule, dict):
                continue
            pattern, aid = rule.get("glob"), rule.get("id")
            required = bool(rule.get("required"))
            matches: list[Path] = []
            if isinstance(pattern, str) and pattern:
                for hit in _glob.glob(str(working_dir / pattern), recursive=True):
                    hp = Path(hit)
                    if not hp.is_file():
                        continue
                    try:
                        st = hp.stat()
                    except OSError:
                        continue
                    if baseline.get(str(hp)) == (st.st_mtime, st.st_size):
                        continue  # unchanged since before this case → not produced by it
                    matches.append(hp)
            for m in matches:
                try:
                    rel = m.relative_to(working_dir)
                except ValueError:
                    rel = Path(m.name)
                tgt = dest / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(m, tgt)
                collected += 1
            if required and not matches:
                self.issue("missing_artifact",
                           f"required artifact '{aid}' (glob {pattern!r}) produced no files",
                           runtime_id=runtime_id, case_id=case_id, harness_id=harness_id,
                           evidence_ref=f"evidence/artifacts/{runtime_id}/{case_id}/")
        return collected

    def flush_issues(self) -> None:
        """Persist issues from this run to evidence/issues.jsonl.

        Defect 3b: per-trial append semantics — prior-trial issues from earlier
        calls are preserved (evidence immutability). Each run_auto call appends
        its own issues to the file rather than truncating it. Issue records for
        trial >= 1 carry a `trial` field (stamped in .issue()); trial-0 records
        carry no `trial` field (byte-identity contract mirrors traces).

        Inspector's run_inspection re-reads the full file and deduplicates, so
        accumulation across trial boundaries is handled at the inspection layer.
        Across separate invocations (historical runs) this accumulates correctly
        because each new trial appends; --fresh is the only sanctioned wipe.
        """
        issues_path = self.dir / "issues.jsonl"
        if not self.issues:
            return
        with issues_path.open("a", encoding="utf-8") as f:
            for rec in self.issues:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _snapshot(working_dir: Path) -> dict[str, tuple]:
    """{path: (mtime, size)} of every file under working_dir, for per-case artifact
    isolation (so a prior case's leftover output is not re-collected as this case's)."""
    snap: dict[str, tuple] = {}
    if working_dir.is_dir():
        for p in working_dir.rglob("*"):
            if p.is_file():
                try:
                    st = p.stat()
                    snap[str(p)] = (st.st_mtime, st.st_size)
                except OSError:
                    pass
    return snap


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _sweep_group(proc: "subprocess.Popen", pgid: int | None) -> None:
    """Kill any surviving member of the script child's process group and reap.

    The script connector runs `sh -c <cmd>` (or cmd.exe) in its OWN session
    (start_new_session on POSIX). A worker the script backgrounds becomes a group
    member that can outlive the direct child — the "normal completion path that
    still leaves a child" case. We sweep the whole group on BOTH the normal-exit
    and timeout paths so nothing lingers:
      - POSIX: killpg(pgid). If the group is already empty/gone we get ESRCH,
        which is harmless. (pgid == the child's pid; the microsecond pid-reuse
        window after wait() reaped the leader is acceptable for a single-machine
        eval harness.)
      - Windows: taskkill /F /T reaps the tree by pid.
    Idempotent and never raises.
    """
    try:
        # killpg the WHOLE group unconditionally — even after the direct child has
        # exited, a worker it backgrounded can still be alive in the group, and that
        # is exactly what this sweep must reap. (Do NOT guard on proc.poll(): the
        # leader is often already gone here by design.)
        if _POSIX and pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:  # noqa: BLE001 — group gone / not permitted
                pass
        elif not _POSIX:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=False)
            except Exception:  # noqa: BLE001
                pass
    finally:
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


def _case_id(case: dict, idx: int) -> str:
    cid = case.get("id") if isinstance(case, dict) else None
    return str(cid) if isinstance(cid, str) and cid.strip() else f"case-{idx + 1:03d}"


def _connector_fields(rt) -> tuple[str | None, str, Any]:
    """(command, working_dir_rel, timeout_raw) from a runtime spec (nested or flat)."""
    conn = rt.raw.get("connector") if isinstance(rt.raw, dict) else None
    conn = conn if isinstance(conn, dict) else {}
    command = conn.get("command") or (rt.raw.get("command") if isinstance(rt.raw, dict) else None)
    wd = conn.get("working_dir") or (rt.raw.get("working_dir") if isinstance(rt.raw, dict) else None) or "."
    timeout = conn.get("timeout") if conn.get("timeout") is not None else (
        rt.raw.get("timeout") if isinstance(rt.raw, dict) else None)
    return command, wd, timeout


def _local_cli_case(ev: EvidenceCollector, rt_ref, sess, case, idx: int,
                    working_dir: Path, rules, result: AutoRunResult) -> bool:
    """Run ONE case through an already-open session and write its evidence.

    Returns True if the connector is still alive (the caller may send the next case
    through it), False if it died on this case. Shared by the isolated path (one
    session for all cases) and the reset path (a fresh session per case)."""
    cid = _case_id(case, idx)
    result.dispatched += 1
    baseline = _snapshot(working_dir)  # per-case artifact isolation
    try:
        resp = sess.send(str(case.get("input", "")))
    except Exception as e:  # noqa: BLE001 — turn timeout / process died
        stderr_tail = "".join(getattr(sess, "_stderr_tail", []))
        ev.raw(rt_ref.id, cid, "", stderr_tail)  # keep stderr even on failure
        ev.issue("connector_failure", f"runtime {rt_ref.id} case {cid}: {e}",
                 runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
        ev.trace(rt_ref.id, {"case_id": cid, "runtime_id": rt_ref.id,
                             "harness_id": rt_ref.harness, "ok": False, "error": str(e)})
        result.traces_written += 1
        return False
    stderr_tail = "".join(getattr(sess, "_stderr_tail", []))
    ev.raw(rt_ref.id, cid, resp, stderr_tail)
    ok = bool(resp and resp.strip())
    ev.trace(rt_ref.id, {"case_id": cid, "runtime_id": rt_ref.id,
                         "harness_id": rt_ref.harness, "input": case.get("input"),
                         "response": resp, "ok": ok})
    result.traces_written += 1
    if not ok:
        ev.issue("empty_output", f"runtime {rt_ref.id} case {cid}: empty agent response",
                 runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
    ev.collect_artifacts(working_dir, rules, rt_ref.id, cid, rt_ref.harness, baseline)
    return True


# --- multi-turn execution (v1.1, execution-model.md §14) -----------------------

@dataclass
class _SimPlan:
    """How this run drives the user side of multi-turn cases.

    `label` is what trace records carry as `simulator` ("role_play"|"scripted"|
    "script"); `forced` marks an AHL_SIM_STUB=1 redirect onto the scripted path.
    `factory` builds a per-case simulator function (case_id -> fn(transcript) ->
    next|None). A non-empty `error` means the simulator cannot run (e.g.
    role_play without AHL_SIM_* keys): dispatch is skipped with a
    simulator_unconfigured issue — never a fabricated follow-up.
    A non-empty `warning` is recorded as a warn-severity issue but the run
    continues (e.g. corrupt playbook fell back to built-in default)."""

    label: str
    max_turns: int
    factory: Callable[[str], Callable[[list], "str | None"]] | None = None
    forced: bool = False
    error: str = ""
    warning: str = ""


def _plan_simulator(spec: ExperimentSpec, exp_dir: Path) -> _SimPlan | None:
    """None for the single_turn path (frozen); a _SimPlan for multi-turn types.

    AHL_SIM_STUB=1 forces the scripted playbook path (the experiment's playbook
    when it has one, else the built-in default) for key-free CI/smoke runs —
    it redirects every multi-turn type, including `script`."""
    sim = spec.simulator
    if sim is None or sim.type not in MULTI_TURN_SIMULATOR_TYPES:
        return None
    raw = sim.raw if isinstance(sim.raw, dict) else {}
    mt = raw.get("max_turns")
    max_turns = mt if isinstance(mt, int) else user_sim.DEFAULT_MAX_TURNS
    forced = os.environ.get("AHL_SIM_STUB", "") == "1"

    if forced or sim.type == "scripted":
        pb_rel = raw.get("playbook")
        playbook = None
        fallback_warning = ""
        if isinstance(pb_rel, str) and pb_rel.strip():
            try:
                playbook = user_sim.load_playbook(exp_dir / pb_rel)
            except user_sim.SimulatorError as e:
                if not forced:  # a real scripted run must not silently swap its mock
                    return _SimPlan("scripted", max_turns, error=str(e))
                # forced (AHL_SIM_STUB=1): keep the run alive but warn — the user's
                # playbook was unusable so we fell back to the built-in default.
                fallback_warning = (
                    f"playbook_invalid_fallback: AHL_SIM_STUB=1 forced run — "
                    f"playbook '{pb_rel}' could not be loaded ({e}); "
                    f"fell back to built-in default playbook"
                )
        elif sim.type == "scripted" and not forced:
            return _SimPlan("scripted", max_turns,
                            error="simulator type=scripted has no usable `playbook:`")
        if playbook is None:
            playbook = user_sim.default_playbook()  # forced smoke fallback
        return _SimPlan("scripted", max_turns, forced=forced,
                        factory=lambda cid: user_sim.make_scripted_simulator(
                            playbook.sequence_for(cid)),
                        warning=fallback_warning)

    if sim.type == "role_play":
        if not user_sim.sim_configured():
            return _SimPlan("role_play", max_turns, error=(
                "simulator type=role_play needs AHL_SIM_BASE_URL / AHL_SIM_MODEL / "
                "AHL_SIM_API_KEY (or AHL_SIM_STUB=1 to force the scripted playbook "
                "path); no follow-up is ever fabricated"))
        pol = raw.get("policy")
        actor = raw.get("actor") or ""
        try:
            card = user_sim.parse_policy_card(exp_dir / str(pol), actor=str(actor))
        except (OSError, UnicodeError) as e:
            return _SimPlan("role_play", max_turns,
                            error=f"cannot read simulator policy {pol!r}: {e}")
        fn = user_sim.make_role_play_simulator(card)
        return _SimPlan("role_play", max_turns, factory=lambda cid: fn)

    if sim.type == "script":
        scr = raw.get("script")
        if not isinstance(scr, str) or not scr.strip():
            return _SimPlan("script", max_turns,
                            error="simulator type=script has no usable `script:`")
        script_path = exp_dir / scr
        if not script_path.is_file():
            return _SimPlan("script", max_turns, error=(
                f"simulator `script` '{scr}' does not exist relative to the "
                f"experiment dir"))
        fn = _make_script_simulator(script_path, exp_dir)
        return _SimPlan("script", max_turns, factory=lambda cid: fn)

    return None


def _make_script_simulator(script_path: Path, exp_dir: Path,
                           timeout: float | None = None) -> Callable[[list], "str | None"]:
    """Build the script-type simulator: one subprocess per turn (protocol A,
    execution-model.md §14.8).

    The script runs with the same Python interpreter as benchmark evaluator
    scripts (cwd = the experiment dir); stdin receives {"transcript": [...]}
    and stdout must print {"next": str|null} — null ends the case. All three
    streams are FILES, the runner waits on the direct child with a timeout
    (AHL_SIM_TIMEOUT, read at build time like role_play's), and the whole
    process group is swept afterwards — the script connector's anti-hang
    hardening, so a misbehaving simulator can neither hang the run nor orphan
    a child. PYTHONIOENCODING=utf-8 keeps the JSON protocol encoding-safe on
    Windows (locale-encoded stdio would corrupt non-ASCII turns). Any failure
    (timeout / non-zero exit / non-JSON stdout / a bad `next`) raises into the
    partial-transcript contract (§14.4) — a follow-up is never fabricated."""
    script_path = Path(script_path)
    if timeout is None:
        timeout = user_sim._sim_timeout()
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    def _sim(transcript: list) -> "str | None":
        with tempfile.TemporaryDirectory(prefix="hlab-sim-",
                                         ignore_cleanup_errors=True) as td:
            tdir = Path(td)
            in_path = tdir / "stdin.json"
            so_path, se_path = tdir / "stdout.txt", tdir / "stderr.txt"
            in_path.write_text(json.dumps({"transcript": transcript}, ensure_ascii=False),
                               encoding="utf-8")
            timed_out = False
            with open(in_path, "r", encoding="utf-8") as fi, \
                    open(so_path, "w", encoding="utf-8") as fo, \
                    open(se_path, "w", encoding="utf-8") as fe:
                proc = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    shell=False, cwd=str(exp_dir), env=env,
                    stdin=fi, stdout=fo, stderr=fe,
                    text=True, encoding="utf-8", close_fds=True,
                    start_new_session=_POSIX,
                )
                pgid = _pgid_of(proc)
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
            _sweep_group(proc, pgid)  # reap the direct child + any backgrounded worker
            stdout, stderr = _read_text(so_path), _read_text(se_path)
        if timed_out:
            raise RuntimeError(
                f"script simulator timed out after {timeout:g}s ({script_path.name})")
        if proc.returncode != 0:
            raise RuntimeError(
                f"script simulator exited {proc.returncode}: {stderr.strip()[:200]}")
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"script simulator stdout is not JSON: {stdout.strip()[:200]}") from None
        if not isinstance(data, dict) or "next" not in data:
            raise RuntimeError(
                'script simulator stdout must be {"next": str|null}; got '
                f"{stdout.strip()[:200]}")
        nxt = data["next"]
        if nxt is not None and not isinstance(nxt, str):
            raise RuntimeError(
                f'script simulator `next` must be a string or null, '
                f"got {type(nxt).__name__}")
        return nxt

    return _sim


def _run_case_turns(sess, opening: str, simulator_fn, max_turns: int,
                    transcript: list | None = None) -> list:
    """Run ONE multi-turn case over an already-open session; returns the transcript.

    Turn-loop contract (execution-model.md §14.3):
      turn 0 = case input; simulator consulted only when another turn may follow.
    The simulator is NOT called after the final allowed turn (turn count ==
    max(1, max_turns) cap) — that call would be wasted and can fail on an
    otherwise complete case. The loop ends without consulting the simulator when
    either None is returned (user done) or the cap is reached.

    Unlike Stack A run_agent_session the dispatch layer owns session close
    (not this loop). Pass `transcript` in to keep turns already collected when
    a turn raises mid-case (v1.1 partial-transcript contract, §14.4)."""
    if transcript is None:
        transcript = []
    user_turn: str | None = opening
    cap = max(1, max_turns)
    for i in range(cap):
        agent_resp = sess.send(user_turn)
        transcript.append({"turn": i, "user": user_turn, "agent": agent_resp})
        if i + 1 >= cap:
            break
        user_turn = simulator_fn(transcript)
        if user_turn is None:
            break
    return transcript


def _multiturn_case(ev: EvidenceCollector, rt_ref, sess, case, idx: int,
                    working_dir: Path, rules, result: AutoRunResult,
                    plan: _SimPlan) -> None:
    """Run ONE multi-turn case and write its evidence.

    The trace record keeps every single-turn key with remapped semantics
    (input=opening, response=final agent reply, ok=no turn error and a non-empty
    final reply) and adds turns / transcript / simulator (+forced). A mid-case
    exception keeps the partial transcript plus an `error` field (§14.4); raw
    output concatenates the turns collected so far."""
    cid = _case_id(case, idx)
    result.dispatched += 1
    baseline = _snapshot(working_dir)  # per-case artifact isolation
    transcript: list = []
    error = ""
    try:
        sim_fn = plan.factory(cid)
        _run_case_turns(sess, str(case.get("input", "")), sim_fn, plan.max_turns,
                        transcript)
    except Exception as e:  # noqa: BLE001 — turn timeout / process died / simulator failed
        error = str(e)
    stderr_tail = "".join(getattr(sess, "_stderr_tail", []))
    ev.raw(rt_ref.id, cid, "\n".join(t.get("agent", "") for t in transcript), stderr_tail)
    last = transcript[-1].get("agent", "") if transcript else ""
    ok = (not error) and bool(last and last.strip())
    record: dict[str, Any] = {
        "case_id": cid, "runtime_id": rt_ref.id, "harness_id": rt_ref.harness,
        "input": case.get("input"), "response": last, "ok": ok,
        "turns": len(transcript), "transcript": transcript, "simulator": plan.label,
    }
    if plan.forced:
        record["forced"] = True
    if error:
        record["error"] = error
        ev.issue("connector_failure", f"runtime {rt_ref.id} case {cid}: {error}",
                 runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
    ev.trace(rt_ref.id, record)
    result.traces_written += 1
    if not error and not ok:
        ev.issue("empty_output", f"runtime {rt_ref.id} case {cid}: empty agent response",
                 runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
    ev.collect_artifacts(working_dir, rules, rt_ref.id, cid, rt_ref.harness, baseline)


def _dispatch_local_cli(ev: EvidenceCollector, rt_ref, command, working_dir: Path,
                        timeout: float, rules, cases, result: AutoRunResult,
                        *, state_policy: str | None = None,
                        sim_plan: _SimPlan | None = None,
                        env_overlay: dict | None = None) -> None:
    if not command or not isinstance(command, str):
        ev.issue("connector_failure", f"runtime {rt_ref.id}: local_cli has no `command`",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
    if not working_dir.is_dir():
        ev.issue("connector_failure",
                 f"runtime {rt_ref.id}: working_dir '{working_dir}' does not exist",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
    # PR6: merge patch env_overlay on top of inherited env for this runtime only
    _env: dict | None = None
    if env_overlay:
        _env = dict(os.environ)
        _env.update(env_overlay)

    if sim_plan is not None:
        # multi-turn (v1.1): a FRESH session per case — the reset code path. A
        # multi-turn case needs the agent process to keep THIS case's context
        # across turns, so under multi-turn the isolation unit of `isolated` is
        # the case, not the send (execution-model.md §14.2). A per-case failure
        # is isolated; later cases still get a clean session.
        for idx, case in enumerate(cases):
            try:
                sess = _SandboxCliSession(command, cwd=working_dir, timeout=timeout,
                                          env_override=_env)
            except Exception as e:  # noqa: BLE001
                cid = _case_id(case, idx)
                result.dispatched += 1
                ev.issue("connector_failure",
                         f"runtime {rt_ref.id} case {cid}: cannot start connector: {e}",
                         runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
                continue
            try:
                _multiturn_case(ev, rt_ref, sess, case, idx, working_dir, rules,
                                result, sim_plan)
            finally:
                sess.close()  # the dispatch layer owns the session lifecycle
        return

    if state_policy == "reset":
        # reset (StatePolicy): reuse the runtime spec but restart a FRESH process
        # before each case, so no in-process state carries across cases. Each case is
        # independent, so a per-case start/turn failure is isolated — later cases still
        # get a clean session (unlike the isolated path, which stops on a dead session).
        for idx, case in enumerate(cases):
            try:
                sess = _SandboxCliSession(command, cwd=working_dir, timeout=timeout,
                                          env_override=_env)
            except Exception as e:  # noqa: BLE001
                cid = _case_id(case, idx)
                result.dispatched += 1
                ev.issue("connector_failure",
                         f"runtime {rt_ref.id} case {cid}: cannot start connector: {e}",
                         runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
                continue
            try:
                _local_cli_case(ev, rt_ref, sess, case, idx, working_dir, rules, result)
            finally:
                sess.close()
        return

    # isolated (default): one persistent session for all cases. local_cli agents are
    # request/response (stateless per send), so reusing the process keeps each case
    # independent; a dead connector stops this runtime (the session cannot recover).
    try:
        sess = _SandboxCliSession(command, cwd=working_dir, timeout=timeout,
                                  env_override=_env)
    except Exception as e:  # noqa: BLE001
        ev.issue("connector_failure", f"runtime {rt_ref.id}: cannot start connector: {e}",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
    try:
        for idx, case in enumerate(cases):
            if not _local_cli_case(ev, rt_ref, sess, case, idx, working_dir, rules, result):
                break  # connector is dead → stop this runtime
    finally:
        sess.close()


def _dispatch_script(ev: EvidenceCollector, rt_ref, command, working_dir: Path,
                     timeout: float, rules, cases, result: AutoRunResult,
                     *, state_policy: str | None = None,
                     env_overlay: dict | None = None) -> None:
    if not command or not isinstance(command, str):
        ev.issue("connector_failure", f"runtime {rt_ref.id}: script connector has no `command`",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
    if not working_dir.is_dir():
        ev.issue("connector_failure",
                 f"runtime {rt_ref.id}: working_dir '{working_dir}' does not exist",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
    # PR6: merge patch env_overlay on top of inherited env for this runtime only
    _script_env: dict | None = None
    if env_overlay:
        _script_env = dict(os.environ)
        _script_env.update(env_overlay)
    # The script connector spawns a fresh process per case, so each case starts from
    # the runtime's on-disk state with no carried in-process state — isolated and reset
    # are both inherently satisfied here. state_policy is accepted for a uniform
    # dispatch signature; cumulative/snapshot_branch are not executed in Auto v1.
    for idx, case in enumerate(cases):
        cid = _case_id(case, idx)
        result.dispatched += 1
        out_dir = ev.dir / "raw" / rt_ref.id / cid
        out_dir.mkdir(parents=True, exist_ok=True)
        case_file = out_dir / "case.json"
        case_file.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        baseline = _snapshot(working_dir)  # per-case artifact isolation
        cmd = command.replace("{case_file}", f'"{case_file}"').replace(
            "{output_dir}", f'"{out_dir}"')
        # Redirect the child's stdout/stderr to FILES, not pipes, and wait on the
        # DIRECT child with proc.wait(timeout). Completion is then the child's own
        # exit — it never depends on pipe-EOF, so a worker the script backgrounds
        # (or any unrelated process that inherited a fd) can no longer hold a pipe
        # open and park communicate() forever (the canonical Linux hang). There is
        # also no pipe buffer to fill. We sweep the whole process group afterward
        # (normal exit AND timeout) so no grandchild lingers.
        so_path, se_path = out_dir / "stdout.txt", out_dir / "stderr.txt"
        timed_out = False
        with open(so_path, "w", encoding="utf-8") as fo, \
                open(se_path, "w", encoding="utf-8") as fe:
            proc = subprocess.Popen(
                cmd, shell=True, cwd=str(working_dir),
                stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                text=True, encoding="utf-8", close_fds=True, start_new_session=_POSIX,
                env=_script_env,
            )
            pgid = _pgid_of(proc)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        _sweep_group(proc, pgid)  # reap the direct child + any backgrounded worker
        stdout, stderr = _read_text(so_path), _read_text(se_path)
        ev.raw(rt_ref.id, cid, stdout, stderr)
        if timed_out:
            ev.issue("connector_failure",
                     f"runtime {rt_ref.id} case {cid}: script timed out after {timeout:g}s",
                     runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
            ev.trace(rt_ref.id, {"case_id": cid, "runtime_id": rt_ref.id,
                                 "harness_id": rt_ref.harness, "ok": False, "error": "timeout"})
            result.traces_written += 1
            continue
        rc = proc.returncode
        ok = rc == 0
        ev.trace(rt_ref.id, {"case_id": cid, "runtime_id": rt_ref.id,
                             "harness_id": rt_ref.harness, "input": case.get("input"),
                             "exit_code": rc, "ok": ok})
        result.traces_written += 1
        if not ok:
            ev.issue("case_failure", f"runtime {rt_ref.id} case {cid}: script exited {rc}",
                     runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
        elif not (stdout or "").strip():
            ev.issue("empty_output", f"runtime {rt_ref.id} case {cid}: script produced no stdout",
                     runtime_id=rt_ref.id, case_id=cid, harness_id=rt_ref.harness)
        ev.collect_artifacts(working_dir, rules, rt_ref.id, cid, rt_ref.harness, baseline)


def _next_trial(evidence_dir: Path) -> int:
    """Determine the next trial number for an append run.

    Scans existing trace JSONL files for the highest `trial` value seen, then
    returns that + 1. A fresh evidence dir (no trace files) returns 0."""
    traces_dir = evidence_dir / "traces"
    if not traces_dir.is_dir():
        return 0
    max_trial = -1
    for p in traces_dir.glob("*.jsonl"):
        try:
            for ln in p.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                t = rec.get("trial")
                if t is None:
                    t = 0
                if isinstance(t, int) and t > max_trial:
                    max_trial = t
        except OSError:
            continue
    return max_trial + 1


# _restore_or_materialize was removed (defect 2: cross-invocation sandbox reuse
# served stale trees and silently dropped patch env / mislabelled sandbox_type).
# Sandbox is now rebuilt at the START of every run_auto invocation; within-
# invocation trials still share the one materialized tree (the loop is inside
# run_auto). Documented in execution-model.md §15.1.


def run_auto(exp_dir: Path, spec: ExperimentSpec, *,
             evidence_dir: Path | None = None,
             working_dir_override: Path | None = None,
             trial: int | None = None,
             fresh: bool = False) -> AutoRunResult:
    """Execute run.mode=auto: dispatch cases to each runtime, collect evidence.

    evidence_dir overrides where evidence is written (default exp_dir/evidence) —
    the Auto Optimize loop points each iteration at its own evidence dir.
    working_dir_override forces every runtime's working_dir (the loop points it at
    the candidate harness dir so the candidate is what actually runs).

    trial: explicit trial number override (used by multi-trial loop in cmd_run).
    fresh: wipe evidence/ before running — the ONLY sanctioned destruction; starts
           a clean trial-0 run regardless of prior runs.

    PR5 5a: without --fresh, a re-run appends as a new trial (old evidence is
    immutable). With --fresh, evidence/ is wiped and trial resets to 0."""
    import shutil as _shutil
    # absolute so paths passed to a script connector (which runs with cwd=working_dir)
    # resolve correctly, and so artifact globs are unambiguous.
    exp_dir = Path(exp_dir).resolve()
    ev_dir = Path(evidence_dir).resolve() if evidence_dir else exp_dir / "evidence"
    wd_override = Path(working_dir_override).resolve() if working_dir_override else None

    # --fresh wipes evidence/ and sandbox/ (the only sanctioned destruction) and
    # starts a clean trial-0 run.  Order: sandbox first so that if sandbox wipe
    # fails (e.g. a read-only git clone on Windows), evidence is left intact and
    # we abort cleanly (fail-closed: nothing destroyed on a known-undeletable tree).
    # robust_rmtree uses onerror=_chmod_retry to handle read-only .git/objects on
    # Windows (defect 1).
    if fresh:
        _sandbox_dir = exp_dir / "sandbox"
        if _sandbox_dir.exists():
            try:
                robust_rmtree(_sandbox_dir)
            except OSError as _e:
                sys.stderr.write(
                    f"HLAB_RUNTIME_FAILURE: --fresh: cannot remove sandbox/ "
                    f"({_e}); aborting to preserve evidence integrity\n"
                )
                sys.exit(1)
        if ev_dir.exists():
            robust_rmtree(ev_dir)

    # determine the trial number for this run
    if trial is not None:
        _trial = trial
    else:
        _trial = _next_trial(ev_dir)

    result = AutoRunResult(evidence_dir=ev_dir)
    ev = EvidenceCollector(ev_dir, trial=_trial)

    try:
        cases = (load_cases(exp_dir / spec.cases_root, spec.cases_files)
                 if spec.cases_root and spec.cases_files else [])
    except ExperimentSpecError as e:
        ev.issue("case_failure", f"cannot load cases: {e}")
        cases = []
    result.cases = len(cases)

    sim_plan = _plan_simulator(spec, exp_dir)
    if sim_plan is not None and sim_plan.warning:
        ev.issue("playbook_invalid_fallback", sim_plan.warning, severity="warn")

    # --- PR6: pre-run materialize (once per run_auto invocation, per runtime) ---
    # Defect 2: sandbox is rebuilt FRESH at the start of EVERY run_auto call so that
    # source edits always take effect on re-run (no cross-invocation stale-tree reuse).
    # Within one invocation the materialized tree is shared by all trial iterations.
    # Documented limitation: an agent that mutates its sandbox affects later trials of
    # the same invocation — expected behavior, noted in execution-model.md §15.1.
    #
    # Materialize failures (missing source, clone failure, fingerprint mismatch) are
    # recorded as connector_failure issues (HLAB_RUNTIME_FAILURE / exit 3 contract).
    # Defect 3: a failed materialize marks the runtime as skip-for-dispatch; the
    # dispatch loop below checks _materialized_failed before dispatching.
    # Runtimes without source: are untouched — zero behavior change for them.
    _materialized: dict[str, MaterializeResult] = {}   # rt_id -> MaterializeResult
    _materialized_failed: set[str] = set()             # rt_ids that failed materialize
    for rt_ref in spec.agent_runtimes:
        if not isinstance(rt_ref.spec, str) or not rt_ref.id:
            continue
        spec_path = exp_dir / rt_ref.spec
        if not spec_path.is_file():
            continue
        try:
            rt = load_agent_runtime_spec(spec_path)
        except ExperimentSpecError:
            continue
        if rt.source is None:
            continue
        # Defect 2: always wipe and rebuild the sandbox (rebuild-per-invocation contract).
        sandbox_dir = exp_dir / "sandbox" / rt_ref.id
        robust_rmtree(sandbox_dir)
        try:
            mat_result = materialize_runtime(rt_ref.id, rt.source, exp_dir, ev_dir)
        except (RuntimeError, FileNotFoundError, OSError) as exc:
            msg = str(exc)
            sys.stderr.write(f"HLAB_RUNTIME_FAILURE: materialize failed for "
                             f"runtime {rt_ref.id}: {msg}\n")
            ev.issue("connector_failure",
                     f"runtime {rt_ref.id}: materialize failed: {msg}",
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness)
            _materialized_failed.add(rt_ref.id)  # defect 3: mark for dispatch skip
            continue
        try:
            build_and_write_snapshot(
                rt_ref.id, exp_dir, ev_dir, mat_result,
                run_id=spec.id or exp_dir.name)
        except OSError as exc:
            sys.stderr.write(f"HLAB_RUNTIME_FAILURE: cannot write snapshot for "
                             f"runtime {rt_ref.id}: {exc}\n")
            ev.issue("connector_failure",
                     f"runtime {rt_ref.id}: snapshot write failed: {exc}",
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness)
            _materialized_failed.add(rt_ref.id)  # defect 3: mark for dispatch skip
            continue
        _materialized[rt_ref.id] = mat_result

    for rt_ref in spec.agent_runtimes:
        result.runtimes += 1
        # Defect 3: skip dispatch entirely for runtimes whose materialize failed.
        # The connector_failure issue and exit 3 contract already convey the failure;
        # running in an un-materialized working_dir would produce misleading traces.
        if rt_ref.id in _materialized_failed:
            continue
        if sim_plan is not None and sim_plan.error:
            # no-key / unusable simulator: record and skip dispatch for this
            # runtime — never a fabricated follow-up (execution-model.md §14.5).
            ev.issue("simulator_unconfigured", sim_plan.error,
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness)
            continue
        spec_path = exp_dir / rt_ref.spec if isinstance(rt_ref.spec, str) else None
        if spec_path is None or not spec_path.is_file():
            ev.issue("connector_failure", f"runtime {rt_ref.id}: spec file missing",
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness)
            continue
        try:
            rt = load_agent_runtime_spec(spec_path)
        except ExperimentSpecError as e:
            ev.issue("connector_failure", f"runtime {rt_ref.id}: bad spec: {e}",
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness)
            continue
        command, wd_rel, timeout_raw = _connector_fields(rt)
        # PR6: if materialize succeeded, redirect working_dir to the sandbox.
        # Defect 9 (BELT): working_dir_override (Auto Optimize candidate dir) takes
        # precedence over materialize when both somehow coexist — the optimize loop
        # must run the candidate, not the pristine sandbox.  A warn-level issue is
        # recorded to document the override.
        mat_result = _materialized.get(rt_ref.id)
        if wd_override is not None and mat_result is not None:
            ev.issue("optimize_source_conflict",
                     f"runtime {rt_ref.id}: working_dir_override and materialize both "
                     f"present; using working_dir_override (optimize candidate wins); "
                     f"this combination is unsupported — see optimize_source_unsupported",
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness,
                     severity="warn")
            working_dir = wd_override
        elif mat_result is not None:
            working_dir = mat_result.sandbox_dir
        elif wd_override is not None:
            working_dir = wd_override
        else:
            working_dir = exp_dir / wd_rel
        timeout = _coerce_timeout(timeout_raw)
        # PR6: merge patch env_overlay on top of subprocess env for this runtime only
        _env_overlay = mat_result.env_overlay if mat_result is not None else {}
        if rt.connector_type == "local_cli":
            _dispatch_local_cli(ev, rt_ref, command, working_dir, timeout, rt.artifacts, cases, result,
                                state_policy=spec.state_policy, sim_plan=sim_plan,
                                env_overlay=_env_overlay)
        elif rt.connector_type == "script":
            if sim_plan is not None:
                # the script connector is one fresh process per case with no turn
                # IPC — it cannot keep a conversation. Honest failure, not a
                # silent single-turn downgrade.
                ev.issue("connector_failure",
                         f"runtime {rt_ref.id}: the script connector cannot drive a "
                         f"multi-turn simulator ({sim_plan.label}) in v1.1; use a "
                         f"local_cli connector",
                         runtime_id=rt_ref.id, harness_id=rt_ref.harness)
                continue
            _dispatch_script(ev, rt_ref, command, working_dir, timeout, rt.artifacts, cases, result,
                             state_policy=spec.state_policy, env_overlay=_env_overlay)
        else:
            ev.issue("connector_failure",
                     f"runtime {rt_ref.id}: connector {rt.connector_type!r} is not executable in "
                     f"Auto v1 (use local_cli or script)",
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness)

    ev.flush_issues()
    result.issues = ev.issues
    return result
