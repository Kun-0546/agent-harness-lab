"""snapshot.py:RuntimeSnapshot dataclass + build_snapshot + write_snapshot。

覆盖 C4:
- compute_snapshot_id: legacy 固定 "legacy", materialized = "snap-<run_id>-<vid>"
- build_environment: python_version / os / captured_at
- build_snapshot: legacy 路径 sandbox 可为 None
- write_snapshot: 落盘到 results/snapshots/<run_id>/<variant_id>.json
- JSON 序列化/反序列化 roundtrip
"""
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from agent_harness_lab.connect import Connect
from agent_harness_lab.materialize import MaterializeContext
from agent_harness_lab.materialize.legacy import LegacyAdapter
from agent_harness_lab.snapshot import (
    RuntimeSnapshot,
    build_environment,
    build_snapshot,
    compute_snapshot_id,
    write_snapshot,
)
from agent_harness_lab.version import Version


def _make_version(version_id="V1", runtime_source=None) -> Version:
    return Version(
        path=Path("fake.md"),
        version_id=version_id,
        is_baseline=True,
        what="test",
        connect=Connect(path=Path("c.md"), conn_type="进程内库", config="m:f"),
        runtime_source=runtime_source,
    )


def _make_ctx(experiment_dir: Path) -> MaterializeContext:
    return MaterializeContext(
        run_id="run-20260523-010203",
        experiment_dir=experiment_dir,
        fallback_connect=None,
        runtime_sources=[],
    )


class TestComputeSnapshotId(unittest.TestCase):
    """spec §3 固定 contract:legacy 是字符串 'legacy',materialized 是
    'snap-<run_id>-<variant_id>'。"""

    def test_legacy_id_is_literal_legacy(self):
        v = _make_version(runtime_source=None)
        self.assertEqual(compute_snapshot_id(v, "run-X"), "legacy")

    def test_materialized_id_format(self):
        v = _make_version(version_id="V2", runtime_source="openmanus-main")
        self.assertEqual(
            compute_snapshot_id(v, "run-20260523-010203"),
            "snap-run-20260523-010203-V2",
        )


class TestBuildEnvironment(unittest.TestCase):
    """spec §5 environment 段:python_version / os / captured_at(UTC ISO)。"""

    def test_required_fields_present(self):
        env = build_environment()
        self.assertIn("python_version", env)
        self.assertIn("os", env)
        self.assertIn("captured_at", env)

    def test_captured_at_is_iso_utc(self):
        env = build_environment()
        # ISO 8601:含 'T' 分隔时间,'+00:00' 或 'Z' 表示 UTC
        self.assertIn("T", env["captured_at"])
        self.assertTrue(
            env["captured_at"].endswith("+00:00") or env["captured_at"].endswith("Z"))


class TestBuildSnapshot(unittest.TestCase):
    """legacy 路径 sandbox 可为 None;runtime_source 来自 adapter.snapshot_fields。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-test"
        self.exp.mkdir(parents=True)

    def test_legacy_snapshot_id_is_legacy(self):
        v = _make_version(runtime_source=None)
        snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
        self.assertEqual(snap.snapshot_id, "legacy")
        self.assertEqual(snap.variant_id, "V1")
        self.assertEqual(snap.experiment, "001-test")
        self.assertEqual(snap.run_id, "run-20260523-010203")

    def test_legacy_snapshot_runtime_source_type(self):
        """spec §2.2:legacy 的 runtime_source.type='legacy_connect'。"""
        v = _make_version()
        snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
        self.assertEqual(snap.runtime_source["type"], "legacy_connect")

    def test_legacy_harness_patch_and_sandbox_are_none(self):
        """spec §2.2:legacy schema 的 harness_patch / sandbox 是 null(留 C5+)。"""
        v = _make_version()
        snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
        self.assertIsNone(snap.harness_patch)
        self.assertIsNone(snap.sandbox)

    def test_environment_attached(self):
        v = _make_version()
        snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
        self.assertIn("python_version", snap.environment)
        self.assertIn("os", snap.environment)


class TestWriteSnapshot(unittest.TestCase):
    """落盘路径 + JSON 结构。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp = Path(self._tmp.name) / "experiments" / "001-test"
        self.exp.mkdir(parents=True)

    def test_writes_to_correct_path(self):
        """spec §2.1:results/snapshots/<run_id>/<variant_id>.json。"""
        v = _make_version()
        snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
        path = write_snapshot(snap, self.exp)
        expected = (self.exp / "results" / "snapshots" / "run-20260523-010203"
                    / "V1.json")
        self.assertEqual(path, expected)
        self.assertTrue(path.exists())

    def test_json_content_has_required_fields(self):
        v = _make_version()
        snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
        path = write_snapshot(snap, self.exp)
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("snapshot_id", "run_id", "variant_id", "experiment",
                    "created_at", "runtime_source", "harness_patch",
                    "sandbox", "environment"):
            self.assertIn(key, data)
        self.assertEqual(data["snapshot_id"], "legacy")
        self.assertEqual(data["runtime_source"]["type"], "legacy_connect")
        self.assertIsNone(data["harness_patch"])
        self.assertIsNone(data["sandbox"])

    def test_json_roundtrip(self):
        """asdict → json.dumps → json.loads → 字段一致。"""
        v = _make_version()
        snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
        path = write_snapshot(snap, self.exp)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data, asdict(snap))

    def test_per_variant_files_in_same_run_id_dir(self):
        """多 variant 在同一 run_id 下产出多个 .json 文件,平铺(无嵌套目录)。"""
        for vid in ("V1", "V2", "V3"):
            v = _make_version(version_id=vid)
            snap = build_snapshot(v, _make_ctx(self.exp), LegacyAdapter())
            write_snapshot(snap, self.exp)
        snap_dir = self.exp / "results" / "snapshots" / "run-20260523-010203"
        files = sorted(p.name for p in snap_dir.glob("*.json"))
        self.assertEqual(files, ["V1.json", "V2.json", "V3.json"])


if __name__ == "__main__":
    unittest.main()
