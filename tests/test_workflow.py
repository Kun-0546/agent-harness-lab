"""workflow 的单测 —— run 前的聚合校验、基线数量、parse 异常翻译、review 三态。"""
import json
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.program import Program
from agent_harness_lab.testset import TestCase
from agent_harness_lab.version import Version
from agent_harness_lab.workflow import (
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
        # program 假设没填 —— ahl show 能看到的,run 也要拦
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
        (self.exp / "cases").mkdir(parents=True)
        (self.exp / "harnesses").mkdir()
        # V1 给 compare 用 —— 让 baseline_problems 不会先把 compare 拦下来。
        (self.exp / "harnesses" / "V1.md").write_text(
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


# ---- P1.a:review 不把 program 解析失败 cascade 到 cases ----


class TestReviewCascade(unittest.TestCase):
    """P1.a:program.md 解析失败时,cases 应标「未检查」而不是「解析失败」。

    dogfood 发现:load_testset 内部调 parse_program 读对话模式,program 坏了 →
    UnicodeDecodeError(ValueError 子类)→ _dir_piece 误归到「cases 解析失败」。
    修法:review 在 cascade 前 short-circuit,标 skipped 而非 broken。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-cascade"
        (self.exp / "cases").mkdir(parents=True)
        (self.exp / "harnesses").mkdir()
        # 健全的 case —— 自己没坏,任何「cases 解析失败」都得来自 program cascade
        (self.exp / "cases" / "D-01.md").write_text(
            "---\nid: D-01\n---\n## 起始输入\nhi\n", encoding="utf-8")

    def test_corrupt_program_marks_cases_skipped(self):
        (self.exp / "program.md").write_bytes(b"\xff\xfe not utf8\n")
        result = review(self.exp)
        # program.md 应在 broken
        self.assertTrue(
            any("program.md" in b for b in result.broken),
            f"program.md 应在 broken 里: {result.broken}",
        )
        # cases 应在 skipped(未检查),不在 broken —— 这是 P1.a 的核心断言
        self.assertTrue(
            any("cases/" in s for s in result.skipped),
            f"cases 应在 skipped 里: {result.skipped}",
        )
        self.assertFalse(
            any("cases/" in b for b in result.broken),
            f"cases 不应在 broken 里(P1.a 修的就是这个误归因): {result.broken}",
        )
        # review.md 文本里也应是「未检查」
        review_text = (self.exp / "review.md").read_text(encoding="utf-8")
        self.assertIn("未检查", review_text)


# ---- P1.b:review 收集 validate warnings,cli 不再说「齐了」 ----


class TestReviewWarnings(unittest.TestCase):
    """P1.b:产物 parse OK 但 validate 有问题时,review.warnings 应该非空,
    cli 不应再说「齐了」(它会读 warnings 字段决定)。

    dogfood 发现:第一轮 bad-path 时 review.md 满是 ⚠ 校验提醒,CLI 却说
    「齐了 —— 没问题就 ahl run」。修法:review 收集 validate 问题进 warnings,
    cli 把它纳入「是否齐了」的判断。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-warn"
        (self.exp / "cases").mkdir(parents=True)
        (self.exp / "harnesses").mkdir()

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
        (self.exp / "simulator.md").write_text(
            "# simulator\n\n## 人设\n一个用户。\n\n## 背景知识\n无。\n\n"
            "## 追问策略\n追问。\n", encoding="utf-8")
        (self.exp / "harnesses" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线版。\n",
            encoding="utf-8")
        (self.exp / "cases" / "D-01.md").write_text(
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


# ---- Phase 2:legacy 目录/文件检测 ----


class TestLegacyDetection(unittest.TestCase):
    """Phase 2 命名同步:发现旧目录/文件时,新代码应抛友好错误(不 fallback)。

    新名:harnesses/ / cases/ / simulator.md。如果用户实验里还是
    旧名 versions/ / 测试集/ / 模拟器.md,run / cli 应明确告知"请改名为新名"。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-legacy"
        self.exp.mkdir(parents=True)
        (self.exp / "program.md").write_text(
            "# program\n\n## 假设\n测试。\n\n## 声明\n"
            "- 环境:无\n- 对话模式:模拟\n- 状态:重置\n"
            "- 评分:本地桩\n- 运行模式:人评\n- 对比方式:对基线\n\n"
            "## 留/丢规则\n人评。\n\n## 喊人规则\n人评。\n",
            encoding="utf-8")
        (self.exp / "rubric.md").write_text(
            "## 准确\n权重: 1.0\n判甲。\n", encoding="utf-8")

    def test_legacy_versions_dir_triggers_friendly_error(self):
        """有 versions/ 没 harnesses/ → run 抛友好错误指向 harnesses/。"""
        (self.exp / "versions").mkdir()
        (self.exp / "versions" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\nx\n", encoding="utf-8")
        (self.exp / "cases").mkdir()
        (self.exp / "cases" / "D-01.md").write_text(
            "---\nid: D-01\n---\n## 起始输入\nhi\n", encoding="utf-8")
        with self.assertRaises(WorkflowError) as ctx:
            run(self.exp, use_llm=False)
        msg = str(ctx.exception)
        self.assertIn("versions/", msg)
        self.assertIn("harnesses/", msg)
        self.assertIn("请改名为", msg)

    def test_legacy_testset_dir_triggers_friendly_error(self):
        """有 测试集/ 没 cases/ → run 抛友好错误指向 cases/。"""
        (self.exp / "harnesses").mkdir()
        (self.exp / "harnesses" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\nx\n", encoding="utf-8")
        (self.exp / "测试集").mkdir()
        (self.exp / "测试集" / "D-01.md").write_text(
            "---\nid: D-01\n---\n## 起始输入\nhi\n", encoding="utf-8")
        with self.assertRaises(WorkflowError) as ctx:
            run(self.exp, use_llm=False)
        msg = str(ctx.exception)
        self.assertIn("测试集/", msg)
        self.assertIn("cases/", msg)
        self.assertIn("请改名为", msg)

    def test_legacy_simulator_md_triggers_friendly_error_via_cli(self):
        """有 模拟器.md 没 simulator.md → cli simulator 命令抛友好错误。"""
        import io
        import os
        from contextlib import redirect_stderr
        from agent_harness_lab import cli as cli_mod

        (self.exp / "harnesses").mkdir()
        (self.exp / "cases").mkdir()
        (self.exp / "模拟器.md").write_text(
            "## 人设\n一个用户\n\n## 追问策略\n追问\n", encoding="utf-8")

        original = Path.cwd()
        os.chdir(self.root)
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = cli_mod.main(["simulator", "001"])
            self.assertEqual(exit_code, 1)
            err_text = err.getvalue()
            self.assertIn("模拟器.md", err_text)
            self.assertIn("simulator.md", err_text)
            self.assertIn("请改名为", err_text)
        finally:
            os.chdir(original)

    def test_harnesses_subcommand_invokes_cmd_versions(self):
        """ahl harnesses <exp> 复用 cmd_versions 逻辑,读出 harnesses/ 下的 variants。"""
        import io
        import os
        from contextlib import redirect_stdout
        from agent_harness_lab import cli as cli_mod

        (self.exp / "harnesses").mkdir()
        (self.exp / "harnesses" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\nx\n", encoding="utf-8")

        original = Path.cwd()
        os.chdir(self.root)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = cli_mod.main(["harnesses", "001"])
            self.assertEqual(exit_code, 0)
            out_text = out.getvalue()
            self.assertIn("harnesses:1 个", out_text)
            self.assertIn("V1", out_text)
        finally:
            os.chdir(original)

    def test_versions_subcommand_redirects_to_harnesses(self):
        """Phase 3:ahl versions <exp> 不再正常执行,打印 legacy redirect 并 exit 1。"""
        import io
        import os
        from contextlib import redirect_stderr
        from agent_harness_lab import cli as cli_mod

        original = Path.cwd()
        os.chdir(self.root)
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = cli_mod.main(["versions", "001"])
            self.assertEqual(exit_code, 1)
            err_text = err.getvalue()
            self.assertIn("versions", err_text)
            self.assertIn("harnesses", err_text)
            self.assertIn("请用", err_text)
        finally:
            os.chdir(original)


# ---- Runtime Materialization local_path (C5) ----


class TestRuntimeSourceLocalPathPreflight(unittest.TestCase):
    """C5: local_path runtime_source 通过 preflight + 走 materialize 跑通。

    新加的 patch 段 validate 在 preflight 阶段抓 (patch=None / 缺 start_command /
    patch source 文件不存在)。
    """

    def setUp(self) -> None:
        import sys
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-lp"
        self.exp.mkdir(parents=True)
        (self.exp / "program.md").write_text(
            "# program\n\n## 假设\nlocal_path。\n\n## 声明\n"
            "- 环境:无\n- 对话模式:模拟\n- 状态:重置\n"
            "- 评分:本地桩\n- 运行模式:人评\n- 对比方式:对基线\n\n"
            "## 留/丢规则\n人评。\n\n## 喊人规则\n人评。\n",
            encoding="utf-8")
        (self.exp / "rubric.md").write_text(
            "## 准确\n权重: 1.0\n判甲。\n", encoding="utf-8")
        (self.exp / "harnesses").mkdir()
        (self.exp / "cases").mkdir()
        (self.exp / "cases" / "D-01.md").write_text(
            "---\nid: D-01\n---\n## 起始输入\nhi\n", encoding="utf-8")

        # 真 source dir 含 echo agent (workflow.run 会跑它)
        self.source = self.root / "local-src"
        self.source.mkdir()
        echo_script = """import json, sys
for line in sys.stdin:
    data = json.loads(line)
    sys.stdout.write(json.dumps({"response": "echo:" + data["input"]}) + "\\n")
    sys.stdout.flush()
"""
        (self.source / "agent.py").write_text(echo_script, encoding="utf-8")

        # runtime-sources.md 声明 local_path source
        (self.root / "runtime-sources.md").write_text(
            f"## local-src\n"
            f"type: local_path\n"
            f"path: {self.source}\n",
            encoding="utf-8")

        # patches/V1/ 文件 (变更 agent.py)
        patches = self.exp / "patches" / "V1"
        patches.mkdir(parents=True)
        patched_script = """import json, sys
for line in sys.stdin:
    data = json.loads(line)
    sys.stdout.write(json.dumps({"response": "patched:" + data["input"]}) + "\\n")
    sys.stdout.flush()
"""
        (patches / "agent.py").write_text(patched_script, encoding="utf-8")

        self.python = sys.executable

    def _write_v1(self, *, patch_section: str):
        (self.exp / "harnesses" / "V1.md").write_text(
            "---\n"
            "id: V1\n"
            "基线: 是\n"
            "runtime_source: local-src\n"
            "---\n"
            "## 这是什么\n极简模式。\n\n"
            f"{patch_section}",
            encoding="utf-8")

    def test_run_passes_preflight_and_writes_materialized_snapshot(self):
        """完整 local_path 跑通:preflight pass + materialize + snapshot.json 含
        materialized 字段(source_dir_hash / harness_patch / sandbox)。
        """
        self._write_v1(patch_section=(
            "## Patch\n\n"
            "files:\n"
            "  - target: agent.py\n"
            "    source: patches/V1/agent.py\n\n"
            f'start_command: "{self.python}" agent.py\n'))

        # 跑 run (echo agent 实际会跑;stub_simulator 决定多少轮)
        # capture stdout 防止 pytest 输出嘈杂
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = run(self.exp, use_llm=False)

        # run 应成功(至少 1 case OK)
        self.assertGreater(result.ok, 0,
                           f"run failed: {result.errors};stdout: {buf.getvalue()}")

        # snapshot.json 应落盘到 results/snapshots/<run_id>/V1.json
        snapshots_dir = self.exp / "results" / "snapshots"
        run_dirs = list(snapshots_dir.iterdir())
        self.assertEqual(len(run_dirs), 1, "应该只有一个 run_id 目录")
        v1_snap = run_dirs[0] / "V1.json"
        self.assertTrue(v1_snap.exists())

        # snapshot 内容 materialized 字段全部 present
        data = json.loads(v1_snap.read_text(encoding="utf-8"))
        self.assertTrue(data["snapshot_id"].startswith("snap-"))
        self.assertEqual(data["runtime_source"]["type"], "local_path")
        self.assertEqual(data["runtime_source"]["name"], "local-src")
        self.assertTrue(
            data["runtime_source"]["source_dir_hash"].startswith("sha256:"))
        self.assertIsNotNone(data["harness_patch"])
        self.assertTrue(
            data["harness_patch"]["patch_hash"].startswith("sha256:"))
        self.assertEqual(len(data["harness_patch"]["applied"]), 1)
        self.assertIsNotNone(data["sandbox"])
        self.assertEqual(data["sandbox"]["type"], "copy_dir")

    def test_run_with_cleanup_sandboxes_removes_sandbox_dir(self):
        """C7: cleanup_sandboxes=True → 跑完 sandbox dir 不存在;snapshot.json 保留。"""
        self._write_v1(patch_section=(
            "## Patch\n\n"
            "files:\n"
            "  - target: agent.py\n"
            "    source: patches/V1/agent.py\n\n"
            f'start_command: "{self.python}" agent.py\n'))

        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = run(self.exp, use_llm=False, cleanup_sandboxes=True)

        self.assertGreater(result.ok, 0,
                           f"run failed: {result.errors};stdout: {buf.getvalue()}")

        # sandbox dir 应被 shutil.rmtree
        sandbox_root = self.exp / "sandbox"
        if sandbox_root.exists():
            # sandbox/<run_id>/<vid>/ 子目录应不存在 (V1 被 rmtree)
            run_dirs = list(sandbox_root.iterdir())
            for run_dir in run_dirs:
                variant_dirs = list(run_dir.iterdir())
                self.assertEqual(variant_dirs, [],
                                 f"sandbox 应被清空,实际有: {variant_dirs}")
        # snapshot.json 仍保留 (snapshot 不被 cleanup 影响)
        snapshots_dir = self.exp / "results" / "snapshots"
        self.assertTrue(snapshots_dir.exists())
        run_dirs = list(snapshots_dir.iterdir())
        self.assertEqual(len(run_dirs), 1)
        self.assertTrue((run_dirs[0] / "V1.json").exists())

    def test_run_default_keeps_sandbox_dir(self):
        """C7: 不传 cleanup_sandboxes (默认 False) → sandbox dir 仍保留。"""
        self._write_v1(patch_section=(
            "## Patch\n\n"
            "files:\n"
            "  - target: agent.py\n"
            "    source: patches/V1/agent.py\n\n"
            f'start_command: "{self.python}" agent.py\n'))

        import contextlib
        import io as _io
        with contextlib.redirect_stdout(_io.StringIO()):
            run(self.exp, use_llm=False)  # 默认 cleanup_sandboxes=False

        sandbox_root = self.exp / "sandbox"
        self.assertTrue(sandbox_root.exists())
        run_dirs = list(sandbox_root.iterdir())
        self.assertEqual(len(run_dirs), 1)
        variant_dirs = list(run_dirs[0].iterdir())
        self.assertEqual(len(variant_dirs), 1)   # V1 sandbox 仍在
        self.assertTrue((variant_dirs[0] / "agent.py").exists())

    def test_preflight_rejects_missing_start_command(self):
        """patch.start_command 缺 → preflight 拒 (M1 不假设默认命令)。"""
        self._write_v1(patch_section=(
            "## Patch\n\n"
            "files:\n"
            "  - target: agent.py\n"
            "    source: patches/V1/agent.py\n"))   # 没 start_command
        with self.assertRaises(WorkflowError) as ctx:
            run(self.exp, use_llm=False)
        msg = str(ctx.exception)
        self.assertIn("start_command", msg)

    def test_preflight_rejects_missing_patch_source_file(self):
        """patch.files[i].source 文件不存在 → preflight 拒。"""
        self._write_v1(patch_section=(
            "## Patch\n\n"
            "files:\n"
            "  - target: agent.py\n"
            "    source: patches/V1/nonexistent.py\n\n"
            f'start_command: "{self.python}" agent.py\n'))
        with self.assertRaises(WorkflowError) as ctx:
            run(self.exp, use_llm=False)
        msg = str(ctx.exception)
        self.assertIn("source 文件不存在", msg)


# ---- Runtime Materialization git_repo (C6) ----


class TestRuntimeSourceGitRepoPreflight(unittest.TestCase):
    """C6: git_repo runtime_source 通过 preflight + materialize (clone+checkout)
    + 走完整 run/snapshot 链路。本地 git init mock repo,不联网。
    """

    def setUp(self) -> None:
        import subprocess as sp
        import sys
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.exp = self.root / "experiments" / "001-gr"
        self.exp.mkdir(parents=True)
        (self.exp / "program.md").write_text(
            "# program\n\n## 假设\ngit_repo。\n\n## 声明\n"
            "- 环境:无\n- 对话模式:模拟\n- 状态:重置\n"
            "- 评分:本地桩\n- 运行模式:人评\n- 对比方式:对基线\n\n"
            "## 留/丢规则\n人评。\n\n## 喊人规则\n人评。\n",
            encoding="utf-8")
        (self.exp / "rubric.md").write_text(
            "## 准确\n权重: 1.0\n判甲。\n", encoding="utf-8")
        (self.exp / "harnesses").mkdir()
        (self.exp / "cases").mkdir()
        (self.exp / "cases" / "D-01.md").write_text(
            "---\nid: D-01\n---\n## 起始输入\nhi\n", encoding="utf-8")

        # mock git repo 含 echo agent
        echo_script = """import json, sys
for line in sys.stdin:
    data = json.loads(line)
    sys.stdout.write(json.dumps({"response": "git-echo:" + data["input"]}) + "\\n")
    sys.stdout.flush()
"""
        self.repo = self.root / "mock-repo"
        self.repo.mkdir()
        sp.run(["git", "init", "-b", "main", str(self.repo)],
               check=True, capture_output=True)
        sp.run(["git", "-C", str(self.repo), "config", "user.email", "t@t"],
               check=True, capture_output=True)
        sp.run(["git", "-C", str(self.repo), "config", "user.name", "t"],
               check=True, capture_output=True)
        (self.repo / "agent.py").write_text(echo_script, encoding="utf-8")
        sp.run(["git", "-C", str(self.repo), "add", "."],
               check=True, capture_output=True)
        sp.run(["git", "-C", str(self.repo), "commit", "-m", "init"],
               check=True, capture_output=True)

        # runtime-sources.md 声明 git_repo source
        (self.root / "runtime-sources.md").write_text(
            f"## git-src\n"
            f"type: git_repo\n"
            f"url: {self.repo}\n"
            f"ref: main\n",
            encoding="utf-8")

        # patches/V1/agent.py (覆盖)
        patches = self.exp / "patches" / "V1"
        patches.mkdir(parents=True)
        patched = """import json, sys
for line in sys.stdin:
    data = json.loads(line)
    sys.stdout.write(json.dumps({"response": "patched-git:" + data["input"]}) + "\\n")
    sys.stdout.flush()
"""
        (patches / "agent.py").write_text(patched, encoding="utf-8")
        self.python = sys.executable

    def _write_v1(self):
        (self.exp / "harnesses" / "V1.md").write_text(
            "---\n"
            "id: V1\n"
            "基线: 是\n"
            "runtime_source: git-src\n"
            "---\n"
            "## 这是什么\ngit_repo variant。\n\n"
            "## Patch\n\n"
            "files:\n"
            "  - target: agent.py\n"
            "    source: patches/V1/agent.py\n\n"
            f'start_command: "{self.python}" agent.py\n',
            encoding="utf-8")

    def test_run_passes_preflight_and_writes_materialized_snapshot(self):
        """端到端: workflow.run 跑 git_repo,snapshot.json 含 commit_sha +
        source_dir_hash + harness_patch + sandbox.type=git_clone。"""
        self._write_v1()
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = run(self.exp, use_llm=False)

        self.assertGreater(result.ok, 0,
                           f"run failed: {result.errors};stdout: {buf.getvalue()}")

        # snapshot.json 落盘
        snapshots_dir = self.exp / "results" / "snapshots"
        run_dirs = list(snapshots_dir.iterdir())
        self.assertEqual(len(run_dirs), 1)
        v1_snap = run_dirs[0] / "V1.json"
        self.assertTrue(v1_snap.exists())

        # 字段完整性: git_repo schema 必含 commit_sha + source_dir_hash
        data = json.loads(v1_snap.read_text(encoding="utf-8"))
        self.assertTrue(data["snapshot_id"].startswith("snap-"))
        self.assertEqual(data["runtime_source"]["type"], "git_repo")
        self.assertEqual(data["runtime_source"]["name"], "git-src")
        self.assertEqual(data["runtime_source"]["url"], str(self.repo))
        self.assertEqual(data["runtime_source"]["ref"], "main")
        self.assertEqual(len(data["runtime_source"]["commit_sha"]), 40)
        self.assertTrue(
            data["runtime_source"]["source_dir_hash"].startswith("sha256:"))
        self.assertIsNotNone(data["harness_patch"])
        self.assertTrue(
            data["harness_patch"]["patch_hash"].startswith("sha256:"))
        self.assertEqual(len(data["harness_patch"]["applied"]), 1)
        self.assertIsNotNone(data["sandbox"])
        self.assertEqual(data["sandbox"]["type"], "git_clone")

    def test_run_with_cleanup_sandboxes_removes_git_sandbox(self):
        """C7: cleanup_sandboxes=True → git_repo sandbox (含 .git) 整个被 rmtree。"""
        self._write_v1()
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = run(self.exp, use_llm=False, cleanup_sandboxes=True)

        self.assertGreater(result.ok, 0,
                           f"run failed: {result.errors};stdout: {buf.getvalue()}")

        # sandbox dir 应被清 (含 .git)
        sandbox_root = self.exp / "sandbox"
        if sandbox_root.exists():
            run_dirs = list(sandbox_root.iterdir())
            for run_dir in run_dirs:
                variant_dirs = list(run_dir.iterdir())
                self.assertEqual(variant_dirs, [])
        # snapshot.json 仍保留
        snapshots_dir = self.exp / "results" / "snapshots"
        self.assertTrue(snapshots_dir.exists())


if __name__ == "__main__":
    unittest.main()
