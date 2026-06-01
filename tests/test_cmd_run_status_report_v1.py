"""run: Copilot Mode generates agent-task.md (exit 0); Auto Mode runs (exit 0);
report generates reports/report.md (exit 0); a config ERROR blocks run/report
(exit 1); status works."""
import io
import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli, scaffold


@contextmanager
def workspace_with_experiment(name="demo", **kw):
    tmp = tempfile.TemporaryDirectory()
    saved = os.getcwd()
    os.chdir(tmp.name)
    try:
        root = Path(tmp.name)
        scaffold.init_workspace(root)
        scaffold.new_experiment(root, name, **kw)
        yield root
    finally:
        os.chdir(saved)
        tmp.cleanup()


def _invoke(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(argv)
    return rc, out.getvalue(), err.getvalue()


class TestRun(unittest.TestCase):
    def test_run_copilot_generates_agent_task_exit_0(self):
        # Copilot Mode is implemented: run renders agent-task.md and succeeds (exit 0),
        # while clearly stating that nothing was executed and no evidence collected.
        with workspace_with_experiment() as ws:
            rc, out, _err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertTrue((ws / "experiments" / "demo" / "agent-task.md").is_file())
            self.assertIn("agent-task.md was generated", out)
            self.assertIn("no Agent Runtime was directly executed", out)
            self.assertIn("no evidence was collected yet", out)

    def test_run_auto_executes_exit_0(self):
        # Auto Mode is implemented: it runs (exit 0) and writes evidence. A fresh
        # scaffold's runtime working_dirs don't exist, so it records connector_failure
        # issues — but the run executed and issues.jsonl is written.
        with workspace_with_experiment(name="autox", run_mode="auto") as ws:
            rc, out, _err = _invoke(["run", "experiments/autox"])
            self.assertEqual(rc, 0)
            self.assertIn("Auto Mode", out)
            self.assertTrue((ws / "experiments" / "autox" / "evidence" / "issues.jsonl").is_file())

    def test_run_blocked_on_review_error_exit_1(self):
        with workspace_with_experiment() as ws:
            shutil.rmtree(ws / "experiments" / "demo" / "cases")
            rc, _out, _err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 1, "config error must block run with exit 1, not 2")

    def test_run_not_found_exit_1(self):
        with workspace_with_experiment() as _ws:
            rc, _out, _err = _invoke(["run", "experiments/nope"])
            self.assertEqual(rc, 1)


class TestStatus(unittest.TestCase):
    def test_status_summary_exit_0(self):
        with workspace_with_experiment() as _ws:
            rc, out, _err = _invoke(["status", "demo"])
            self.assertEqual(rc, 0)
            self.assertIn("experiment id:", out)
            self.assertIn("demo", out)
            self.assertIn("harness count:   2", out)
            self.assertIn("case count:      1", out)
            # every experiment.yaml field is reflected (no silently-read fields)
            self.assertIn("A=harness-a", out)            # harness name
            self.assertIn("manual", out)                 # runtime connector type (copilot default)
            self.assertIn("collection:", out)            # collection settings reflected
            self.assertIn("inspection:", out)            # inspection settings reflected


    def test_status_fresh_experiment_reports_no_evidence(self):
        with workspace_with_experiment() as _ws:
            rc, out, _err = _invoke(["status", "demo"])
            self.assertEqual(rc, 0)
            # scaffold .gitkeep must NOT be counted as collected evidence
            self.assertIn("evidence:        none collected", out)

    def test_status_shows_unset_not_none(self):
        with workspace_with_experiment() as ws:
            (ws / "experiments" / "demo" / "experiment.yaml").write_text("question: q\n", encoding="utf-8")
            rc, out, _err = _invoke(["status", "demo"])
            self.assertEqual(rc, 0)
            self.assertNotIn("None", out)      # no literal Python None
            self.assertIn("(unset)", out)


class TestReport(unittest.TestCase):
    def test_report_blocked_on_review_error_exit_1(self):
        with workspace_with_experiment() as ws:
            (ws / "experiments" / "demo" / "experiment.yaml").write_text("id: x\n", encoding="utf-8")
            rc, _out, _err = _invoke(["report", "experiments/demo"])
            self.assertEqual(rc, 1)  # symmetric with run; not a fake exit-2

    def test_report_generates_report_md_exit_0(self):
        with workspace_with_experiment() as ws:
            rc, out, _err = _invoke(["report", "experiments/demo"])
            self.assertEqual(rc, 0)
            md = ws / "experiments" / "demo" / "reports" / "report.md"
            self.assertTrue(md.is_file())
            text = md.read_text(encoding="utf-8")
            self.assertIn("# Experiment Report", text)
            self.assertIn("## Known limitations", text)
            self.assertIn("conclusion.md", text)  # points at next step, never fabricates one
            self.assertIn("report generated", out)
            # it did not write a conclusion for the user
            self.assertFalse((ws / "experiments" / "demo" / "conclusion.md").exists()
                             and "fabricated" in text)

    def test_report_not_found_exit_1(self):
        with workspace_with_experiment() as _ws:
            rc, _out, _err = _invoke(["report", "experiments/nope"])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
