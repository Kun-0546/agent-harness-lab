"""CI workflow drift guard — rc2 spec R2 锁定的矩阵形态。

钉住:矩阵 = [ubuntu-latest, macos-latest] × ["3.10","3.11","3.12"](6 jobs);
两个 verify 脚本步骤在 macOS BSD 工具链验证前仅跑 ubuntu(if 门控)。
"""
import unittest
from pathlib import Path

import yaml

WORKFLOW = (Path(__file__).resolve().parent.parent
            / ".github" / "workflows" / "test.yml")


class TestCiWorkflowMatrix(unittest.TestCase):

    def setUp(self):
        self.doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.job = self.doc["jobs"]["test"]

    def test_matrix_two_os_three_pythons(self):
        """矩阵 = 2 OS × 3 Python(R2 验收口径,共 6 jobs)。"""
        matrix = self.job["strategy"]["matrix"]
        self.assertEqual(matrix["os"], ["ubuntu-latest", "macos-latest"])
        self.assertEqual(matrix["python-version"], ["3.10", "3.11", "3.12"])

    def test_python_versions_are_strings(self):
        """版本号必须带引号成字符串,否则 YAML 把 3.10 解析成 3.1。"""
        for v in self.job["strategy"]["matrix"]["python-version"]:
            self.assertIsInstance(v, str)

    def test_runs_on_follows_matrix_os(self):
        """runs-on 跟随矩阵 os,不再硬编码 ubuntu-latest。"""
        self.assertEqual(self.job["runs-on"], "${{ matrix.os }}")

    def test_verify_steps_gated_to_ubuntu(self):
        """两个 verify 脚本步骤都有 ubuntu-only 门控(macOS 工具链未验证)。"""
        verify_steps = [s for s in self.job["steps"]
                        if "verify_" in s.get("run", "")]
        self.assertEqual(len(verify_steps), 2)
        for step in verify_steps:
            self.assertEqual(step.get("if"), "matrix.os == 'ubuntu-latest'",
                             f"step '{step.get('name')}' 缺 ubuntu-only 门控")

    def test_unit_tests_step_not_gated(self):
        """单测步骤必须在全矩阵跑,不允许被 os 门控。"""
        unit_steps = [s for s in self.job["steps"]
                      if "unittest" in s.get("run", "")]
        self.assertEqual(len(unit_steps), 1)
        self.assertNotIn("if", unit_steps[0])


if __name__ == "__main__":
    unittest.main()
