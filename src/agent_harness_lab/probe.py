"""Runtime Probe MVP — pre-run inspection of variants (read-only).

Spec: docs/runtime-probe-mvp.md.

Probe is read-only on filesystem and on the network (only `git ls-remote`
+ user-supplied `--command` are allowed). It never creates a sandbox,
never installs a package, never mutates a source. Probe writes its own
artifact under:

    experiments/<id>/probe-results/<probe_id>/<variant_id>.json

Optional `--write-evidence` flag writes `materials/runtime-evidence.md`
**only for legacy_connect variants with status ∈ {ok, warn}** (spec §7.4
correction). Status=fail variants never trigger a materials write.

v0.6 MVP locked decisions (spec §16):
- smoke command default timeout: 30 seconds (CLI `--timeout` override)
- materials evidence target: `materials/runtime-evidence.md` (single file)
- no auto-cleanup of probe-results
- exit code: any variant fail → 1; otherwise 0; non-blocking on future `ahl run`
- smoke stdout/stderr each truncated to 1KB UTF-8 bytes

Pure stdlib + already-internal modules (hash_utils, harness_package,
runtime_source, version, materialize, connect).
"""
from __future__ import annotations

import datetime
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_harness_lab.hash_utils import compute_dir_hash

# Status enum (spec §15 locked)
STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_SKIP = "skip"

# Truncation limit (spec §16 locked decision 5)
_OUTPUT_MAX_BYTES = 1024
_DEFAULT_SMOKE_TIMEOUT = 30
_GIT_LSREMOTE_TIMEOUT = 30   # internal probe (git ls-remote); not the smoke


# ===========================================================================
# Result containers
# ===========================================================================


@dataclass
class ProbeRun:
    """End-to-end probe of one experiment."""

    probe_id: str
    probe_dir: Path                       # experiments/<id>/probe-results/<probe_id>/
    variants: dict[str, dict] = field(default_factory=dict)   # variant_id → artifact
    overall_status: str = STATUS_OK
    evidence_writes: list[str] = field(default_factory=list)   # paths written
    materialized_write_skipped: list[str] = field(default_factory=list)


# ===========================================================================
# Internal helpers
# ===========================================================================


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def make_probe_id() -> str:
    """probe-YYYYMMDD-HHMMSS (UTC) — spec §15 format locked."""
    return time.strftime("probe-%Y%m%d-%H%M%S", time.gmtime())


def _aggregate_status(statuses: list[str]) -> str:
    """fail wins; warn next; skip → warn (partial verification); else ok.

    Empty list defaults to ok (defensive; should not occur in practice).
    """
    if not statuses:
        return STATUS_OK
    if STATUS_FAIL in statuses:
        return STATUS_FAIL
    if STATUS_WARN in statuses:
        return STATUS_WARN
    if STATUS_SKIP in statuses:
        return STATUS_WARN
    return STATUS_OK


def _truncate(text: str, max_bytes: int = _OUTPUT_MAX_BYTES) -> str:
    """Truncate to max_bytes UTF-8 bytes; tag with `(truncated)` marker."""
    if not text:
        return ""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="replace") + "(truncated)"


# ===========================================================================
# Per-aspect probes (read-only)
# ===========================================================================


def probe_runtime_source(version, ctx) -> dict:
    """Inspect variant's runtime_source state.

    For variants without runtime_source: classified as legacy_connect path
    (relies on connect.md in workspace, or variant's own connect block).
    """
    if version.runtime_source is None:
        # Legacy path
        has_workspace_connect = ctx.fallback_connect is not None
        has_variant_connect = version.connect is not None
        if not has_workspace_connect and not has_variant_connect:
            return {
                "name": None, "type": "legacy_connect",
                "status": STATUS_FAIL,
                "reasons": [
                    "legacy variant but no connect.md in workspace and no "
                    "variant ## 类型/## 配置 section"],
            }
        return {
            "name": None, "type": "legacy_connect",
            "status": STATUS_OK,
            "reasons": ["legacy connect available "
                        f"({'variant-level' if has_variant_connect else 'workspace-level'})"],
        }

    sources_by_name = {s.name: s for s in ctx.runtime_sources}
    src = sources_by_name.get(version.runtime_source)
    if src is None:
        return {
            "name": version.runtime_source, "type": None,
            "status": STATUS_FAIL,
            "reasons": [f"runtime_source '{version.runtime_source}' not in runtime-sources.md"],
        }

    if src.type == "local_path":
        return _probe_local_path(src)
    if src.type == "git_repo":
        return _probe_git_repo(src)
    return {
        "name": src.name, "type": src.type,
        "status": STATUS_SKIP,
        "reasons": [f"runtime type '{src.type}' not implemented in v0.5 "
                    f"(supported: local_path, git_repo)"],
    }


def _probe_local_path(src) -> dict:
    """local_path probe: dir exists + readable + dir_hash."""
    path = Path(src.config.get("path", ""))
    if not path.exists():
        return {
            "name": src.name, "type": "local_path", "path": str(path),
            "status": STATUS_FAIL,
            "reasons": [f"source path does not exist: {path}"],
        }
    try:
        # Readability test
        next(iter(path.iterdir()), None)
    except PermissionError as e:
        return {
            "name": src.name, "type": "local_path", "path": str(path),
            "status": STATUS_FAIL,
            "reasons": [f"source path unreadable (permission): {e}"],
        }
    except OSError as e:
        return {
            "name": src.name, "type": "local_path", "path": str(path),
            "status": STATUS_FAIL,
            "reasons": [f"source path unreadable (OS error): {e}"],
        }

    try:
        dir_hash = compute_dir_hash(path)
    except OSError as e:
        return {
            "name": src.name, "type": "local_path", "path": str(path),
            "status": STATUS_WARN,
            "reasons": [f"could not compute dir_hash: {e}"],
        }

    return {
        "name": src.name, "type": "local_path", "path": str(path),
        "status": STATUS_OK,
        "source_dir_hash": dir_hash,
        "reasons": ["local_path source exists + readable + dir_hash computed"],
    }


def _probe_git_repo(src) -> dict:
    """git_repo probe: git ls-remote check (read-only, no clone)."""
    url = src.config.get("url", "")
    ref = src.config.get("ref", "")
    git = shutil.which("git")
    if not git:
        return {
            "name": src.name, "type": "git_repo",
            "status": STATUS_FAIL,
            "reasons": ["git binary not in PATH"],
        }
    if not url:
        return {
            "name": src.name, "type": "git_repo",
            "status": STATUS_FAIL,
            "reasons": ["runtime_source url missing"],
        }
    try:
        result = subprocess.run(
            [git, "ls-remote", url, ref] if ref else [git, "ls-remote", url],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_GIT_LSREMOTE_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "name": src.name, "type": "git_repo", "url": url, "ref": ref,
            "status": STATUS_FAIL,
            "reasons": [f"git ls-remote timed out ({_GIT_LSREMOTE_TIMEOUT}s)"],
        }
    except OSError as e:
        return {
            "name": src.name, "type": "git_repo", "url": url, "ref": ref,
            "status": STATUS_FAIL,
            "reasons": [f"git ls-remote OS error: {e}"],
        }

    if result.returncode != 0:
        return {
            "name": src.name, "type": "git_repo", "url": url, "ref": ref,
            "status": STATUS_FAIL,
            "reasons": [f"git ls-remote failed (exit {result.returncode}): "
                        f"{(result.stderr or '').strip()[:200]}"],
        }
    if not result.stdout.strip():
        return {
            "name": src.name, "type": "git_repo", "url": url, "ref": ref,
            "status": STATUS_FAIL,
            "reasons": [f"git ls-remote returned empty: ref '{ref}' not in remote"],
        }
    head_sha = result.stdout.split("\n")[0].split("\t")[0].strip()
    return {
        "name": src.name, "type": "git_repo", "url": url, "ref": ref,
        "status": STATUS_OK,
        "remote_commit_sha": head_sha,
        "reasons": [f"git ls-remote ok (HEAD at {head_sha[:12]})"],
    }


def probe_harness_package(version, manifest) -> dict | None:
    """If variant has harness_package, inspect package state.

    Returns None when variant has no harness_package frontmatter (per spec §7.1).
    """
    if not version.harness_package:
        return None
    if manifest is None:
        return {
            "ref": version.harness_package,
            "status": STATUS_FAIL,
            "reasons": [
                f"package ref '{version.harness_package}' not resolved "
                f"(manifest missing or invalid ref format)"],
        }

    missing_payload = []
    for f in manifest.payload_files:
        src_path = f.get("source")
        if not src_path or not src_path.exists():
            missing_payload.append(str(src_path))

    if missing_payload:
        return {
            "ref": manifest.ref,
            "status": STATUS_FAIL,
            "manifest_readable": True,
            "payload_files_missing": missing_payload,
            "reasons": [f"payload files missing: {', '.join(missing_payload[:3])}"],
        }

    return {
        "ref": manifest.ref,
        "status": STATUS_OK,
        "manifest_readable": True,
        "payload_files_present": [str(f["source"]) for f in manifest.payload_files],
        "runtime_compatibility": list(manifest.runtime_compatibility),
        "reasons": ["package manifest + payload + runtime_compatibility OK"],
    }


def probe_start_command(version, manifest, smoke_cmd: str | None = None,
                         timeout: int = _DEFAULT_SMOKE_TIMEOUT) -> dict:
    """Resolve effective start_command (patch wins, fallback to manifest);
    optionally execute user-supplied smoke command.

    Legacy variants (no runtime_source) use `命令` field in connect.md,
    not `start_command`; for them this probe returns ok with the connect
    command string surfaced.
    """
    from agent_harness_lab.harness_package import resolve_start_command

    # Legacy variant: start_command concept lives in connect.md (`命令` field),
    # not in patch/manifest. Don't fail on missing patch.start_command here.
    if version.runtime_source is None:
        legacy_cmd = ""
        legacy_source = "workspace_connect"
        if version.connect is not None:
            legacy_cmd = (version.connect.config or "").strip()
            legacy_source = "variant_connect"
        result_legacy = {
            "status": STATUS_OK,
            "command": legacy_cmd or None,
            "source": legacy_source,
            "smoke_executed": False,
            "smoke_status": None,
            "exit_code": None,
            "stdout_truncated": "",
            "stderr_truncated": "",
            "timeout_seconds": timeout,
            "reasons": ["legacy variant: start_command lives in connect.md "
                        "(`命令` field), not in patch/manifest"],
        }
        if smoke_cmd:
            smoke_outcome = _execute_smoke(smoke_cmd, timeout)
            result_legacy.update(smoke_outcome)
            if smoke_outcome["smoke_status"] == STATUS_FAIL:
                result_legacy["status"] = STATUS_FAIL
            elif smoke_outcome["smoke_status"] == STATUS_WARN:
                result_legacy["status"] = STATUS_WARN
            result_legacy["reasons"].append(
                f"smoke command executed: {smoke_outcome['smoke_status']}")
        return result_legacy

    patch_start = (version.patch.start_command if version.patch else None)
    manifest_start = manifest.payload_start_command if manifest else None
    effective = resolve_start_command(patch_start, manifest_start)
    if patch_start:
        source = "patch"
    elif manifest_start:
        source = "manifest"
    else:
        source = "none"

    if not effective:
        return {
            "status": STATUS_FAIL,
            "command": None,
            "source": source,
            "smoke_executed": False,
            "smoke_status": None,
            "exit_code": None,
            "stdout_truncated": "",
            "stderr_truncated": "",
            "timeout_seconds": timeout,
            "reasons": ["start_command not provided by patch or package manifest"],
        }

    result: dict = {
        "status": STATUS_OK,
        "command": effective,
        "source": source,
        "smoke_executed": False,
        "smoke_status": None,
        "exit_code": None,
        "stdout_truncated": "",
        "stderr_truncated": "",
        "timeout_seconds": timeout,
        "reasons": [f"start_command resolved from {source}"],
    }

    if smoke_cmd:
        smoke_outcome = _execute_smoke(smoke_cmd, timeout)
        result.update(smoke_outcome)
        # Propagate worst sub-status up to start_command.status
        if smoke_outcome["smoke_status"] == STATUS_FAIL:
            result["status"] = STATUS_FAIL
        elif smoke_outcome["smoke_status"] == STATUS_WARN:
            result["status"] = STATUS_WARN
        result["reasons"].append(
            f"smoke command executed: {smoke_outcome['smoke_status']}")

    return result


def _execute_smoke(cmd: str, timeout: int) -> dict:
    """Execute user-supplied smoke command (shell=False); capture truncated output."""
    try:
        # POSIX mode always — backslashes inside double-quotes stay literal
        # (Windows paths quoted as "C:\Users\..." parse correctly).
        tokens = shlex.split(cmd, posix=True)
    except ValueError as e:
        return {
            "smoke_executed": False,
            "smoke_status": STATUS_FAIL,
            "exit_code": None,
            "stdout_truncated": "",
            "stderr_truncated": _truncate(f"shlex parse error: {e}"),
            "timeout_seconds": timeout,
        }
    if not tokens:
        return {
            "smoke_executed": False,
            "smoke_status": STATUS_FAIL,
            "exit_code": None,
            "stdout_truncated": "",
            "stderr_truncated": _truncate("smoke command parsed to empty token list"),
            "timeout_seconds": timeout,
        }
    try:
        proc = subprocess.run(
            tokens, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
        smoke_status = STATUS_OK if proc.returncode == 0 else STATUS_WARN
        return {
            "smoke_executed": True,
            "smoke_status": smoke_status,
            "exit_code": proc.returncode,
            "stdout_truncated": _truncate(proc.stdout or ""),
            "stderr_truncated": _truncate(proc.stderr or ""),
            "timeout_seconds": timeout,
        }
    except subprocess.TimeoutExpired:
        return {
            "smoke_executed": True,
            "smoke_status": STATUS_FAIL,
            "exit_code": None,
            "stdout_truncated": "",
            "stderr_truncated": _truncate(
                f"smoke command timed out after {timeout}s"),
            "timeout_seconds": timeout,
        }
    except FileNotFoundError as e:
        return {
            "smoke_executed": True,
            "smoke_status": STATUS_FAIL,
            "exit_code": None,
            "stdout_truncated": "",
            "stderr_truncated": _truncate(f"smoke command not found: {e}"),
            "timeout_seconds": timeout,
        }
    except OSError as e:
        return {
            "smoke_executed": True,
            "smoke_status": STATUS_FAIL,
            "exit_code": None,
            "stdout_truncated": "",
            "stderr_truncated": _truncate(f"smoke OS error: {e}"),
            "timeout_seconds": timeout,
        }


# ===========================================================================
# Per-variant orchestration
# ===========================================================================


def probe_variant(version, ctx, manifest=None,
                   smoke_cmd: str | None = None,
                   timeout: int = _DEFAULT_SMOKE_TIMEOUT) -> dict:
    """Build per-variant artifact dict (spec §7.1 schema)."""
    runtime_state = probe_runtime_source(version, ctx)
    package_state = probe_harness_package(version, manifest)
    start_cmd_state = probe_start_command(version, manifest, smoke_cmd, timeout)

    sub_statuses = [runtime_state.get("status", STATUS_FAIL)]
    if package_state is not None:
        sub_statuses.append(package_state.get("status", STATUS_FAIL))
    sub_statuses.append(start_cmd_state.get("status", STATUS_FAIL))

    overall = _aggregate_status(sub_statuses)

    limitations = ["probe is read-only; no sandbox created or modified"]
    if smoke_cmd:
        limitations.append(
            "smoke command output is supplied runtime evidence captured at "
            "probe time, not cloud attestation")

    return {
        "probe_id": "",      # filled by caller (workflow.probe)
        "variant_id": version.version_id,
        "experiment": "",    # filled by caller
        "status": overall,
        "created_at": _utc_now_iso(),
        "runtime_source": runtime_state,
        "harness_package": package_state,
        "start_command": start_cmd_state,
        "limitations": limitations,
    }


# ===========================================================================
# Artifact persistence
# ===========================================================================


def write_artifact(probe_dir: Path, variant_id: str,
                    artifact: dict) -> Path:
    """Write per-variant JSON to probe-results/<probe_id>/<variant_id>.json."""
    probe_dir.mkdir(parents=True, exist_ok=True)
    out_path = probe_dir / f"{variant_id}.json"
    out_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def write_runtime_evidence_md(materials_dir: Path,
                                artifacts: list[dict]) -> Path | None:
    """Write materials/runtime-evidence.md from ok/warn legacy_connect artifacts.

    Per spec §7.4 correction:
    - Only includes artifacts with status ∈ {ok, warn}
    - Only includes legacy_connect (filter applied by caller in workflow.probe)
    - Must include probe_id / variant_id / status / captured_at /
      checks performed / smoke command / exit code / truncated outputs /
      limitations

    Returns None if no eligible artifacts (nothing written).
    """
    eligible = [a for a in artifacts
                if a.get("status") in (STATUS_OK, STATUS_WARN)]
    if not eligible:
        return None

    materials_dir.mkdir(parents=True, exist_ok=True)
    out = materials_dir / "runtime-evidence.md"

    lines: list[str] = [
        "# Runtime Evidence",
        "",
        "> Auto-generated by `ahl probe --write-evidence`.",
        "> **Supplied runtime evidence, not cloud attestation.**",
        "> Re-run `ahl probe --write-evidence` to refresh.",
        "",
    ]

    for a in eligible:
        vid = a.get("variant_id", "?")
        lines.append(f"## variant {vid}")
        lines.append("")
        lines.append(f"- probe_id: `{a.get('probe_id', '?')}`")
        lines.append(f"- status: **{a.get('status', '?')}**")
        lines.append(f"- captured_at: {a.get('created_at', '?')}")

        rs = a.get("runtime_source") or {}
        pkg = a.get("harness_package")
        sc = a.get("start_command") or {}

        lines.append("- checks performed:")
        lines.append(f"  - runtime_source: type={rs.get('type', '?')}, "
                     f"status={rs.get('status', '?')}")
        if pkg is not None:
            lines.append(f"  - harness_package: ref={pkg.get('ref', '?')}, "
                         f"status={pkg.get('status', '?')}")
        lines.append(f"  - start_command: source={sc.get('source', '?')}, "
                     f"status={sc.get('status', '?')}")

        if sc.get("smoke_executed"):
            lines.append("- smoke command:")
            lines.append(f"  - command: `{sc.get('command', '?')}`")
            lines.append(f"  - exit_code: {sc.get('exit_code', '?')}")
            lines.append(f"  - timeout_seconds: {sc.get('timeout_seconds', '?')}")
            stdout = sc.get("stdout_truncated") or ""
            stderr = sc.get("stderr_truncated") or ""
            if stdout:
                lines.append("  - stdout (truncated, ≤1KB):")
                lines.append("    ```")
                for line in stdout.splitlines():
                    lines.append(f"    {line}")
                lines.append("    ```")
            if stderr:
                lines.append("  - stderr (truncated, ≤1KB):")
                lines.append("    ```")
                for line in stderr.splitlines():
                    lines.append(f"    {line}")
                lines.append("    ```")
        else:
            lines.append("- smoke command: (none provided)")

        lims = a.get("limitations") or []
        if lims:
            lines.append("- limitations:")
            for lim in lims:
                lines.append(f"  - {lim}")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ===========================================================================
# Review-side helpers
# ===========================================================================


def find_latest_probe(exp_dir: Path) -> Path | None:
    """Latest probe-results/<probe_id>/ dir (by name sort); None if none."""
    probe_root = exp_dir / "probe-results"
    if not probe_root.exists():
        return None
    candidates = sorted([d for d in probe_root.iterdir()
                          if d.is_dir() and d.name.startswith("probe-")])
    return candidates[-1] if candidates else None


def summarize_latest_probe(exp_dir: Path) -> dict | None:
    """Compact summary for ahl review display. None if no probes yet."""
    latest = find_latest_probe(exp_dir)
    if latest is None:
        return None

    counts = {STATUS_OK: 0, STATUS_WARN: 0, STATUS_FAIL: 0, STATUS_SKIP: 0}
    total = 0
    for f in sorted(latest.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        s = data.get("status")
        if s in counts:
            counts[s] += 1
        total += 1

    if total == 0:
        return None

    return {
        "probe_id": latest.name,
        "probe_dir": str(latest),
        "total": total,
        "counts": counts,
    }
