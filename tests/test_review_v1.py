"""hlab review verdicts (PASS / WARN / ERROR)."""
import io
import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli, scaffold
from agent_harness_lab.reviewer import ERROR, PASS, WARN, review_experiment


@contextmanager
def workspace_with_experiment(name="demo", **kw):
    tmp = tempfile.TemporaryDirectory()
    saved = os.getcwd()
    os.chdir(tmp.name)
    try:
        root = Path(tmp.name)
        scaffold.init_workspace(root)
        res = scaffold.new_experiment(root, name, **kw)
        yield root, res.experiment_dir
    finally:
        os.chdir(saved)
        tmp.cleanup()


class TestReviewVerdicts(unittest.TestCase):
    def test_fresh_experiment_passes(self):
        with workspace_with_experiment() as (_root, exp):
            report = review_experiment(exp)
            self.assertEqual(report.verdict, PASS, [str(p) for p in report.problems])

    def test_cli_review_pass_exit_0(self):
        with workspace_with_experiment() as (_root, _exp):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["review", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertIn("PASS", out.getvalue())

    def test_missing_experiment_yaml_is_error(self):
        with workspace_with_experiment() as (_root, exp):
            (exp / "experiment.yaml").unlink()
            report = review_experiment(exp)
            self.assertEqual(report.verdict, ERROR)
            self.assertTrue(any(p.code == "experiment_yaml_missing" for p in report.errors))

    def test_invalid_yaml_is_error(self):
        with workspace_with_experiment() as (_root, exp):
            (exp / "experiment.yaml").write_text("id: x\n : : bad\n- nope\n", encoding="utf-8")
            report = review_experiment(exp)
            self.assertEqual(report.verdict, ERROR)

    def test_missing_harness_path_error_exit_1(self):
        with workspace_with_experiment() as (_root, exp):
            shutil.rmtree(exp / "harnesses" / "A")
            shutil.rmtree(exp / "harnesses" / "B")
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["review", "experiments/demo"])
            self.assertEqual(rc, 1)
            self.assertIn("ERROR", out.getvalue())

    def test_html_format_warns(self):
        with workspace_with_experiment() as (_root, exp):
            y = exp / "experiment.yaml"
            text = y.read_text(encoding="utf-8").replace("    - md\n", "    - md\n    - html\n")
            y.write_text(text, encoding="utf-8")
            report = review_experiment(exp)
            self.assertEqual(report.verdict, WARN)
            self.assertTrue(any(p.code == "html_renderer_unavailable" for p in report.warnings))

    def test_auto_unsupported_connector_error(self):
        with workspace_with_experiment(name="autox", run_mode="auto") as (_root, exp):
            (exp / "agent-runtimes" / "runtime-a.yaml").write_text(
                "id: runtime-a\nconnector:\n  type: api\n  command: x\n", encoding="utf-8")
            report = review_experiment(exp)
            self.assertEqual(report.verdict, ERROR)
            self.assertTrue(any(p.code == "auto_connector_unsupported" for p in report.errors))

    def test_review_experiment_not_found(self):
        with workspace_with_experiment() as (_root, _exp):
            rc = cli.main(["review", "experiments/does-not-exist"])
            self.assertEqual(rc, 1)

    def test_review_empty_string_arg_is_not_found(self):
        with workspace_with_experiment() as (_root, _exp):
            rc = cli.main(["review", ""])  # must not resolve to cwd
            self.assertEqual(rc, 1)

    def test_bare_name_not_shadowed_by_cwd_dir(self):
        with workspace_with_experiment(name="exp-one") as (root, _exp):
            (root / "exp-one").mkdir()  # decoy empty dir in cwd
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["review", "exp-one"])
            self.assertEqual(rc, 0)        # resolved to experiments/exp-one, not ./exp-one
            self.assertIn("PASS", out.getvalue())


if __name__ == "__main__":
    unittest.main()
