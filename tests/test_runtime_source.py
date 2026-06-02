"""runtime_source.py — parse_runtime_sources + validate_variant_source_refs。

覆盖 spec §5 test matrix 的 test 1/2/3/7。
"""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.runtime_source import (
    RuntimeSource,
    parse_runtime_sources,
    validate_variant_source_refs,
)


class _MdCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _md(self, content: str) -> Path:
        p = Path(self._tmp.name) / "runtime-sources.md"
        p.write_text(content, encoding="utf-8")
        return p


class TestParseRuntimeSources(_MdCase):
    """spec §1.1。"""

    def test_mixed_types(self):
        """test 1:local_path + git_repo 混合。"""
        p = self._md(
            "# runtime sources\n\n"
            "## openmanus-main\n"
            "type: git_repo\n"
            "url: https://example.com/openmanus.git\n"
            "ref: main\n\n"
            "## local-aider\n"
            "type: local_path\n"
            "path: /tmp/aider-src\n"
        )
        sources = parse_runtime_sources(p)
        self.assertEqual(len(sources), 2)
        by = {s.name: s for s in sources}
        self.assertEqual(by["openmanus-main"].type, "git_repo")
        self.assertEqual(
            by["openmanus-main"].config["url"],
            "https://example.com/openmanus.git",
        )
        self.assertEqual(by["openmanus-main"].config["ref"], "main")
        self.assertEqual(by["local-aider"].type, "local_path")
        self.assertEqual(by["local-aider"].config["path"], "/tmp/aider-src")

    def test_local_path_missing_path_caught_by_validate(self):
        """test 2a:local_path 缺 path → validate() 报问题(parse 不抛错)。"""
        p = self._md("## bad\ntype: local_path\n")
        sources = parse_runtime_sources(p)
        self.assertEqual(len(sources), 1)
        problems = sources[0].validate()
        self.assertTrue(any("path" in pr for pr in problems))

    def test_git_repo_missing_url_caught_by_validate(self):
        """test 2b:git_repo 缺 url → validate() 报问题。"""
        p = self._md("## bad\ntype: git_repo\nref: main\n")
        sources = parse_runtime_sources(p)
        problems = sources[0].validate()
        self.assertTrue(any("url" in pr for pr in problems))

    def test_git_repo_missing_ref_caught_by_validate(self):
        """test 2b':git_repo 缺 ref → validate() 报问题。"""
        p = self._md("## bad\ntype: git_repo\nurl: https://example.com/a.git\n")
        sources = parse_runtime_sources(p)
        problems = sources[0].validate()
        self.assertTrue(any("ref" in pr for pr in problems))

    def test_unknown_type_raises(self):
        """test 2c:unknown type → parse 阶段抛 ValueError(M1 硬边界)。"""
        p = self._md("## bad\ntype: docker_image\nimage: foo\n")
        with self.assertRaises(ValueError) as ctx:
            parse_runtime_sources(p)
        self.assertIn("docker_image", str(ctx.exception))

    def test_file_not_exists_returns_empty(self):
        """test 3:文件不存在 → 返回空 list,不抛错(legacy 路径全用)。"""
        missing = Path(self._tmp.name) / "absent.md"
        self.assertEqual(parse_runtime_sources(missing), [])

    def test_file_exists_but_no_sections_raises(self):
        """文件存在但 0 个 source 段 → 抛 ValueError(避免空文件 misleading)。"""
        p = self._md("# runtime sources\n\n(none yet)\n")
        with self.assertRaises(ValueError) as ctx:
            parse_runtime_sources(p)
        self.assertIn("没有 source 段", str(ctx.exception))

    def test_duplicate_source_name_raises(self):
        """C2 cleanup:source name 必 unique;重复 ## heading → ValueError。"""
        p = self._md(
            "## openmanus\n"
            "type: git_repo\n"
            "url: https://example.com/a.git\n"
            "ref: main\n\n"
            "## openmanus\n"
            "type: local_path\n"
            "path: /tmp/other\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse_runtime_sources(p)
        msg = str(ctx.exception)
        self.assertIn("重复", msg)
        self.assertIn("openmanus", msg)

    def test_local_path_unknown_field_raises(self):
        """C2 cleanup:local_path 只允许 type/path;含未知字段 → ValueError。"""
        p = self._md(
            "## bad\n"
            "type: local_path\n"
            "path: /tmp/x\n"
            "ref: main\n"  # ref 是 git_repo 字段,不该出现在 local_path
        )
        with self.assertRaises(ValueError) as ctx:
            parse_runtime_sources(p)
        msg = str(ctx.exception)
        self.assertIn("未知字段", msg)
        self.assertIn("ref", msg)
        self.assertIn("local_path", msg)

    def test_git_repo_unknown_field_raises(self):
        """C2 cleanup:git_repo 只允许 type/url/ref;含未知字段 → ValueError。"""
        p = self._md(
            "## bad\n"
            "type: git_repo\n"
            "url: https://example.com/a.git\n"
            "ref: main\n"
            "branch: feature\n"  # branch 不是 git_repo 允许字段
            "image: foo\n"       # image 也不是
        )
        with self.assertRaises(ValueError) as ctx:
            parse_runtime_sources(p)
        msg = str(ctx.exception)
        self.assertIn("未知字段", msg)
        # 多个 unknown 字段都该在错误信息里
        self.assertIn("branch", msg)
        self.assertIn("image", msg)


class TestValidateVariantSourceRefs(unittest.TestCase):
    """spec §5 test 7:cross-validation variant 的 runtime_source 引用。"""

    def test_all_refs_present(self):
        sources = [RuntimeSource("openmanus", "git_repo", {})]
        refs = [("V1", "openmanus"), ("V2", "openmanus")]
        self.assertEqual(validate_variant_source_refs(refs, sources), [])

    def test_legacy_refs_skipped(self):
        """runtime_source=None 时跳过(legacy 路径)。"""
        sources = [RuntimeSource("openmanus", "git_repo", {})]
        refs = [("V1", None), ("V2", "openmanus")]
        self.assertEqual(validate_variant_source_refs(refs, sources), [])

    def test_missing_ref_caught(self):
        """variant 引用了不存在的 source → 报问题。"""
        sources = [RuntimeSource("openmanus", "git_repo", {})]
        refs = [("V1", "openmanus"), ("V2", "nonexistent")]
        problems = validate_variant_source_refs(refs, sources)
        self.assertEqual(len(problems), 1)
        self.assertIn("V2", problems[0])
        self.assertIn("nonexistent", problems[0])
        self.assertIn("openmanus", problems[0])  # 可用列表里展示

    def test_empty_sources_with_legacy_variants_ok(self):
        """所有 variant 都 legacy + sources 列表空 → 无问题。"""
        refs = [("V1", None), ("V2", None)]
        self.assertEqual(validate_variant_source_refs(refs, []), [])

    def test_empty_sources_with_referencing_variant_caught(self):
        """sources 空但 variant 引用了一个名字 → 报问题(指出'空')。"""
        refs = [("V1", "openmanus")]
        problems = validate_variant_source_refs(refs, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("(空)", problems[0])


if __name__ == "__main__":
    unittest.main()
