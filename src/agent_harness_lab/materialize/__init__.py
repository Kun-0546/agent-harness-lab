"""Runtime Materialization 调度层 —— Adapter Protocol + Sandbox + dispatch。

当前范围:LegacyAdapter (v0.2.0 兼容) + LocalPathAdapter (C5)。GitRepoAdapter
留 C6;其他 type 的 variant,workflow.preflight 阶段 hard fail (不到 dispatch)。

Protocol 签名采用 ctx 模式(spec §7 原 source/patch/run_id/variant_id 4-args
偏离),让所有 adapter 共用 same signature:Legacy 不需要 source/patch,
materialized adapter 从 ctx.runtime_sources 自己解。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from agent_harness_lab.connect import Connect
from agent_harness_lab.runtime_source import RuntimeSource
from agent_harness_lab.version import Version


@dataclass
class Sandbox:
    """一次 (variant, case) 跑时的隔离运行环境。

    Legacy 路径下没有物理 sandbox:type="legacy", path=None, metadata 带
    connect 引用供 LegacyAdapter.start() 用。Materialized 路径(local_path
    C5 / git_repo C6 实现后)下 type="copy_dir" / "git_worktree",path 指
    sandbox/<run_id>/<variant_id>/。
    """

    type: str                              # "legacy" | "copy_dir" | "git_worktree"
    path: Path | None                      # None 表示无物理 sandbox(legacy)
    start_command: str | None              # adapter 默认启动命令
    metadata: dict = field(default_factory=dict)


@dataclass
class MaterializeContext:
    """运行时上下文 —— 实验级(不含 variant 信息),传一次给所有 adapter。

    variant 单独作为第二参数传给 adapter 方法,避免重复构造 ctx。
    """

    run_id: str
    experiment_dir: Path
    fallback_connect: Connect | None       # workspace 根的 connect.md;legacy variant 用
    runtime_sources: list[RuntimeSource]   # workspace 根的 runtime-sources.md 解析结果


class RuntimeAdapter(Protocol):
    """Materialize → Start → Teardown 三段管线的统一接口。

    snapshot_fields 给 snapshot persistence 用,返 spec §2 schema 字段
    (LegacyAdapter 返 §2.2 legacy_connect + connect_md_hash)。
    """

    def materialize(self, version: Version, ctx: MaterializeContext) -> Sandbox: ...

    def start(self, sandbox: Sandbox):  # -> AgentSession (agentconn.AgentSession;避循环 import)
        ...

    def teardown(self, sandbox: Sandbox) -> None: ...

    def snapshot_fields(self, version: Version, ctx: MaterializeContext,
                        sandbox: Sandbox) -> dict: ...


def adapter_for(version: Version, ctx: MaterializeContext) -> RuntimeAdapter:
    """按 version.runtime_source + ctx.runtime_sources 决定用哪个 adapter。

    - runtime_source=None → LegacyAdapter (v0.2.0 兼容路径)
    - runtime_source 写了,对应 source.type=local_path → LocalPathAdapter
    - runtime_source 写了,对应 source.type=git_repo → NotImplementedError (留 C6)
    - runtime_source 名不在 ctx.runtime_sources → NotImplementedError
      (preflight 应已 hard fail,本 raise 是 defensive)
    """
    from agent_harness_lab.materialize.legacy import LegacyAdapter
    from agent_harness_lab.materialize.local_path import LocalPathAdapter

    if version.runtime_source is None:
        return LegacyAdapter()

    source = next(
        (s for s in ctx.runtime_sources if s.name == version.runtime_source),
        None)
    if source is None:
        raise NotImplementedError(
            f"版本 {version.version_id}:runtime_source={version.runtime_source!r} "
            f"不在 runtime-sources.md (preflight 应已 hard fail)"
        )
    if source.type == "local_path":
        return LocalPathAdapter()
    raise NotImplementedError(
        f"版本 {version.version_id}:runtime_source={version.runtime_source!r} "
        f"type={source.type} adapter 还没实现 "
        f"(当前支持 legacy + local_path;git_repo 留 C6)"
    )
