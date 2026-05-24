"""patch.py — parse_patch / apply_patch / compute_patch_hash。

覆盖 spec §5 test matrix 的 test 6 + C5 apply / patch_hash 行为。
"""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.patch import (
    HarnessPatch,
    PatchFile,
    apply_patch,
    compute_patch_hash,
    parse_patch,
)


class TestParsePatch(unittest.TestCase):
    """spec §1.2 / §5 test 6:files + env + start_command 三段。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # 模拟 experiment_dir;在它下面创建 patches/V2/ 含两个 patch 文件
        self.exp_dir = Path(self._tmp.name)
        patches_dir = self.exp_dir / "patches" / "V2"
        patches_dir.mkdir(parents=True)
        (patches_dir / "system.md").write_text(
            "custom system prompt", encoding="utf-8")
        (patches_dir / "tools.yaml").write_text(
            "custom tools config", encoding="utf-8")

    def test_full_patch(self):
        """files + env + start_command 全部解析正确。"""
        text = """
files:
  - target: prompts/system.md
    source: patches/V2/system.md
  - target: config/tools.yaml
    source: patches/V2/tools.yaml

env:
  HARNESS_MAX_DEPTH: "5"
  HARNESS_TEMPERATURE: "0.7"

start_command: python -m openmanus.agent
"""
        patch = parse_patch(text, self.exp_dir)
        self.assertEqual(len(patch.files), 2)
        self.assertEqual(patch.files[0].target_path, "prompts/system.md")
        self.assertEqual(
            patch.files[0].source_path,
            self.exp_dir / "patches" / "V2" / "system.md",
        )
        self.assertTrue(patch.files[0].hash.startswith("sha256:"))
        self.assertEqual(patch.files[1].target_path, "config/tools.yaml")
        self.assertTrue(patch.files[1].hash.startswith("sha256:"))
        self.assertEqual(patch.env["HARNESS_MAX_DEPTH"], "5")
        self.assertEqual(patch.env["HARNESS_TEMPERATURE"], "0.7")
        self.assertEqual(patch.start_command, "python -m openmanus.agent")

    def test_only_start_command(self):
        """只有 start_command;files/env 为空。"""
        patch = parse_patch("start_command: python -m foo\n", self.exp_dir)
        self.assertEqual(patch.files, [])
        self.assertEqual(patch.env, {})
        self.assertEqual(patch.start_command, "python -m foo")

    def test_empty_text_yields_empty_patch(self):
        """空 patch 段 → 空 HarnessPatch。"""
        patch = parse_patch("", self.exp_dir)
        self.assertEqual(patch.files, [])
        self.assertEqual(patch.env, {})
        self.assertIsNone(patch.start_command)

    def test_validate_catches_missing_start_command(self):
        """validate:start_command 必填(M1 不假设默认命令)。"""
        patch = parse_patch("", self.exp_dir)
        problems = patch.validate()
        self.assertTrue(any("start_command" in p for p in problems))

    def test_validate_catches_missing_source_file(self):
        """patch source 文件不存在 → validate 报问题。"""
        text = """files:
  - target: prompts/system.md
    source: patches/V2/nonexistent.md

start_command: cmd
"""
        patch = parse_patch(text, self.exp_dir)
        problems = patch.validate()
        self.assertTrue(any("source 文件不存在" in p for p in problems))

    def test_hash_stable_across_parses(self):
        """同样的 source 内容 → 同样的 hash(deterministic)。"""
        text = """files:
  - target: prompts/system.md
    source: patches/V2/system.md

start_command: cmd
"""
        patch1 = parse_patch(text, self.exp_dir)
        patch2 = parse_patch(text, self.exp_dir)
        self.assertEqual(patch1.files[0].hash, patch2.files[0].hash)
        self.assertNotEqual(patch1.files[0].hash, "")

    def test_env_quote_stripped(self):
        """env 值的双引号/单引号会被去掉。"""
        text = """env:
  KEY1: "value-with-quotes"
  KEY2: 'single-quoted'
  KEY3: raw-no-quotes

start_command: cmd
"""
        patch = parse_patch(text, self.exp_dir)
        self.assertEqual(patch.env["KEY1"], "value-with-quotes")
        self.assertEqual(patch.env["KEY2"], "single-quoted")
        self.assertEqual(patch.env["KEY3"], "raw-no-quotes")


class TestApplyPatch(unittest.TestCase):
    """C5: apply_patch 把 patch 内容 copy 到 sandbox。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp_dir = Path(self._tmp.name) / "exp"
        self.exp_dir.mkdir()
        # 准备 source patch files
        patches = self.exp_dir / "patches" / "V2"
        patches.mkdir(parents=True)
        (patches / "system.md").write_text("custom-system", encoding="utf-8")
        (patches / "tools.yaml").write_text("custom-tools", encoding="utf-8")
        # 准备 sandbox (空 dir)
        self.sandbox = Path(self._tmp.name) / "sandbox"
        self.sandbox.mkdir()

    def _patch(self, text):
        return parse_patch(text, self.exp_dir)

    def test_apply_copies_files_to_sandbox(self):
        """apply 后 sandbox 内有 target 文件,内容跟 source 一致。"""
        text = """files:
  - target: prompts/system.md
    source: patches/V2/system.md
  - target: config/tools.yaml
    source: patches/V2/tools.yaml

start_command: cmd
"""
        patch = self._patch(text)
        applied = apply_patch(patch, self.sandbox)
        self.assertEqual(len(applied), 2)
        self.assertEqual(
            (self.sandbox / "prompts" / "system.md").read_text(encoding="utf-8"),
            "custom-system")
        self.assertEqual(
            (self.sandbox / "config" / "tools.yaml").read_text(encoding="utf-8"),
            "custom-tools")

    def test_apply_auto_mkdir_parent(self):
        """target 父目录不存在 → 自动 mkdir。"""
        text = """files:
  - target: deeply/nested/path/file.md
    source: patches/V2/system.md

start_command: cmd
"""
        patch = self._patch(text)
        apply_patch(patch, self.sandbox)
        self.assertTrue(
            (self.sandbox / "deeply" / "nested" / "path" / "file.md").exists())

    def test_apply_overwrites_existing(self):
        """target 已存在 → 被覆盖。"""
        existing = self.sandbox / "prompts" / "system.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("original-content", encoding="utf-8")
        text = """files:
  - target: prompts/system.md
    source: patches/V2/system.md

start_command: cmd
"""
        patch = self._patch(text)
        apply_patch(patch, self.sandbox)
        self.assertEqual(existing.read_text(encoding="utf-8"), "custom-system")

    def test_apply_missing_source_raises(self):
        """patch source 不存在 → FileNotFoundError。"""
        text = """files:
  - target: prompts/system.md
    source: patches/V2/nonexistent.md

start_command: cmd
"""
        patch = self._patch(text)
        with self.assertRaises(FileNotFoundError) as ctx:
            apply_patch(patch, self.sandbox)
        self.assertIn("patches/V2/nonexistent.md", str(ctx.exception).replace("\\", "/"))

    def test_apply_empty_files_noop(self):
        """patch.files 为空 → 不做事,返空 list。"""
        patch = self._patch("start_command: cmd\n")
        applied = apply_patch(patch, self.sandbox)
        self.assertEqual(applied, [])


class TestParsePatchSourceTraversal(unittest.TestCase):
    """C5 cleanup: source 必须在 experiment root 内,防 path traversal 读取外部文件。

    parse 阶段抓 (ValueError) —— 让 _safe_call 自然翻成 WorkflowError。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp_dir = Path(self._tmp.name) / "exp"
        self.exp_dir.mkdir()
        patches = self.exp_dir / "patches" / "V2"
        patches.mkdir(parents=True)
        (patches / "system.md").write_text("custom", encoding="utf-8")

    def _parse(self, source_path: str):
        text = f"""files:
  - target: prompts/system.md
    source: {source_path}

start_command: cmd
"""
        return parse_patch(text, self.exp_dir)

    def test_source_dotdot_raises(self):
        """source: '../outside.txt' → ValueError 含 '越出 experiment'。"""
        with self.assertRaises(ValueError) as exc:
            self._parse("../outside.txt")
        self.assertIn("越出 experiment", str(exc.exception))

    def test_source_deep_dotdot_raises(self):
        """source: 'patches/../../outside.txt' resolve 后越界 → ValueError。"""
        with self.assertRaises(ValueError) as exc:
            self._parse("patches/../../outside.txt")
        self.assertIn("越出 experiment", str(exc.exception))

    def test_source_absolute_path_raises(self):
        """source 绝对路径(C:/... 或 /etc/...) → ValueError。"""
        import sys as _sys
        target = ("C:/Windows/system32/whatever.txt" if _sys.platform == "win32"
                  else "/etc/passwd")
        with self.assertRaises(ValueError) as exc:
            self._parse(target)
        self.assertIn("越出 experiment", str(exc.exception))

    def test_source_normal_path_ok(self):
        """source: 'patches/V2/system.md' → 解析成功。"""
        patch = self._parse("patches/V2/system.md")
        self.assertEqual(len(patch.files), 1)
        self.assertTrue(patch.files[0].source_path.exists())
        self.assertEqual(
            patch.files[0].source_path,
            (self.exp_dir / "patches" / "V2" / "system.md").resolve())

    def test_source_dotdot_back_into_exp_ok(self):
        """source: 'patches/../patches/V2/system.md' resolve 后还在 exp → OK。"""
        patch = self._parse("patches/../patches/V2/system.md")
        self.assertEqual(len(patch.files), 1)
        self.assertTrue(patch.files[0].source_path.exists())


class TestApplyPatchPathTraversal(unittest.TestCase):
    """C5 review: target_path 越出 sandbox 必须 raise (path traversal 防御)。

    用 Path.resolve() + relative_to() 检测,覆盖 `..` 段 / 绝对路径 / 多层 `..`
    嵌套等多种 traversal 模式。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp_dir = Path(self._tmp.name) / "exp"
        self.exp_dir.mkdir()
        patches = self.exp_dir / "patches" / "V1"
        patches.mkdir(parents=True)
        (patches / "evil.txt").write_text("evil-content", encoding="utf-8")
        self.sandbox = Path(self._tmp.name) / "sandbox"
        self.sandbox.mkdir()

    def _patch_with_target(self, target: str):
        text = f"""files:
  - target: {target}
    source: patches/V1/evil.txt

start_command: cmd
"""
        return parse_patch(text, self.exp_dir)

    def test_traversal_dotdot_raises(self):
        """target_path = '../outside.txt' → RuntimeError 含 '越出 sandbox'。"""
        patch = self._patch_with_target("../outside.txt")
        with self.assertRaises(RuntimeError) as exc:
            apply_patch(patch, self.sandbox)
        self.assertIn("越出 sandbox", str(exc.exception))
        # 原 outside.txt 不应被写
        self.assertFalse((self.sandbox.parent / "outside.txt").exists())

    def test_traversal_deep_dotdot_raises(self):
        """target_path = 'subdir/../../outside.txt' → resolve 后越界 → RuntimeError。"""
        patch = self._patch_with_target("subdir/../../outside.txt")
        with self.assertRaises(RuntimeError) as exc:
            apply_patch(patch, self.sandbox)
        self.assertIn("越出 sandbox", str(exc.exception))

    def test_absolute_path_raises(self):
        """target_path 是绝对路径 → resolve 后不在 sandbox 内 → RuntimeError。"""
        import sys as _sys
        target = ("C:/Windows/system32/whatever.txt" if _sys.platform == "win32"
                  else "/etc/passwd")
        patch = self._patch_with_target(target)
        with self.assertRaises(RuntimeError) as exc:
            apply_patch(patch, self.sandbox)
        self.assertIn("越出 sandbox", str(exc.exception))

    def test_nested_relative_path_ok(self):
        """正常 nested path (sub/dir/file.txt) → apply 成功,父目录自动 mkdir。"""
        patch = self._patch_with_target("sub/dir/file.txt")
        applied = apply_patch(patch, self.sandbox)
        self.assertEqual(len(applied), 1)
        self.assertTrue((self.sandbox / "sub" / "dir" / "file.txt").exists())
        self.assertEqual(
            (self.sandbox / "sub" / "dir" / "file.txt").read_text(encoding="utf-8"),
            "evil-content")

    def test_dotdot_then_back_into_sandbox_ok(self):
        """target_path = 'a/../b.txt' resolve 后是 sandbox/b.txt (没越界) → OK。"""
        patch = self._patch_with_target("a/../b.txt")
        applied = apply_patch(patch, self.sandbox)
        self.assertEqual(len(applied), 1)
        self.assertTrue((self.sandbox / "b.txt").exists())


class TestComputePatchHash(unittest.TestCase):
    """C5: compute_patch_hash 是 deterministic + 各输入都影响 hash。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp_dir = Path(self._tmp.name)
        patches = self.exp_dir / "patches" / "V2"
        patches.mkdir(parents=True)
        (patches / "system.md").write_text("custom-system", encoding="utf-8")

    def _make_patch(self, env=None, start_command="cmd", with_file=True):
        if with_file:
            text = f"""files:
  - target: prompts/system.md
    source: patches/V2/system.md

env:
{chr(10).join(f"  {k}: \"{v}\"" for k, v in (env or {}).items())}

start_command: {start_command}
"""
        else:
            text = f"""env:
{chr(10).join(f"  {k}: \"{v}\"" for k, v in (env or {}).items())}

start_command: {start_command}
"""
        return parse_patch(text, self.exp_dir)

    def test_hash_deterministic(self):
        """同样 patch 两次算 → 同样 hash。"""
        p1 = self._make_patch(env={"X": "1"})
        p2 = self._make_patch(env={"X": "1"})
        self.assertEqual(compute_patch_hash(p1), compute_patch_hash(p2))

    def test_hash_changes_with_env(self):
        """env 改 → hash 变。"""
        h1 = compute_patch_hash(self._make_patch(env={"X": "1"}))
        h2 = compute_patch_hash(self._make_patch(env={"X": "2"}))
        self.assertNotEqual(h1, h2)

    def test_hash_changes_with_start_command(self):
        """start_command 改 → hash 变。"""
        h1 = compute_patch_hash(self._make_patch(start_command="cmd-a"))
        h2 = compute_patch_hash(self._make_patch(start_command="cmd-b"))
        self.assertNotEqual(h1, h2)

    def test_hash_changes_with_file_content(self):
        """patch file 内容改 → patch_hash 变 (经 PatchFile.hash 链路)。"""
        h1 = compute_patch_hash(self._make_patch())
        (self.exp_dir / "patches" / "V2" / "system.md").write_text(
            "changed", encoding="utf-8")
        h2 = compute_patch_hash(self._make_patch())
        self.assertNotEqual(h1, h2)

    def test_hash_independent_of_env_dict_order(self):
        """env key 顺序不影响 hash (sort_keys=True)。"""
        h1 = compute_patch_hash(self._make_patch(env={"A": "1", "B": "2"}))
        h2 = compute_patch_hash(self._make_patch(env={"B": "2", "A": "1"}))
        self.assertEqual(h1, h2)

    def test_hash_format(self):
        """hash 格式: sha256:<64 hex>。"""
        h = compute_patch_hash(self._make_patch())
        self.assertTrue(h.startswith("sha256:"))
        self.assertEqual(len(h), len("sha256:") + 64)

    def test_hash_empty_patch(self):
        """空 patch (无 files, 无 env, 无 start_command) 也能算出 hash。"""
        p = HarnessPatch()  # 全空 dataclass
        h = compute_patch_hash(p)
        self.assertTrue(h.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
