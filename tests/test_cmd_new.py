"""Step 2: ahl new 三种 setup mode 的行为契约。

v0.3.1 Step 2 后:ahl new 统一入口,通过 --mode 选 experiment setup mode。
- copilot (默认): brief.md + materials/README.md + cases/ + harnesses/
- manual: program.md + rubric.md + simulator.md + cases/ + harnesses/
- auto: 不创建任何文件,exit 2,stderr 报 not implemented

setup mode 只决定 ahl new 建什么结构;不影响 run/score/compare;
不写元数据到实验目录。
"""
import argparse
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import cli


def _run_new(tmp_root: Path, name: str, mode: str | None = None) -> tuple[int, str, str]:
    """在 tmp_root 跑 cli.main(['new', name, ...]),返回 (rc, stdout, stderr)。"""
    orig_cwd = Path.cwd()
    os.chdir(tmp_root)
    try:
        args = ["new", name]
        if mode is not None:
            args.extend(["--mode", mode])
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), \
             contextlib.redirect_stderr(err_buf):
            rc = cli.main(args)
        return rc, out_buf.getvalue(), err_buf.getvalue()
    finally:
        os.chdir(orig_cwd)


def _setup_workspace(tmp_root: Path) -> None:
    """ahl init 等价 setup —— 创建 experiments/ 目录。"""
    (tmp_root / "experiments").mkdir(exist_ok=True)


class TestCmdNewDefaultMode(unittest.TestCase):
    """不带 --mode 时默认 copilot。"""

    def test_no_mode_defaults_to_copilot(self):
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            _setup_workspace(root_p)
            rc, out, _ = _run_new(root_p, "demo")
            self.assertEqual(rc, 0)
            exp = root_p / "experiments" / "001-demo"
            # 产物 = copilot 产物
            self.assertTrue((exp / "brief.md").exists())
            self.assertTrue((exp / "materials" / "README.md").exists())
            # stdout 含 setup mode 标识
            self.assertIn("setup mode=copilot", out)


class TestCmdNewCopilot(unittest.TestCase):
    """copilot 模式产物契约。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _setup_workspace(self.root)
        self.rc, self.stdout, _ = _run_new(self.root, "demo", "copilot")
        self.exp = self.root / "experiments" / "001-demo"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_exits_zero(self):
        self.assertEqual(self.rc, 0)

    def test_creates_brief_and_materials_readme_and_dirs(self):
        self.assertTrue((self.exp / "brief.md").exists())
        self.assertTrue((self.exp / "materials" / "README.md").exists())
        self.assertTrue((self.exp / "cases").is_dir())
        self.assertTrue((self.exp / "harnesses").is_dir())

    def test_does_not_create_manual_files_or_locked(self):
        """M5: copilot 默认不创建 materials/locked.md;不创建 manual 骨架。"""
        self.assertFalse((self.exp / "program.md").exists())
        self.assertFalse((self.exp / "rubric.md").exists())
        self.assertFalse((self.exp / "simulator.md").exists())
        self.assertFalse((self.exp / "materials" / "locked.md").exists())

    def test_brief_md_uses_copilot_experiment_setup_title(self):
        """修正 3: brief.md 标题是 'Brief — Co-pilot Experiment Setup',
        不是 '# brief — <name>'。"""
        content = (self.exp / "brief.md").read_text(encoding="utf-8")
        self.assertIn("# Brief — Co-pilot Experiment Setup", content)

    def test_brief_md_has_12_section_anchors(self):
        """v0.9 Co-pilot Setup Productization: BRIEF_TEMPLATE 12 节 H2
        锚点必须全在且无后缀。section keys = split_sections 直接产物;
        任何后缀(如 '(必填)')会破坏 parse_brief。"""
        content = (self.exp / "brief.md").read_text(encoding="utf-8")
        # v0.9 12 节 H2 锚点
        for key in (
            "想优化什么",
            "目标行为",
            "当前问题",
            "Runtime 信息",
            "Harness 假设",
            "Cases 要覆盖什么",
            "Rubric 应该如何判断",
            "Evidence / probe expectations",
            "Files the coding agent may create",
            "Files the coding agent should not change",
            "Acceptance commands",
            "Done criteria",
        ):
            self.assertIn(f"## {key}\n", content,
                          f"BRIEF_TEMPLATE 必须含精确标题 '## {key}\\n';"
                          f"任何后缀(如 '(必填)')会破坏 parse_brief")
        # §1 反向断言:不应再有 "## 想优化什么 (必填)"
        self.assertNotIn("## 想优化什么 (必填)", content,
                         "Blocker fix:'(必填)' 不能放在 H2 标题里")
        # "必填" 提示应在 §1 正文里(任意形式)
        self.assertIn("必填", content,
                      "§1 应有'必填'提示在正文里")

    def test_brief_template_parseable_by_parse_brief(self):
        """集成测试:用 BRIEF_TEMPLATE 写文件,parse_brief 必须能识别
        v0.9 12-section 模板。compat 路径见 brief.parse_brief docstring。

        v0.9 12 sections 不再保留 "怎么比" anchor,因此 compare 段允许空
        (validate() 仅检查 §1「想优化什么」)。"""
        from agent_harness_lab.brief import parse_brief
        brief_path = self.exp / "brief.md"
        b = parse_brief(brief_path)
        # optimize / change / care / redlines 都应该读到 placeholder
        self.assertNotEqual(b.optimize, "",
                            "parse_brief 应读到 optimize 段(说明 H2 标题匹配)")
        self.assertNotEqual(b.change, "",
                            "parse_brief 应读到 change 段(v0.9: Harness 假设)")
        self.assertNotEqual(b.care, "",
                            "parse_brief 应读到 care 段(v0.9: Rubric 应该如何判断)")
        self.assertNotEqual(b.redlines, "",
                            "parse_brief 应读到 redlines 段(v0.9: "
                            "Files the coding agent should not change)")
        # §1 是 placeholder → is_filled 应为 False → validate 应报 §1 缺失
        problems = b.validate()
        self.assertTrue(
            any("想优化什么" in p for p in problems),
            f"BRIEF_TEMPLATE 默认 §1 是占位符,validate 应报缺失;"
            f"实际 problems:{problems}",
        )

    def test_materials_readme_mentions_locked_convention(self):
        """materials/README.md 解释 locked.md 约定,但不强制 / 不默认创建。"""
        content = (self.exp / "materials" / "README.md").read_text(
            encoding="utf-8")
        self.assertIn("locked.md", content)
        # 应说明是 "产品约定" 而非强制
        self.assertTrue("约定" in content or "convention" in content.lower(),
                        "materials/README.md 应说明 locked.md 是产品约定")

    def test_materials_readme_mentions_evidence_concept(self):
        """v0.3.1 Step 3 + v0.9 §6 Evidence files: materials/README.md 应含
        evidence 概念,提及具体 evidence 文件名 (runtime-evidence /
        harness-evidence / cloud-evidence 之一)。v0.9 还应 cross-link 到
        docs/evidence-guide.md。"""
        content = (self.exp / "materials" / "README.md").read_text(
            encoding="utf-8")
        # 含 evidence 概念
        self.assertIn("evidence", content.lower(),
                      "materials/README.md 应含 evidence 概念 (Step 3)")
        # 含至少一个具体 evidence 文件名
        self.assertTrue(
            any(name in content
                for name in ("runtime-evidence", "harness-evidence",
                             "cloud-evidence")),
            "materials/README.md 应提及 runtime-evidence / "
            "harness-evidence / cloud-evidence 之一作为按需文件")
        # v0.9: cross-link 到 evidence-guide.md(不重复 evidence-guide 内容)
        self.assertIn("evidence-guide", content,
                      "v0.9 materials/README.md 应 cross-link 到 "
                      "docs/evidence-guide.md")

    def test_stdout_mentions_setup_mode(self):
        self.assertIn("setup mode=copilot", self.stdout)


class TestCmdNewManual(unittest.TestCase):
    """manual 模式产物契约 = 当前完整骨架行为。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _setup_workspace(self.root)
        self.rc, self.stdout, _ = _run_new(self.root, "demo", "manual")
        self.exp = self.root / "experiments" / "001-demo"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_exits_zero(self):
        self.assertEqual(self.rc, 0)

    def test_creates_full_skeleton(self):
        self.assertTrue((self.exp / "program.md").exists())
        self.assertTrue((self.exp / "rubric.md").exists())
        self.assertTrue((self.exp / "simulator.md").exists())
        self.assertTrue((self.exp / "cases").is_dir())
        self.assertTrue((self.exp / "harnesses").is_dir())

    def test_does_not_create_brief_or_materials(self):
        self.assertFalse((self.exp / "brief.md").exists())
        self.assertFalse((self.exp / "materials").exists())

    def test_stdout_mentions_setup_mode(self):
        self.assertIn("setup mode=manual", self.stdout)


class TestCmdNewAuto(unittest.TestCase):
    """M3: auto mode 不创建任何文件,exit 2。"""

    def test_returns_exit_2_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            _setup_workspace(root_p)
            rc, out, err = _run_new(root_p, "demo", "auto")
            self.assertEqual(rc, 2, f"auto 应 exit 2,实际 {rc}")
            # experiments/ 下没有任何新目录
            entries = list((root_p / "experiments").iterdir())
            self.assertEqual(entries, [],
                             f"auto 不应创建任何实验目录,实际:{entries}")
            # stderr 提到 not implemented / M2
            self.assertTrue(
                "not implemented" in err.lower() or "未实现" in err
                or "M2" in err,
                f"auto stderr 应含 not implemented / 未实现 / M2;实际:{err!r}")
            # stdout 应该是空(只 stderr 输出)
            self.assertEqual(out, "")


class TestCmdNewErrorCases(unittest.TestCase):
    """重名 + 无效 mode 的错误处理。"""

    def test_invalid_mode_rejected_by_argparse(self):
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            _setup_workspace(root_p)
            orig_cwd = Path.cwd()
            os.chdir(root_p)
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    # argparse 的 choices 校验失败会 SystemExit(2)
                    with self.assertRaises(SystemExit) as ctx:
                        cli.main(["new", "demo", "--mode", "foo"])
                    self.assertEqual(ctx.exception.code, 2)
            finally:
                os.chdir(orig_cwd)


if __name__ == "__main__":
    unittest.main()
