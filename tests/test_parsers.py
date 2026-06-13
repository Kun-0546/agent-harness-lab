"""文件解析器单测 —— connect。

其余 v0.x 解析器(program / rubric / version / testset / brief)随 Stack A
在 PR9 一并退役删除;connect 仍是 v1 活代码,保留其解析器测试。
"""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.connect import parse_connect


class _MdCase(unittest.TestCase):
    """带临时目录的基类:_md(内容) 写一个临时 .md、返回路径。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _md(self, content: str) -> Path:
        p = Path(self._tmp.name) / "f.md"
        p.write_text(content, encoding="utf-8")
        return p


class TestConnect(_MdCase):
    def test_parse(self):
        c = parse_connect(self._md("## 类型\n外部命令行\n\n## 配置\n命令:py x.py\n"))
        self.assertEqual(c.conn_type, "外部命令行")
        self.assertEqual(c.config, "命令:py x.py")
        self.assertEqual(c.validate(), [])

    def test_validate_bad_type(self):
        c = parse_connect(self._md("## 类型\n瞎写\n\n## 配置\n命令:x\n"))
        self.assertTrue(any("识别不了" in p for p in c.validate()))


if __name__ == "__main__":
    unittest.main()
