"""LegacyAdapter —— v0.2.0 兼容路径,wrap agentconn.open_session。

C3 重要约束:行为必须 100% 等价 v0.2.0。具体:
- materialize:no-op,只构造 sandbox 带 connect 引用。缺 connect 时抛
  ValueError("没有接入配置") —— v0.2.0 runner 写的同样错误信息。
- start:直接调 agentconn.open_session(connect),跟 v0.2.0 一样。
- teardown:no-op (没有物理 sandbox)。
- snapshot_fields:C3 不做 snapshot persistence,返回 stub 满足 Protocol;
  C4 真做 snapshot 时再扩展字段(spec §2.2 legacy schema)。
"""
from __future__ import annotations

from agent_harness_lab.agentconn import AgentSession, open_session
from agent_harness_lab.materialize import MaterializeContext, Sandbox
from agent_harness_lab.version import Version


class LegacyAdapter:
    """对应 v0.2.0 的 4 种接入(进程内库/外部命令行/HTTP无状态/HTTP有状态)。

    所有 4 种接入实现仍在 agentconn.py,本 adapter 只负责 dispatch。
    """

    def materialize(self, version: Version, ctx: MaterializeContext) -> Sandbox:
        # variant.connect 优先;没有就用 workspace 根 connect.md fallback
        conn = version.connect or ctx.fallback_connect
        if conn is None:
            # v0.2.0 runner 检查 v_connect is None 时写 "没有接入配置",同。
            raise ValueError("没有接入配置")
        return Sandbox(
            type="legacy",
            path=None,
            start_command=None,
            metadata={"connect": conn},
        )

    def start(self, sandbox: Sandbox) -> AgentSession:
        return open_session(sandbox.metadata["connect"])

    def teardown(self, sandbox: Sandbox) -> None:
        # 没有物理 sandbox 要清。
        pass

    def snapshot_fields(self, version: Version, ctx: MaterializeContext,
                        sandbox: Sandbox) -> dict:
        # C3 不实现 snapshot persistence;返 stub 满足 Protocol。
        # C4 真做 snapshot 时按 spec §2.2 扩展(legacy_connect + connect_md_hash)。
        return {"type": "legacy_connect"}
