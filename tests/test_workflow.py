"""workflow 的单测 —— run 前的聚合校验。"""
import unittest
from pathlib import Path

from harness_design_loop.testset import TestCase
from harness_design_loop.version import Version
from harness_design_loop.workflow import run_preflight


def _version(vid: str = "V1", what: str = "基线版") -> Version:
    return Version(path=Path(f"{vid}.md"), version_id=vid, is_baseline=True, what=what)


def _case(cid: str = "D-01", opening: str = "帮我做个搬家计划") -> TestCase:
    return TestCase(path=Path(f"{cid}.md"), case_id=cid, opening=opening)


class TestRunPreflight(unittest.TestCase):
    def test_clean_setup_passes(self):
        self.assertEqual(run_preflight([_version()], [_case()]), [])

    def test_empty_opening_is_caught(self):
        # case 段名写错(「## 初始输入」而不是「## 起始输入」)→ 起始输入为空。
        # run 以前会静默把空串发给 agent;preflight 必须拦下。
        problems = run_preflight([_version()], [_case(opening="")])
        self.assertTrue(any("起始输入" in p for p in problems))
        self.assertTrue(any("D-01" in p for p in problems))

    def test_bad_version_is_caught(self):
        # 版本没写「这是什么」
        problems = run_preflight([_version(what="")], [_case()])
        self.assertTrue(any("这是什么" in p for p in problems))

    def test_reports_every_problem(self):
        problems = run_preflight([_version(what="")], [_case(opening="")])
        self.assertEqual(len(problems), 2)


if __name__ == "__main__":
    unittest.main()
