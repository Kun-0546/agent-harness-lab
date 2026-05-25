"""Step 0.5: ahl walkthrough 输出契约 + docs/product-walkthrough.md 存在性。

walkthrough 是 v0.3.1 新增的产品流程入口。契约:
- 输出 9 步流程(Step 1 Define goal → Step 9 Decide next iteration)
- 含三种模式(Manual / Co-pilot / Auto future)
- 含三种 runtime(local_path / git_repo / legacy)
- 引用的 docs/product-walkthrough.md 必须真实存在
  (CLI 不能引用不存在的文档 —— 产品文档断裂红线)
"""
import argparse
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_harness_lab.cli import cmd_walkthrough


def _run_walkthrough() -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_walkthrough(argparse.Namespace())
    assert rc == 0
    return buf.getvalue()


class TestWalkthroughOutput(unittest.TestCase):
    """walkthrough CLI 输出契约。"""

    def setUp(self):
        self.stdout = _run_walkthrough()

    def test_lists_all_nine_steps(self):
        for label in (
            "Step 1", "Step 2", "Step 3", "Step 4", "Step 5",
            "Step 6", "Step 7", "Step 8", "Step 9",
        ):
            self.assertIn(label, self.stdout,
                          f"walkthrough 应含 {label}")
        for name in (
            "Define goal",
            "Choose setup mode",  # v0.3.1 Step 2: 改名标 setup mode
            "Declare runtime",
            "Create experiment",
            "Design harness variants",
            "Prepare cases and rubric",
            "Run experiment",
            "Inspect evidence",
            "Decide next iteration",
        ):
            self.assertIn(name, self.stdout,
                          f"walkthrough 应含步骤名:{name}")

    def test_mentions_three_modes(self):
        for mode in ("Manual", "Co-pilot", "Auto"):
            self.assertIn(mode, self.stdout)
        # Auto 应标 future / 未来 / M2,表示未实现
        auto_idx = self.stdout.find("Auto")
        auto_context = self.stdout[auto_idx:auto_idx + 200]
        self.assertTrue(
            any(token in auto_context
                for token in ("future", "未来", "M2")),
            f"Auto 段应注明 future/未来/M2;实际:{auto_context!r}",
        )

    def test_mentions_three_runtime_options(self):
        for runtime in ("local_path", "git_repo", "legacy"):
            self.assertIn(runtime, self.stdout,
                          f"Step 3 应含 runtime 类型:{runtime}")

    def test_does_not_mention_ahl_draft(self):
        """v0.3.1 Step 2: ahl draft 已合并到 ahl new --mode copilot,
        walkthrough 不应再出现 ahl draft 命令。"""
        self.assertNotIn("ahl draft", self.stdout,
                         "walkthrough 不应再展示 ahl draft (已合并到 ahl new --mode copilot)")

    def test_mentions_setup_mode_flags(self):
        """v0.3.1 Step 2: walkthrough Step 4 必须展示 --mode flag (非默认值)。
        copilot 是默认,不必带 --mode;walkthrough 应明示它是默认 (避免读者
        以为不写 --mode 会报错)。"""
        # copilot 是默认 —— 应在 walkthrough 标"默认"或 "default"
        self.assertTrue(
            "默认" in self.stdout or "default" in self.stdout.lower(),
            "walkthrough 应说明 copilot 是默认 setup mode")
        # manual / auto 必须以 --mode flag 形式出现
        for flag in ("--mode manual", "--mode auto"):
            self.assertIn(flag, self.stdout,
                          f"walkthrough Step 4 应含 setup mode flag:{flag}")

    def test_copilot_described_as_guided_setup(self):
        """v0.3.1 Step 2 Co-pilot 新定义:AI 引导式配置 / 通过对话维护
        brief.md 和 materials/,不再是被动'起草,你审核'。"""
        # 找到 Co-pilot 或 copilot 描述段 (大小写不敏感)
        lower = self.stdout.lower()
        copilot_idx = lower.find("copilot")
        self.assertGreater(copilot_idx, -1, "walkthrough 应提到 copilot")
        # 取 copilot 之后 400 字符作为描述上下文
        ctx = self.stdout[copilot_idx:copilot_idx + 400]
        # 应含"引导"或"guided"或"配置"或"协作"或"对话"之一的协作语义
        self.assertTrue(
            any(kw in ctx for kw in ("引导", "guided", "协作", "对话")),
            f"Co-pilot 应描述为引导式 / guided / 协作 / 通过对话;"
            f"实际描述:{ctx!r}",
        )
        # 应提到 brief.md 和 materials/(维护对象)
        self.assertTrue("brief" in ctx.lower(),
                        f"Co-pilot 描述应提 brief.md;实际:{ctx!r}")
        self.assertTrue("materials" in ctx.lower(),
                        f"Co-pilot 描述应提 materials/;实际:{ctx!r}")

    def test_step_3_mentions_runtime_boundary_and_evidence(self):
        """v0.3.1 Step 3:walkthrough Step 3 必须含 boundary + evidence 评级。
        不再只是 'Declare runtime',而是 'Declare runtime boundary and
        evidence level',并标 strong/medium/weak。"""
        step_3_idx = self.stdout.find("Step 3")
        step_4_idx = self.stdout.find("Step 4")
        self.assertGreater(step_3_idx, -1)
        self.assertGreater(step_4_idx, step_3_idx)
        step_3_seg = self.stdout[step_3_idx:step_4_idx]
        # 含 boundary 概念
        self.assertIn("boundary", step_3_seg.lower(),
                      f"Step 3 应含 'boundary' 概念;实际:{step_3_seg!r}")
        # 含 evidence 强度评级 (任一关键词)
        self.assertTrue(
            any(kw in step_3_seg.lower()
                for kw in ("evidence", "strong", "weak")),
            f"Step 3 应含 evidence/strong/weak 评级概念;"
            f"实际:{step_3_seg!r}")

    def test_step_3_mentions_2x2_matrix_concept(self):
        """v0.3.1 Step 3:walkthrough Step 3 应反映 agent location × harness
        location 2×2 矩阵心智 (至少出现 Local 或 Cloud 维度,或 2×2 字眼)。"""
        step_3_idx = self.stdout.find("Step 3")
        step_4_idx = self.stdout.find("Step 4")
        step_3_seg = self.stdout[step_3_idx:step_4_idx]
        self.assertTrue(
            "2×2" in step_3_seg or "Local" in step_3_seg
            or "Cloud" in step_3_seg,
            f"Step 3 应反映 2×2 矩阵心智 (local/cloud 维度或 2×2 字眼);"
            f"实际:{step_3_seg!r}")

    def test_step_3_mentions_evidence_files_or_materials(self):
        """v0.3.1 Step 3:walkthrough Step 3 应让用户知道 evidence 文件
        在 materials/ 下整理 (按需,Co-pilot 主路径)。"""
        step_3_idx = self.stdout.find("Step 3")
        step_4_idx = self.stdout.find("Step 4")
        step_3_seg = self.stdout[step_3_idx:step_4_idx]
        # 应提到 materials/ 作为 evidence 位置
        self.assertIn(
            "materials", step_3_seg.lower(),
            f"Step 3 应提及 materials/ 作为 evidence 位置;"
            f"实际:{step_3_seg!r}")


class TestWalkthroughDocExistence(unittest.TestCase):
    """red-line:CLI 引用的 docs/product-walkthrough.md 必须真实存在,
    否则用户跟着提示去找会扑空。"""

    def test_references_product_walkthrough_doc(self):
        stdout = _run_walkthrough()
        self.assertIn("docs/product-walkthrough.md", stdout)

    def test_product_walkthrough_doc_file_exists(self):
        repo_root = Path(__file__).resolve().parent.parent
        doc_path = repo_root / "docs" / "product-walkthrough.md"
        self.assertTrue(doc_path.exists(),
                        f"docs/product-walkthrough.md 必须存在;路径:{doc_path}")
        # 不能是空文件
        self.assertGreater(doc_path.stat().st_size, 100,
                           "product-walkthrough.md 不应是空文件")


if __name__ == "__main__":
    unittest.main()
