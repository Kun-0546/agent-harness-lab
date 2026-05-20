"""workflow 的单测 —— run 前的聚合校验、基线数量、parse 异常翻译、review 三态。"""
import json
import tempfile
import unittest
from pathlib import Path

from harness_design_loop.program import Program
from harness_design_loop.testset import TestCase
from harness_design_loop.version import Version
from harness_design_loop.workflow import (
    WorkflowError,
    baseline_problems,
    compare,
    review,
    run,
    run_preflight,
    score,
)


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


# ---- P0:parse_* 异常被翻成 WorkflowError(不再 traceback)----


class TestParserErrorWrapped(unittest.TestCase):
    """P0:run / score / compare 遇到 corrupt 文件应抛 WorkflowError,不是裸 Python exception。

    dogfood 发现:cli.cmd_* 只 catch WorkflowError;parse_* 内层 UnicodeDecodeError /
    JSONDecodeError 不被它们接住,会冒到 main 变 traceback。修法:workflow 层
    用 _safe_call 统一翻译。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-bad"
        (self.exp / "测试集").mkdir(parents=True)
        (self.exp / "versions").mkdir()
        # V1 给 compare 用 —— 让 baseline_problems 不会先把 compare 拦下来。
        (self.exp / "versions" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线。\n",
            encoding="utf-8")

    def test_run_wraps_corrupt_program(self):
        (self.exp / "program.md").write_bytes(b"\xff\xfe not utf8\n")
        with self.assertRaises(WorkflowError) as ctx:
            run(self.exp, use_llm=False)
        msg = str(ctx.exception)
        self.assertIn("program.md", msg)
        self.assertIn("UTF-8", msg)

    def test_score_wraps_corrupt_rubric(self):
        (self.exp / "rubric.md").write_bytes(b"\xff\xfe not utf8\n")
        results = self.exp / "results"
        results.mkdir()
        (results / "run-x.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(WorkflowError) as ctx:
            score(self.exp, use_llm=False)
        self.assertIn("rubric.md", str(ctx.exception))

    def test_score_wraps_bad_run_json(self):
        # rubric 合法 + run-*.json 不是合法 JSON → score 应抛 WorkflowError 提 JSON
        (self.exp / "rubric.md").write_text(
            "# rubric\n\n## 维度甲\n权重: 0.5\n判甲。\n\n## 维度乙\n权重: 0.5\n判乙。\n",
            encoding="utf-8")
        results = self.exp / "results"
        results.mkdir()
        (results / "run-x.json").write_text("not valid json {{{",
                                              encoding="utf-8")
        with self.assertRaises(WorkflowError) as ctx:
            score(self.exp, use_llm=False)
        self.assertIn("JSON", str(ctx.exception))

    def test_compare_wraps_corrupt_program(self):
        # score-*.json 合法 + program.md corrupt → compare 在读 compare_mode 时应抛 WorkflowError
        (self.exp / "program.md").write_bytes(b"\xff\xfe not utf8\n")
        results = self.exp / "results"
        results.mkdir()
        score_data = {
            "run": "run.json",
            "rubric": "rubric.md",
            "grader": "stub",
            "scores": [{"version_id": "V1", "case_id": "D-01",
                         "total": 7.0, "dims": {}}],
        }
        (results / "score-x.json").write_text(
            json.dumps(score_data), encoding="utf-8")
        with self.assertRaises(WorkflowError) as ctx:
            compare(self.exp)
        self.assertIn("program.md", str(ctx.exception))


# ---- P1.a:review 不把 program 解析失败 cascade 到 测试集 ----


class TestReviewCascade(unittest.TestCase):
    """P1.a:program.md 解析失败时,测试集 应标「未检查」而不是「解析失败」。

    dogfood 发现:load_testset 内部调 parse_program 读对话模式,program 坏了 →
    UnicodeDecodeError(ValueError 子类)→ _dir_piece 误归到「测试集解析失败」。
    修法:review 在 cascade 前 short-circuit,标 skipped 而非 broken。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-cascade"
        (self.exp / "测试集").mkdir(parents=True)
        (self.exp / "versions").mkdir()
        # 健全的 case —— 自己没坏,任何「测试集解析失败」都得来自 program cascade
        (self.exp / "测试集" / "D-01.md").write_text(
            "---\nid: D-01\n---\n## 起始输入\nhi\n", encoding="utf-8")

    def test_corrupt_program_marks_testset_skipped(self):
        (self.exp / "program.md").write_bytes(b"\xff\xfe not utf8\n")
        result = review(self.exp)
        # program.md 应在 broken
        self.assertTrue(
            any("program.md" in b for b in result.broken),
            f"program.md 应在 broken 里: {result.broken}",
        )
        # 测试集应在 skipped(未检查),不在 broken —— 这是 P1.a 的核心断言
        self.assertTrue(
            any("测试集/" in s for s in result.skipped),
            f"测试集 应在 skipped 里: {result.skipped}",
        )
        self.assertFalse(
            any("测试集/" in b for b in result.broken),
            f"测试集 不应在 broken 里(P1.a 修的就是这个误归因): {result.broken}",
        )
        # review.md 文本里也应是「未检查」
        review_text = (self.exp / "review.md").read_text(encoding="utf-8")
        self.assertIn("未检查", review_text)


# ---- P1.b:review 收集 validate warnings,cli 不再说「齐了」 ----


class TestReviewWarnings(unittest.TestCase):
    """P1.b:产物 parse OK 但 validate 有问题时,review.warnings 应该非空,
    cli 不应再说「齐了」(它会读 warnings 字段决定)。

    dogfood 发现:第一轮 bad-path 时 review.md 满是 ⚠ 校验提醒,CLI 却说
    「齐了 —— 没问题就 hdl run」。修法:review 收集 validate 问题进 warnings,
    cli 把它纳入「是否齐了」的判断。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-warn"
        (self.exp / "测试集").mkdir(parents=True)
        (self.exp / "versions").mkdir()

    def test_brief_placeholder_surfaced_as_warnings(self):
        # brief 仍是模板占位符 —— is_filled 判 False,brief.validate 返回 4 条
        (self.exp / "brief.md").write_text(
            "# brief\n\n## 想优化什么\n<x>\n\n## 验证什么改动\n<y>\n\n"
            "## 最在意什么\n<z>\n\n## 不能牺牲什么\n<w>\n",
            encoding="utf-8")
        # 其他产物都健全 —— missing / broken / skipped 都应为空
        (self.exp / "program.md").write_text(
            "# program\n\n## 假设\n这是假设。\n\n## 声明\n"
            "- 环境:无\n- 对话模式:模拟\n- 状态:重置\n"
            "- 评分:本地桩\n- 运行模式:人评\n- 对比方式:对基线\n\n"
            "## 留/丢规则\n人评留空。\n\n## 喊人规则\n人评留空。\n",
            encoding="utf-8")
        (self.exp / "rubric.md").write_text(
            "# rubric\n\n## 维度甲\n权重: 0.5\n判甲。\n\n## 维度乙\n权重: 0.5\n判乙。\n",
            encoding="utf-8")
        (self.exp / "模拟器.md").write_text(
            "# 模拟器\n\n## 人设\n一个用户。\n\n## 背景知识\n无。\n\n"
            "## 追问策略\n追问。\n", encoding="utf-8")
        (self.exp / "versions" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线版。\n",
            encoding="utf-8")
        (self.exp / "测试集" / "D-01.md").write_text(
            "---\nid: D-01\n---\n## 起始输入\n你好。\n", encoding="utf-8")

        result = review(self.exp)
        # missing / broken / skipped 都应为空 —— 所有产物都到位、能 parse
        self.assertEqual(result.missing, [])
        self.assertEqual(result.broken, [])
        self.assertEqual(result.skipped, [])
        # 但 warnings 应非空 —— brief 的 4 个未填段必须出现
        self.assertTrue(result.warnings,
                         "应该收到 warnings,cli 不该说「齐了」")
        brief_warns = [w for w in result.warnings if "brief.md" in w]
        self.assertGreaterEqual(
            len(brief_warns), 4,
            f"brief 4 段都该报: {brief_warns}",
        )


if __name__ == "__main__":
    unittest.main()
