"""LegacyAdapter:v0.2.0 兼容路径 wrap agentconn.open_session。

覆盖:materialize / start / teardown 与 v0.2.0 等价 + dispatcher 选择 +
snapshot_fields 真实计算 connect_md_hash(workspace connect.md sha256)。
LegacyAdapter 必须保住 v0.2.0 行为细节(包括 '没有接入配置' 错误消息原文),
v0.2.0 legacy tests + e2e 仍全绿是关键 contract。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_harness_lab.connect import Connect
from agent_harness_lab.materialize import MaterializeContext, adapter_for
from agent_harness_lab.materialize.legacy import LegacyAdapter
from agent_harness_lab.version import Version


def _make_version(version_id="V1", connect=None, runtime_source=None) -> Version:
    return Version(
        path=Path("fake.md"),
        version_id=version_id,
        is_baseline=True,
        what="test",
        connect=connect,
        runtime_source=runtime_source,
    )


def _make_ctx(fallback_connect=None) -> MaterializeContext:
    return MaterializeContext(
        run_id="run-test",
        experiment_dir=Path("/tmp/exp"),
        fallback_connect=fallback_connect,
        runtime_sources=[],
    )


class TestLegacyAdapterMaterialize(unittest.TestCase):
    """materialize:no-op + sandbox 带 connect 引用。"""

    def test_returns_legacy_sandbox_with_connect_in_metadata(self):
        """sandbox.type='legacy', path=None, metadata['connect'] 指向 variant.connect。"""
        conn = Connect(path=Path("c.md"), conn_type="进程内库", config="模块:foo:bar")
        v = _make_version(connect=conn)
        sandbox = LegacyAdapter().materialize(v, _make_ctx())
        self.assertEqual(sandbox.type, "legacy")
        self.assertIsNone(sandbox.path)
        self.assertIsNone(sandbox.start_command)
        self.assertIs(sandbox.metadata["connect"], conn)

    def test_variant_connect_overrides_fallback(self):
        """variant.connect 优先于 ctx.fallback_connect(跟 v0.2.0 runner v.connect or connect 一致)。"""
        v_conn = Connect(path=Path("v.md"), conn_type="进程内库", config="模块:v:fn")
        fb_conn = Connect(path=Path("f.md"), conn_type="进程内库", config="模块:f:fn")
        v = _make_version(connect=v_conn)
        sandbox = LegacyAdapter().materialize(v, _make_ctx(fallback_connect=fb_conn))
        self.assertIs(sandbox.metadata["connect"], v_conn)

    def test_falls_back_to_global_connect_when_variant_has_none(self):
        """variant 无 connect → 用 ctx.fallback_connect(workspace 根 connect.md)。"""
        fb_conn = Connect(path=Path("c.md"), conn_type="进程内库", config="模块:m:fn")
        v = _make_version(connect=None)
        sandbox = LegacyAdapter().materialize(v, _make_ctx(fallback_connect=fb_conn))
        self.assertIs(sandbox.metadata["connect"], fb_conn)

    def test_no_connect_raises_with_v0_2_0_message(self):
        """无 variant.connect + 无 fallback → ValueError('没有接入配置')。

        v0.2.0 runner 缺 connect 写的错误消息是 '没有接入配置',
        本 adapter 必须保住原文(行为等价契约)。
        """
        v = _make_version(connect=None)
        with self.assertRaises(ValueError) as ctx:
            LegacyAdapter().materialize(v, _make_ctx(fallback_connect=None))
        self.assertEqual(str(ctx.exception), "没有接入配置")


class TestLegacyAdapterLifecycle(unittest.TestCase):
    """start / teardown / snapshot_fields。"""

    def test_start_calls_open_session_with_sandbox_connect(self):
        """start 直接转发到 agentconn.open_session(sandbox.metadata['connect'])。"""
        conn = Connect(path=Path("c.md"), conn_type="进程内库", config="模块:foo:bar")
        v = _make_version(connect=conn)
        adapter = LegacyAdapter()
        sandbox = adapter.materialize(v, _make_ctx())
        with patch("agent_harness_lab.materialize.legacy.open_session") as mock_open:
            mock_open.return_value = "fake-session"
            session = adapter.start(sandbox)
        mock_open.assert_called_once_with(conn)
        self.assertEqual(session, "fake-session")

    def test_teardown_is_noop(self):
        """没有物理 sandbox,teardown 不应抛错 / 无副作用。"""
        conn = Connect(path=Path("c.md"), conn_type="进程内库", config="x")
        v = _make_version(connect=conn)
        adapter = LegacyAdapter()
        sandbox = adapter.materialize(v, _make_ctx())
        adapter.teardown(sandbox)  # 不应抛错

    def test_snapshot_fields_returns_legacy_with_connect_md_hash(self):
        """C4:type='legacy_connect' + connect_md_hash 是 workspace connect.md 的 sha256。"""
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            (root_p / "connect.md").write_text(
                "# c\n\n## 类型\n进程内库\n\n## 配置\nm:f\n", encoding="utf-8")
            exp_dir = root_p / "experiments" / "001-test"
            exp_dir.mkdir(parents=True)
            ctx = MaterializeContext(
                run_id="r", experiment_dir=exp_dir,
                fallback_connect=None, runtime_sources=[],
            )
            conn = Connect(path=Path("c.md"), conn_type="进程内库", config="m:f")
            v = _make_version(connect=conn)
            adapter = LegacyAdapter()
            sandbox = adapter.materialize(v, ctx)
            fields = adapter.snapshot_fields(v, ctx, sandbox)
            self.assertEqual(fields["type"], "legacy_connect")
            self.assertTrue(fields["connect_md_hash"].startswith("sha256:"))
            # sha256 hex = 64 chars
            self.assertEqual(len(fields["connect_md_hash"]), len("sha256:") + 64)

    def test_snapshot_fields_handles_missing_connect_md(self):
        """workspace 无 connect.md → connect_md_hash 空串
        (variant 都自带 connect 时合法,不抛错)。
        """
        with tempfile.TemporaryDirectory() as root:
            exp_dir = Path(root) / "experiments" / "001-test"
            exp_dir.mkdir(parents=True)
            ctx = MaterializeContext(
                run_id="r", experiment_dir=exp_dir,
                fallback_connect=None, runtime_sources=[],
            )
            conn = Connect(path=Path("c.md"), conn_type="进程内库", config="m:f")
            v = _make_version(connect=conn)
            adapter = LegacyAdapter()
            sandbox = adapter.materialize(v, ctx)
            fields = adapter.snapshot_fields(v, ctx, sandbox)
            self.assertEqual(fields["type"], "legacy_connect")
            self.assertEqual(fields["connect_md_hash"], "")

    def test_snapshot_fields_accepts_sandbox_none(self):
        """C4:sandbox 参数可为 None —— snapshot 写在跑之前,不依赖 materialize 成功。"""
        with tempfile.TemporaryDirectory() as root:
            exp_dir = Path(root) / "experiments" / "001-test"
            exp_dir.mkdir(parents=True)
            ctx = MaterializeContext(
                run_id="r", experiment_dir=exp_dir,
                fallback_connect=None, runtime_sources=[],
            )
            v = _make_version()
            fields = LegacyAdapter().snapshot_fields(v, ctx, sandbox=None)
            self.assertEqual(fields["type"], "legacy_connect")
            self.assertEqual(fields["connect_md_hash"], "")


class TestAdapterDispatcher(unittest.TestCase):
    """adapter_for(version) 路由。"""

    def test_no_runtime_source_yields_legacy(self):
        """version.runtime_source=None → LegacyAdapter。"""
        v = _make_version(runtime_source=None)
        adapter = adapter_for(v)
        self.assertIsInstance(adapter, LegacyAdapter)

    def test_runtime_source_written_raises_not_implemented(self):
        """version.runtime_source 写了 → NotImplementedError(当前只支持 legacy)。

        正常路径在 workflow.preflight 已 hard fail;本测试是 defensive,
        防 preflight bypass 的代码路径无声跑到 dispatcher。
        """
        v = _make_version(runtime_source="openmanus-main")
        with self.assertRaises(NotImplementedError) as ctx:
            adapter_for(v)
        msg = str(ctx.exception)
        self.assertIn("V1", msg)
        self.assertIn("openmanus-main", msg)
        self.assertIn("local_path 留 C5", msg)
        self.assertIn("git_repo 留 C6", msg)


if __name__ == "__main__":
    unittest.main()
