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

_Q = "Does harness B beat harness A?"  # a real (non-placeholder) question


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
    def test_fresh_experiment_passes_with_real_question(self):
        with workspace_with_experiment(question=_Q) as (_root, exp):
            report = review_experiment(exp)
            self.assertEqual(report.verdict, PASS, [str(p) for p in report.problems])

    def test_fresh_default_warns_only_placeholder_question(self):
        # the scaffold's default `<...>` question is an unfilled placeholder (R4):
        # review WARNs question_placeholder and nothing else fires.
        with workspace_with_experiment() as (_root, exp):
            report = review_experiment(exp)
            self.assertEqual(report.verdict, WARN)
            self.assertEqual(report.errors, [], [str(p) for p in report.errors])
            self.assertEqual({p.code for p in report.warnings}, {"question_placeholder"})

    def test_cli_review_pass_exit_0(self):
        with workspace_with_experiment(question=_Q) as (_root, _exp):
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

    def test_html_format_does_not_warn(self):
        # report.html has a real stdlib renderer — the default scaffold now requests
        # `html` (R7) and that must not warn.
        with workspace_with_experiment(question=_Q) as (_root, exp):
            text = (exp / "experiment.yaml").read_text(encoding="utf-8")
            self.assertIn("- html", text)  # scaffold default includes html
            report = review_experiment(exp)
            self.assertNotEqual(report.verdict, ERROR)
            self.assertFalse(any(p.code == "html_renderer_unavailable"
                                 for p in report.warnings + report.errors))

    def test_auto_unsupported_connector_error(self):
        with workspace_with_experiment(name="autox", run_mode="auto") as (_root, exp):
            (exp / "agent-runtimes" / "runtime-a.yaml").write_text(
                "id: runtime-a\nconnector:\n  type: api\n  command: x\n", encoding="utf-8")
            report = review_experiment(exp)
            self.assertEqual(report.verdict, ERROR)
            self.assertTrue(any(p.code == "auto_connector_unsupported" for p in report.errors))

    def test_auto_fresh_scaffold_reviews_pass(self):
        # R4: the auto scaffold ships a runnable echo agent whose working_dir exists,
        # so with a real question a fresh auto experiment reviews PASS.
        with workspace_with_experiment(name="autoy", run_mode="auto",
                                       question=_Q) as (_root, exp):
            report = review_experiment(exp)
            self.assertEqual(report.verdict, PASS, [str(p) for p in report.problems])

    def test_auto_missing_working_dir_error(self):
        # R4: the runner's run-time working_dir check is left-shifted into review
        # (auto + local_cli/script only).
        with workspace_with_experiment(name="autoz", run_mode="auto",
                                       question=_Q) as (_root, exp):
            y = exp / "agent-runtimes" / "runtime-a.yaml"
            y.write_text(y.read_text(encoding="utf-8").replace(
                'working_dir: "./harnesses/A"', 'working_dir: "./nope"'), encoding="utf-8")
            report = review_experiment(exp)
            self.assertEqual(report.verdict, ERROR)
            self.assertTrue(any(p.code == "auto_working_dir_missing" for p in report.errors))

    def test_copilot_missing_working_dir_not_checked(self):
        # the precheck is auto-only: the copilot scaffold's working_dir does not
        # exist either, but a Copilot flow may create it right before the run.
        with workspace_with_experiment(question=_Q) as (_root, exp):
            report = review_experiment(exp)
            self.assertFalse(any(p.code == "auto_working_dir_missing"
                                 for p in report.problems))

    def test_review_experiment_not_found(self):
        with workspace_with_experiment() as (_root, _exp):
            rc = cli.main(["review", "experiments/does-not-exist"])
            self.assertEqual(rc, 1)

    def test_review_empty_string_arg_is_not_found(self):
        with workspace_with_experiment() as (_root, _exp):
            rc = cli.main(["review", ""])  # must not resolve to cwd
            self.assertEqual(rc, 1)

    def test_bare_name_not_shadowed_by_cwd_dir(self):
        with workspace_with_experiment(name="exp-one", question=_Q) as (root, _exp):
            (root / "exp-one").mkdir()  # decoy empty dir in cwd
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["review", "exp-one"])
            self.assertEqual(rc, 0)        # resolved to experiments/exp-one, not ./exp-one
            self.assertIn("PASS", out.getvalue())


if __name__ == "__main__":
    unittest.main()
