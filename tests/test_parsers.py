"""文件解析器的单测 —— program / rubric / version / connect / cases / brief。"""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.brief import parse_brief
from agent_harness_lab.connect import parse_connect
from agent_harness_lab.program import parse_program
from agent_harness_lab.rubric import parse_rubric
from agent_harness_lab.testset import parse_sim_case
from agent_harness_lab.version import parse_version


class _MdCase(unittest.TestCase):
    """带临时目录的基类:_md(内容) 写一个临时 .md、返回路径。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _md(self, content: str) -> Path:
        p = Path(self._tmp.name) / "f.md"
        p.write_text(content, encoding="utf-8")
        return p


class TestProgram(_MdCase):
    PROG = (
        "# 实验 X · program\n\n"
        "## 假设\n这是假设\n\n"
        "## 声明\n"
        "- 环境:无\n- 对话模式:模拟\n- 状态:重置\n"
        "- 评分:LLM Judge\n- 运行模式:人评\n- 对比方式:线性迭代\n\n"
        "## 留/丢规则\n人评留空\n\n## 喊人规则\n人评留空\n"
    )

    def test_parse(self):
        prog = parse_program(self._md(self.PROG))
        self.assertEqual(prog.title, "实验 X · program")
        self.assertEqual(prog.assumption, "这是假设")
        self.assertEqual(prog.declarations["对话模式"], "模拟")
        self.assertEqual(prog.compare_mode, "线性迭代")

    def test_compare_mode_defaults(self):
        prog = parse_program(self._md("## 假设\nx\n\n## 声明\n- 环境:无\n"))
        self.assertEqual(prog.compare_mode, "对基线")

    def test_validate_ok(self):
        self.assertEqual(parse_program(self._md(self.PROG)).validate(), [])

    def test_validate_missing_assumption(self):
        prog = parse_program(self._md("## 声明\n- 环境:无\n"))
        self.assertIn("假设 没填", prog.validate())

    def test_validate_bad_compare_mode(self):
        prog = parse_program(self._md(self.PROG.replace("线性迭代", "瞎比")))
        self.assertTrue(any("对比方式" in p for p in prog.validate()))

    def test_compare_mode_placeholder_falls_back(self):
        # program.md 里 对比方式 那行还是模板占位符、没改
        prog = parse_program(self._md(
            "## 假设\nx\n\n## 声明\n"
            "- 对比方式:<对基线 / 线性迭代;多版本怎么比,默认 对基线、可不写>\n"))
        # compare 必须拿到合法值 —— 占位符不能进对比报告
        self.assertEqual(prog.compare_mode, "对基线")
        # 但 validate(ahl show 用)要把这行报成问题
        self.assertTrue(any("对比方式" in p for p in prog.validate()))


class TestRubric(_MdCase):
    def test_parse(self):
        r = parse_rubric(self._md(
            "## 准确\n权重: 0.6\n答得对不对。\n\n## 完整\n权重: 0.4\n覆盖全不全。\n"))
        self.assertEqual(len(r.dimensions), 2)
        self.assertEqual(r.dimensions[0].name, "准确")
        self.assertEqual(r.dimensions[0].weight, 0.6)
        self.assertEqual(r.dimensions[0].description, "答得对不对。")
        self.assertAlmostEqual(r.weight_total(), 1.0)

    def test_validate_ok(self):
        r = parse_rubric(self._md(
            "## 准确\n权重: 0.6\n说明甲。\n## 完整\n权重: 0.4\n说明乙。\n"))
        self.assertEqual(r.validate(), [])

    def test_validate_weight_sum_off(self):
        r = parse_rubric(self._md(
            "## 准确\n权重: 0.6\n说明甲。\n## 完整\n权重: 0.6\n说明乙。\n"))
        self.assertTrue(any("权重之和" in p for p in r.validate()))


class TestVersion(_MdCase):
    def test_parse_no_connect(self):
        v = parse_version(self._md("---\nid: V1\n基线: 是\n---\n## 这是什么\n基线版。\n"))
        self.assertEqual(v.version_id, "V1")
        self.assertTrue(v.is_baseline)
        self.assertIsNone(v.connect)
        # test 5:legacy 路径下 runtime_source / patch 必须为 None
        self.assertIsNone(v.runtime_source)
        self.assertIsNone(v.patch)

    def test_parse_with_connect(self):
        v = parse_version(self._md(
            "---\nid: V2\n基线: 否\n---\n## 这是什么\n改版。\n\n"
            "## 类型\n外部命令行\n\n## 配置\n命令:py agent.py\n"))
        self.assertFalse(v.is_baseline)
        self.assertIsNotNone(v.connect)
        self.assertEqual(v.connect.conn_type, "外部命令行")
        # legacy 路径(无 runtime_source) — Patch 段就算误写也忽略
        self.assertIsNone(v.runtime_source)

    def test_validate_ok(self):
        v = parse_version(self._md("---\nid: V1\n基线: 是\n---\n## 这是什么\n基线。\n"))
        self.assertEqual(v.validate(), [])

    def test_parse_with_runtime_source(self):
        """test 4:V*.md 带 runtime_source frontmatter + ## Patch 段。

        模拟 experiments/<id>/harnesses/V2.md 布局 —— patch source 文件相对
        experiment_dir(path.parent.parent)解析。
        """
        exp_dir = Path(self._tmp.name) / "001-test"
        harnesses_dir = exp_dir / "harnesses"
        harnesses_dir.mkdir(parents=True)
        patches_dir = exp_dir / "patches" / "V2"
        patches_dir.mkdir(parents=True)
        (patches_dir / "system.md").write_text("override prompt", encoding="utf-8")

        v_path = harnesses_dir / "V2.md"
        v_path.write_text(
            "---\n"
            "id: V2\n"
            "基线: 否\n"
            "runtime_source: openmanus-main\n"
            "---\n"
            "## 这是什么\n极简模式。\n\n"
            "## Patch\n"
            "files:\n"
            "  - target: prompts/system.md\n"
            "    source: patches/V2/system.md\n"
            "\n"
            "env:\n"
            "  HARNESS_MAX_DEPTH: \"5\"\n"
            "\n"
            "start_command: python -m openmanus.agent\n",
            encoding="utf-8")
        v = parse_version(v_path)
        self.assertEqual(v.version_id, "V2")
        self.assertEqual(v.runtime_source, "openmanus-main")
        self.assertIsNotNone(v.patch)
        self.assertEqual(len(v.patch.files), 1)
        self.assertEqual(v.patch.files[0].target_path, "prompts/system.md")
        self.assertTrue(v.patch.files[0].hash.startswith("sha256:"))
        self.assertEqual(v.patch.env["HARNESS_MAX_DEPTH"], "5")
        self.assertEqual(v.patch.start_command, "python -m openmanus.agent")


class TestConnect(_MdCase):
    def test_parse(self):
        c = parse_connect(self._md("## 类型\n外部命令行\n\n## 配置\n命令:py x.py\n"))
        self.assertEqual(c.conn_type, "外部命令行")
        self.assertEqual(c.config, "命令:py x.py")
        self.assertEqual(c.validate(), [])

    def test_validate_bad_type(self):
        c = parse_connect(self._md("## 类型\n瞎写\n\n## 配置\n命令:x\n"))
        self.assertTrue(any("识别不了" in p for p in c.validate()))


class TestTestset(_MdCase):
    def test_parse(self):
        c = parse_sim_case(self._md(
            "---\nid: D-01\ntype: D\nmax_turns: 5\n---\n"
            "## 起始输入\n帮我做个 PRD。\n\n## 完成标准\n有分层。\n"))
        self.assertEqual(c.case_id, "D-01")
        self.assertEqual(c.type, "D")
        self.assertEqual(c.max_turns, 5)
        self.assertEqual(c.opening, "帮我做个 PRD。")

    def test_validate_missing_opening(self):
        c = parse_sim_case(self._md("---\nid: D-01\n---\n## 起始输入\n\n"))
        self.assertTrue(any("起始输入" in p for p in c.validate()))


class TestBrief(_MdCase):
    BRIEF = (
        "# brief — X\n\n"
        "## 想优化什么\n让回答更简洁\n\n"
        "## 验证什么改动\n砍掉开场寒暄\n\n"
        "## 最在意什么\n回答密度\n\n"
        "## 不能牺牲什么\n不能漏关键信息\n\n"
        "## 怎么比\n对基线\n"
    )

    def test_parse(self):
        b = parse_brief(self._md(self.BRIEF))
        self.assertEqual(b.optimize, "让回答更简洁")
        self.assertEqual(b.change, "砍掉开场寒暄")
        self.assertEqual(b.redlines, "不能漏关键信息")
        self.assertEqual(b.compare, "对基线")

    def test_validate_ok(self):
        self.assertEqual(parse_brief(self._md(self.BRIEF)).validate(), [])

    def test_validate_missing_section(self):
        # 「最在意什么」空着
        b = parse_brief(self._md(self.BRIEF.replace("回答密度", "")))
        self.assertTrue(any("最在意什么" in p for p in b.validate()))

    def test_compare_is_optional(self):
        # 「怎么比」可空 —— 不该报问题
        b = parse_brief(self._md(self.BRIEF.replace("对基线", "")))
        self.assertEqual(b.validate(), [])

    def test_validate_bad_compare(self):
        # 「怎么比」填了识别不了的值 —— validate 要报问题
        b = parse_brief(self._md(self.BRIEF.replace("对基线", "随便比比")))
        self.assertTrue(any("怎么比" in p for p in b.validate()))


if __name__ == "__main__":
    unittest.main()
