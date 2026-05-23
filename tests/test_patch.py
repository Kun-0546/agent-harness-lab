"""patch.py — parse_patch:## Patch 段 YAML-like 解析。

覆盖 spec §5 test matrix 的 test 6。
"""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.patch import HarnessPatch, PatchFile, parse_patch


class TestParsePatch(unittest.TestCase):
    """spec §1.2 / §5 test 6:files + env + start_command 三段。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # 模拟 experiment_dir;在它下面创建 patches/V2/ 含两个 patch 文件
        self.exp_dir = Path(self._tmp.name)
        patches_dir = self.exp_dir / "patches" / "V2"
        patches_dir.mkdir(parents=True)
        (patches_dir / "system.md").write_text(
            "custom system prompt", encoding="utf-8")
        (patches_dir / "tools.yaml").write_text(
            "custom tools config", encoding="utf-8")

    def test_full_patch(self):
        """files + env + start_command 全部解析正确。"""
        text = """
files:
  - target: prompts/system.md
    source: patches/V2/system.md
  - target: config/tools.yaml
    source: patches/V2/tools.yaml

env:
  HARNESS_MAX_DEPTH: "5"
  HARNESS_TEMPERATURE: "0.7"

start_command: python -m openmanus.agent
"""
        patch = parse_patch(text, self.exp_dir)
        self.assertEqual(len(patch.files), 2)
        self.assertEqual(patch.files[0].target_path, "prompts/system.md")
        self.assertEqual(
            patch.files[0].source_path,
            self.exp_dir / "patches" / "V2" / "system.md",
        )
        self.assertTrue(patch.files[0].hash.startswith("sha256:"))
        self.assertEqual(patch.files[1].target_path, "config/tools.yaml")
        self.assertTrue(patch.files[1].hash.startswith("sha256:"))
        self.assertEqual(patch.env["HARNESS_MAX_DEPTH"], "5")
        self.assertEqual(patch.env["HARNESS_TEMPERATURE"], "0.7")
        self.assertEqual(patch.start_command, "python -m openmanus.agent")

    def test_only_start_command(self):
        """只有 start_command;files/env 为空。"""
        patch = parse_patch("start_command: python -m foo\n", self.exp_dir)
        self.assertEqual(patch.files, [])
        self.assertEqual(patch.env, {})
        self.assertEqual(patch.start_command, "python -m foo")

    def test_empty_text_yields_empty_patch(self):
        """空 patch 段 → 空 HarnessPatch。"""
        patch = parse_patch("", self.exp_dir)
        self.assertEqual(patch.files, [])
        self.assertEqual(patch.env, {})
        self.assertIsNone(patch.start_command)

    def test_validate_catches_missing_start_command(self):
        """validate:start_command 必填(M1 不假设默认命令)。"""
        patch = parse_patch("", self.exp_dir)
        problems = patch.validate()
        self.assertTrue(any("start_command" in p for p in problems))

    def test_validate_catches_missing_source_file(self):
        """patch source 文件不存在 → validate 报问题。"""
        text = """files:
  - target: prompts/system.md
    source: patches/V2/nonexistent.md

start_command: cmd
"""
        patch = parse_patch(text, self.exp_dir)
        problems = patch.validate()
        self.assertTrue(any("source 文件不存在" in p for p in problems))

    def test_hash_stable_across_parses(self):
        """同样的 source 内容 → 同样的 hash(deterministic)。"""
        text = """files:
  - target: prompts/system.md
    source: patches/V2/system.md

start_command: cmd
"""
        patch1 = parse_patch(text, self.exp_dir)
        patch2 = parse_patch(text, self.exp_dir)
        self.assertEqual(patch1.files[0].hash, patch2.files[0].hash)
        self.assertNotEqual(patch1.files[0].hash, "")

    def test_env_quote_stripped(self):
        """env 值的双引号/单引号会被去掉。"""
        text = """env:
  KEY1: "value-with-quotes"
  KEY2: 'single-quoted'
  KEY3: raw-no-quotes

start_command: cmd
"""
        patch = parse_patch(text, self.exp_dir)
        self.assertEqual(patch.env["KEY1"], "value-with-quotes")
        self.assertEqual(patch.env["KEY2"], "single-quoted")
        self.assertEqual(patch.env["KEY3"], "raw-no-quotes")


if __name__ == "__main__":
    unittest.main()
