"""Step 0: ahl init 行为契约。

v0.3.1 Product Surface Cleanup 后:
- init 产物只含 goal.md + experiments/
- 不创建 connect.md (legacy 主入口降级,留 Step 3 选 runtime 时手工建)
- 不创建 calibration/golden/ (留 Step 8+ Inspect evidence)
- stdout 引导用户进 9 步流程,goal.md 是 Step 1,connect.md 只在 Step 3 作为 legacy 选项
"""
import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_harness_lab.cli import cmd_init


def _run_init_in(tmp_root: Path) -> str:
    """在 tmp_root 跑 cmd_init,返回抓到的 stdout。"""
    orig_cwd = Path.cwd()
    os.chdir(tmp_root)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_init(argparse.Namespace())
        assert rc == 0, f"cmd_init returned {rc}"
        return buf.getvalue()
    finally:
        os.chdir(orig_cwd)


class TestCmdInitFiles(unittest.TestCase):
    """Step 0 产品契约:产物只含 goal.md + experiments/。"""

    def test_creates_only_goal_and_experiments(self):
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            _run_init_in(root_p)
            self.assertTrue((root_p / "goal.md").exists(),
                            "init 必须创建 goal.md")
            self.assertTrue((root_p / "experiments").is_dir(),
                            "init 必须创建 experiments/")
            self.assertFalse((root_p / "connect.md").exists(),
                             "init 不应创建 connect.md (legacy 主入口降级)")
            self.assertFalse((root_p / "calibration").exists(),
                             "init 不应创建 calibration/ (留到 Step 8+)")

    def test_idempotent_skips_existing(self):
        with tempfile.TemporaryDirectory() as root:
            root_p = Path(root)
            _run_init_in(root_p)
            content_first = (root_p / "goal.md").read_text(encoding="utf-8")
            # 改 goal.md 后再跑 init,内容不应被覆盖
            (root_p / "goal.md").write_text("USER EDITED",
                                            encoding="utf-8")
            _run_init_in(root_p)
            self.assertEqual((root_p / "goal.md").read_text(encoding="utf-8"),
                             "USER EDITED",
                             "init 不应覆盖已存在的 goal.md")
            # 第一次的内容跟模板一致
            self.assertNotEqual(content_first, "USER EDITED")


class TestCmdInitGoalTemplate(unittest.TestCase):
    """Step 1 产品契约:goal.md 含 6 段引导 + 8 个 harness 层复选框。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _run_init_in(self.root)
        self.goal_content = (self.root / "goal.md").read_text(encoding="utf-8")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_six_sections_present(self):
        """6 段引导都在,顺序正确。"""
        sections = (
            "## 1. 目标 agent",
            "## 2. 想改善的行为",
            "## 3. 当前 baseline",
            "## 4. Harness 层假设",
            "## 5. 成功标准",
            "## 6. 不能牺牲的红线",
        )
        last_idx = -1
        for section in sections:
            idx = self.goal_content.find(section)
            self.assertNotEqual(idx, -1,
                                f"goal.md 应包含段落:{section}")
            self.assertGreater(idx, last_idx,
                               f"段落顺序错乱:{section} 应在前一段之后")
            last_idx = idx

    def test_harness_layer_checkboxes_present(self):
        """§4 含 8 个 harness 层复选框,把 harness 一等对象产品化。"""
        for layer in (
            "system prompt",
            "workflow",
            "tool configuration",
            "memory",
            "context packaging",
            "output format",
            "guardrails",
            "other",
        ):
            self.assertIn(layer, self.goal_content,
                          f"§4 应包含 harness 层关键词:{layer}")
        # 至少含 8 个 markdown 复选框
        self.assertGreaterEqual(self.goal_content.count("- [ ]"), 8,
                                "§4 应含至少 8 个 - [ ] 复选框")

    def test_explains_goal_vs_brief_boundary(self):
        """顶部说明 goal.md = workspace-level,brief.md = experiment-level。"""
        self.assertIn("workspace", self.goal_content.lower())
        self.assertIn("brief.md", self.goal_content)


class TestCmdInitOutput(unittest.TestCase):
    """init stdout 必须引导进 9 步流程,不再把 connect.md 当首要 step。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.stdout = _run_init_in(self.root)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_mentions_walkthrough_and_product_doc(self):
        self.assertIn("ahl walkthrough", self.stdout)
        self.assertIn("docs/product-walkthrough.md", self.stdout)

    def test_mentions_step_flow(self):
        for step in ("Step 1", "Step 2", "Step 3"):
            self.assertIn(step, self.stdout)
        self.assertIn("goal.md", self.stdout)

    def test_does_not_make_connect_the_first_step(self):
        """legacy 心智清理红线:Step 1 必须是 goal.md,connect.md 只在 Step 3 作为 legacy 选项。"""
        step1_idx = self.stdout.find("Step 1")
        step3_idx = self.stdout.find("Step 3")
        self.assertGreater(step1_idx, -1)
        self.assertGreater(step3_idx, step1_idx)
        # Step 1 段(到 Step 2)不应提 connect.md
        step2_idx = self.stdout.find("Step 2")
        step1_segment = self.stdout[step1_idx:step2_idx]
        self.assertNotIn("connect.md", step1_segment,
                         "Step 1 段不应再引导用户先填 connect.md")
        # goal.md 应早于 connect.md 出现(产品默认心智)
        goal_idx = self.stdout.find("goal.md")
        connect_idx = self.stdout.find("connect.md")
        self.assertGreater(goal_idx, -1)
        self.assertGreater(connect_idx, -1)
        self.assertLess(goal_idx, connect_idx,
                        "goal.md 必须在 connect.md 之前提及")


if __name__ == "__main__":
    unittest.main()
