"""v0.9 Co-pilot Setup Productization: BRIEF_TEMPLATE / MATERIALS_README_TEMPLATE
drift detectors。

These tests assert the canonical 12-section brief.md schema and 8-section
materials/README.md schema in `src/agent_harness_lab/templates.py`. Any PR
that silently changes template section names or removes contractual anchors
trips here.

Length budgets:
- BRIEF_TEMPLATE   ≤200 lines (per `docs/copilot-setup-productization.md` §8)
- MATERIALS_README ≤80 lines  (per spec §9)

Contract anchors:
- 12 brief.md H2 headings (in order)
- 8 materials/README.md H2 headings (in order)
- brief.md must mention Manual / Co-pilot / Auto boundary
- brief.md must mention acceptance commands list
- brief.md must mention done criteria
- materials/README.md must say generated `results/` / `sandbox/` not to be
  mutated
- materials/README.md must reference docs/evidence-guide.md
- materials/README.md must mention `locked.md` convention
"""
import unittest

from agent_harness_lab import templates


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


class TestBriefTemplate(unittest.TestCase):
    """BRIEF_TEMPLATE 12-section contract."""

    def setUp(self):
        self.content = templates.BRIEF_TEMPLATE

    def test_has_12_section_anchors_in_order(self):
        positions = []
        for anchor in BRIEF_SECTION_ANCHORS:
            idx = self.content.find(f"## {anchor}\n")
            self.assertGreaterEqual(
                idx, 0,
                f"BRIEF_TEMPLATE 必须含 '## {anchor}\\n' 锚点;"
                f"未找到 = 模板退化")
            positions.append(idx)
        # In-order check
        for i in range(1, len(positions)):
            self.assertGreater(
                positions[i], positions[i - 1],
                f"BRIEF_TEMPLATE 12 节必须按 spec §8 顺序;"
                f"'{BRIEF_SECTION_ANCHORS[i]}' 出现在 "
                f"'{BRIEF_SECTION_ANCHORS[i-1]}' 之前")

    def test_under_200_lines(self):
        """spec §8: brief.md template length budget ≤200 lines."""
        line_count = self.content.count("\n") + 1
        self.assertLessEqual(
            line_count, 200,
            f"BRIEF_TEMPLATE 行数预算 ≤200,当前 {line_count}")

    def test_mentions_modes_boundary(self):
        """spec §8 preamble: 必须 mention Manual / Co-pilot / Auto boundary."""
        self.assertIn("Manual", self.content,
                      "BRIEF_TEMPLATE preamble 应提 Manual mode")
        self.assertIn("Co-pilot", self.content,
                      "BRIEF_TEMPLATE preamble 应提 Co-pilot mode")
        self.assertIn("Auto", self.content,
                      "BRIEF_TEMPLATE preamble 应提 Auto mode")

    def test_mentions_coding_agent_proposal_labels(self):
        """spec §8 + Q2 lock: brief.md preamble 必须告诉 coding agent 可以
        加 [proposal] / [interpretation] / [open question] 标签,不可静默
        改写。"""
        self.assertIn("[proposal]", self.content)
        self.assertIn("[interpretation]", self.content)
        self.assertIn("[open question]", self.content)
        self.assertTrue(
            "不可" in self.content
            or "不要猜" in self.content,
            "BRIEF_TEMPLATE 应警告 coding agent 不可静默改写 / 不要猜")

    def test_acceptance_commands_section_lists_5_ahl_commands(self):
        """§Acceptance commands: 必须 list ahl review / probe / run / score
        / compare 5 个命令。"""
        # Pull just the Acceptance commands section
        acc_marker = "## Acceptance commands\n"
        done_marker = "## Done criteria\n"
        acc_idx = self.content.find(acc_marker)
        done_idx = self.content.find(done_marker)
        self.assertGreaterEqual(acc_idx, 0)
        self.assertGreater(done_idx, acc_idx)
        acc_section = self.content[acc_idx:done_idx]
        for cmd in ("ahl review", "ahl probe", "ahl run",
                    "ahl score", "ahl compare"):
            self.assertIn(cmd, acc_section,
                          f"§Acceptance commands 应 list `{cmd}`")

    def test_done_criteria_section_references_evidence_alignment(self):
        """§Done criteria: 必须提 evidence level 跟 brief.md
        Evidence / probe expectations 目标对齐。"""
        done_idx = self.content.find("## Done criteria\n")
        self.assertGreaterEqual(done_idx, 0)
        done_section = self.content[done_idx:]
        self.assertIn("evidence", done_section.lower(),
                      "§Done criteria 应 mention evidence level alignment")


class TestMaterialsReadmeTemplate(unittest.TestCase):
    """MATERIALS_README_TEMPLATE 8-section contract."""

    def setUp(self):
        self.content = templates.MATERIALS_README_TEMPLATE

    def test_has_8_section_anchors_in_order(self):
        positions = []
        for anchor in MATERIALS_SECTION_ANCHORS:
            # H2 headings use "## N. <name>" format
            # Find by looking for the heading content
            idx = self.content.find(f". {anchor}\n")
            self.assertGreaterEqual(
                idx, 0,
                f"MATERIALS_README_TEMPLATE 必须含 '. {anchor}\\n' 锚点;"
                f"未找到 = 模板退化")
            positions.append(idx)
        for i in range(1, len(positions)):
            self.assertGreater(
                positions[i], positions[i - 1],
                f"MATERIALS_README_TEMPLATE 8 节必须按 spec §9 顺序;"
                f"'{MATERIALS_SECTION_ANCHORS[i]}' 出现在 "
                f"'{MATERIALS_SECTION_ANCHORS[i-1]}' 之前")

    def test_under_80_lines(self):
        """spec §9: materials/README.md template length budget ≤80 lines."""
        line_count = self.content.count("\n") + 1
        self.assertLessEqual(
            line_count, 80,
            f"MATERIALS_README_TEMPLATE 行数预算 ≤80,当前 {line_count}")

    def test_mentions_locked_md_convention(self):
        """§7 Locked files convention: 必须提 locked.md。"""
        self.assertIn("locked.md", self.content)
        self.assertTrue(
            "约定" in self.content or "convention" in self.content.lower(),
            "MATERIALS_README_TEMPLATE 应说明 locked.md 是产品约定")

    def test_mentions_generated_results_not_to_mutate(self):
        """§8 Coding-agent operational rules: 必须提 results/ + sandbox/
        AHL 生成产物 coding agent 不可改。"""
        self.assertIn("results/", self.content)
        self.assertIn("sandbox/", self.content)
        # Mention "不修改" / "不动" / "not modify" / etc.
        self.assertTrue(
            "不修改" in self.content or "不改" in self.content
            or "not modify" in self.content.lower()
            or "不可" in self.content,
            "MATERIALS_README_TEMPLATE 应明确 coding agent 不可改 "
            "AHL 生成产物")

    def test_links_to_evidence_guide(self):
        """§6 Evidence files: 必须 cross-link 到 docs/evidence-guide.md
        (不在此重复内容)。"""
        self.assertIn("evidence-guide", self.content,
                      "MATERIALS_README_TEMPLATE §6 应 cross-link "
                      "docs/evidence-guide.md")

    def test_links_to_copilot_setup_guide(self):
        """§8 Coding-agent operational rules: 完整规则指向
        docs/copilot-setup.md。"""
        self.assertIn("copilot-setup", self.content,
                      "MATERIALS_README_TEMPLATE §8 应 cross-link "
                      "docs/copilot-setup.md")


if __name__ == "__main__":
    unittest.main()
