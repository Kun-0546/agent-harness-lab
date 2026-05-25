"""Step 2 M2: ahl draft 已合并到 ahl new --mode copilot。

v0.3.1 Step 2 后:cmd_draft 作为 friendly redirect 保留(跟 cmd_versions_legacy_redirect
套路一致):
- exit 1 (非 0)
- 不创建任何实验目录或文件
- stderr 给明确迁移指引 (指向 ahl new --mode copilot)
- ahl --help 不展示 draft (从 sub._choices_actions 移除)
"""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import cli


def _run_draft(tmp_root: Path, name: str | None = "demo") -> tuple[int, str, str]:
    """在 tmp_root 跑 cli.main(['draft', name]),返回 (rc, stdout, stderr)。"""
    orig_cwd = Path.cwd()
    os.chdir(tmp_root)
    try:
        args = ["draft"]
        if name is not None:
            args.append(name)
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), \
             contextlib.redirect_stderr(err_buf):
            rc = cli.main(args)
        return rc, out_buf.getvalue(), err_buf.getvalue()
    finally:
        os.chdir(orig_cwd)


class TestCmdDraftRedirect(unittest.TestCase):

    def test_prints_redirect_to_new_mode_copilot(self):
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            (root_p / "experiments").mkdir()
            _, _, err = _run_draft(root_p, "demo")
            # stderr 指向 ahl new --mode copilot
            self.assertIn("ahl new", err)
            self.assertIn("--mode copilot", err)
            # 不应含"已建好"类成功语
            self.assertNotIn("建好实验", err)

    def test_exits_nonzero_and_creates_nothing(self):
        """M2 核心契约:draft 不创建任何实验目录,exit 1。"""
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            (root_p / "experiments").mkdir()
            rc, _, _ = _run_draft(root_p, "demo")
            self.assertEqual(rc, 1, f"draft 应 exit 1,实际 {rc}")
            # experiments/ 下没有任何新目录
            entries = list((root_p / "experiments").iterdir())
            self.assertEqual(entries, [],
                             f"draft 不应创建任何目录,实际:{entries}")
            # cwd 也没有新文件 (排除 experiments/)
            cwd_entries = [
                p for p in root_p.iterdir() if p.name != "experiments"
            ]
            self.assertEqual(cwd_entries, [],
                             f"draft 不应在 cwd 创建文件,实际:{cwd_entries}")

    def test_mentions_walkthrough_for_setup_mode_doc(self):
        """提示应指向 walkthrough / product-walkthrough.md 让用户看 setup mode 说明。"""
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            (root_p / "experiments").mkdir()
            _, _, err = _run_draft(root_p, "demo")
            self.assertTrue(
                "walkthrough" in err.lower()
                or "product-walkthrough.md" in err,
                f"draft 提示应指向 walkthrough/product-walkthrough.md;实际:{err!r}")


if __name__ == "__main__":
    unittest.main()
