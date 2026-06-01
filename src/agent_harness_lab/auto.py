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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_harness_lab.agentconn import _POSIX, _pgid_of, _SandboxCliSession
from agent_harness_lab.experiment_spec import (
    ExperimentSpec,
    ExperimentSpecError,
    load_agent_runtime_spec,
    load_cases,
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
    """Writes evidence/* + issues.jsonl for an Auto Mode run."""

    def __init__(self, evidence_dir: Path):
        self.dir = evidence_dir
        for sub in _EVIDENCE_SUBDIRS:
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        self.issues: list[dict] = []
        self._seq = 0
        self._trace_started: set[str] = set()  # truncate each runtime's trace once per run

    def trace(self, runtime_id: str, record: dict) -> None:
        p = self.dir / "traces" / f"{runtime_id}.jsonl"
        # first write of this run truncates (a re-run overwrites, not appends); then append
        mode = "a" if runtime_id in self._trace_started else "w"
        self._trace_started.add(runtime_id)
        with p.open(mode, encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def raw(self, runtime_id: str, case_id: str, stdout: str, stderr: str) -> Path:
        d = self.dir / "raw" / runtime_id
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{case_id}.out").write_text(stdout or "", encoding="utf-8")
        (d / f"{case_id}.err").write_text(stderr or "", encoding="utf-8")
        return d

    def issue(self, type_: str, message: str, *, runtime_id: str | None = None,
              case_id: str | None = None, harness_id: str | None = None,
              evidence_ref: str | None = None, severity: str = "error") -> None:
        self._seq += 1
        self.issues.append({
            "id": f"issue-{self._seq:03d}", "type": type_, "severity": severity,
            "message": message, "runtime_id": runtime_id, "case_id": case_id,
            "harness_id": harness_id, "evidence_ref": evidence_ref,
            "created_by": "AutoRunner",
        })

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
        with (self.dir / "issues.jsonl").open("w", encoding="utf-8") as f:
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


def _dispatch_local_cli(ev: EvidenceCollector, rt_ref, command, working_dir: Path,
                        timeout: float, rules, cases, result: AutoRunResult,
                        *, state_policy: str | None = None) -> None:
    if not command or not isinstance(command, str):
        ev.issue("connector_failure", f"runtime {rt_ref.id}: local_cli has no `command`",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
    if not working_dir.is_dir():
        ev.issue("connector_failure",
                 f"runtime {rt_ref.id}: working_dir '{working_dir}' does not exist",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return

    if state_policy == "reset":
        # reset (StatePolicy): reuse the runtime spec but restart a FRESH process
        # before each case, so no in-process state carries across cases. Each case is
        # independent, so a per-case start/turn failure is isolated — later cases still
        # get a clean session (unlike the isolated path, which stops on a dead session).
        for idx, case in enumerate(cases):
            try:
                sess = _SandboxCliSession(command, cwd=working_dir, timeout=timeout)
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
        sess = _SandboxCliSession(command, cwd=working_dir, timeout=timeout)
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
                     *, state_policy: str | None = None) -> None:
    if not command or not isinstance(command, str):
        ev.issue("connector_failure", f"runtime {rt_ref.id}: script connector has no `command`",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
    if not working_dir.is_dir():
        ev.issue("connector_failure",
                 f"runtime {rt_ref.id}: working_dir '{working_dir}' does not exist",
                 runtime_id=rt_ref.id, harness_id=rt_ref.harness)
        return
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


def run_auto(exp_dir: Path, spec: ExperimentSpec, *,
             evidence_dir: Path | None = None,
             working_dir_override: Path | None = None) -> AutoRunResult:
    """Execute run.mode=auto: dispatch cases to each runtime, collect evidence.

    evidence_dir overrides where evidence is written (default exp_dir/evidence) —
    the Auto Optimize loop points each iteration at its own evidence dir.
    working_dir_override forces every runtime's working_dir (the loop points it at
    the candidate harness dir so the candidate is what actually runs)."""
    # absolute so paths passed to a script connector (which runs with cwd=working_dir)
    # resolve correctly, and so artifact globs are unambiguous.
    exp_dir = Path(exp_dir).resolve()
    ev_dir = Path(evidence_dir).resolve() if evidence_dir else exp_dir / "evidence"
    wd_override = Path(working_dir_override).resolve() if working_dir_override else None
    result = AutoRunResult(evidence_dir=ev_dir)
    ev = EvidenceCollector(ev_dir)

    try:
        cases = (load_cases(exp_dir / spec.cases_root, spec.cases_files)
                 if spec.cases_root and spec.cases_files else [])
    except ExperimentSpecError as e:
        ev.issue("case_failure", f"cannot load cases: {e}")
        cases = []
    result.cases = len(cases)

    for rt_ref in spec.agent_runtimes:
        result.runtimes += 1
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
        working_dir = wd_override if wd_override is not None else (exp_dir / wd_rel)
        timeout = _coerce_timeout(timeout_raw)
        if rt.connector_type == "local_cli":
            _dispatch_local_cli(ev, rt_ref, command, working_dir, timeout, rt.artifacts, cases, result,
                                state_policy=spec.state_policy)
        elif rt.connector_type == "script":
            _dispatch_script(ev, rt_ref, command, working_dir, timeout, rt.artifacts, cases, result,
                             state_policy=spec.state_policy)
        else:
            ev.issue("connector_failure",
                     f"runtime {rt_ref.id}: connector {rt.connector_type!r} is not executable in "
                     f"Auto v1 (use local_cli or script)",
                     runtime_id=rt_ref.id, harness_id=rt_ref.harness)

    ev.flush_issues()
    result.issues = ev.issues
    return result
