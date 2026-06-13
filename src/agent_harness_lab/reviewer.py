"""hlab review — pre-run structural review of a v1 experiment.

Produces a PASS / WARN / ERROR verdict per docs/cli.md §5 and the validation
rules in docs/experiment-yaml-schema.md §18. Read-only.

Phase 1 — static validation (validate_spec): structure, schema, file refs.
Phase 2 — source health checks (PR8): for each runtime that declares source:,
  performs a read-only check of the source (local_path existence/readability,
  git_repo ls-remote reachability + ref, harness_package fingerprint). Also
  checks patch file sources exist (deferred from PR6). Results are appended as
  Problem items with probe_* codes. The review is read-only: no sandboxes are
  created, no evidence is written, no clones are performed.

probe↔snapshot reconciliation: the fingerprint values emitted here (source
  _dir_hash for local_path, remote_commit_sha for git_repo, manifest/dir hash
  for harness_package) are computed with the SAME functions that materialize_v1
  uses during a run, so a user can compare `hlab review` output against
  evidence/snapshots/<rt>.json after a run to confirm identity. This closes the
  roadmap's deferred probe↔snapshot binding item (previously tracked as a
  deferred item in temp/v0.10.0-planning.md:417).

Performance: for local_path sources, source_dir_hash is computed only when the
  source directory is below a size cap (_DIR_HASH_CAP_BYTES = 256 MiB). Above
  the cap, hashing is skipped with a WARN-level note. This is best-effort: the
  hash is informational for reconciliation; the existence/readability check is
  the gate.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from agent_harness_lab.experiment_spec import (
    ERROR,
    WARN,
    ExperimentSpecError,
    Problem,
    parse_experiment_yaml,
    validate_spec,
)

PASS = "PASS"

# Above this total source size we skip hashing (best-effort, informational only)
_DIR_HASH_CAP_BYTES = 256 * 1024 * 1024  # 256 MiB

# git ls-remote timeout (seconds)
_GIT_LSREMOTE_TIMEOUT = 30

# Regex that matches a full or abbreviated commit SHA (7-40 hex chars, case-insensitive).
# git ls-remote returns nothing for commit SHAs that are not ref tips, so when the
# ref looks like a commit SHA we skip the ls-remote ref-resolution check and emit a
# WARN instead (probe_git_ref_unverifiable) — defect 8.
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


@dataclass
class ReviewReport:
    experiment_dir: Path
    verdict: str  # PASS | WARN | ERROR
    problems: list[Problem] = field(default_factory=list)
    # Per-runtime source check summaries (added by PR8 health check).
    # Each entry: {runtime_id, source_type, target, check_result, fingerprint}
    source_checks: list[dict] = field(default_factory=list)

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level == ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.problems if p.level == WARN]


# ---------------------------------------------------------------------------
# Source health check helpers (read-only; no sandbox, no clone, no write)
# ---------------------------------------------------------------------------

def _dir_size(path: Path) -> int:
    """Approximate total size of a directory tree in bytes. Returns 0 on error."""
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _check_local_path(
    rt_id: str,
    source_spec,   # RuntimeSourceSpec
    experiment_dir: Path,
    problems: list[Problem],
) -> dict:
    """Check a local_path source. Returns a summary dict for display.

    Checks:
    - source directory exists and is a directory
    - readable (can list contents)
    - patch file sources exist (PR6-deferred patch-target existence check)
    Emits source_dir_hash when directory is below _DIR_HASH_CAP_BYTES.
    """
    from agent_harness_lab.hash_utils import compute_dir_hash

    raw_path = source_spec.path or ""
    src_path = Path(raw_path)
    if not src_path.is_absolute():
        src_path = (experiment_dir / raw_path).resolve()

    summary = {
        "runtime_id": rt_id, "source_type": "local_path",
        "target": str(src_path), "check_result": "PASS", "fingerprint": "",
    }

    if not src_path.exists():
        problems.append(Problem(
            ERROR, "probe_source_missing",
            f"runtime {rt_id}: source.path '{raw_path}' does not exist",
        ))
        summary["check_result"] = "ERROR"
        return summary

    if not src_path.is_dir():
        problems.append(Problem(
            ERROR, "probe_source_not_dir",
            f"runtime {rt_id}: source.path '{raw_path}' is not a directory",
        ))
        summary["check_result"] = "ERROR"
        return summary

    try:
        next(iter(src_path.iterdir()), None)
    except PermissionError as e:
        problems.append(Problem(
            ERROR, "probe_source_unreadable",
            f"runtime {rt_id}: source.path '{raw_path}' is not readable: {e}",
        ))
        summary["check_result"] = "ERROR"
        return summary
    except OSError as e:
        problems.append(Problem(
            ERROR, "probe_source_unreadable",
            f"runtime {rt_id}: source.path '{raw_path}' OS error: {e}",
        ))
        summary["check_result"] = "ERROR"
        return summary

    # Patch file sources existence check (deferred from PR6 parse_source_spec)
    patch_raw = source_spec.patch_raw
    if isinstance(patch_raw, dict):
        files = patch_raw.get("files") or []
        if isinstance(files, list):
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                src_rel = entry.get("source", "")
                if not src_rel:
                    continue
                patch_src = (experiment_dir / src_rel).resolve()
                if not patch_src.exists():
                    problems.append(Problem(
                        ERROR, "probe_patch_source_missing",
                        f"runtime {rt_id}: patch.files source '{src_rel}' does not exist",
                    ))
                    summary["check_result"] = "ERROR"

    # Compute dir hash (best-effort; skip if too large)
    size = _dir_size(src_path)
    if size > _DIR_HASH_CAP_BYTES:
        problems.append(Problem(
            WARN, "probe_source_hash_skipped",
            f"runtime {rt_id}: source.path '{raw_path}' is large ({size // (1024*1024)} MiB); "
            f"source_dir_hash skipped (above {_DIR_HASH_CAP_BYTES // (1024*1024)} MiB cap) — "
            f"existence and readability confirmed",
        ))
        if summary["check_result"] == "PASS":
            summary["check_result"] = "WARN"
    else:
        try:
            dir_hash = compute_dir_hash(src_path)
            summary["fingerprint"] = dir_hash
        except OSError as e:
            problems.append(Problem(
                WARN, "probe_source_hash_failed",
                f"runtime {rt_id}: could not compute source_dir_hash: {e}",
            ))
            if summary["check_result"] == "PASS":
                summary["check_result"] = "WARN"

    return summary


def _git_env_reviewer() -> dict:
    """Build subprocess env that prevents all interactive git prompts (defect 10)."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"
    env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    return env


def _run_git_ls_remote(
    git: str,
    url: str,
    ref_arg: str | None,
) -> tuple[int, str, str]:
    """Run `git ls-remote <url> [ref]` with file-redirection to avoid pipe-hold hangs.

    Defect 7: subprocess.run(capture_output=True, timeout=N) can hang on Windows
    when a git transport-helper grandchild holds the pipes.  Use temp files for
    stdout/stderr + Popen.wait(timeout) + process-tree kill on timeout (same pattern
    as the script connector hardening in auto.py).

    Returns (returncode, stdout, stderr).  On timeout, returns (None, "", "timeout").
    """
    from agent_harness_lab.agentconn import _POSIX
    import signal as _sig

    cmd = [git, "ls-remote", url]
    if ref_arg:
        cmd.append(ref_arg)

    with tempfile.TemporaryDirectory(prefix="hlab-probe-", ignore_cleanup_errors=True) as td:
        tdir = Path(td)
        so_path = tdir / "stdout.txt"
        se_path = tdir / "stderr.txt"
        with open(so_path, "w", encoding="utf-8", errors="replace") as fo, \
             open(se_path, "w", encoding="utf-8", errors="replace") as fe:
            proc = subprocess.Popen(
                cmd, stdout=fo, stderr=fe,
                env=_git_env_reviewer(),
                start_new_session=_POSIX,
            )
        timed_out = False
        try:
            proc.wait(timeout=_GIT_LSREMOTE_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True

        if timed_out:
            # Kill the process tree
            try:
                if _POSIX:
                    try:
                        import os as _os
                        _os.killpg(_os.getpgid(proc.pid), _sig.SIGKILL)
                    except Exception:  # noqa: BLE001
                        pass
                else:
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
            return -1, "", "timeout"

        try:
            stdout = so_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stdout = ""
        try:
            stderr = se_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stderr = ""
        return proc.returncode, stdout, stderr


def _check_git_repo(
    rt_id: str,
    source_spec,   # RuntimeSourceSpec
    problems: list[Problem],
) -> dict:
    """Check a git_repo source via ls-remote (read-only; no clone).

    Unreachable remote → ERROR (with a note that it may be transient).
    Defect 8: commit SHA refs (^[0-9a-f]{7,40}$) return nothing from ls-remote
    because they are not ref tips.  When the ref looks like a commit SHA, skip
    the ref-resolution check and emit probe_git_ref_unverifiable WARN instead of
    ERROR — the SHA will be verified at clone time (materialize).

    Emits remote_commit_sha (the resolved SHA of the ref) so users can
    reconcile against evidence/snapshots/<rt>.json commit_sha after a run.

    Defect 7: uses file-redirection I/O + Popen.wait(timeout) + taskkill to
    avoid the Windows pipe-hold hang pattern.
    """
    url = source_spec.url or ""
    ref = source_spec.ref or ""

    summary = {
        "runtime_id": rt_id, "source_type": "git_repo",
        "target": f"{url}@{ref}" if ref else url,
        "check_result": "PASS", "fingerprint": "",
    }

    git = shutil.which("git")
    if not git:
        problems.append(Problem(
            ERROR, "probe_git_missing",
            f"runtime {rt_id}: git binary not found in PATH; git_repo source requires git",
        ))
        summary["check_result"] = "ERROR"
        return summary

    if not url:
        problems.append(Problem(
            ERROR, "probe_git_url_missing",
            f"runtime {rt_id}: source.url is missing for git_repo source",
        ))
        summary["check_result"] = "ERROR"
        return summary

    # Defect 8: commit SHA refs cannot be verified via ls-remote (they are not
    # ref tips).  Detect them and emit a WARN instead of an ERROR.
    if ref and _COMMIT_SHA_RE.match(ref):
        # First verify the remote is reachable (ls-remote with no ref arg)
        rc, stdout, stderr = _run_git_ls_remote(git, url, None)
        if stderr == "timeout":
            problems.append(Problem(
                ERROR, "probe_git_unreachable",
                f"runtime {rt_id}: git ls-remote timed out ({_GIT_LSREMOTE_TIMEOUT}s) — "
                f"remote may be unreachable or credential-blocked; fix before running",
            ))
            summary["check_result"] = "ERROR"
            return summary
        if rc != 0:
            stderr_snippet = stderr.strip()[:200]
            problems.append(Problem(
                ERROR, "probe_git_unreachable",
                f"runtime {rt_id}: git ls-remote failed (exit {rc}) — "
                f"remote '{url}' may be unreachable or the url is invalid "
                f"(may be transient; re-run `hlab review` after verifying connectivity). "
                f"stderr: {stderr_snippet}",
            ))
            summary["check_result"] = "ERROR"
            return summary
        # Remote is reachable; SHA ref itself cannot be verified without cloning
        problems.append(Problem(
            WARN, "probe_git_ref_unverifiable",
            f"runtime {rt_id}: source.ref '{ref}' looks like a commit SHA; "
            f"commit SHAs cannot be verified without cloning — will be verified at "
            f"materialize time (hlab run). Remote reachability confirmed.",
        ))
        summary["check_result"] = "WARN"
        return summary

    # Normal branch/tag ref — run ls-remote with the ref arg to resolve it
    try:
        rc, stdout, stderr = _run_git_ls_remote(git, url, ref or None)
    except OSError as e:
        problems.append(Problem(
            ERROR, "probe_git_unreachable",
            f"runtime {rt_id}: git ls-remote OS error: {e}",
        ))
        summary["check_result"] = "ERROR"
        return summary

    if stderr == "timeout":
        problems.append(Problem(
            ERROR, "probe_git_unreachable",
            f"runtime {rt_id}: git ls-remote timed out ({_GIT_LSREMOTE_TIMEOUT}s) — "
            f"remote may be unreachable or credential-blocked; fix before running",
        ))
        summary["check_result"] = "ERROR"
        return summary

    if rc != 0:
        stderr_snippet = stderr.strip()[:200]
        problems.append(Problem(
            ERROR, "probe_git_unreachable",
            f"runtime {rt_id}: git ls-remote failed (exit {rc}) — "
            f"remote '{url}' may be unreachable or the url is invalid "
            f"(may be transient; re-run `hlab review` after verifying connectivity). "
            f"stderr: {stderr_snippet}",
        ))
        summary["check_result"] = "ERROR"
        return summary

    if not stdout.strip():
        problems.append(Problem(
            ERROR, "probe_git_ref_missing",
            f"runtime {rt_id}: git ls-remote returned empty — "
            f"ref '{ref}' not found in remote '{url}'",
        ))
        summary["check_result"] = "ERROR"
        return summary

    # Extract resolved SHA from ls-remote output (first line, first tab-delimited field)
    first_line = stdout.strip().split("\n")[0]
    remote_sha = first_line.split("\t")[0].strip()
    summary["fingerprint"] = remote_sha
    return summary


def _check_harness_package(
    rt_id: str,
    source_spec,   # RuntimeSourceSpec
    experiment_dir: Path,
    problems: list[Problem],
) -> dict:
    """Check a harness_package source (fingerprint verification; read-only).

    Checks:
    - package path exists and is a directory
    - declared expected_fingerprint (if any) matches actual hashes
    Emits actual manifest_hash + dir_hash for reconciliation.
    """
    from agent_harness_lab.materialize_v1 import (
        _verify_harness_package_fingerprint,
    )

    raw_path = source_spec.path or ""
    pkg_path = Path(raw_path)
    if not pkg_path.is_absolute():
        pkg_path = (experiment_dir / raw_path).resolve()

    summary = {
        "runtime_id": rt_id, "source_type": "harness_package",
        "target": str(pkg_path), "check_result": "PASS", "fingerprint": "",
    }

    if not pkg_path.exists():
        problems.append(Problem(
            ERROR, "probe_source_missing",
            f"runtime {rt_id}: source.path (harness_package) '{raw_path}' does not exist",
        ))
        summary["check_result"] = "ERROR"
        return summary

    if not pkg_path.is_dir():
        problems.append(Problem(
            ERROR, "probe_source_not_dir",
            f"runtime {rt_id}: source.path (harness_package) '{raw_path}' is not a directory",
        ))
        summary["check_result"] = "ERROR"
        return summary

    # Also check patch file sources for harness_package (same as local_path)
    patch_raw = source_spec.patch_raw
    if isinstance(patch_raw, dict):
        files = patch_raw.get("files") or []
        if isinstance(files, list):
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                src_rel = entry.get("source", "")
                if not src_rel:
                    continue
                patch_src = (experiment_dir / src_rel).resolve()
                if not patch_src.exists():
                    problems.append(Problem(
                        ERROR, "probe_patch_source_missing",
                        f"runtime {rt_id}: patch.files source '{src_rel}' does not exist",
                    ))
                    summary["check_result"] = "ERROR"

    try:
        manifest_hash, dir_hash = _verify_harness_package_fingerprint(
            pkg_path, source_spec.expected_fingerprint)
        summary["fingerprint"] = f"manifest={manifest_hash[:19] if manifest_hash else '(none)'}; dir={dir_hash[:19] if dir_hash else '(none)'}"
    except RuntimeError as e:
        problems.append(Problem(
            ERROR, "probe_fingerprint_mismatch",
            f"runtime {rt_id}: harness_package fingerprint mismatch: {e}",
        ))
        summary["check_result"] = "ERROR"

    return summary


def _run_source_health_checks(
    spec,             # ExperimentSpec
    experiment_dir: Path,
) -> tuple[list[Problem], list[dict]]:
    """For each runtime that declares source:, run the read-only health check.

    Returns (problems, source_check_summaries).
    Read-only: no sandboxes created, no evidence written, no git clones.
    """
    from agent_harness_lab.experiment_spec import load_agent_runtime_spec

    problems: list[Problem] = []
    summaries: list[dict] = []

    for rt_ref in spec.agent_runtimes:
        if not isinstance(rt_ref.spec, str) or not rt_ref.spec:
            continue
        spec_path = experiment_dir / rt_ref.spec
        if not spec_path.is_file():
            continue  # already flagged by validate_spec; skip silently
        try:
            rt = load_agent_runtime_spec(spec_path)
        except ExperimentSpecError:
            continue  # already flagged by validate_spec

        source_spec = rt.source
        if source_spec is None:
            continue  # no source: section — health check is a no-op for this runtime

        stype = source_spec.type
        if stype == "local_path":
            summary = _check_local_path(rt_ref.id or rt.id or "?", source_spec,
                                        experiment_dir, problems)
        elif stype == "git_repo":
            summary = _check_git_repo(rt_ref.id or rt.id or "?", source_spec,
                                      problems)
        elif stype == "harness_package":
            summary = _check_harness_package(rt_ref.id or rt.id or "?", source_spec,
                                             experiment_dir, problems)
        else:
            # Unknown type already caught by parse_source_spec; skip
            continue

        summaries.append(summary)

    return problems, summaries


# ---------------------------------------------------------------------------
# Public review entry point
# ---------------------------------------------------------------------------

def review_experiment(experiment_dir: Path) -> ReviewReport:
    """Review an experiment directory. Never raises for ordinary problems —
    a missing/invalid experiment.yaml is reported as an ERROR verdict.

    Phase 1: static schema validation (validate_spec).
    Phase 2: source health checks (PR8) — appended after static validation.
      Only runs when at least one runtime declares source:. Read-only.
    """
    yaml_path = experiment_dir / "experiment.yaml"
    if not yaml_path.exists():
        return ReviewReport(
            experiment_dir, ERROR,
            [Problem(ERROR, "experiment_yaml_missing",
                     "experiment.yaml not found in experiment directory")],
        )
    try:
        spec = parse_experiment_yaml(yaml_path)
    except ExperimentSpecError as e:
        return ReviewReport(
            experiment_dir, ERROR,
            [Problem(ERROR, "experiment_yaml_invalid", str(e))],
        )

    problems = validate_spec(spec, experiment_dir)

    # Phase 2: source health checks (PR8). Run after static validation so probe
    # codes never shadow structural errors. If validate_spec already raised ERROR
    # on the runtime spec file itself, load_agent_runtime_spec will fail silently
    # inside _run_source_health_checks (already handled by the continue guards).
    probe_problems, source_checks = _run_source_health_checks(spec, experiment_dir)
    problems = problems + probe_problems

    if any(p.level == ERROR for p in problems):
        verdict = ERROR
    elif any(p.level == WARN for p in problems):
        verdict = WARN
    else:
        verdict = PASS
    return ReviewReport(experiment_dir, verdict, problems, source_checks)
