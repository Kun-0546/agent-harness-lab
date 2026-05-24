"""LocalPathAdapter (C5) —— materialize / start / teardown / snapshot_fields。

覆盖 spec §5 test matrix:
- 8: materialize 复制 + apply patch + sandbox 路径
- 9: snapshot 含 source_dir_hash (pre-patch raw source 指纹)
- 10: teardown M1 默认 keep
- 20: materialize 失败 (source 不存在 / patch source 不存在 / 缺 patch / 缺
     start_command / source name 不在 ctx) → RuntimeError / FileNotFoundError

+ source_dir_hash 时机 (apply patch 之前算)
+ start 起子进程跑 IPC (集成测试,真 Python subprocess)
"""
import sys
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.hash_utils import compute_dir_hash
from agent_harness_lab.materialize import MaterializeContext
from agent_harness_lab.materialize.local_path import LocalPathAdapter
from agent_harness_lab.patch import HarnessPatch, PatchFile, parse_patch
from agent_harness_lab.runtime_source import RuntimeSource
from agent_harness_lab.version import Version


def _make_version(version_id="V1", runtime_source=None, patch=None):
    return Version(
        path=Path("fake.md"),
        version_id=version_id,
        is_baseline=True,
        what="test",
        connect=None,
        runtime_source=runtime_source,
        patch=patch,
    )


class TestLocalPathAdapterMaterialize(unittest.TestCase):
    """spec test 8: materialize copy + apply patch + sandbox 内容验证。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        # source dir: 模拟 openmanus 风格小项目
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "agent.py").write_text("original agent", encoding="utf-8")
        (self.source / "prompts").mkdir()
        (self.source / "prompts" / "system.md").write_text(
            "default-system", encoding="utf-8")
        # experiment dir + patches
        self.exp = self.root / "experiments" / "001-exp"
        self.exp.mkdir(parents=True)
        patches = self.exp / "patches" / "V1"
        patches.mkdir(parents=True)
        (patches / "system.md").write_text(
            "custom-system-prompt", encoding="utf-8")

    def _ctx(self):
        return MaterializeContext(
            run_id="run-test-001",
            experiment_dir=self.exp,
            fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="local-aider", type="local_path",
                config={"path": str(self.source)})],
        )

    def _patch_text(self):
        return """files:
  - target: prompts/system.md
    source: patches/V1/system.md

env:
  X_DEBUG: "1"

start_command: python agent.py
"""

    def test_materialize_copies_source_to_sandbox(self):
        v = _make_version(runtime_source="local-aider",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = LocalPathAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.type, "copy_dir")
        self.assertTrue(sandbox.path.exists())
        # source 里的非 patch 文件原样 copy 过来
        self.assertEqual(
            (sandbox.path / "agent.py").read_text(encoding="utf-8"),
            "original agent")

    def test_materialize_applies_patch_overwrites_target(self):
        v = _make_version(runtime_source="local-aider",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = LocalPathAdapter().materialize(v, self._ctx())
        # patch 覆盖了 prompts/system.md
        self.assertEqual(
            (sandbox.path / "prompts" / "system.md").read_text(encoding="utf-8"),
            "custom-system-prompt")

    def test_materialize_sandbox_path_per_variant(self):
        """sandbox path = exp/sandbox/<run_id>/<variant_id>/。"""
        v = _make_version(version_id="V2", runtime_source="local-aider",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = LocalPathAdapter().materialize(v, self._ctx())
        expected = self.exp / "sandbox" / "run-test-001" / "V2"
        self.assertEqual(sandbox.path, expected)

    def test_materialize_metadata_source_dir_hash(self):
        """sandbox.metadata['source_dir_hash'] = raw source 的 hash (pre-patch)。"""
        v = _make_version(runtime_source="local-aider",
                          patch=parse_patch(self._patch_text(), self.exp))
        raw_hash = compute_dir_hash(self.source)
        sandbox = LocalPathAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.metadata["source_dir_hash"], raw_hash)

    def test_materialize_metadata_env(self):
        """sandbox.metadata['env'] 来自 patch.env。"""
        v = _make_version(runtime_source="local-aider",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = LocalPathAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.metadata["env"], {"X_DEBUG": "1"})

    def test_materialize_start_command_from_patch(self):
        v = _make_version(runtime_source="local-aider",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = LocalPathAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.start_command, "python agent.py")

    def test_materialize_rejects_existing_sandbox(self):
        """sandbox path 已存在 → RuntimeError, 原内容不被覆盖。
        sandbox 是证据链一部分,不能被静默 rmtree 覆盖。
        """
        v = _make_version(runtime_source="local-aider",
                          patch=parse_patch(self._patch_text(), self.exp))
        # 第一次 materialize 起 sandbox
        sandbox1 = LocalPathAdapter().materialize(v, self._ctx())
        self.assertTrue(sandbox1.path.exists())
        # 放 marker 文件,证明 "未被静默覆盖"
        marker = sandbox1.path / "ORIGINAL_MARKER.txt"
        marker.write_text("original", encoding="utf-8")
        # 第二次 materialize 应该 raise (sandbox 已存在)
        with self.assertRaises(RuntimeError) as exc:
            LocalPathAdapter().materialize(v, self._ctx())
        self.assertIn("已存在", str(exc.exception))
        self.assertIn("拒绝覆盖", str(exc.exception))
        # 原 marker 仍存在 (未被删)
        self.assertTrue(marker.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "original")


class TestLocalPathAdapterSourceDirHashTiming(unittest.TestCase):
    """source_dir_hash 必须在 apply patch 之前算 —— 不是 post-patch sandbox hash。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "src"
        self.source.mkdir()
        (self.source / "file.txt").write_text("original", encoding="utf-8")
        self.exp = self.root / "exp"
        self.exp.mkdir()
        patches = self.exp / "patches" / "V1"
        patches.mkdir(parents=True)
        (patches / "file.txt").write_text("patched", encoding="utf-8")

    def test_source_dir_hash_is_pre_patch(self):
        """sandbox 里 file.txt 是 patched 内容,但 source_dir_hash 是 raw 'original' 的 hash。"""
        raw_hash = compute_dir_hash(self.source)
        text = """files:
  - target: file.txt
    source: patches/V1/file.txt

start_command: cmd
"""
        ctx = MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="local_path", config={"path": str(self.source)})])
        v = _make_version(runtime_source="src",
                          patch=parse_patch(text, self.exp))
        sandbox = LocalPathAdapter().materialize(v, ctx)
        # sandbox 里 file.txt 是 patched 内容
        self.assertEqual(
            (sandbox.path / "file.txt").read_text(encoding="utf-8"),
            "patched")
        # source_dir_hash 是 raw "original" 的 hash (pre-patch)
        self.assertEqual(sandbox.metadata["source_dir_hash"], raw_hash)
        # 跟 post-patch sandbox dir hash 不一样
        sandbox_hash = compute_dir_hash(sandbox.path)
        self.assertNotEqual(sandbox.metadata["source_dir_hash"], sandbox_hash)


class TestLocalPathAdapterErrors(unittest.TestCase):
    """spec test 20: materialize 失败路径全覆盖。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def _ctx(self, sources):
        return MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=sources)

    def test_source_path_not_exist_raises(self):
        """source.config['path'] 指向不存在 path → RuntimeError 含 '不存在'。"""
        v = _make_version(runtime_source="missing-src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([RuntimeSource(
            name="missing-src", type="local_path",
            config={"path": "/definitely/does/not/exist/abcdef-xyz"})])
        with self.assertRaises(RuntimeError) as exc:
            LocalPathAdapter().materialize(v, ctx)
        self.assertIn("不存在", str(exc.exception))

    def test_missing_patch_raises(self):
        """version.patch=None → RuntimeError 含 'patch 段'。"""
        source = self.root / "src"
        source.mkdir()
        v = _make_version(runtime_source="src", patch=None)
        ctx = self._ctx([RuntimeSource(
            name="src", type="local_path", config={"path": str(source)})])
        with self.assertRaises(RuntimeError) as exc:
            LocalPathAdapter().materialize(v, ctx)
        self.assertIn("patch 段", str(exc.exception))

    def test_missing_start_command_raises(self):
        """patch.start_command 缺 → RuntimeError 含 'start_command'。"""
        source = self.root / "src"
        source.mkdir()
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command=None))
        ctx = self._ctx([RuntimeSource(
            name="src", type="local_path", config={"path": str(source)})])
        with self.assertRaises(RuntimeError) as exc:
            LocalPathAdapter().materialize(v, ctx)
        self.assertIn("start_command", str(exc.exception))

    def test_patch_source_file_not_exist_raises(self):
        """patch.files[i].source_path 不存在 → FileNotFoundError (via apply_patch)。"""
        source = self.root / "src"
        source.mkdir()
        (source / "file.txt").write_text("x", encoding="utf-8")
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(
                              files=[PatchFile(target_path="file.txt",
                                              source_path=self.root / "ghost.txt")],
                              env={}, start_command="cmd"))
        ctx = self._ctx([RuntimeSource(
            name="src", type="local_path", config={"path": str(source)})])
        with self.assertRaises(FileNotFoundError):
            LocalPathAdapter().materialize(v, ctx)

    def test_source_name_not_in_ctx_raises(self):
        """runtime_source 名不在 ctx.runtime_sources → RuntimeError 含 '不在 runtime-sources.md'。"""
        v = _make_version(runtime_source="ghost",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([])
        with self.assertRaises(RuntimeError) as exc:
            LocalPathAdapter().materialize(v, ctx)
        self.assertIn("不在 runtime-sources.md", str(exc.exception))

    def test_source_type_mismatch_raises(self):
        """source 在 ctx 但 type != local_path → RuntimeError 'adapter 类型不匹配'。
        (defensive:adapter_for dispatch 应不会到这里;但 LocalPathAdapter
        被错误直接 call 时该 fail loudly)
        """
        source = self.root / "src"
        source.mkdir()
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([RuntimeSource(
            name="src", type="git_repo",   # 类型不对
            config={"url": "x", "ref": "main"})])
        with self.assertRaises(RuntimeError) as exc:
            LocalPathAdapter().materialize(v, ctx)
        self.assertIn("类型不匹配", str(exc.exception))


class TestLocalPathAdapterTeardown(unittest.TestCase):
    """spec test 10: teardown M1 默认 keep (no-op)。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "src"
        self.source.mkdir()
        (self.source / "a.txt").write_text("x", encoding="utf-8")
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def _setup_sandbox(self):
        ctx = MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="local_path", config={"path": str(self.source)})])
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        adapter = LocalPathAdapter()
        sandbox = adapter.materialize(v, ctx)
        return adapter, sandbox

    def test_teardown_keeps_sandbox(self):
        """teardown 默认 keep:sandbox.path 仍存在,内容仍在。"""
        adapter, sandbox = self._setup_sandbox()
        self.assertTrue(sandbox.path.exists())
        self.assertTrue((sandbox.path / "a.txt").exists())
        adapter.teardown(sandbox)
        self.assertTrue(sandbox.path.exists())
        self.assertTrue((sandbox.path / "a.txt").exists())

    def test_teardown_with_cleanup_removes_sandbox(self):
        """C7: cleanup=True → shutil.rmtree(sandbox.path)。"""
        adapter, sandbox = self._setup_sandbox()
        self.assertTrue(sandbox.path.exists())
        adapter.teardown(sandbox, cleanup=True)
        self.assertFalse(sandbox.path.exists())

    def test_teardown_with_cleanup_on_missing_path_is_noop(self):
        """C7 defensive: sandbox.path 已不存在时 cleanup=True 也不应抛错。"""
        adapter, sandbox = self._setup_sandbox()
        import shutil
        shutil.rmtree(sandbox.path)  # 模拟外部已删
        self.assertFalse(sandbox.path.exists())
        adapter.teardown(sandbox, cleanup=True)   # 不应抛错


class TestLocalPathAdapterSnapshotFields(unittest.TestCase):
    """snapshot_fields 返 spec §2.1 materialized runtime_source schema。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "src"
        self.source.mkdir()
        (self.source / "file.txt").write_text("content", encoding="utf-8")
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def _ctx(self):
        return MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="local_path", config={"path": str(self.source)})])

    def test_snapshot_fields_full_schema(self):
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        adapter = LocalPathAdapter()
        sandbox = adapter.materialize(v, self._ctx())
        fields = adapter.snapshot_fields(v, self._ctx(), sandbox)
        self.assertEqual(fields["type"], "local_path")
        self.assertEqual(fields["name"], "src")
        self.assertEqual(fields["path"], str(self.source))
        self.assertTrue(fields["source_dir_hash"].startswith("sha256:"))
        self.assertEqual(fields["source_dir_hash"], compute_dir_hash(self.source))

    def test_snapshot_fields_without_sandbox_recomputes(self):
        """sandbox=None → 重算 source_dir_hash (用 materialize 失败仍 snapshot 场景)。"""
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        adapter = LocalPathAdapter()
        fields = adapter.snapshot_fields(v, self._ctx(), None)
        self.assertEqual(fields["source_dir_hash"], compute_dir_hash(self.source))

    def test_snapshot_fields_source_missing_empty_hash(self):
        """source path 不存在,sandbox=None → source_dir_hash 空串(不 crash)。"""
        v = _make_version(runtime_source="ghost",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="ghost", type="local_path", config={"path": "/no/such/path"})])
        fields = LocalPathAdapter().snapshot_fields(v, ctx, None)
        self.assertEqual(fields["source_dir_hash"], "")


class TestLocalPathAdapterStart(unittest.TestCase):
    """LocalPathAdapter.start —— 真子进程 + IPC 集成测试。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "src"
        self.source.mkdir()
        # echo agent: 读 input → 回 "got:<input>"
        script = """import json, sys
for line in sys.stdin:
    data = json.loads(line)
    sys.stdout.write(json.dumps({"response": "got:" + data["input"]}) + "\\n")
    sys.stdout.flush()
"""
        (self.source / "agent.py").write_text(script, encoding="utf-8")
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def test_start_runs_subprocess_in_sandbox_cwd(self):
        """start 起子进程,cwd=sandbox,IPC 通畅。"""
        v = _make_version(
            runtime_source="src",
            patch=HarnessPatch(
                files=[], env={},
                start_command=f'"{sys.executable}" agent.py'))
        ctx = MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="local_path", config={"path": str(self.source)})])
        adapter = LocalPathAdapter()
        sandbox = adapter.materialize(v, ctx)
        session = adapter.start(sandbox)
        try:
            resp = session.send("hello")
            self.assertEqual(resp, "got:hello")
            resp2 = session.send("world")
            self.assertEqual(resp2, "got:world")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
