"""端到端测试 —— 跑通 run → score → compare,workflow 层和 CLI 层各一遍。

把一直手跑的 smoke 固化成自动化测试:临时工作区里搭一个最小实验,
用一个进程内桩 agent,过一遍 run / score / compare,断言每步产出。
全程走本地桩,不碰真模型。
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

from harness_design_loop import cli, workflow

# 一个最小的「进程内库」agent —— 回显最后一句用户话。
_AGENT_MODULE = '''\
def respond(history):
    last = ""
    for turn in history:
        if turn.get("role") == "user":
            last = turn.get("content", "")
    return f"\\u6536\\u5230:{last}"
'''

_CONNECT = """# connect

## 类型
进程内库

## 配置
模块:e2e_stub_agent:respond
"""

_PROGRAM = """# 实验 001-e2e · program

## 假设
端到端测试:验证 run / score / compare 跑得通。

## 声明
- 环境:无
- 对话模式:模拟
- 状态:重置
- 评分:本地桩
- 运行模式:人评
- 对比方式:对基线

## 留/丢规则
人评模式,留空。

## 喊人规则
人评模式,留空。
"""

_RUBRIC = """# rubric

## 相关性
权重: 0.5
回答扣不扣题。

## 完整度
权重: 0.5
要点说全没有。
"""

_V1 = "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线版。\n"
_V2 = "---\nid: V2\n基线: 否\n---\n## 这是什么\n对照版。\n"
_CASE = ("---\nid: D-01\nmax_turns: 3\n---\n"
         "## 起始输入\n帮我列个计划。\n\n## 完成标准\n有步骤。\n")


class TestEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        # 桩 agent 模块,放进工作区根并挂上 import 路径
        (self.root / "e2e_stub_agent.py").write_text(_AGENT_MODULE, encoding="utf-8")
        sys.path.insert(0, str(self.root))
        self.addCleanup(lambda: sys.path.remove(str(self.root)))
        self.addCleanup(lambda: sys.modules.pop("e2e_stub_agent", None))

        (self.root / "connect.md").write_text(_CONNECT, encoding="utf-8")
        self.exp = self.root / "experiments" / "001-e2e"
        (self.exp / "测试集").mkdir(parents=True)
        (self.exp / "versions").mkdir()
        (self.exp / "program.md").write_text(_PROGRAM, encoding="utf-8")
        (self.exp / "rubric.md").write_text(_RUBRIC, encoding="utf-8")
        (self.exp / "versions" / "V1.md").write_text(_V1, encoding="utf-8")
        (self.exp / "versions" / "V2.md").write_text(_V2, encoding="utf-8")
        (self.exp / "测试集" / "D-01.md").write_text(_CASE, encoding="utf-8")

    def test_workflow_run_score_compare(self) -> None:
        """workflow 层:直接调 run / score / compare。"""
        with contextlib.redirect_stdout(io.StringIO()):
            run = workflow.run(self.exp, use_llm=False)
            score = workflow.score(self.exp, use_llm=False)
            comp = workflow.compare(self.exp)

        self.assertEqual(run.total, 2)
        self.assertEqual(run.failed, 0)
        self.assertTrue(run.out_path.exists())
        self.assertEqual(len(score.by_version), 2)
        self.assertTrue(score.out_path.exists())
        self.assertIn("V1", comp.report_text)
        self.assertIn("V2", comp.report_text)
        self.assertTrue(comp.out_path.exists())

    def test_cli_run_score_compare(self) -> None:
        """CLI 层:走 cli.main 真入口(argparse + cmd_ 包装)。"""
        original = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, original)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["run", "001"]), 0)
            self.assertEqual(cli.main(["score", "001"]), 0)
            self.assertEqual(cli.main(["compare", "001"]), 0)
        results = self.exp / "results"
        self.assertTrue(list(results.glob("run-*.json")))
        self.assertTrue(list(results.glob("score-*.json")))
        self.assertTrue(list(results.glob("compare-*.md")))


class TestDraftEndToEnd(unittest.TestCase):
    """V2:hdl draft 两阶段(stub Designer)→ 起草出的实验直接 run / score / compare。"""

    BRIEF = (
        "# brief — demo\n\n"
        "## 想优化什么\n让 agent 回答更简洁\n\n"
        "## 验证什么改动\n砍掉开场寒暄\n\n"
        "## 最在意什么\n回答密度\n\n"
        "## 不能牺牲什么\n不能漏关键信息\n\n"
        "## 怎么比\n对基线\n"
    )

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        (self.root / "e2e_stub_agent.py").write_text(_AGENT_MODULE, encoding="utf-8")
        sys.path.insert(0, str(self.root))
        self.addCleanup(lambda: sys.path.remove(str(self.root)))
        self.addCleanup(lambda: sys.modules.pop("e2e_stub_agent", None))

        (self.root / "connect.md").write_text(_CONNECT, encoding="utf-8")
        (self.root / "goal.md").write_text(
            "# goal\n把 agent 做成简洁、可靠的助手。\n", encoding="utf-8")

    def test_draft_then_run(self) -> None:
        original = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, original)
        exp = self.root / "experiments" / "001-demo"
        with contextlib.redirect_stdout(io.StringIO()):
            # 首阶段:建 brief.md
            self.assertEqual(cli.main(["draft", "demo"]), 0)
            self.assertTrue((exp / "brief.md").exists())
            # 人填 brief.md
            (exp / "brief.md").write_text(self.BRIEF, encoding="utf-8")
            # 次阶段:stub Designer 起草整套实验
            self.assertEqual(cli.main(["draft", "demo"]), 0)
            # 起草出的实验应能直接跑通
            self.assertEqual(cli.main(["run", "001"]), 0)
            self.assertEqual(cli.main(["score", "001"]), 0)
            self.assertEqual(cli.main(["compare", "001"]), 0)
        self.assertTrue((exp / "program.md").exists())
        self.assertTrue((exp / "review.md").exists())
        # review.md 列出每个 case 的起始输入,不只写 case 数
        self.assertIn("D-01", (exp / "review.md").read_text(encoding="utf-8"))
        self.assertTrue(list((exp / "results").glob("compare-*.md")))

    def test_force_redraft_cleans_stale(self) -> None:
        """--force 重起草前清掉上一轮残留的 case / version 文件。"""
        original = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, original)
        exp = self.root / "experiments" / "001-demo"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["draft", "demo"]), 0)
            (exp / "brief.md").write_text(self.BRIEF, encoding="utf-8")
            self.assertEqual(cli.main(["draft", "demo"]), 0)
            # 塞两个上一轮残留的文件,模拟「这轮 Designer 不再生成它们」
            (exp / "测试集" / "D-99.md").write_text(
                "---\nid: D-99\n---\n## 起始输入\n陈年旧 case。\n", encoding="utf-8")
            (exp / "versions" / "V9.md").write_text(
                "---\nid: V9\n基线: 否\n---\n## 这是什么\n陈年旧版本。\n",
                encoding="utf-8")
            # --force 重起草:旧残留该被清掉
            self.assertEqual(cli.main(["draft", "demo", "--force"]), 0)
        self.assertFalse((exp / "测试集" / "D-99.md").exists())
        self.assertFalse((exp / "versions" / "V9.md").exists())
        self.assertTrue((exp / "测试集" / "D-01.md").exists())   # 新草案还在


if __name__ == "__main__":
    unittest.main()
