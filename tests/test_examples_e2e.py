"""End-to-end tests for the shipped v1 examples.

Each example is copied to a temp dir, its `local_cli` command is rewritten to the
test interpreter (the committed command is `python3 agent.py`; CI may run under `py`
or a venv), any generated outputs are cleared, then `review → run → report` is driven
through the real CLI and the produced evidence is asserted. Deterministic, no network.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli

_EXE = sys.executable.replace("\\", "/")  # forward slashes → no YAML/shlex escaping
_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@contextmanager
def _example_copy(name):
    """Copy examples/<name> to a temp dir, point local_cli at this interpreter,
    clear any generated outputs, and chdir into it for the duration."""
    src = _EXAMPLES / name
    saved = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / name
        shutil.copytree(src, root)
        for yml in root.rglob("agent-runtimes/*.yaml"):
            yml.write_text(
                yml.read_text(encoding="utf-8").replace("python3 agent.py", f"{_EXE} agent.py"),
                encoding="utf-8")
        exp = root / "experiments" / "demo"
        for d in ("evidence", "reports", "optimization"):
            shutil.rmtree(exp / d, ignore_errors=True)
        for d in ("incumbent", "candidates"):
            shutil.rmtree(exp / "harnesses" / d, ignore_errors=True)
        shutil.rmtree(exp / "harnesses" / "base" / "produced", ignore_errors=True)
        os.chdir(root)
        try:
            yield root
        finally:
            os.chdir(saved)


def _run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(args)
    return rc, out.getvalue() + err.getvalue()


class TestAutoRunExample(unittest.TestCase):
    def test_ab_run_scores_concise_over_verbose(self):
        with _example_copy("auto-run-local-cli-lite") as root:
            exp = root / "experiments" / "demo"
            self.assertEqual(_run(["review", "experiments/demo"])[0], 0)  # WARN-only → exit 0
            rc, out = _run(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            # run summary must read the A/B result as a comparison, never "failed"
            self.assertNotIn("objective primary track 'quality': failed", out)
            self.assertNotIn("{'failed': 1}", out)
            self.assertIn("comparative", out)
            self.assertIn("winner B", out)
            # both harnesses produced complete evidence (traces / raw / artifact)
            for rt in ("runtime-a", "runtime-b"):
                self.assertTrue((exp / "evidence" / "traces" / f"{rt}.jsonl").is_file())
                self.assertTrue((exp / "evidence" / "raw" / rt / "faq-reset.out").is_file())
                self.assertTrue((exp / "evidence" / "artifacts" / rt / "faq-reset"
                                 / "produced" / "answer.txt").is_file())
            self.assertTrue((exp / "evidence" / "issues.jsonl").is_file())
            # per-harness benchmark: verbose A fails every case, concise B passes every case
            recs = [json.loads(ln) for ln in (exp / "evidence" / "scores" / "quality"
                    / "conciseness.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
            a = [r for r in recs if r["harness_id"] == "A"]
            b = [r for r in recs if r["harness_id"] == "B"]
            self.assertEqual(len(a), 3)
            self.assertEqual(len(b), 3)
            self.assertTrue(all(r["status"] == "failed" for r in a))
            self.assertTrue(all(r["status"] == "passed" for r in b))
            # report reads as an A/B comparison that names the winner
            self.assertEqual(_run(["report", "experiments/demo"])[0], 0)
            report = (exp / "reports" / "report.md").read_text(encoding="utf-8")
            self.assertIn("## Harness comparison", report)
            self.assertIn("Winner (by `quality`): `B`", report)
            self.assertIn("concise alternative", report)
            self.assertIn("verbose baseline", report)
            self.assertIn("Objective met:", report)


class TestAutoOptimizeExample(unittest.TestCase):
    def test_review_run_report_runs_bounded_loop(self):
        with _example_copy("auto-optimize-copy-lite") as root:
            exp = root / "experiments" / "demo"
            self.assertEqual(_run(["review", "experiments/demo"])[0], 0)
            self.assertEqual(_run(["run", "experiments/demo"])[0], 0)
            hist = exp / "optimization" / "history.jsonl"
            self.assertTrue(hist.is_file())
            recs = [json.loads(ln) for ln in hist.read_text(encoding="utf-8").splitlines()
                    if ln.strip()]
            self.assertEqual(len(recs), 2)                          # stop_conditions max_iterations: 2
            self.assertTrue(all(not r["promoted"] for r in recs))   # copy-only never promotes
            self.assertTrue((exp / "optimization" / "iterations" / "iter-001"
                             / "evidence" / "traces" / "runtime-a.jsonl").is_file())
            self.assertTrue((exp / "harnesses" / "incumbent" / "agent.py").is_file())
            self.assertEqual(_run(["report", "experiments/demo"])[0], 0)
            self.assertTrue((exp / "reports" / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
