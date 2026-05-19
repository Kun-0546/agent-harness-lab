"""workflow 的单测 —— run 前的聚合校验、基线数量。"""
import unittest
from pathlib import Path

from harness_design_loop.program import Program
from harness_design_loop.testset import TestCase
from harness_design_loop.version import Version
from harness_design_loop.workflow import baseline_problems, run_preflight


def _program(assumption: str = "验证某个改动", compare_mode: str = "对基线") -> Program:
    decls = {"环境": "无", "对话模式": "模拟", "状态": "重置",
             "评分": "本地桩", "运行模式": "人评", "对比方式": compare_mode}
    return Program(path=Path("program.md"), assumption=assumption, declarations=decls)


def _version(vid: str = "V1", what: str = "基线版", baseline: bool = True) -> Version:
    return Version(path=Path(f"{vid}.md"), version_id=vid,
                   is_baseline=baseline, what=what)


def _case(cid: str = "D-01", opening: str = "帮我做个搬家计划") -> TestCase:
    return TestCase(path=Path(f"{cid}.md"), case_id=cid, opening=opening)


class TestRunPreflight(unittest.TestCase):
    def test_clean_setup_passes(self):
        self.assertEqual(run_preflight(_program(), [_version()], [_case()]), [])

    def test_empty_opening_is_caught(self):
        # case 段名写错(「## 初始输入」而非「## 起始输入」)→ 起始输入为空。
        # run 以前会静默把空串发给 agent;preflight 必须拦下。
        problems = run_preflight(_program(), [_version()], [_case(opening="")])
        self.assertTrue(any("起始输入" in p for p in problems))
        self.assertTrue(any("D-01" in p for p in problems))

    def test_bad_version_is_caught(self):
        problems = run_preflight(_program(), [_version(what="")], [_case()])
        self.assertTrue(any("这是什么" in p for p in problems))

    def test_bad_program_is_caught(self):
        # program 假设没填 —— hdl show 能看到的,run 也要拦
        problems = run_preflight(_program(assumption=""), [_version()], [_case()])
        self.assertTrue(any(p.startswith("program:") and "假设" in p
                            for p in problems))

    def test_reports_every_source(self):
        problems = run_preflight(_program(assumption=""),
                                 [_version(what="")], [_case(opening="")])
        self.assertTrue(any(p.startswith("program:") for p in problems))
        self.assertTrue(any(p.startswith("版本 ") for p in problems))
        self.assertTrue(any(p.startswith("case ") for p in problems))


class TestBaselineCount(unittest.TestCase):
    def test_baseline_mode_one_ok(self):
        self.assertEqual(baseline_problems([_version(baseline=True)], "对基线"), [])

    def test_baseline_mode_zero_caught(self):
        problems = baseline_problems([_version(vid="V1", baseline=False)], "对基线")
        self.assertTrue(any("没有标基线" in p for p in problems))

    def test_baseline_mode_two_caught(self):
        vs = [_version(vid="V1", baseline=True), _version(vid="V2", baseline=True)]
        problems = baseline_problems(vs, "对基线")
        self.assertTrue(any("2 个" in p for p in problems))

    def test_linear_mode_needs_no_baseline(self):
        vs = [_version(vid="V1", baseline=False), _version(vid="V2", baseline=False)]
        self.assertEqual(baseline_problems(vs, "线性迭代"), [])

    def test_preflight_includes_baseline_check(self):
        # 对基线 + 0 基线 → run_preflight 也要带出这个问题
        problems = run_preflight(_program(compare_mode="对基线"),
                                 [_version(baseline=False)], [_case()])
        self.assertTrue(any("基线" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
