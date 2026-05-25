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
            "Choose mode",
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
