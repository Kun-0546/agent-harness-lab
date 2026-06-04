"""Concept-hygiene gate: no legacy/confusing terms in the v1 public surface.

Banned in scaffolded files and CLI output. Old INTERNAL modules may still use
legacy terms during migration and are NOT scanned here.
"""
import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli, scaffold

BANNED = ["variant", "program.md", "decision.md", "hdl", "harness-packages"]


class TestPublicVocabulary(unittest.TestCase):
    def _assert_clean(self, text: str, where: str) -> None:
        low = text.lower()
        for term in BANNED:
            self.assertNotIn(term, low, f"banned term '{term}' leaked into {where}")

    def test_scaffolded_files_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            scaffold.init_workspace(root)
            scaffold.new_experiment(root, "skill-creator-ab")
            scaffold.new_experiment(root, "memcmp", run_mode="auto", execution_mode="longitudinal")
            files = [p for p in root.rglob("*") if p.is_file()]
            self.assertTrue(files, "scaffold produced no files")
            for p in files:
                try:
                    text = p.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                self._assert_clean(text, str(p.relative_to(root)))

    def test_cli_output_clean(self):
        tmp = tempfile.TemporaryDirectory()
        saved = os.getcwd()
        os.chdir(tmp.name)
        try:
            cmds = [
                ["--help"], ["init"], ["new", "demo"], ["review", "experiments/demo"],
                ["status", "demo"], ["run", "experiments/demo"], ["report", "experiments/demo"],
                ["new", "autox", "--mode", "auto"], ["review", "experiments/autox"],
            ]
            for argv in cmds:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    try:
                        cli.main(argv)
                    except SystemExit:
                        pass  # --help raises SystemExit under argparse
                self._assert_clean(out.getvalue() + err.getvalue(), f"CLI {' '.join(argv)}")
        finally:
            os.chdir(saved)
            tmp.cleanup()

    def test_no_old_subcommands_or_harness_packages_in_parser(self):
        p = cli.build_parser()
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction):
                choices = set(a.choices)
                self.assertNotIn("harness-packages", choices)
                self.assertEqual(choices, {"init", "new", "review", "run", "status",
                                           "report", "compare", "conclude"})


if __name__ == "__main__":
    unittest.main()
