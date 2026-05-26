"""v0.9 Co-pilot Setup Productization: examples/copilot-setup-example/ 是
setup-state-only reference,不应含 end-state 文件。

Acceptance:
- 目录结构在
- brief.md 含所有 12 节锚点(filled,非空 body)
- materials/README.md 含所有 8 节锚点
- 不含 program.md / rubric.md / simulator.md / cases/ / harnesses/
- 不含 results/ / sandbox/ / probe-results/(AHL 生成产物)
- materials/locked.md 至少含一行(本例:prompts-baseline.md)
- expected-coding-agent-plan.md 含 3-anchor 固定 schema:
  1. Files to create / modify
  2. Acceptance commands
  3. Risks / open questions
"""
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO_ROOT / "examples" / "copilot-setup-example"
EXP_DIR = EXAMPLE_DIR / "experiments" / "01-clarify-questions"


BRIEF_SECTION_ANCHORS = (
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
)

MATERIALS_SECTION_ANCHORS = (
    "What materials are for",
    "What user should put here",
    "Runtime notes",
    "Example transcripts",
    "Product requirements",
    "Evidence files",
    "Locked files convention",
    "Coding-agent operational rules",
)

PLAN_ANCHORS = (
    "Files to create / modify",
    "Acceptance commands",
    "Risks / open questions",
)


class TestCopilotSetupExampleDirectoryShape(unittest.TestCase):
    """Directory structure exists, expected files are present."""

    def test_example_root_exists(self):
        self.assertTrue(EXAMPLE_DIR.is_dir(),
                        f"examples/copilot-setup-example/ 必须存在;"
                        f"未找到:{EXAMPLE_DIR}")

    def test_top_level_files_present(self):
        self.assertTrue((EXAMPLE_DIR / "README.md").is_file())
        self.assertTrue((EXAMPLE_DIR / "goal.md").is_file())
        self.assertTrue(EXP_DIR.is_dir())

    def test_experiment_files_present(self):
        self.assertTrue((EXP_DIR / "brief.md").is_file())
        self.assertTrue((EXP_DIR / "expected-coding-agent-plan.md").is_file())
        self.assertTrue((EXP_DIR / "materials").is_dir())

    def test_materials_files_present(self):
        m = EXP_DIR / "materials"
        for name in (
            "README.md",
            "prompts-baseline.md",
            "target-behavior-examples.md",
            "domain-knowledge.md",
            "locked.md",
        ):
            self.assertTrue((m / name).is_file(),
                            f"materials/{name} 必须存在")


class TestCopilotSetupExampleSetupStateOnly(unittest.TestCase):
    """Q4 lock: example 必须是 setup-state only,不含 end-state 文件。"""

    def test_no_program_md(self):
        self.assertFalse((EXP_DIR / "program.md").exists(),
                         "setup-state example 不应含 program.md")

    def test_no_rubric_md(self):
        self.assertFalse((EXP_DIR / "rubric.md").exists(),
                         "setup-state example 不应含 rubric.md")

    def test_no_simulator_md(self):
        self.assertFalse((EXP_DIR / "simulator.md").exists(),
                         "setup-state example 不应含 simulator.md")

    def test_no_cases_dir(self):
        self.assertFalse((EXP_DIR / "cases").exists(),
                         "setup-state example 不应含 cases/")

    def test_no_harnesses_dir(self):
        self.assertFalse((EXP_DIR / "harnesses").exists(),
                         "setup-state example 不应含 harnesses/")

    def test_no_results_dir(self):
        self.assertFalse((EXP_DIR / "results").exists(),
                         "setup-state example 不应含 results/")

    def test_no_sandbox_dir(self):
        self.assertFalse((EXP_DIR / "sandbox").exists(),
                         "setup-state example 不应含 sandbox/")

    def test_no_probe_results_dir(self):
        self.assertFalse((EXP_DIR / "probe-results").exists(),
                         "setup-state example 不应含 probe-results/")


class TestExampleBriefIs12SectionFilled(unittest.TestCase):
    """example brief.md 12 节都填好,非占位符。"""

    def setUp(self):
        self.content = (EXP_DIR / "brief.md").read_text(encoding="utf-8")

    def test_has_all_12_anchors(self):
        for anchor in BRIEF_SECTION_ANCHORS:
            self.assertIn(f"## {anchor}\n", self.content,
                          f"example brief.md 必须含锚点 '## {anchor}\\n'")

    def test_each_section_nonempty_body(self):
        """每节都应有 filled-in body,不是单纯 placeholder。"""
        # Naive check: between consecutive anchors,合法填写 ≥3 lines of text
        lines = self.content.splitlines()
        # Find anchor line indices
        anchor_positions = {}
        for i, line in enumerate(lines):
            for anchor in BRIEF_SECTION_ANCHORS:
                if line.strip() == f"## {anchor}":
                    anchor_positions[anchor] = i
        self.assertEqual(
            set(anchor_positions.keys()), set(BRIEF_SECTION_ANCHORS),
            f"example brief.md 应含全部 12 anchor,找到: "
            f"{set(anchor_positions.keys())}")
        # Each section has at least 3 non-blank content lines below its anchor
        ordered = sorted(anchor_positions.items(), key=lambda kv: kv[1])
        for i, (anchor, start) in enumerate(ordered):
            end = ordered[i + 1][1] if i + 1 < len(ordered) else len(lines)
            body_lines = [ln for ln in lines[start + 1:end] if ln.strip()]
            self.assertGreaterEqual(
                len(body_lines), 3,
                f"example brief.md §{anchor} body 应 ≥3 非空行 (filled);"
                f"实际 {len(body_lines)}")


class TestExampleMaterialsReadme(unittest.TestCase):
    """example materials/README.md 含 8 节锚点。"""

    def test_has_all_8_anchors(self):
        content = (EXP_DIR / "materials" / "README.md").read_text(
            encoding="utf-8")
        for anchor in MATERIALS_SECTION_ANCHORS:
            self.assertIn(f". {anchor}\n", content,
                          f"example materials/README.md 必须含锚点 "
                          f"'. {anchor}\\n'")


class TestExampleLockedMd(unittest.TestCase):
    """locked.md 至少含一行(本例:prompts-baseline.md)。"""

    def test_locked_md_nonempty(self):
        content = (EXP_DIR / "materials" / "locked.md").read_text(
            encoding="utf-8")
        non_empty_lines = [ln for ln in content.splitlines() if ln.strip()]
        self.assertGreaterEqual(
            len(non_empty_lines), 1,
            "example locked.md 应至少含一行 (本例:prompts-baseline.md)")
        self.assertIn("prompts-baseline.md", content,
                      "example locked.md 应含 prompts-baseline.md")


class TestExpectedCodingAgentPlanSchema(unittest.TestCase):
    """Q3 lock: expected-coding-agent-plan.md 必须含 3 固定 anchor。"""

    def setUp(self):
        self.content = (EXP_DIR / "expected-coding-agent-plan.md").read_text(
            encoding="utf-8")

    def test_has_3_fixed_anchors(self):
        for anchor in PLAN_ANCHORS:
            self.assertIn(f"## {anchor}\n", self.content,
                          f"expected-coding-agent-plan.md 必须含锚点 "
                          f"'## {anchor}\\n' (Q3 lock)")


if __name__ == "__main__":
    unittest.main()
