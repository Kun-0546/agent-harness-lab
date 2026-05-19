"""designer 的单测 —— 桩 Designer 的产物结构、模型未配置时报错。"""
import os
import unittest
from pathlib import Path

from harness_design_loop.brief import Brief
from harness_design_loop.designer import DesignerError, design, stub_designer


def _brief() -> Brief:
    return Brief(path=Path("brief.md"), optimize="让回答更简洁",
                 change="砍掉开场寒暄", care="回答密度", redlines="不能漏关键信息")


class TestStubDesigner(unittest.TestCase):
    def test_package_shape(self):
        pkg = stub_designer(_brief(), "把 agent 做成一个好顾问")
        self.assertIn("## 假设", pkg.program)
        self.assertIn("## 声明", pkg.program)
        self.assertEqual(set(pkg.versions), {"V1.md", "V2.md"})
        self.assertTrue(pkg.cases)
        self.assertIn("权重", pkg.rubric)
        self.assertIn("人设", pkg.simulator)

    def test_uses_brief_content(self):
        # brief 的「验证什么改动」应进 program 假设
        pkg = stub_designer(_brief(), "")
        self.assertIn("砍掉开场寒暄", pkg.program)

    def test_respects_brief_compare(self):
        # 填了「怎么比」→ stub 起草的 program 跟着走(线性迭代/对基线在 stub 里只此一处)
        b = Brief(path=Path("brief.md"), optimize="x", change="y",
                  care="z", redlines="w", compare="线性迭代")
        self.assertIn("线性迭代", stub_designer(b, "").program)
        # 没填(_brief() 不带 compare)→ 默认对基线
        self.assertIn("对基线", stub_designer(_brief(), "").program)


class TestDesignerDispatch(unittest.TestCase):
    def test_llm_without_env_raises(self):
        # 没配 HDL_DESIGNER_* 时,走真 Designer 应抛 DesignerError
        saved = {k: os.environ.pop(k, None) for k in
                 ("HDL_DESIGNER_BASE_URL", "HDL_DESIGNER_MODEL", "HDL_DESIGNER_API_KEY")}
        try:
            with self.assertRaises(DesignerError):
                design(_brief(), "目标", use_llm=True)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
