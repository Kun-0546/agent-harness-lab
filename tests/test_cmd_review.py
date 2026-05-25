"""Step 2 Round-3 blocker fix: cmd_review 提示契约。

v0.3.1 Step 2 Round 3:cmd_review stdout 在"不齐了"分支必须引导用户去
docs/product-walkthrough.md 和 docs/file-formats.md(当前 setup mode flow),
不再引 docs/agent-authoring-guide.md(旧心智:brief=human-owned / ahl draft 入口 /
v2-minimal-spec 必读)。
"""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import cli


def _setup_incomplete_experiment(root: Path, name: str = "demo") -> Path:
    """造一个 incomplete 实验:只有 brief.md 占位符。其他文件全缺,
    review 必触发 missing/warnings,走"不齐了"提示分支。"""
    (root / "experiments").mkdir()
    exp = root / "experiments" / f"001-{name}"
    exp.mkdir()
    (exp / "brief.md").write_text(
        "# brief\n\n## 想优化什么\n<占位符>\n\n## 验证什么改动\n<占位符>\n"
        "\n## 最在意什么\n<占位符>\n\n## 不能牺牲什么\n<占位符>\n"
        "\n## 怎么比\n<占位符>\n",
        encoding="utf-8")
    (exp / "harnesses").mkdir()
    (exp / "cases").mkdir()
    return exp


def _run_review(root: Path, name: str = "demo") -> tuple[int, str, str]:
    """在 root 跑 cli.main(['review', name]),返回 (rc, stdout, stderr)。"""
    orig_cwd = Path.cwd()
    os.chdir(root)
    try:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), \
             contextlib.redirect_stderr(err_buf):
            rc = cli.main(["review", name])
        return rc, out_buf.getvalue(), err_buf.getvalue()
    finally:
        os.chdir(orig_cwd)


class TestCmdReviewIncompleteHint(unittest.TestCase):
    """cmd_review 不齐了分支的产品文档引用契约。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _setup_incomplete_experiment(self.root)
        self.rc, self.stdout, _ = _run_review(self.root)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_review_succeeds(self):
        """review 是宽松命令,不齐了也不报错。"""
        self.assertEqual(self.rc, 0)

    def test_triggers_incomplete_branch(self):
        """前置条件:测试 setup 让 review 真的进入"不齐了"分支
        (有 missing / broken / skipped / warnings 之一)。"""
        self.assertNotIn("齐了", self.stdout,
                         "前置条件:review 应进入'不齐了'分支才能测后续断言")

    def test_does_not_mention_agent_authoring_guide(self):
        """v0.3.1 Step 2 红线:不再引 docs/agent-authoring-guide.md
        (它仍是旧心智,跟 Step 2 当前 setup mode flow 冲突)。"""
        self.assertNotIn(
            "agent-authoring-guide", self.stdout,
            f"review 提示不应再引 agent-authoring-guide.md;实际 stdout:{self.stdout!r}")

    def test_mentions_product_walkthrough_doc(self):
        """v0.3.1 Step 2:review 提示应引导用户去当前 setup mode flow 文档。"""
        self.assertIn(
            "docs/product-walkthrough.md", self.stdout,
            f"review 提示应引 docs/product-walkthrough.md;实际:{self.stdout!r}")

    def test_mentions_file_formats_or_materials(self):
        """review 提示应引 file-formats.md 或 materials/(具体文件格式 /
        协作目录),让 coding agent 知道往哪看。"""
        self.assertTrue(
            "docs/file-formats.md" in self.stdout
            or "materials" in self.stdout,
            f"review 提示应引 file-formats.md 或 materials/;"
            f"实际:{self.stdout!r}")


if __name__ == "__main__":
    unittest.main()
