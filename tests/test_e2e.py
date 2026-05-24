"""端到端测试 —— 跑通 run → score → compare,workflow 层和 CLI 层各一遍。

把一直手跑的 smoke 固化成自动化测试:临时工作区里搭一个最小实验,
用一个进程内桩 agent,过一遍 run / score / compare,断言每步产出。
全程走本地桩,不碰真模型。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import cli, workflow

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
        (self.exp / "cases").mkdir(parents=True)
        (self.exp / "harnesses").mkdir()
        (self.exp / "program.md").write_text(_PROGRAM, encoding="utf-8")
        (self.exp / "rubric.md").write_text(_RUBRIC, encoding="utf-8")
        (self.exp / "harnesses" / "V1.md").write_text(_V1, encoding="utf-8")
        (self.exp / "harnesses" / "V2.md").write_text(_V2, encoding="utf-8")
        (self.exp / "cases" / "D-01.md").write_text(_CASE, encoding="utf-8")

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

        # C4:run-*.json 每条 record 有 snapshot_id;legacy 路径固定 "legacy"
        run_data = json.loads(run.out_path.read_text(encoding="utf-8"))
        self.assertEqual(len(run_data), 2)
        for rec in run_data:
            self.assertIn("snapshot_id", rec)
            self.assertEqual(rec["snapshot_id"], "legacy")

        # C4:每个 variant 产出 snapshot.json,落 results/snapshots/<run_id>/<vid>.json
        run_id = run.out_path.stem   # "run-<timestamp>"
        snap_dir = self.exp / "results" / "snapshots" / run_id
        self.assertTrue(snap_dir.is_dir(), f"snapshots dir not found: {snap_dir}")
        snap_files = sorted(p.name for p in snap_dir.glob("*.json"))
        self.assertEqual(snap_files, ["V1.json", "V2.json"])

        # snapshot.json 内容:type=legacy_connect + connect_md_hash 是 sha256
        v1_snap = json.loads((snap_dir / "V1.json").read_text(encoding="utf-8"))
        self.assertEqual(v1_snap["snapshot_id"], "legacy")
        self.assertEqual(v1_snap["variant_id"], "V1")
        self.assertEqual(v1_snap["runtime_source"]["type"], "legacy_connect")
        self.assertTrue(
            v1_snap["runtime_source"]["connect_md_hash"].startswith("sha256:"))
        self.assertIsNone(v1_snap["harness_patch"])
        self.assertIsNone(v1_snap["sandbox"])

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


class TestExternalAgentAuthoring(unittest.TestCase):
    """V2:模拟外层 coding agent 据 brief.md 写文件 → ahl review → run/score/compare。

    AHL 不调模型起草 —— 这里测试代码直接 write_text 扮演那个外层 agent
    (Claude Code / Cursor / Codex)。证 v2-minimal 的真实使用路径:
    scaffold(ahl draft)→ 人填 brief → agent 起草 → ahl review → v1 管线。
    """

    BRIEF = (
        "# brief — demo\n\n"
        "## 想优化什么\n让 agent 回答更简洁\n\n"
        "## 验证什么改动\n砍掉开场寒暄\n\n"
        "## 最在意什么\n回答密度\n\n"
        "## 不能牺牲什么\n不能漏关键信息\n\n"
        "## 怎么比\n对基线\n"
    )

    # 「外层 agent 起草」的产物 —— 实际项目里由 Claude Code / Cursor 写。
    AUTHORED_PROGRAM = (
        "# 实验 001-demo · program\n\n"
        "## 假设\n砍掉开场寒暄,看是否让回答更简洁、不漏要点。\n\n"
        "## 声明\n"
        "- 环境:无\n- 对话模式:模拟\n- 状态:重置\n"
        "- 评分:本地桩\n- 运行模式:人评\n- 对比方式:对基线\n\n"
        "## 留/丢规则\n人评模式,留空。\n\n"
        "## 喊人规则\n人评模式,留空。\n"
    )
    AUTHORED_V1 = "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线版:含开场寒暄。\n"
    AUTHORED_V2 = "---\nid: V2\n基线: 否\n---\n## 这是什么\n改版:砍掉开场寒暄。\n"
    AUTHORED_CASE = ("---\nid: D-01\nmax_turns: 3\n---\n"
                     "## 起始输入\n帮我列个搬家清单。\n\n## 完成标准\n有可执行步骤。\n")
    AUTHORED_RUBRIC = (
        "# rubric\n\n"
        "## 信息密度\n权重: 0.6\n同字数说清更多。\n\n"
        "## 关键信息保留\n权重: 0.4\n来自 brief 红线:不能漏关键信息。\n"
    )
    AUTHORED_SIMULATOR = (
        "# simulator\n\n## 人设\n一个普通用户,沟通直接。\n\n"
        "## 背景知识\n(无)\n\n## 追问策略\n盯没答透的点追问两三轮。\n"
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

    def test_external_agent_authoring_e2e(self) -> None:
        original = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, original)
        exp = self.root / "experiments" / "001-demo"
        with contextlib.redirect_stdout(io.StringIO()):
            # 1. ahl draft —— 只 scaffold,不调模型
            self.assertEqual(cli.main(["draft", "demo"]), 0)
            self.assertTrue((exp / "brief.md").exists())
            # scaffold-only:program 等等都没起草
            self.assertFalse((exp / "program.md").exists())

            # 2. 人填 brief.md
            (exp / "brief.md").write_text(self.BRIEF, encoding="utf-8")

            # 3. 没 author 前跑 ahl review —— 宽松,出 review.md,标 5 个「未起草」
            self.assertEqual(cli.main(["review", "demo"]), 0)
            review_text = (exp / "review.md").read_text(encoding="utf-8")
            self.assertIn("未起草", review_text)
            self.assertIn("brief.md:human", review_text)

            # 4. 模拟外层 coding agent 据 brief.md 起草整套产物
            (exp / "program.md").write_text(self.AUTHORED_PROGRAM, encoding="utf-8")
            (exp / "harnesses" / "V1.md").write_text(self.AUTHORED_V1, encoding="utf-8")
            (exp / "harnesses" / "V2.md").write_text(self.AUTHORED_V2, encoding="utf-8")
            (exp / "cases" / "D-01.md").write_text(self.AUTHORED_CASE, encoding="utf-8")
            (exp / "rubric.md").write_text(self.AUTHORED_RUBRIC, encoding="utf-8")
            (exp / "simulator.md").write_text(self.AUTHORED_SIMULATOR, encoding="utf-8")

            # 5. 再跑 ahl review —— 都齐了,review.md 不再有「未起草」
            self.assertEqual(cli.main(["review", "demo"]), 0)
            review_text = (exp / "review.md").read_text(encoding="utf-8")
            self.assertNotIn("未起草", review_text)
            self.assertIn("external_agent_drafted", review_text)
            self.assertIn("D-01", review_text)        # cases 清单
            self.assertIn("信息密度", review_text)     # rubric 维度

            # 6. v1 管线:run / score / compare 不区分文件来源
            self.assertEqual(cli.main(["run", "001"]), 0)
            self.assertEqual(cli.main(["score", "001"]), 0)
            self.assertEqual(cli.main(["compare", "001"]), 0)

        self.assertTrue(list((exp / "results").glob("compare-*.md")))


if __name__ == "__main__":
    unittest.main()
