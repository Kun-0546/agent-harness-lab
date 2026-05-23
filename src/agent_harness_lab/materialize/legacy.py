"""LegacyAdapter —— v0.2.0 兼容路径,wrap agentconn.open_session。

重要约束:行为必须 100% 等价 v0.2.0。具体:
- materialize:no-op,只构造 sandbox 带 connect 引用。缺 connect 时抛
  ValueError("没有接入配置") —— v0.2.0 runner 写的同样错误信息。
- start:直接调 agentconn.open_session(connect),跟 v0.2.0 一样。
- teardown:no-op (没有物理 sandbox)。
- snapshot_fields:返 spec §2.2 legacy schema —— type="legacy_connect"
  + connect_md_hash(workspace 根 connect.md 的 sha256;不存在则空串)。
  sandbox 参数允许 None(legacy snapshot 不依赖 materialize 成功)。
"""
from __future__ import annotations

import hashlib

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
                        sandbox: Sandbox | None) -> dict:
        """spec §2.2 legacy schema:type="legacy_connect" + connect_md_hash。

        sandbox 允许 None —— snapshot 是 per variant 在 run 之前 build,不要求
        materialize 成功。connect_md_hash 取 workspace 根 connect.md 内容
        sha256;不存在时空串(variant 都有自带 connect 时合法)。
        """
        # workspace 根:experiments/<id>/ 的上两级
        workspace_root = ctx.experiment_dir.parents[1]
        connect_md = workspace_root / "connect.md"
        if connect_md.exists():
            digest = hashlib.sha256(connect_md.read_bytes()).hexdigest()
            connect_md_hash = f"sha256:{digest}"
        else:
            connect_md_hash = ""
        return {
            "type": "legacy_connect",
            "connect_md_hash": connect_md_hash,
        }
