"""The v1 public CLI surface is exactly 6 `hlab` commands; `ahl` redirects."""
import argparse
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

from agent_harness_lab import cli

V1_COMMANDS = {"init", "new", "review", "run", "status", "report"}
OLD_COMMANDS = {
    "walkthrough", "connect", "show", "cases", "rubric", "simulator",
    "harnesses", "versions", "draft", "score", "compare", "probe",
}


def _subparser_choices(parser: argparse.ArgumentParser) -> set[str]:
    for a in parser._actions:
        if isinstance(a, argparse._SubParsersAction):
            return set(a.choices.keys())
    return set()


class TestSurface(unittest.TestCase):
    def test_prog_is_hlab(self):
        self.assertEqual(cli.build_parser().prog, "hlab")

    def test_exactly_six_commands(self):
        choices = _subparser_choices(cli.build_parser())
        self.assertEqual(choices, V1_COMMANDS,
                         f"public surface must be exactly {sorted(V1_COMMANDS)}, got {sorted(choices)}")

    def test_no_old_commands(self):
        choices = _subparser_choices(cli.build_parser())
        leaked = choices & OLD_COMMANDS
        self.assertEqual(leaked, set(), f"old v0.10 commands leaked into v1 surface: {leaked}")

    def test_help_no_args_returns_zero(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.main([])
        self.assertEqual(rc, 0)
        self.assertIn("hlab", out.getvalue())


class TestAhlRedirect(unittest.TestCase):
    def test_ahl_redirect_exit_1_with_message(self):
        saved = sys.argv
        sys.argv = ["ahl", "review", "foo"]
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                rc = cli.ahl_redirect()
        finally:
            sys.argv = saved
        self.assertEqual(rc, 1)
        text = err.getvalue()
        self.assertIn("hlab", text)
        self.assertIn("ahl", text)


if __name__ == "__main__":
    unittest.main()
