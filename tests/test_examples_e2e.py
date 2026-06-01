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
    def test_review_run_report_produces_evidence(self):
        with _example_copy("auto-run-local-cli-lite") as root:
            exp = root / "experiments" / "demo"
            self.assertEqual(_run(["review", "experiments/demo"])[0], 0)  # WARN-only → exit 0
            rc, out = _run(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertTrue((exp / "evidence" / "traces" / "runtime-a.jsonl").is_file())
            self.assertTrue((exp / "evidence" / "raw" / "runtime-a" / "c1.out").is_file())
            self.assertTrue((exp / "evidence" / "artifacts" / "runtime-a" / "c1"
                             / "produced" / "out.txt").is_file())
            self.assertTrue((exp / "evidence" / "scores" / "tracks" / "quality.json").is_file())
            self.assertTrue((exp / "evidence" / "issues.jsonl").is_file())
            self.assertIn("objective primary track 'quality': passed", out)
            self.assertEqual(_run(["report", "experiments/demo"])[0], 0)
            self.assertTrue((exp / "reports" / "report.md").is_file())


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
