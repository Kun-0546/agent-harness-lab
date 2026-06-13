"""The v1 public CLI surface is exactly 9 `hlab` commands (8 + eval from v1.1 PR4);
`ahl` redirects."""
import argparse
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli

V1_COMMANDS = {"init", "new", "review", "run", "eval", "status", "report", "compare", "conclude"}
OLD_COMMANDS = {
    "walkthrough", "connect", "show", "cases", "rubric", "simulator",
    "harnesses", "versions", "draft", "score", "probe",
}


def _subparser_choices(parser: argparse.ArgumentParser) -> set[str]:
    for a in parser._actions:
        if isinstance(a, argparse._SubParsersAction):
            return set(a.choices.keys())
    return set()


class TestSurface(unittest.TestCase):
    def test_prog_is_hlab(self):
        self.assertEqual(cli.build_parser().prog, "hlab")

    def test_exactly_nine_commands(self):
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


class TestHelpPresentation(unittest.TestCase):
    """C1/C2: the top-level help states the object model, groups commands by
    loop stage, names the exit-code contract, and every per-command line shows
    its explicit object argument."""

    def _help(self) -> str:
        return cli.build_parser().format_help()

    def test_object_model_sentence_on_top(self):
        text = self._help()
        self.assertIn("exactly two objects", text)
        self.assertIn("WORKSPACE", text)
        self.assertIn("EXPERIMENT", text)
        self.assertIn("every other command acts on one experiment directory", text)

    def test_commands_grouped_by_loop_stage(self):
        text = self._help()
        self.assertIn("the experiment loop", text)
        for group in ("prepare", "gate & execute", "conclude"):
            self.assertIn(group, text)

    def test_exit_code_contract_in_help(self):
        text = self._help()
        self.assertIn("exit codes", text)
        self.assertIn("3  runtime failure", text)
        self.assertIn("2  not implemented", text)

    def test_each_experiment_command_help_line_names_its_object(self):
        # verb + explicit object argument + one-line user understanding
        text = self._help()
        for cmd in ("review", "run", "eval", "status", "report", "compare", "conclude"):
            self.assertRegex(text, rf"{cmd}\s+<experiment>:",
                             f"`{cmd}` help line must show its <experiment> object")
        self.assertRegex(text, r"new\s+<name>:")

    def test_subcommand_usage_shows_experiment_metavar(self):
        for a in cli.build_parser()._actions:
            if isinstance(a, argparse._SubParsersAction):
                for name in ("review", "run", "eval", "status", "report", "compare", "conclude"):
                    usage = a.choices[name].format_usage()
                    self.assertIn("<experiment>", usage,
                                  f"`hlab {name}` usage must show <experiment>")


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

    def test_ahl_redirect_is_honest_about_incompatibility(self):
        # R9: no fake "Please use: hlab <args>" shim — the two stacks' workspace
        # formats are NOT compatible, and the message must say so + point at the
        # README and at the shipped migration guide (v1.1, PR1).
        saved = sys.argv
        sys.argv = ["ahl", "score", "foo"]
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                rc = cli.ahl_redirect()
        finally:
            sys.argv = saved
        self.assertEqual(rc, 1)
        text = err.getvalue()
        self.assertNotIn("Please use: hlab", text)
        self.assertNotIn("hlab score", text)  # never echo an old command as if it works
        self.assertIn("NOT compatible", text)
        self.assertIn("README", text)
        self.assertIn("docs/migrating-from-ahl.md", text)
        self.assertNotIn("planned", text)  # the guide shipped — no stale promise

    def test_ahl_redirect_migration_guide_exists(self):
        # the path the redirect prints must exist in the repo — no dead pointer
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "docs" / "migrating-from-ahl.md").is_file(),
                        "ahl_redirect points at docs/migrating-from-ahl.md, "
                        "which must ship with the repo")


if __name__ == "__main__":
    unittest.main()
