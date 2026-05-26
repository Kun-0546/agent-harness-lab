"""RuntimeSnapshot —— 一次 (variant) 跑的可复现指纹(spec §1.7 / §2 / §5)。

范围:
- RuntimeSnapshot dataclass + JSON I/O
- build_snapshot:legacy 路径不依赖 sandbox(connect_md_hash 跟 materialize
  是否成功无关);materialized 路径需 sandbox(已 materialize)才能填 harness_patch
  / sandbox 字段。
- write_snapshot:落盘到 results/snapshots/<run_id>/<variant_id>.json
- build_environment:采 python_version / os / captured_at(UTC ISO)

snapshot_id (spec §3 固定 contract):
- legacy → "legacy"
- materialized → "snap-<run_id>-<variant_id>"
"""
from __future__ import annotations

import datetime
import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_harness_lab.materialize import MaterializeContext, RuntimeAdapter, Sandbox
    from agent_harness_lab.version import Version


@dataclass
class RuntimeSnapshot:
    """spec §2:一次 (variant) 跑的 snapshot。

    legacy 路径:harness_patch / sandbox / harness_package 都是 None,
    runtime_source 是 {type: "legacy_connect", connect_md_hash: "sha256:..."}。
    materialized 路径(C5+):harness_patch / sandbox 填实际值。
    v0.5+:variant 引用 harness_package 时,harness_package 块为 spec §12.1
    schema;否则为 None。
    """

    snapshot_id: str                       # "legacy" or "snap-<run_id>-<variant_id>"
    run_id: str
    variant_id: str
    experiment: str
    created_at: str                        # UTC ISO
    runtime_source: dict                   # adapter.snapshot_fields() 的产出
    harness_patch: dict | None             # legacy: None;C5+ filled
    sandbox: dict | None                   # legacy: None;C5+ filled
    environment: dict = field(default_factory=dict)
    harness_package: dict | None = None    # v0.5 新增;无 package 时 None

    def to_json(self) -> dict:
        """转 dict 用于 json.dumps。"""
        return asdict(self)


def build_environment() -> dict:
    """采当前进程环境元数据 —— spec §5 environment 段。"""
    captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "captured_at": captured_at,
    }


def compute_snapshot_id(version: "Version", run_id: str) -> str:
    """spec §3 固定:legacy → "legacy",materialized → "snap-<run_id>-<variant_id>"。"""
    if version.runtime_source is None:
        return "legacy"
    return f"snap-{run_id}-{version.version_id}"


def build_snapshot(
    version: "Version",
    ctx: "MaterializeContext",
    adapter: "RuntimeAdapter",
    sandbox: "Sandbox | None" = None,
) -> RuntimeSnapshot:
    """构造 RuntimeSnapshot。adapter.snapshot_fields 提供 runtime_source dict。

    Legacy 路径(version.runtime_source=None):harness_patch / sandbox 永远 None;
    sandbox 参数可为 None(snapshot 不依赖 materialize 成功)。

    Materialized 路径(runtime_source 写了 + sandbox 已 materialize + patch 有值):
    harness_patch 填 spec §2.1 schema (applied + env + start_command + patch_hash),
    sandbox 填 (type + path + start_command)。
    """
    env = build_environment()
    is_materialized = version.runtime_source is not None

    if is_materialized and sandbox is not None and version.patch is not None:
        from agent_harness_lab.patch import compute_patch_hash
        harness_patch_dict: dict | None = {
            "applied": [
                {"target_path": pf.target_path,
                 "source_path": str(pf.source_path),
                 "hash": pf.hash}
                for pf in version.patch.files
            ],
            "env": dict(version.patch.env),
            "start_command": version.patch.start_command,
            "patch_hash": compute_patch_hash(version.patch),
        }
        sandbox_dict: dict | None = {
            "type": sandbox.type,
            "path": str(sandbox.path) if sandbox.path else None,
            "start_command": sandbox.start_command,
        }
    else:
        harness_patch_dict = None
        sandbox_dict = None

    # v0.5: harness_package 块(spec §12)。variant 无 package → None。
    # materialize 失败(sandbox=None)→ None(无法算 effective_harness_hash)。
    manifest = (getattr(ctx, "variant_packages", None) or {}).get(
        version.version_id)
    harness_package_dict: dict | None
    if (manifest is not None and sandbox is not None
            and sandbox.path is not None):
        from agent_harness_lab.harness_package import (
            build_snapshot_block,
            compute_effective_harness_hash,
            compute_payload_hash,
            merge_env,
        )
        package_targets = [f["target"] for f in manifest.payload_files]
        patch_targets = ([pf.target_path for pf in version.patch.files]
                         if version.patch is not None else [])
        merged_env = merge_env(
            manifest.payload_env,
            dict(version.patch.env) if version.patch is not None else {},
        )
        effective_hash = compute_effective_harness_hash(
            sandbox.path, package_targets, patch_targets,
            merged_env, sandbox.start_command or "",
        )
        payload_hash = compute_payload_hash(manifest)
        workspace_root = ctx.experiment_dir.parents[1]
        harness_package_dict = build_snapshot_block(
            manifest, workspace_root, payload_hash, effective_hash,
        )
    else:
        harness_package_dict = None

    return RuntimeSnapshot(
        snapshot_id=compute_snapshot_id(version, ctx.run_id),
        run_id=ctx.run_id,
        variant_id=version.version_id,
        experiment=ctx.experiment_dir.name,
        created_at=env["captured_at"],
        runtime_source=adapter.snapshot_fields(version, ctx, sandbox),
        harness_patch=harness_patch_dict,
        sandbox=sandbox_dict,
        environment=env,
        harness_package=harness_package_dict,
    )


def write_snapshot(snapshot: RuntimeSnapshot, experiment_dir: Path) -> Path:
    """落盘到 experiments/<id>/results/snapshots/<run_id>/<variant_id>.json。

    spec §2.1 路径。写失败(IO / permission)向上 propagate,workflow.run
    翻成 WorkflowError —— snapshot 是关键证据,写不上 fail 整个 run。
    """
    snap_dir = experiment_dir / "results" / "snapshots" / snapshot.run_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    out = snap_dir / f"{snapshot.variant_id}.json"
    out.write_text(
        json.dumps(snapshot.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out
