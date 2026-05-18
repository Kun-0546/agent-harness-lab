"""mdutil 的单测 —— 占位符判断、区块切分、frontmatter。"""
import unittest

from harness_design_loop import mdutil


class TestIsFilled(unittest.TestCase):
    def test_real(self):
        self.assertTrue(mdutil.is_filled("内容"))

    def test_empty(self):
        self.assertFalse(mdutil.is_filled(""))
        self.assertFalse(mdutil.is_filled("   "))

    def test_placeholder(self):
        self.assertFalse(mdutil.is_filled("<占位>"))


class TestSplitSections(unittest.TestCase):
    def test_basic(self):
        sec = mdutil.split_sections("## 甲\n甲内容\n\n## 乙\n乙内容\n")
        self.assertEqual(sec["甲"], "甲内容")
        self.assertEqual(sec["乙"], "乙内容")

    def test_order_preserved(self):
        sec = mdutil.split_sections("## 一\nx\n## 二\ny\n## 三\nz\n")
        self.assertEqual(list(sec), ["一", "二", "三"])

    def test_ignores_text_before_first_header(self):
        sec = mdutil.split_sections("# 大标题\n前言\n## 甲\nx\n")
        self.assertEqual(list(sec), ["甲"])


class TestParseFrontmatter(unittest.TestCase):
    def test_with_frontmatter(self):
        fields, body = mdutil.parse_frontmatter("---\nid: D-01\ntype: D\n---\n## 段\nx\n")
        self.assertEqual(fields["id"], "D-01")
        self.assertEqual(fields["type"], "D")
        self.assertIn("## 段", body)

    def test_no_frontmatter(self):
        fields, body = mdutil.parse_frontmatter("## 段\nx\n")
        self.assertEqual(fields, {})
        self.assertEqual(body, "## 段\nx\n")


if __name__ == "__main__":
    unittest.main()
