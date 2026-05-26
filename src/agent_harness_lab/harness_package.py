"""Harness Package MVP — workspace-level installable harness component.

See docs/harness-package-mvp.md for the full contract. Summary:

- Manifest at `harness-packages/<id>/<version>/manifest.md`
- Payload at `harness-packages/<id>/<version>/payload/...`
- Variant frontmatter `harness_package: <id>@<version>` opts in
- Install order in materialize: source copy → package payload → variant `## Patch` → snapshot
- Variant patch wins on file / env / start_command conflicts
- Snapshot block `harness_package` records `manifest_hash` + `payload_hash` +
  `effective_harness_hash` + `install_order=["package","patch"]`
- v0.5 only supports materialized runtime sources (`local_path`, `git_repo`);
  legacy_connect + harness_package = preflight `WorkflowError`

Pure stdlib. No external dependencies.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from agent_harness_lab import mdutil

# v0.5 supported runtime types for harness_package install
SUPPORTED_RUNTIME_TYPES = ("local_path", "git_repo")

# Manifest frontmatter allowed fields
_MANIFEST_FRONTMATTER_FIELDS = frozenset({"id", "version", "runtime_compatibility"})

# Variant ref format: <kebab-id>@<semver>
_VARIANT_REF_RE = re.compile(
    r"^([a-z0-9][a-z0-9-]*)@([0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?)$"
)
_PACKAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass
class Manifest:
    """`harness-packages/<id>/<version>/manifest.md` 解析后的结构。"""

    id: str
    version: str
    runtime_compatibility: list[str]
    description: str
    payload_files: list[dict]   # [{"target": str, "source": Path}]; source 是 absolute path
    payload_env: dict[str, str]
    payload_start_command: str | None
    manifest_path: Path         # absolute path to manifest.md
    pkg_dir: Path               # absolute path to harness-packages/<id>/<version>/

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


def parse_variant_ref(ref: str) -> tuple[str, str]:
    """Parse `<id>@<version>` ref. Raises ValueError on bare id or bad format.

    v0.5 强制 `<id>@<version>` 显式 pin;bare id 无版本不接受。
    """
    if not ref:
        raise ValueError("harness_package ref 空")
    m = _VARIANT_REF_RE.match(ref.strip())
    if not m:
        raise ValueError(
            f"harness_package ref 必须是 '<id>@<version>' 格式 "
            f"(kebab-case id + SemVer, v0.5 不接受 bare id): {ref!r}"
        )
    return m.group(1), m.group(2)


def manifest_path_posix(workspace_root: Path, manifest_path: Path) -> str:
    """Forward-slash relative path string from workspace_root.

    snapshot.manifest_path 用这个,跨 OS reproducible
    (`harness-packages/<id>/<version>/manifest.md` 永远是 `/`)。
    """
    rel = manifest_path.resolve().relative_to(workspace_root.resolve())
    return rel.as_posix()


def _safe_payload_source_path(pkg_dir: Path, source_rel: str) -> Path:
    """Defense:payload source 必须落在 `payload/` 子目录内。"""
    payload_root = (pkg_dir / "payload").resolve()
    src_abs = (pkg_dir / source_rel).resolve()
    try:
        src_abs.relative_to(payload_root)
    except ValueError as exc:
        raise ValueError(
            f"package payload source 越出 payload/ 目录: {source_rel}"
        ) from exc
    return src_abs


def _parse_payload_section(text: str, pkg_dir: Path) -> tuple[
    list[dict], dict[str, str], str | None,
]:
    """Mini YAML-like parser for `## Payload`(镜像 `patch.parse_patch` 结构)。

    Returns (files, env, start_command)。files 列表每项 `{target, source}`,
    source 是 resolve 后的 absolute Path,traversal 已校验。
    """
    files: list[dict] = []
    env: dict[str, str] = {}
    start_command: str | None = None
    state = "top"
    current_file: dict[str, str] = {}

    def _flush_file() -> None:
        if not current_file:
            return
        target = current_file.get("target", "")
        source_rel = current_file.get("source", "")
        if source_rel:
            source_abs = _safe_payload_source_path(pkg_dir, source_rel)
        else:
            source_abs = Path()
        files.append({"target": target, "source": source_abs})
        current_file.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if indent == 0:
            _flush_file()
            m = re.match(r"^(\w+)\s*:\s*(.*)$", stripped)
            if not m:
                state = "top"
                continue
            key, val = m.group(1), m.group(2).strip()
            if key == "files":
                state = "files"
            elif key == "env":
                state = "env"
            elif key == "start_command":
                start_command = val
                state = "top"
            else:
                state = "top"
        else:
            if state == "files":
                if stripped.startswith("- "):
                    _flush_file()
                    m = re.match(r"^-\s+(\w+)\s*:\s*(.*)$", stripped)
                    if m:
                        current_file[m.group(1)] = m.group(2).strip()
                else:
                    m = re.match(r"^(\w+)\s*:\s*(.*)$", stripped)
                    if m:
                        current_file[m.group(1)] = m.group(2).strip()
            elif state == "env":
                m = re.match(r"^(\w+)\s*:\s*(.*)$", stripped)
                if m:
                    env[m.group(1)] = m.group(2).strip().strip("\"'")
    _flush_file()
    return files, env, start_command


def parse_manifest(manifest_path: Path,
                   expected_id: str | None = None,
                   expected_version: str | None = None) -> Manifest:
    """Parse `harness-packages/<id>/<version>/manifest.md`。

    expected_id / expected_version:从路径推得的 id / version,parser 强制
    manifest 自身字段 = 路径(path = 真理)。两边任一不匹配抛 ValueError。
    """
    manifest_path = Path(manifest_path).resolve()
    pkg_dir = manifest_path.parent

    text = manifest_path.read_text(encoding="utf-8")
    fields, body = mdutil.parse_frontmatter(text)

    unknown = set(fields.keys()) - _MANIFEST_FRONTMATTER_FIELDS
    if unknown:
        raise ValueError(
            f"manifest 含未知 frontmatter 字段: {', '.join(sorted(unknown))} "
            f"(allowed: {', '.join(sorted(_MANIFEST_FRONTMATTER_FIELDS))}): "
            f"{manifest_path}"
        )

    pkg_id = (fields.get("id") or "").strip()
    pkg_version = (fields.get("version") or "").strip()
    rc_raw = (fields.get("runtime_compatibility") or "").strip()

    if not pkg_id:
        raise ValueError(f"manifest 缺 id: {manifest_path}")
    if not _PACKAGE_ID_RE.match(pkg_id):
        raise ValueError(
            f"manifest id 必须 kebab-case ([a-z0-9][a-z0-9-]*): "
            f"{pkg_id!r} ({manifest_path})"
        )
    if not pkg_version:
        raise ValueError(f"manifest 缺 version: {manifest_path}")
    if not rc_raw:
        raise ValueError(
            f"manifest 缺 runtime_compatibility (MVP 必须含至少一个 type, "
            f"支持: {', '.join(SUPPORTED_RUNTIME_TYPES)}): {manifest_path}"
        )

    rc_str = rc_raw.strip()
    if rc_str.startswith("[") and rc_str.endswith("]"):
        rc_str = rc_str[1:-1]
    runtime_compat = [t.strip() for t in rc_str.split(",") if t.strip()]
    if not runtime_compat:
        raise ValueError(
            f"manifest runtime_compatibility 解析为空: {rc_raw!r} ({manifest_path})"
        )
    if "legacy_connect" in runtime_compat:
        raise ValueError(
            f"runtime_compatibility 不能含 legacy_connect "
            f"(MVP 仅 materialized runtime support): {rc_raw!r} ({manifest_path})"
        )

    if expected_id is not None and pkg_id != expected_id:
        raise ValueError(
            f"manifest id {pkg_id!r} 跟目录 {expected_id!r} 不一致 "
            f"(路径=真理): {manifest_path}"
        )
    if expected_version is not None and pkg_version != expected_version:
        raise ValueError(
            f"manifest version {pkg_version!r} 跟目录 {expected_version!r} "
            f"不一致: {manifest_path}"
        )

    sections = mdutil.split_sections(body)
    if "Description" not in sections:
        raise ValueError(
            f"manifest 缺 ## Description 段: {manifest_path}"
        )
    description = sections.get("Description", "").strip()

    if "Payload" not in sections:
        raise ValueError(
            f"manifest 缺 ## Payload 段: {manifest_path}"
        )
    payload_text = sections.get("Payload", "")
    files, env, start_command = _parse_payload_section(payload_text, pkg_dir)

    if not files and not env and not start_command:
        raise ValueError(
            f"package payload 三段全空 (files/env/start_command); "
            f"package 没有任何 effect: {manifest_path}"
        )

    return Manifest(
        id=pkg_id,
        version=pkg_version,
        runtime_compatibility=runtime_compat,
        description=description,
        payload_files=files,
        payload_env=env,
        payload_start_command=start_command,
        manifest_path=manifest_path,
        pkg_dir=pkg_dir,
    )


def discover_packages(workspace_root: Path) -> dict[tuple[str, str], Manifest]:
    """Scan `workspace_root/harness-packages/` → `{(id, version): Manifest}`。

    - 目录不存在 → 空 dict(空 packages index)
    - 子目录无 manifest.md → 跳过(可能是 WIP),不报错
    - 任一 manifest 校验失败 → ValueError(由调用方翻成 WorkflowError)
    """
    pkgs_root = workspace_root / "harness-packages"
    out: dict[tuple[str, str], Manifest] = {}
    if not pkgs_root.exists():
        return out
    for id_dir in sorted(pkgs_root.iterdir()):
        if not id_dir.is_dir():
            continue
        path_id = id_dir.name
        for ver_dir in sorted(id_dir.iterdir()):
            if not ver_dir.is_dir():
                continue
            path_version = ver_dir.name
            manifest_path = ver_dir / "manifest.md"
            if not manifest_path.exists():
                continue
            manifest = parse_manifest(
                manifest_path,
                expected_id=path_id,
                expected_version=path_version,
            )
            out[(path_id, path_version)] = manifest
    return out


def compute_manifest_hash(manifest_path: Path) -> str:
    """sha256 over raw bytes of `manifest.md`。"""
    h = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return f"sha256:{h}"


def _file_sha256(path: Path) -> str:
    """Read+hash file; return empty string if file missing."""
    if not path or not path.exists():
        return ""
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{h}"


def compute_payload_hash(manifest: Manifest) -> str:
    """Deterministic sha256 over sorted [target+file_sha256] + env + start_command。

    Reproducible:同样 payload 内容 → 同样 hash。file order 不影响(sorted)。
    """
    h = hashlib.sha256()
    sorted_files = sorted(manifest.payload_files, key=lambda f: f["target"])
    for f in sorted_files:
        h.update(f["target"].encode("utf-8") + b"\0")
        h.update(_file_sha256(f["source"]).encode("utf-8") + b"\0")
    h.update(
        json.dumps(manifest.payload_env, sort_keys=True,
                   ensure_ascii=False).encode("utf-8") + b"\0"
    )
    h.update((manifest.payload_start_command or "").encode("utf-8") + b"\0")
    return f"sha256:{h.hexdigest()}"


def compute_effective_harness_hash(
    sandbox_dir: Path,
    package_targets: list[str],
    patch_targets: list[str],
    merged_env: dict[str, str],
    effective_start_command: str,
) -> str:
    """Hash over union(package.targets, patch.targets) 在 sandbox 中的实际内容
    + merged env + 最终 start_command。

    含义:"最后实际生效的 harness 是什么"。同样 (sandbox 起始 + package + patch)
    → 同样 hash。
    """
    union_targets = sorted(set(package_targets) | set(patch_targets))
    h = hashlib.sha256()
    sandbox_root = sandbox_dir.resolve()
    for t in union_targets:
        target_abs = (sandbox_root / t).resolve()
        try:
            target_abs.relative_to(sandbox_root)
        except ValueError:
            # path traversal 早被 _safe_target_path 阻拦;此处 defensive 跳过
            continue
        file_hash = _file_sha256(target_abs) if target_abs.exists() else ""
        h.update(t.encode("utf-8") + b"\0")
        h.update(file_hash.encode("utf-8") + b"\0")
    h.update(
        json.dumps(merged_env, sort_keys=True,
                   ensure_ascii=False).encode("utf-8") + b"\0"
    )
    h.update((effective_start_command or "").encode("utf-8") + b"\0")
    return f"sha256:{h.hexdigest()}"


def _safe_target_path(sandbox_dir: Path, target_path: str) -> Path:
    """Defense:install target 必须落在 sandbox 内。"""
    sandbox_root = sandbox_dir.resolve()
    target_abs = (sandbox_root / target_path).resolve()
    try:
        target_abs.relative_to(sandbox_root)
    except ValueError as exc:
        raise RuntimeError(
            f"package payload target_path 越出 sandbox: {target_path}"
        ) from exc
    return target_abs


def install_package_payload(manifest: Manifest, sandbox_dir: Path) -> None:
    """Copy each payload file to its target inside sandbox。

    - 自动 mkdir parent
    - target path traversal → RuntimeError
    - source 文件缺失 → FileNotFoundError(workflow 翻成 WorkflowError)
    - 空 payload_files → no-op(env-only / start_command-only package 合法)
    """
    for f in manifest.payload_files:
        source = f["source"]
        target = f["target"]
        if not source or not source.exists():
            raise FileNotFoundError(
                f"package payload source 不存在: {source} (target: {target})"
            )
        target_abs = _safe_target_path(sandbox_dir, target)
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target_abs)


def merge_env(package_env: dict[str, str],
              patch_env: dict[str, str]) -> dict[str, str]:
    """Patch env 覆盖 package env(per-key)。dict-unpack 语义。"""
    out = dict(package_env)
    out.update(patch_env)
    return out


def resolve_start_command(patch_start_command: str | None,
                          manifest_start_command: str | None) -> str | None:
    """Variant patch 胜出;空则 fallback 到 manifest;都空返 None。"""
    if patch_start_command:
        return patch_start_command
    return manifest_start_command


def build_snapshot_block(
    manifest: Manifest,
    workspace_root: Path,
    payload_hash: str,
    effective_harness_hash: str,
) -> dict:
    """Construct the `harness_package` snapshot block (spec §12)。"""
    return {
        "id": manifest.id,
        "version": manifest.version,
        "ref": manifest.ref,
        "manifest_path": manifest_path_posix(workspace_root,
                                              manifest.manifest_path),
        "manifest_hash": compute_manifest_hash(manifest.manifest_path),
        "payload_hash": payload_hash,
        "effective_harness_hash": effective_harness_hash,
        "install_order": ["package", "patch"],
    }
