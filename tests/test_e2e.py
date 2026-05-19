"""端到端测试 —— 跑通 workflow.run → score → compare。

把一直手跑的 smoke 固化成自动化测试:临时工作区里搭一个最小实验,
用一个进程内桩 agent,过一遍 run / score / compare,断言每步产出。
全程走本地桩,不碰真模型。
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from harness_design_loop import workflow

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
        root = Path(self._tmp.name)

        # 桩 agent 模块,放进工作区根并挂上 import 路径
        (root / "e2e_stub_agent.py").write_text(_AGENT_MODULE, encoding="utf-8")
        sys.path.insert(0, str(root))
        self.addCleanup(lambda: sys.path.remove(str(root)))
        self.addCleanup(lambda: sys.modules.pop("e2e_stub_agent", None))

        (root / "connect.md").write_text(_CONNECT, encoding="utf-8")
        self.exp = root / "experiments" / "001-e2e"
        (self.exp / "测试集").mkdir(parents=True)
        (self.exp / "versions").mkdir()
        (self.exp / "program.md").write_text(_PROGRAM, encoding="utf-8")
        (self.exp / "rubric.md").write_text(_RUBRIC, encoding="utf-8")
        (self.exp / "versions" / "V1.md").write_text(_V1, encoding="utf-8")
        (self.exp / "versions" / "V2.md").write_text(_V2, encoding="utf-8")
        (self.exp / "测试集" / "D-01.md").write_text(_CASE, encoding="utf-8")

    def test_run_score_compare(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            run = workflow.run(self.exp, use_llm=False)
            score = workflow.score(self.exp, use_llm=False)
            comp = workflow.compare(self.exp)

        # run:2 版本 × 1 case,都成功
        self.assertEqual(run.total, 2)
        self.assertEqual(run.failed, 0)
        self.assertTrue(run.out_path.exists())

        # score:两个版本都打了分
        self.assertEqual(len(score.by_version), 2)
        self.assertTrue(score.out_path.exists())

        # compare:出了对比报告
        self.assertIn("V1", comp.report_text)
        self.assertIn("V2", comp.report_text)
        self.assertTrue(comp.out_path.exists())


if __name__ == "__main__":
    unittest.main()
