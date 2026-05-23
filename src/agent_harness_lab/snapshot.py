"""RuntimeSnapshot —— 一次 (variant) 跑的可复现指纹(spec §1.7 / §2 / §5)。

C4 范围:
- RuntimeSnapshot dataclass + JSON I/O
- build_snapshot:legacy 路径不依赖 sandbox(snapshot 写在跑之前;materialize
  失败时也能写)。materialized 路径(C5+)再扩展。
- write_snapshot:落盘到 results/snapshots/<run_id>/<variant_id>.json
- build_environment:采 python_version / os / captured_at(UTC ISO)

Legacy snapshot_id 固定 "legacy"(spec §3 固定 contract);C5+ materialized
snapshot_id 是 "snap-<run_id>-<variant_id>"。
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

    legacy 路径:harness_patch / sandbox 都是 None,runtime_source 是
    {type: "legacy_connect", connect_md_hash: "sha256:..."}。
    materialized 路径(C5+):harness_patch / sandbox 填实际值。
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

    Legacy 路径:sandbox 可为 None(snapshot 在 run 之前就能 build,不依赖
    materialize 成功)。Materialized 路径(C5+):sandbox 必填,且 harness_patch /
    sandbox 字段填实际值(C5+ 实现)。
    """
    env = build_environment()
    return RuntimeSnapshot(
        snapshot_id=compute_snapshot_id(version, ctx.run_id),
        run_id=ctx.run_id,
        variant_id=version.version_id,
        experiment=ctx.experiment_dir.name,
        created_at=env["captured_at"],
        runtime_source=adapter.snapshot_fields(version, ctx, sandbox),
        harness_patch=None,             # C5+ 填(legacy 永远 None)
        sandbox=None,                   # C5+ 填(legacy 永远 None)
        environment=env,
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
