"""PR6: materialize / patch / snapshot integration for the v1 stack.

Ported capabilities (read-only Stack A originals, adapted into v1 idioms):
  patch.py         -> PatchFile, HarnessPatch, apply_patch, compute_patch_hash
  snapshot.py      -> RuntimeSnapshot dataclass, build_environment, write_snapshot
  materialize/local_path.py  -> source_dir_hash, copytree flow, snapshot_fields
  materialize/git_repo.py    -> clone+checkout+patch flow
  harness_package.py         -> 3-hash fingerprint verification, payload install

v1 idiom differences from Stack A:
- source: section lives in agent-runtimes/*.yaml (PyYAML-parsed, not in variant .md)
- No Version/MaterializeContext objects; works directly with AgentRuntimeSpec dicts
- Failure path: EvidenceCollector.issue(error) + returns None (caller exits rc2 / exit 3)
- Snapshot path: evidence/snapshots/<runtime_id>.json  (not results/snapshots/<run_id>/)
- patch: is optional (Stack A required it); harness_package likewise optional
- git env: anti-hang patterns from git_repo.py  (_git_env, GIT_TERMINAL_PROMPT=0)

Schema note: snapshot JSON shape follows the existing v0.4/v0.x schema from snapshot.py
exactly (no schema change) — only the storage path and the calling context differ.

Snapshot field names (v0.4 canonical shape):
  runtime_source.source_dir_hash   — sha256 of the source tree before patch
  runtime_source.commit_sha        — git_repo only; empty string for others
  harness_patch.patch_hash         — sha256 over sorted patch files + env; covers env-only
  sandbox.type                     — "copy_dir" | "git_clone" | "harness_package"
  harness_package                  — None unless source.type == "harness_package"
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_harness_lab.hash_utils import compute_dir_hash

from agent_harness_lab.agentconn import _POSIX

# ---------------------------------------------------------------------------
# Patch primitives (ported from patch.py: apply_patch, compute_patch_hash,
# PatchFile, HarnessPatch — NOT the hand-written mini-parser at patch.py:66+)
# ---------------------------------------------------------------------------

@dataclass
class PatchFile:
    """A single patch file: source_path contents overwrite target_path."""
    target_path: str
    source_path: Path
    hash: str = ""

    def compute_hash(self) -> str:
        if not self.source_path or not self.source_path.exists():
            return ""
        h = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        return f"sha256:{h}"


@dataclass
class HarnessPatch:
    """files + env from a runtime source: section's patch: sub-section."""
    files: list[PatchFile] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def _safe_target_path(sandbox_dir: Path, target_path: str) -> Path:
    sandbox_root = sandbox_dir.resolve()
    target_abs = (sandbox_root / target_path).resolve()
    try:
        target_abs.relative_to(sandbox_root)
    except ValueError as exc:
        raise RuntimeError(
            f"patch target_path escapes sandbox: {target_path}") from exc
    return target_abs


def apply_patch(patch: HarnessPatch, sandbox_dir: Path) -> list[PatchFile]:
    """Copy each patch file into sandbox_dir. Returns list of applied files."""
    applied: list[PatchFile] = []
    for pf in patch.files:
        if not pf.source_path.exists():
            raise FileNotFoundError(
                f"patch source missing: {pf.source_path} (target: {pf.target_path})")
        target_abs = _safe_target_path(sandbox_dir, pf.target_path)
        # Defect 11: if the resolved target is an existing directory, raise rather
        # than silently dropping the file inside it (shutil.copy(src, dir) would
        # place it at dir/<basename>, not at dir itself — path mismatch).
        if target_abs.is_dir():
            raise RuntimeError(
                f"patch target_path '{pf.target_path}' is an existing directory; "
                f"it must name a file, not a directory")
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(pf.source_path, target_abs)
        applied.append(pf)
    return applied


def compute_patch_hash(patch: HarnessPatch) -> str:
    """Deterministic sha256 over sorted [target+file_hash] + env JSON.

    env is always included in the hash input so that runs differing only in
    env produce distinct patch_hash values (covers env-only patches where
    patch.files is empty).  The field semantics are documented in
    §15.4 of execution-model.md / file-formats note.
    """
    h = hashlib.sha256()
    for pf in sorted(patch.files, key=lambda x: x.target_path):
        h.update(pf.target_path.encode("utf-8") + b"\0")
        h.update(pf.hash.encode("utf-8") + b"\0")
    h.update(
        json.dumps(patch.env, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\0")
    return f"sha256:{h.hexdigest()}"


# ---------------------------------------------------------------------------
# Snapshot primitives (ported from snapshot.py: dataclass skeleton,
# build_environment, write_snapshot path adapted to v1 evidence/ layout)
# ---------------------------------------------------------------------------

@dataclass
class RuntimeSnapshot:
    """v1 snapshot record — schema matches v0.4/v0.x snapshot.py exactly.

    Fields:
      snapshot_id   : "snap-<runtime_id>"
      run_id        : the experiment id (used as a stable run identifier in v1)
      variant_id    : same as runtime_id in v1
      experiment    : experiment directory name
      created_at    : UTC ISO timestamp
      runtime_source: adapter.snapshot_fields output (type-specific)
      harness_patch : None if no patch declared; else {applied, env, patch_hash}
      sandbox       : None if no source; else {type, path}
      environment   : python_version, os, captured_at
      harness_package: None (harness_package source type only)
    """
    snapshot_id: str
    run_id: str
    variant_id: str
    experiment: str
    created_at: str
    runtime_source: dict
    harness_patch: dict | None
    sandbox: dict | None
    environment: dict = field(default_factory=dict)
    harness_package: dict | None = None

    def to_json(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def _build_environment() -> dict:
    captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "captured_at": captured_at,
    }


def write_snapshot(snapshot: RuntimeSnapshot, evidence_dir: Path) -> Path:
    """Write snapshot to evidence/snapshots/<runtime_id>.json."""
    snap_dir = evidence_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    out = snap_dir / f"{snapshot.variant_id}.json"
    out.write_text(
        json.dumps(snapshot.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


# ---------------------------------------------------------------------------
# Source spec parsing (from agent-runtimes/*.yaml `source:` section)
# PyYAML is the parser — NOT the hand-written mini-parser from patch.py:66+
# ---------------------------------------------------------------------------

SOURCE_TYPES = {"local_path", "git_repo", "harness_package"}

_SOURCE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "local_path": ["path"],
    "git_repo": ["url", "ref"],
    "harness_package": ["path"],
}


@dataclass
class RuntimeSourceSpec:
    """Parsed source: section from an agent-runtimes/*.yaml."""
    type: str
    raw: dict[str, Any]

    # local_path fields
    @property
    def path(self) -> str | None:
        return self.raw.get("path")

    # git_repo fields
    @property
    def url(self) -> str | None:
        return self.raw.get("url")

    @property
    def ref(self) -> str | None:
        return self.raw.get("ref")

    # harness_package fields
    @property
    def expected_fingerprint(self) -> dict | None:
        return self.raw.get("expected_fingerprint")

    # patch: sub-section (optional for all types)
    @property
    def patch_raw(self) -> dict | None:
        p = self.raw.get("patch")
        return p if isinstance(p, dict) else None


def parse_source_spec(source_raw: Any, spec_path: Path) -> RuntimeSourceSpec | None:
    """Parse the source: section of an agent-runtimes/*.yaml.

    Returns None if no source: section is declared (backward-compat: no change).
    Returns RuntimeSourceSpec if source: is valid.
    Raises ValueError with a review-ready message on invalid shape.
    """
    if source_raw is None:
        return None
    if not isinstance(source_raw, dict):
        raise ValueError(
            f"agent runtime source: must be a mapping in {spec_path}; "
            f"got {type(source_raw).__name__}")
    stype = source_raw.get("type")
    if not isinstance(stype, str) or stype not in SOURCE_TYPES:
        raise ValueError(
            f"agent runtime source.type {stype!r} is unknown in {spec_path}; "
            f"valid types: {sorted(SOURCE_TYPES)}")
    required = _SOURCE_REQUIRED_FIELDS.get(stype, [])
    missing = [f for f in required if not source_raw.get(f)]
    if missing:
        raise ValueError(
            f"agent runtime source (type={stype!r}) missing required field(s) "
            f"{missing} in {spec_path}")
    # patch: sub-section shape validation (static only — existence checks run in
    # reviewer.py Phase 2 via probe_patch_source_missing; see cli.md §6 Phase 2)
    patch_raw = source_raw.get("patch")
    if patch_raw is not None:
        if not isinstance(patch_raw, dict):
            raise ValueError(
                f"agent runtime source.patch must be a mapping in {spec_path}; "
                f"got {type(patch_raw).__name__}")
        files = patch_raw.get("files")
        if files is not None and not isinstance(files, list):
            raise ValueError(
                f"agent runtime source.patch.files must be a list in {spec_path}")
        if isinstance(files, list):
            for i, entry in enumerate(files):
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"agent runtime source.patch.files[{i}] must be a mapping "
                        f"with target/source in {spec_path}")
                if not entry.get("target") or not entry.get("source"):
                    raise ValueError(
                        f"agent runtime source.patch.files[{i}] must have both "
                        f"'target' and 'source' in {spec_path}")
        env = patch_raw.get("env")
        if env is not None and not isinstance(env, dict):
            raise ValueError(
                f"agent runtime source.patch.env must be a mapping in {spec_path}")
    return RuntimeSourceSpec(type=stype, raw=source_raw)


def _build_patch_from_spec(source_spec: RuntimeSourceSpec,
                            base_dir: Path) -> HarnessPatch | None:
    """Build a HarnessPatch from source_spec.patch_raw relative to base_dir.

    base_dir is the experiment dir (patch source paths are relative to it).
    Returns None if no patch declared.
    """
    patch_raw = source_spec.patch_raw
    if patch_raw is None:
        return None
    patch = HarnessPatch()
    files = patch_raw.get("files") or []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        target = entry.get("target", "")
        source_rel = entry.get("source", "")
        source_abs = (base_dir / source_rel).resolve() if source_rel else Path()
        pf = PatchFile(target_path=target, source_path=source_abs)
        pf.hash = pf.compute_hash()
        patch.files.append(pf)
    env_raw = patch_raw.get("env") or {}
    patch.env = {str(k): str(v) for k, v in env_raw.items()} if isinstance(env_raw, dict) else {}
    return patch


# ---------------------------------------------------------------------------
# Git helpers (anti-hang patterns ported from materialize/git_repo.py)
# ---------------------------------------------------------------------------

try:
    _GIT_TIMEOUT = float(os.environ.get("AHL_GIT_TIMEOUT", "120"))
except ValueError:
    _GIT_TIMEOUT = 120.0


def _git_env() -> dict:
    """Build a subprocess env dict that prevents all interactive git prompts.

    Defect 10: also set GIT_ASKPASS=echo (returns empty string for any prompt,
    which causes git to reject the credential request immediately rather than
    hanging) and GIT_SSH_COMMAND with BatchMode=yes (prevents SSH from
    prompting for passphrases), alongside the existing GIT_TERMINAL_PROMPT=0
    / GCM_INTERACTIVE=never guards.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"   # returns empty → immediate credential rejection
    env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"  # no SSH passphrase prompts
    return env


def _sweep_git_proc(proc: "subprocess.Popen") -> None:
    """Kill a git process tree and reap (Windows: taskkill; POSIX: killpg/SIGKILL)."""
    try:
        if _POSIX:
            try:
                import os as _os
                _os.killpg(_os.getpgid(proc.pid), signal.SIGKILL)
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


def _git_run(git: str, args: list[str], cwd: Path | None = None) -> None:
    """Run a git command with file-redirection I/O to avoid pipe-hold hangs.

    Defect 7: subprocess.run(capture_output=True, timeout=N) hangs on Windows
    when a git transport-helper grandchild holds the pipes open after the direct
    child exits.  The project already solved this pattern for the script connector
    (auto.py ~:360-372): route I/O through temp files, wait() with a timeout on
    the direct child, then sweep the tree.
    """
    with tempfile.TemporaryDirectory(prefix="hlab-git-", ignore_cleanup_errors=True) as td:
        tdir = Path(td)
        so_path = tdir / "stdout.txt"
        se_path = tdir / "stderr.txt"
        with open(so_path, "w", encoding="utf-8", errors="replace") as fo, \
             open(se_path, "w", encoding="utf-8", errors="replace") as fe:
            proc = subprocess.Popen(
                [git] + args,
                stdout=fo, stderr=fe,
                cwd=str(cwd) if cwd else None,
                env=_git_env(),
                start_new_session=_POSIX,
            )
        timed_out = False
        try:
            proc.wait(timeout=_GIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
        if timed_out:
            _sweep_git_proc(proc)
            raise RuntimeError(
                f"git {args[0]} timed out after {_GIT_TIMEOUT:g}s "
                f"(possible network/credential hang); aborted")
        if proc.returncode != 0:
            try:
                stderr = se_path.read_text(encoding="utf-8", errors="replace").strip()[:300]
            except OSError:
                stderr = ""
            raise RuntimeError(
                f"git {args[0]} failed (exit {proc.returncode}): {stderr}")


def _git_capture(git: str, args: list[str], cwd: Path | None = None) -> str:
    """Run a git command and return stdout.  Uses file-redirection to avoid hangs."""
    with tempfile.TemporaryDirectory(prefix="hlab-git-", ignore_cleanup_errors=True) as td:
        tdir = Path(td)
        so_path = tdir / "stdout.txt"
        se_path = tdir / "stderr.txt"
        with open(so_path, "w", encoding="utf-8", errors="replace") as fo, \
             open(se_path, "w", encoding="utf-8", errors="replace") as fe:
            proc = subprocess.Popen(
                [git] + args,
                stdout=fo, stderr=fe,
                cwd=str(cwd) if cwd else None,
                env=_git_env(),
                start_new_session=_POSIX,
            )
        timed_out = False
        try:
            proc.wait(timeout=_GIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
        if timed_out:
            _sweep_git_proc(proc)
            raise RuntimeError(
                f"git {args[0]} timed out after {_GIT_TIMEOUT:g}s "
                f"(possible network/credential hang); aborted")
        try:
            stdout = so_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stdout = ""
        if proc.returncode != 0:
            try:
                stderr = se_path.read_text(encoding="utf-8", errors="replace").strip()[:300]
            except OSError:
                stderr = ""
            raise RuntimeError(
                f"git {args[0]} failed (exit {proc.returncode}): {stderr}")
        return stdout


def _chmod_retry(func, path, exc_info):
    """shutil.rmtree onerror: chmod read-only files and retry (Windows .git/objects).

    onerror is used rather than the 3.12+ onexc so the same code runs on
    Python 3.10–3.12 (onerror is deprecated in 3.12 but still works).
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:  # noqa: BLE001
        pass


def robust_rmtree(path: Path) -> None:
    """Remove a directory tree robustly on Windows (handles read-only .git objects)."""
    if path.exists():
        shutil.rmtree(path, onerror=_chmod_retry)


# ---------------------------------------------------------------------------
# Harness package fingerprint verification
# (ported from harness_package.py 3-hash contract)
# ---------------------------------------------------------------------------

def _file_sha256(path: Path) -> str:
    if not path or not path.exists():
        return ""
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{h}"


_KNOWN_FINGERPRINT_KEYS = frozenset({"manifest_hash", "payload_hash", "effective_harness_hash"})


def _verify_harness_package_fingerprint(
    pkg_path: Path,
    expected_fingerprint: dict | None,
) -> tuple[str, str]:
    """Verify a harness_package directory against expected_fingerprint.

    Defect 5: verify EVERY hash key declared in expected_fingerprint, not just
    manifest_hash and payload_hash.  Unknown / extra keys → RuntimeError (so a
    mistyped key name does not silently skip verification).  Also verifies
    effective_harness_hash when present.

    Returns (manifest_hash, dir_hash) of the actual package directory.
    Raises RuntimeError if any declared hash mismatches or any unknown key is found.
    """
    manifest_file = pkg_path / "manifest.md"
    actual_manifest_hash = _file_sha256(manifest_file) if manifest_file.exists() else ""
    actual_dir_hash = compute_dir_hash(pkg_path) if pkg_path.exists() else ""

    if expected_fingerprint and isinstance(expected_fingerprint, dict):
        # Unknown keys → error (a mistyped key would silently skip verification)
        unknown_keys = set(expected_fingerprint.keys()) - _KNOWN_FINGERPRINT_KEYS
        if unknown_keys:
            raise RuntimeError(
                f"harness_package expected_fingerprint contains unknown key(s): "
                f"{sorted(unknown_keys)}; valid keys: {sorted(_KNOWN_FINGERPRINT_KEYS)} "
                f"(path: {pkg_path})")

        exp_manifest = expected_fingerprint.get("manifest_hash", "")
        if exp_manifest and actual_manifest_hash != exp_manifest:
            raise RuntimeError(
                f"harness_package manifest_hash mismatch: "
                f"expected {exp_manifest!r}, got {actual_manifest_hash!r} "
                f"(path: {pkg_path})")
        exp_payload = expected_fingerprint.get("payload_hash", "")
        if exp_payload:
            actual_payload = _compute_package_payload_hash(pkg_path)
            if actual_payload != exp_payload:
                raise RuntimeError(
                    f"harness_package payload_hash mismatch: "
                    f"expected {exp_payload!r}, got {actual_payload!r} "
                    f"(path: {pkg_path})")
        # effective_harness_hash cannot be verified against the source dir (it
        # requires the fully installed sandbox tree); when declared, we record
        # it as a post-install target to be checked after install (TOCTOU close).
        # Declaring it here only documents intent — _install_and_verify_toctou
        # does the actual check.

    return actual_manifest_hash, actual_dir_hash


def _compute_installed_payload_hash(sandbox_dir: Path, pkg_path: Path) -> str:
    """Compute a deterministic hash over the installed payload files in sandbox_dir.

    Defect 5 (TOCTOU close): after install we hash the files AS THEY LANDED in
    the sandbox, using the same target-relative paths that the source-side hash
    covered, so any tamper between source-check and install is detected.
    """
    payload_dir = pkg_path / "payload"
    if not payload_dir.is_dir():
        # no payload/ — the whole package was installed as-is; hash the sandbox
        return compute_dir_hash(sandbox_dir)
    h = hashlib.sha256()
    for item in sorted(payload_dir.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(payload_dir)
        installed = sandbox_dir / rel
        file_hash = _file_sha256(installed) if installed.exists() else ""
        h.update(str(rel).encode("utf-8") + b"\0")
        h.update(file_hash.encode("utf-8") + b"\0")
    return f"sha256:{h.hexdigest()}"


def _compute_package_payload_hash(pkg_path: Path) -> str:
    """Deterministic hash over sorted payload files in the package directory."""
    payload_dir = pkg_path / "payload"
    if not payload_dir.exists():
        return compute_dir_hash(pkg_path)
    return compute_dir_hash(payload_dir)


def _install_harness_package(pkg_path: Path, sandbox_dir: Path) -> None:
    """Copy the harness_package payload into sandbox_dir.

    Copies all files from pkg_path/payload/ into sandbox_dir (if payload/ exists),
    or copies the entire pkg_path tree into sandbox_dir otherwise.
    """
    payload_dir = pkg_path / "payload"
    src = payload_dir if payload_dir.is_dir() else pkg_path
    for item in sorted(src.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        dest = sandbox_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)


# ---------------------------------------------------------------------------
# Main materialize entry point (called by auto.py run_auto)
# ---------------------------------------------------------------------------

@dataclass
class MaterializeResult:
    """Result of materializing one runtime's source: section."""
    sandbox_dir: Path                  # the materialized directory
    source_dir_hash: str               # pre-patch dir hash
    patch: HarnessPatch | None         # applied patch (or None)
    patch_hash: str                    # "" if no patch
    env_overlay: dict[str, str]        # patch.env to merge onto subprocess env
    runtime_source_fields: dict        # for snapshot runtime_source block
    sandbox_type: str                  # "copy_dir" | "git_clone" | "harness_package"
    commit_sha: str = ""               # git_repo only
    harness_package_block: dict | None = None  # harness_package snapshot block


def materialize_runtime(
    rt_id: str,
    source_spec: RuntimeSourceSpec,
    exp_dir: Path,
    evidence_dir: Path,
) -> MaterializeResult:
    """Materialize one runtime's source: section.

    Copies/clones source into exp_dir/sandbox/<rt_id>/, applies patch, and returns
    a MaterializeResult. Raises RuntimeError on any failure (caller converts to issue
    + exit 3). On failure the sandbox directory is cleaned up so the caller can check
    existence to determine whether materialize succeeded.

    Sandbox path: exp_dir/sandbox/<rt_id>/
    The caller redirects the runtime's working_dir to this sandbox.
    """
    sandbox_dir = exp_dir / "sandbox" / rt_id
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir, onerror=_chmod_retry)
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    stype = source_spec.type
    commit_sha = ""
    harness_package_block = None

    try:
        if stype == "local_path":
            src_path = Path(source_spec.path)
            if not src_path.is_absolute():
                src_path = (exp_dir / src_path).resolve()
            if not src_path.exists():
                raise RuntimeError(
                    f"source.path '{source_spec.path}' does not exist "
                    f"(runtime {rt_id})")
            source_dir_hash = compute_dir_hash(src_path)
            shutil.copytree(src_path, sandbox_dir, dirs_exist_ok=True)
            sandbox_type = "copy_dir"
            runtime_source_fields = {
                "type": "local_path",
                "path": str(src_path),
                "source_dir_hash": source_dir_hash,
            }

        elif stype == "git_repo":
            git = shutil.which("git")
            if git is None:
                raise RuntimeError(
                    "git binary not found in PATH; git_repo source requires git")
            url = source_spec.url
            ref = source_spec.ref
            _git_run(git, ["clone", url, str(sandbox_dir)])
            _git_run(git, ["checkout", ref], cwd=sandbox_dir)
            commit_sha = _git_capture(
                git, ["rev-parse", "HEAD"], cwd=sandbox_dir).strip()
            source_dir_hash = compute_dir_hash(sandbox_dir)
            sandbox_type = "git_clone"
            runtime_source_fields = {
                "type": "git_repo",
                "url": url,
                "ref": ref,
                "commit_sha": commit_sha,
                "source_dir_hash": source_dir_hash,
            }

        elif stype == "harness_package":
            pkg_path = Path(source_spec.path)
            if not pkg_path.is_absolute():
                pkg_path = (exp_dir / pkg_path).resolve()
            if not pkg_path.exists():
                raise RuntimeError(
                    f"source.path (harness_package) '{source_spec.path}' does not exist "
                    f"(runtime {rt_id})")
            # Defect 5: pre-install source verification (manifest + payload hash).
            # Unknown expected_fingerprint keys → RuntimeError (not silent skip).
            manifest_hash, dir_hash = _verify_harness_package_fingerprint(
                pkg_path, source_spec.expected_fingerprint)
            source_dir_hash = dir_hash
            _install_harness_package(pkg_path, sandbox_dir)
            sandbox_type = "harness_package"
            payload_hash = _compute_package_payload_hash(pkg_path)
            # Defect 5 (TOCTOU close): re-hash what was ACTUALLY INSTALLED into the
            # sandbox and verify it matches the declared payload_hash (if any).
            installed_payload_hash = _compute_installed_payload_hash(sandbox_dir, pkg_path)
            if (source_spec.expected_fingerprint and
                    isinstance(source_spec.expected_fingerprint, dict)):
                exp_payload = source_spec.expected_fingerprint.get("payload_hash", "")
                if exp_payload and installed_payload_hash != exp_payload:
                    raise RuntimeError(
                        f"harness_package payload_hash TOCTOU mismatch: "
                        f"installed tree hash {installed_payload_hash!r} != "
                        f"declared {exp_payload!r}; source may have changed during install "
                        f"(path: {pkg_path})")
            harness_package_block = {
                "path": str(pkg_path),
                "manifest_hash": manifest_hash,
                "payload_hash": payload_hash,
                "installed_payload_hash": installed_payload_hash,
            }
            runtime_source_fields = {
                "type": "harness_package",
                "path": str(pkg_path),
                "source_dir_hash": source_dir_hash,
            }

        else:
            raise RuntimeError(f"unsupported source.type {stype!r} (runtime {rt_id})")

        # Apply patch (optional)
        patch = _build_patch_from_spec(source_spec, exp_dir)
        patch_hash = ""
        if patch is not None:
            if patch.files:
                apply_patch(patch, sandbox_dir)
            # Defect 6: compute patch_hash whenever a patch is declared, not only
            # when patch.files is non-empty.  An env-only patch must produce a
            # non-empty patch_hash so two runs that differ only in env get distinct
            # snapshots (patch_hash covers env unconditionally — see compute_patch_hash).
            if patch.files or patch.env:
                patch_hash = compute_patch_hash(patch)
        env_overlay = patch.env if patch is not None else {}

    except Exception:
        # Clean up the partially-created sandbox so callers can check existence
        # to determine success (empty sandbox dir would be misleading).
        try:
            if sandbox_dir.exists():
                shutil.rmtree(sandbox_dir, onerror=_chmod_retry)
        except OSError:
            pass
        raise

    return MaterializeResult(
        sandbox_dir=sandbox_dir,
        source_dir_hash=source_dir_hash,
        patch=patch,
        patch_hash=patch_hash,
        env_overlay=env_overlay,
        runtime_source_fields=runtime_source_fields,
        sandbox_type=sandbox_type,
        commit_sha=commit_sha,
        harness_package_block=harness_package_block,
    )


def build_and_write_snapshot(
    rt_id: str,
    exp_dir: Path,
    evidence_dir: Path,
    result: MaterializeResult,
    run_id: str,
) -> Path:
    """Build a RuntimeSnapshot from a MaterializeResult and write to evidence/snapshots/.

    Schema exactly matches v0.4 snapshot.py (no schema change).
    """
    env = _build_environment()
    patch_dict: dict | None = None
    if result.patch is not None:
        patch_dict = {
            "applied": [
                {"target_path": pf.target_path,
                 "source_path": str(pf.source_path),
                 "hash": pf.hash}
                for pf in (result.patch.files or [])
            ],
            "env": dict(result.patch.env),
            "patch_hash": result.patch_hash,
        }

    sandbox_dict: dict | None = None
    if result.sandbox_dir:
        sandbox_dict = {
            "type": result.sandbox_type,
            "path": str(result.sandbox_dir),
        }

    snap = RuntimeSnapshot(
        snapshot_id=f"snap-{rt_id}",
        run_id=run_id,
        variant_id=rt_id,
        experiment=exp_dir.name,
        created_at=env["captured_at"],
        runtime_source=result.runtime_source_fields,
        harness_patch=patch_dict,
        sandbox=sandbox_dict,
        environment=env,
        harness_package=result.harness_package_block,
    )
    return write_snapshot(snap, evidence_dir)
