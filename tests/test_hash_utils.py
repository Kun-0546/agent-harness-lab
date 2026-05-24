"""hash_utils:source_dir_hash 算法测试 —— 必须 reproducible + ignore 生效。"""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.hash_utils import compute_dir_hash


class TestComputeDirHash(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write(self, rel: str, content: str = "hello"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def test_empty_dir_hash(self):
        """空 dir → sha256:<64 hex>。"""
        h = compute_dir_hash(self.root)
        self.assertTrue(h.startswith("sha256:"))
        self.assertEqual(len(h), len("sha256:") + 64)

    def test_same_content_same_hash(self):
        """同样 content → 同样 hash (reproducible)。"""
        self._write("a.txt", "hello")
        self._write("dir/b.py", "print(1)")
        h1 = compute_dir_hash(self.root)
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)

    def test_content_change_changes_hash(self):
        """文件内容改 → hash 变。"""
        self._write("a.txt", "hello")
        h1 = compute_dir_hash(self.root)
        self._write("a.txt", "world")
        h2 = compute_dir_hash(self.root)
        self.assertNotEqual(h1, h2)

    def test_new_file_changes_hash(self):
        """加新文件 → hash 变。"""
        self._write("a.txt", "hello")
        h1 = compute_dir_hash(self.root)
        self._write("b.txt", "world")
        h2 = compute_dir_hash(self.root)
        self.assertNotEqual(h1, h2)

    def test_rename_file_changes_hash(self):
        """文件改名 → hash 变 (path 算入)。"""
        self._write("a.txt", "hello")
        h1 = compute_dir_hash(self.root)
        (self.root / "a.txt").rename(self.root / "b.txt")
        h2 = compute_dir_hash(self.root)
        self.assertNotEqual(h1, h2)

    def test_ignore_git_dir(self):
        """.git 目录被忽略 → 加 .git 内容不影响 hash。"""
        self._write("a.txt", "hello")
        h1 = compute_dir_hash(self.root)
        self._write(".git/HEAD", "ref: refs/heads/main")
        self._write(".git/index", "blob")
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)

    def test_ignore_pycache_dir(self):
        """__pycache__ 忽略。"""
        self._write("a.py", "x=1")
        h1 = compute_dir_hash(self.root)
        self._write("__pycache__/a.cpython.pyc", "bytecode")
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)

    def test_ignore_pyc_suffix(self):
        """.pyc 后缀忽略 (即便不在 __pycache__)。"""
        self._write("a.py", "x=1")
        h1 = compute_dir_hash(self.root)
        self._write("orphan.pyc", "bytecode")
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)

    def test_ignore_ds_store(self):
        """.DS_Store 忽略。"""
        self._write("a.txt", "hello")
        h1 = compute_dir_hash(self.root)
        self._write(".DS_Store", "macos cruft")
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)

    def test_ignore_venv_dir(self):
        """.venv 目录忽略。"""
        self._write("a.txt", "hello")
        h1 = compute_dir_hash(self.root)
        self._write(".venv/bin/python", "shim")
        self._write(".venv/lib/site-packages/foo.py", "import bar")
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)

    def test_ignore_node_modules(self):
        """node_modules 忽略。"""
        self._write("index.js", "console.log(1)")
        h1 = compute_dir_hash(self.root)
        self._write("node_modules/foo/package.json", "{}")
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)

    def test_missing_dir_raises(self):
        """source dir 不存在 → FileNotFoundError。"""
        with self.assertRaises(FileNotFoundError):
            compute_dir_hash(self.root / "missing")

    def test_nested_dirs(self):
        """深层嵌套 dir 内容算入。"""
        self._write("a/b/c/deep.txt", "deep content")
        h1 = compute_dir_hash(self.root)
        self._write("a/b/c/deep.txt", "changed")
        h2 = compute_dir_hash(self.root)
        self.assertNotEqual(h1, h2)

    def test_hash_independent_of_filesystem_order(self):
        """sorted 保证 hash 跟创建顺序无关。"""
        self._write("z.txt", "z")
        self._write("a.txt", "a")
        h1 = compute_dir_hash(self.root)
        # 删后反序重建
        (self.root / "z.txt").unlink()
        (self.root / "a.txt").unlink()
        self._write("a.txt", "a")
        self._write("z.txt", "z")
        h2 = compute_dir_hash(self.root)
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
