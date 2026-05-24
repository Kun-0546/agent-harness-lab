"""GitRepoAdapter (C6) —— materialize / start / teardown / snapshot_fields。

覆盖 spec §5 test matrix:
- 11: materialize (clone + ref checkout + apply patch + sandbox 内容)
- 12: snapshot (commit_sha + patch_hash 经 build_snapshot 链路)
- 13: teardown (M1 默认 keep)
- 20: materialize 失败 (repo 不存在 / ref 不存在 / sandbox 已存在 / 缺 patch /
     缺 start_command / source 名不在 ctx / source type 不匹配) → RuntimeError

+ ref 类型覆盖 (branch / commit_sha / tag)
+ source_dir_hash 时机 (checkout 后 patch 前)
+ start 起子进程跑 IPC (集成测试,真 Python subprocess in cloned repo)

测试用本地 tempdir + git init + commit 造 mock repo,url 用 file:// 协议 (无网络)。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.hash_utils import compute_dir_hash
from agent_harness_lab.materialize import MaterializeContext
from agent_harness_lab.materialize.git_repo import GitRepoAdapter
from agent_harness_lab.patch import HarnessPatch, parse_patch
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


def _git(args, cwd=None):
    """跑 git 命令 helper (test 内造 mock repo 用)。"""
    subprocess.run(
        ["git"] + args,
        check=True, capture_output=True, text=True,
        cwd=str(cwd) if cwd else None,
    )


def _make_mock_repo(root: Path, files: dict | None = None) -> Path:
    """造 mock git repo (本地 git init + first commit)。

    files: {relative_path: content} 默认含一个 agent.py。
    返回 repo 路径。
    """
    repo = root / "mock-repo"
    repo.mkdir()
    _git(["init", "-b", "main"], cwd=repo)
    _git(["config", "user.email", "t@t"], cwd=repo)
    _git(["config", "user.name", "t"], cwd=repo)
    if files is None:
        files = {"agent.py": "# default agent\nprint('v1')\n"}
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "init"], cwd=repo)
    return repo


class TestGitRepoAdapterMaterialize(unittest.TestCase):
    """spec test 11: clone + checkout + apply patch + sandbox 内容。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = _make_mock_repo(self.root)
        self.exp = self.root / "experiments" / "001-exp"
        self.exp.mkdir(parents=True)
        patches = self.exp / "patches" / "V1"
        patches.mkdir(parents=True)
        (patches / "agent.py").write_text(
            "# patched agent\nprint('patched')\n", encoding="utf-8")

    def _ctx(self, ref="main"):
        return MaterializeContext(
            run_id="run-test-001",
            experiment_dir=self.exp,
            fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="git_repo",
                config={"url": str(self.repo), "ref": ref})],
        )

    def _patch_text(self):
        return """files:
  - target: agent.py
    source: patches/V1/agent.py

env:
  X_DEBUG: "1"

start_command: python agent.py
"""

    def test_clone_to_sandbox(self):
        """sandbox 内容来自 repo HEAD,含 .git 目录。"""
        v = _make_version(runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.type, "git_clone")
        self.assertTrue(sandbox.path.exists())
        self.assertTrue((sandbox.path / "agent.py").exists())
        self.assertTrue((sandbox.path / ".git").exists())   # 是真 git repo

    def test_apply_patch_overwrites_target(self):
        """patch 覆盖 agent.py (clone 之后 apply)。"""
        v = _make_version(runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        self.assertEqual(
            (sandbox.path / "agent.py").read_text(encoding="utf-8"),
            "# patched agent\nprint('patched')\n")

    def test_sandbox_path_per_variant(self):
        """sandbox path = exp/sandbox/<run_id>/<variant_id>/。"""
        v = _make_version(version_id="V2", runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        expected = self.exp / "sandbox" / "run-test-001" / "V2"
        self.assertEqual(sandbox.path, expected)

    def test_metadata_has_commit_sha(self):
        """metadata.commit_sha 是 40 字符 hex。"""
        v = _make_version(runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        sha = sandbox.metadata["commit_sha"]
        self.assertEqual(len(sha), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in sha))

    def test_metadata_has_source_dir_hash(self):
        """metadata.source_dir_hash 格式 sha256:<hex>。"""
        v = _make_version(runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        self.assertTrue(sandbox.metadata["source_dir_hash"].startswith("sha256:"))

    def test_metadata_has_url_ref(self):
        v = _make_version(runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.metadata["url"], str(self.repo))
        self.assertEqual(sandbox.metadata["ref"], "main")

    def test_metadata_has_env(self):
        v = _make_version(runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.metadata["env"], {"X_DEBUG": "1"})

    def test_start_command_from_patch(self):
        v = _make_version(runtime_source="src",
                          patch=parse_patch(self._patch_text(), self.exp))
        sandbox = GitRepoAdapter().materialize(v, self._ctx())
        self.assertEqual(sandbox.start_command, "python agent.py")


class TestGitRepoAdapterRefs(unittest.TestCase):
    """ref 类型支持:branch / commit_sha / tag (统一 git checkout,detached HEAD OK)。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = _make_mock_repo(self.root)
        # 加 second commit 让 main HEAD 跟 first commit 区分
        (self.repo / "v2.txt").write_text("v2", encoding="utf-8")
        _git(["add", "."], cwd=self.repo)
        _git(["commit", "-m", "v2"], cwd=self.repo)
        # 拿 first commit sha
        out = subprocess.run(
            ["git", "rev-list", "main", "--reverse"],
            check=True, capture_output=True, text=True, cwd=str(self.repo)
        ).stdout
        self.first_sha = out.split()[0]
        # 在 main HEAD 加 tag
        _git(["tag", "v1.0"], cwd=self.repo)
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def _ctx(self, ref):
        return MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="git_repo",
                config={"url": str(self.repo), "ref": ref})])

    def _v(self):
        return _make_version(runtime_source="src",
                             patch=HarnessPatch(files=[], env={}, start_command="cmd"))

    def test_branch_ref(self):
        """ref='main' (branch) → checkout 成功,HEAD 含 v2.txt。"""
        sandbox = GitRepoAdapter().materialize(self._v(), self._ctx("main"))
        self.assertTrue((sandbox.path / "v2.txt").exists())   # main HEAD 含 v2

    def test_commit_sha_ref(self):
        """ref=<first_sha> (commit) → checkout 到 first,无 v2.txt + commit_sha 等于 first_sha。"""
        sandbox = GitRepoAdapter().materialize(self._v(), self._ctx(self.first_sha))
        self.assertFalse((sandbox.path / "v2.txt").exists())  # first 没 v2
        self.assertEqual(sandbox.metadata["commit_sha"], self.first_sha)

    def test_tag_ref(self):
        """ref='v1.0' (tag) → checkout 成功,HEAD = tag (= main HEAD,含 v2.txt)。"""
        sandbox = GitRepoAdapter().materialize(self._v(), self._ctx("v1.0"))
        self.assertTrue((sandbox.path / "v2.txt").exists())


class TestGitRepoAdapterSourceDirHashTiming(unittest.TestCase):
    """source_dir_hash 必须在 apply patch 之前算 (跟 local_path 一致)。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = _make_mock_repo(self.root, files={"file.txt": "original\n"})
        self.exp = self.root / "exp"
        self.exp.mkdir()
        patches = self.exp / "patches" / "V1"
        patches.mkdir(parents=True)
        (patches / "file.txt").write_text("patched\n", encoding="utf-8")

    def test_source_dir_hash_is_pre_patch(self):
        """sandbox 里 file.txt 是 patched 内容,但 source_dir_hash 不算 patch 改动。"""
        text = """files:
  - target: file.txt
    source: patches/V1/file.txt

start_command: cmd
"""
        ctx = MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="git_repo",
                config={"url": str(self.repo), "ref": "main"})])
        v = _make_version(runtime_source="src", patch=parse_patch(text, self.exp))
        sandbox = GitRepoAdapter().materialize(v, ctx)
        # sandbox 里 file.txt 已 patched
        self.assertEqual(
            (sandbox.path / "file.txt").read_text(encoding="utf-8"), "patched\n")
        # source_dir_hash 跟 post-patch sandbox dir hash 不一样
        # (post-patch 含 patched content,source_dir_hash 算的是 pre-patch raw checkout)
        sandbox_hash = compute_dir_hash(sandbox.path)
        self.assertNotEqual(sandbox.metadata["source_dir_hash"], sandbox_hash)


class TestGitRepoAdapterErrors(unittest.TestCase):
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

    def test_repo_url_not_exist_raises(self):
        """url 指向不存在的本地 path → git clone 失败 → RuntimeError。"""
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([RuntimeSource(
            name="src", type="git_repo",
            config={"url": "/definitely/not/a/git/repo/abcxyz", "ref": "main"})])
        with self.assertRaises(RuntimeError) as exc:
            GitRepoAdapter().materialize(v, ctx)
        self.assertIn("git clone", str(exc.exception))

    def test_ref_not_exist_raises(self):
        """repo 存在但 ref 不存在 → git checkout 失败 → RuntimeError。"""
        repo = _make_mock_repo(self.root)
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([RuntimeSource(
            name="src", type="git_repo",
            config={"url": str(repo), "ref": "nonexistent-ref-xyz"})])
        with self.assertRaises(RuntimeError) as exc:
            GitRepoAdapter().materialize(v, ctx)
        self.assertIn("git checkout", str(exc.exception))

    def test_sandbox_exists_raises(self):
        """sandbox path 已存在 → RuntimeError, 原内容不被覆盖 (跟 local_path 一致 contract)。"""
        repo = _make_mock_repo(self.root)
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([RuntimeSource(
            name="src", type="git_repo",
            config={"url": str(repo), "ref": "main"})])
        # 第一次 materialize 起 sandbox
        sandbox1 = GitRepoAdapter().materialize(v, ctx)
        marker = sandbox1.path / "ORIGINAL_MARKER.txt"
        marker.write_text("original", encoding="utf-8")
        # 第二次 materialize 应 raise
        with self.assertRaises(RuntimeError) as exc:
            GitRepoAdapter().materialize(v, ctx)
        self.assertIn("已存在", str(exc.exception))
        self.assertIn("拒绝覆盖", str(exc.exception))
        # 原 marker 文件仍存在 (未被删)
        self.assertTrue(marker.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "original")

    def test_missing_patch_raises(self):
        """version.patch=None → RuntimeError 含 'patch 段'。"""
        repo = _make_mock_repo(self.root)
        v = _make_version(runtime_source="src", patch=None)
        ctx = self._ctx([RuntimeSource(
            name="src", type="git_repo",
            config={"url": str(repo), "ref": "main"})])
        with self.assertRaises(RuntimeError) as exc:
            GitRepoAdapter().materialize(v, ctx)
        self.assertIn("patch 段", str(exc.exception))

    def test_missing_start_command_raises(self):
        """patch.start_command 缺 → RuntimeError 含 'start_command'。"""
        repo = _make_mock_repo(self.root)
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command=None))
        ctx = self._ctx([RuntimeSource(
            name="src", type="git_repo",
            config={"url": str(repo), "ref": "main"})])
        with self.assertRaises(RuntimeError) as exc:
            GitRepoAdapter().materialize(v, ctx)
        self.assertIn("start_command", str(exc.exception))

    def test_source_name_not_in_ctx_raises(self):
        """runtime_source 名不在 ctx → RuntimeError 含 '不在 runtime-sources.md'。"""
        v = _make_version(runtime_source="ghost",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([])
        with self.assertRaises(RuntimeError) as exc:
            GitRepoAdapter().materialize(v, ctx)
        self.assertIn("不在 runtime-sources.md", str(exc.exception))

    def test_source_type_mismatch_raises(self):
        """source 在 ctx 但 type != git_repo → RuntimeError '类型不匹配'(defensive)。"""
        repo = _make_mock_repo(self.root)
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = self._ctx([RuntimeSource(
            name="src", type="local_path",   # 类型不对
            config={"path": str(repo)})])
        with self.assertRaises(RuntimeError) as exc:
            GitRepoAdapter().materialize(v, ctx)
        self.assertIn("类型不匹配", str(exc.exception))


class TestGitRepoAdapterTeardown(unittest.TestCase):
    """spec test 13: teardown M1 默认 keep。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = _make_mock_repo(self.root)
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def test_teardown_keeps_sandbox(self):
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        ctx = MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="git_repo",
                config={"url": str(self.repo), "ref": "main"})])
        adapter = GitRepoAdapter()
        sandbox = adapter.materialize(v, ctx)
        self.assertTrue(sandbox.path.exists())
        self.assertTrue((sandbox.path / "agent.py").exists())
        adapter.teardown(sandbox)
        self.assertTrue(sandbox.path.exists())
        self.assertTrue((sandbox.path / "agent.py").exists())


class TestGitRepoAdapterSnapshotFields(unittest.TestCase):
    """snapshot_fields 返 spec §2.1.2 git_repo schema (含 commit_sha + source_dir_hash)。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = _make_mock_repo(self.root)
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def _ctx(self):
        return MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="git_repo",
                config={"url": str(self.repo), "ref": "main"})])

    def test_snapshot_fields_full_schema(self):
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        adapter = GitRepoAdapter()
        sandbox = adapter.materialize(v, self._ctx())
        fields = adapter.snapshot_fields(v, self._ctx(), sandbox)
        self.assertEqual(fields["type"], "git_repo")
        self.assertEqual(fields["name"], "src")
        self.assertEqual(fields["url"], str(self.repo))
        self.assertEqual(fields["ref"], "main")
        self.assertEqual(len(fields["commit_sha"]), 40)
        self.assertTrue(fields["source_dir_hash"].startswith("sha256:"))

    def test_snapshot_fields_without_sandbox_empty(self):
        """sandbox=None → commit_sha + source_dir_hash 空串 (诚实表达 materialize 失败)。"""
        v = _make_version(runtime_source="src",
                          patch=HarnessPatch(files=[], env={}, start_command="cmd"))
        fields = GitRepoAdapter().snapshot_fields(v, self._ctx(), None)
        self.assertEqual(fields["type"], "git_repo")
        self.assertEqual(fields["url"], str(self.repo))
        self.assertEqual(fields["ref"], "main")
        self.assertEqual(fields["commit_sha"], "")
        self.assertEqual(fields["source_dir_hash"], "")


class TestGitRepoAdapterStart(unittest.TestCase):
    """GitRepoAdapter.start —— 真子进程 + IPC 集成测试 (echo agent in cloned repo)。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        echo_script = """import json, sys
for line in sys.stdin:
    data = json.loads(line)
    sys.stdout.write(json.dumps({"response": "got:" + data["input"]}) + "\\n")
    sys.stdout.flush()
"""
        self.repo = _make_mock_repo(self.root, files={"agent.py": echo_script})
        self.exp = self.root / "exp"
        self.exp.mkdir()

    def test_start_runs_subprocess_in_sandbox_cwd(self):
        v = _make_version(
            runtime_source="src",
            patch=HarnessPatch(
                files=[], env={},
                start_command=f'"{sys.executable}" agent.py'))
        ctx = MaterializeContext(
            run_id="r", experiment_dir=self.exp, fallback_connect=None,
            runtime_sources=[RuntimeSource(
                name="src", type="git_repo",
                config={"url": str(self.repo), "ref": "main"})])
        adapter = GitRepoAdapter()
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
