"""Completion Release — the public experiment path end to end, plus unit coverage.

Covers the new surface added for the AHL Completion Release:
- llm_judge real judging (monkeypatched llm.chat): pass / fail / request-error / bad-JSON
- report.html stdlib renderer: structure + HTML escaping
- hlab new --template: a complete, runnable tree (and unknown-template error)
- the committed flagship example == the in-package template (no drift)
- the whole path on the flagship: init -> new --template -> review -> run -> report ->
  compare -> conclude -> review, with NO API key, asserting winner B and every artifact

Deterministic, no network. The e2e test spawns the test interpreter for the local_cli
agents (like test_examples_e2e).
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
from types import SimpleNamespace
from unittest import mock

from agent_harness_lab import cli, evaluation, llm, markdown_html, scaffold
from agent_harness_lab.experiment_templates import TEMPLATES

_EXE = sys.executable.replace("\\", "/")


# --- llm_judge real judging --------------------------------------------------

class TestLlmJudgeReal(unittest.TestCase):
    def _judge(self, chat_impl, traces=None):
        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            ev = SimpleNamespace(id="j1", method="llm_judge", rubric=None)
            if traces is None:
                traces = {"runtime-a": [{"case_id": "c1", "harness_id": "A",
                                         "input": "q", "response": "an answer", "ok": True}]}
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat", chat_impl):
                out = evaluation._run_llm_judge(ev, "t", Path(tmp), Path(tmp), scores,
                                                traces=traces, cases=[{"id": "c1"}])
            recs = [json.loads(ln) for ln in (scores / "t" / "j1.jsonl")
                    .read_text(encoding="utf-8").splitlines() if ln.strip()]
            return out, recs

    def test_pass_verdict(self):
        out, recs = self._judge(lambda *a, **k: '{"verdict": "pass", "score": 90, "reason": "good"}')
        self.assertEqual(recs[0]["status"], "passed")
        self.assertEqual(recs[0]["score"], 90.0)
        self.assertEqual(recs[0]["detail"], "good")
        self.assertEqual(out.status, "passed")

    def test_fail_verdict(self):
        _, recs = self._judge(lambda *a, **k: 'noise {"verdict":"fail","score":12,"reason":"leaked"} tail')
        self.assertEqual(recs[0]["status"], "failed")
        self.assertEqual(recs[0]["score"], 12.0)

    def test_request_error_is_error_not_pending(self):
        def boom(*a, **k):
            raise RuntimeError("HTTP 503")
        _, recs = self._judge(boom)
        self.assertEqual(recs[0]["status"], "error")
        self.assertIn("failed", recs[0]["detail"])

    def test_unparseable_reply_is_error_with_preview(self):
        _, recs = self._judge(lambda *a, **k: "the model said no json here")
        self.assertEqual(recs[0]["status"], "error")
        self.assertIn("raw_response", recs[0])
        self.assertIn("no json", recs[0]["raw_response"])

    def test_no_key_stays_pending(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL"):
                os.environ.pop(k, None)
            # llm.chat must NOT be called on the no-key path
            with mock.patch.object(llm, "chat", side_effect=AssertionError("called")):
                with tempfile.TemporaryDirectory() as tmp:
                    ev = SimpleNamespace(id="j1", method="llm_judge", rubric=None)
                    out = evaluation._run_llm_judge(
                        ev, "t", Path(tmp), Path(tmp), Path(tmp) / "scores",
                        traces={"r": [{"case_id": "c1", "harness_id": "A", "response": "x"}]},
                        cases=[{"id": "c1"}])
        self.assertEqual(out.status, "pending")

    def test_no_key_zero_judgeable_units_stays_pending(self):
        # the 0-judgeable-units ERROR must NOT fire offline: no key -> still pending
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL"):
                os.environ.pop(k, None)
            with mock.patch.object(llm, "chat", side_effect=AssertionError("called")):
                with tempfile.TemporaryDirectory() as tmp:
                    ev = SimpleNamespace(id="j1", method="llm_judge", rubric=None)
                    out = evaluation._run_llm_judge(
                        ev, "t", Path(tmp), Path(tmp), Path(tmp) / "scores",
                        traces={"r": [{"case_id": "c1", "harness_id": "A",
                                       "input": "q", "exit_code": 0, "ok": True}]},
                        cases=[{"id": "c1"}])
        self.assertEqual(out.status, "pending")

    def test_configured_zero_judgeable_units_is_error(self):
        # script connector trace shape (input/exit_code/ok, no `response`) + a key:
        # trace records exist but 0 judgeable units -> explicit ERROR, never silent pending
        def never(*a, **k):
            raise AssertionError("llm.chat must not be called with 0 judgeable units")
        out, recs = self._judge(never, traces={
            "runtime-a": [{"case_id": "c1", "harness_id": "A",
                           "input": "q", "exit_code": 0, "ok": True}]})
        self.assertEqual(out.status, "error")
        self.assertIn("response", out.detail)
        self.assertIn("script connector", out.detail)
        self.assertEqual(recs[0]["status"], "error")

    def test_configured_no_trace_records_stays_pending(self):
        # no trace records at all (run not executed yet) -> pending, not error
        def never(*a, **k):
            raise AssertionError("llm.chat must not be called without traces")
        out, _ = self._judge(never, traces={})
        self.assertEqual(out.status, "pending")
        out, _ = self._judge(never, traces={"runtime-a": []})  # file exists, no records
        self.assertEqual(out.status, "pending")

    def test_judge_timeout_passed_to_llm_chat(self):
        # AHL_JUDGE_TIMEOUT (module constant) must reach llm.chat as `timeout=`
        seen = {}
        def chat(base, model, key, prompt, timeout=None, **kw):
            seen["timeout"] = timeout
            return '{"verdict": "pass", "score": 90, "reason": "ok"}'
        with mock.patch.object(evaluation, "_JUDGE_TIMEOUT", 42.5):
            out, _ = self._judge(chat)
        self.assertEqual(out.status, "passed")
        self.assertEqual(seen["timeout"], 42.5)

    def test_judge_timeout_env_parse_and_invalid_fallback(self):
        # module-level parse (mirrors AHL_EVAL_TIMEOUT): valid value taken,
        # garbage falls back to the llm.chat default of 180
        import importlib
        try:
            with mock.patch.dict(os.environ, {"AHL_JUDGE_TIMEOUT": "33.5"}):
                importlib.reload(evaluation)
                self.assertEqual(evaluation._JUDGE_TIMEOUT, 33.5)
            with mock.patch.dict(os.environ, {"AHL_JUDGE_TIMEOUT": "not-a-number"}):
                importlib.reload(evaluation)
                self.assertEqual(evaluation._JUDGE_TIMEOUT, 180.0)
        finally:
            importlib.reload(evaluation)  # restore the ambient-env module state


# --- report.html renderer ----------------------------------------------------

class TestMarkdownHtml(unittest.TestCase):
    def test_structure(self):
        md = ("# Title\n\n## Section\n\n- one\n- two\n\n"
              "| H1 | H2 |\n|----|----|\n| x | y |\n\n> a quote\n\n"
              "`code` and **bold** together\n")
        html = markdown_html.render(md, title="T")
        for needle in ("<!doctype html>", "<h1>Title</h1>", "<h2>Section</h2>",
                       "<ul>", "<li>one</li>", "<table>", "<th>H1</th>", "<td>x</td>",
                       "<blockquote>", "<code>code</code>", "<strong>bold</strong>"):
            self.assertIn(needle, html)

    def test_escapes_dangerous_html(self):
        html = markdown_html.render("hello <script>alert(1)</script> & <b>x</b>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_bold_spanning_inline_code(self):
        # the report writes things like **Winner (by `track`): ...**
        html = markdown_html.render("**Winner (by `quality`): B**")
        self.assertIn("<strong>", html)
        self.assertIn("<code>quality</code>", html)

    def test_forged_nul_placeholder_does_not_crash(self):
        # evidence text containing a literal \x00<digit>\x00 must not raise (was IndexError)
        for payload in ("issue \x009\x00 here", "\x000\x00", "a `c` then \x005\x00 tail"):
            out = markdown_html.render(payload)
            self.assertIn("<!doctype html>", out)


# --- hlab new --template -----------------------------------------------------

class TestTemplateScaffold(unittest.TestCase):
    def test_template_generates_runnable_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "experiments").mkdir()
            res = scaffold.new_experiment(root, "mp", template="memory-policy-ab-lite")
            d = res.experiment_dir
            for rel in ("experiment.yaml", "goal.md", "harnesses/A/agent.py",
                        "harnesses/B/agent.py", "agent-runtimes/runtime-a.yaml",
                        "cases/cases.jsonl", "evaluation/benchmarks/evaluate.py",
                        "evaluation/rubrics/memory_policy.md"):
                self.assertTrue((d / rel).is_file(), f"missing {rel}")
            self.assertIn('id: "mp"', (d / "experiment.yaml").read_text(encoding="utf-8"))
            # conclusion.md is intentionally absent until `hlab conclude`
            self.assertFalse((d / "conclusion.md").exists())

    def test_unknown_template_raises_keyerror(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "experiments").mkdir()
            with self.assertRaises(KeyError):
                scaffold.new_experiment(root, "mp", template="does-not-exist")


class TestExampleMatchesTemplate(unittest.TestCase):
    """The committed flagship example must equal what the template generates (no drift).

    R4: the builder writes the generation-time probed interpreter into the runtime
    YAML `command:` (the committed example keeps the canonical `python3`), so the
    diff normalizes that one substitution back before comparing.
    """
    def test_example_equals_template_output(self):
        from agent_harness_lab.experiment_templates import detect_python_command
        interp = detect_python_command()
        files = TEMPLATES["memory-policy-ab-lite"]("demo")
        base = (Path(__file__).resolve().parents[1] / "examples"
                / "memory-policy-ab-lite" / "experiments" / "demo")
        for rel, content in files.items():
            content = content.replace(f"command: '{interp} agent.py'",
                                      "command: python3 agent.py")
            self.assertEqual((base / rel).read_text(encoding="utf-8"), content,
                             f"committed example diverged from template: {rel}")


# --- full public path on the flagship (no API key) ---------------------------

@contextmanager
def _chdir(p):
    saved = os.getcwd()
    os.chdir(p)
    try:
        yield
    finally:
        os.chdir(saved)


def _cli(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(args)
    return rc, out.getvalue() + err.getvalue()


class TestCompletionPathE2E(unittest.TestCase):
    def test_full_path_winner_b_no_key(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {}, clear=False):
            for k in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL"):
                os.environ.pop(k, None)
            ws = Path(tmp)
            exp_arg = "experiments/memory-policy-ab"
            with _chdir(ws):
                self.assertEqual(_cli(["init"])[0], 0)
                self.assertEqual(_cli(["new", "memory-policy-ab",
                                       "--template", "memory-policy-ab-lite"])[0], 0)
                # run the local_cli agents under the test interpreter
                for yml in (ws / "experiments" / "memory-policy-ab"
                            / "agent-runtimes").glob("*.yaml"):
                    yml.write_text(yml.read_text(encoding="utf-8")
                                   .replace("python3 agent.py", f"{_EXE} agent.py"),
                                   encoding="utf-8")
                self.assertEqual(_cli(["review", exp_arg])[0], 0)   # WARN (conclusion) -> exit 0
                self.assertEqual(_cli(["run", exp_arg])[0], 0)
                self.assertEqual(_cli(["status", exp_arg])[0], 0)
                self.assertEqual(_cli(["report", exp_arg])[0], 0)
                self.assertEqual(_cli(["compare", exp_arg])[0], 0)
                rc, out = _cli(["conclude", exp_arg, "--winner", "B",
                                "--reason", "Filtered retrieval cut leakage."])
                self.assertEqual(rc, 0)
                # second review: conclusion_missing must be gone
                _, review_out = _cli(["review", exp_arg])
                self.assertNotIn("conclusion_missing", review_out)

                d = ws / "experiments" / "memory-policy-ab"
                self.assertTrue(any((d / "evidence" / "traces").glob("*.jsonl")))
                self.assertTrue((d / "reports" / "report.md").is_file())
                self.assertTrue((d / "reports" / "report.html").is_file())
                self.assertTrue((d / "reports" / "compare.json").is_file())
                self.assertTrue((d / "conclusion.md").is_file())

                compare = json.loads((d / "reports" / "compare.json").read_text(encoding="utf-8"))
                self.assertEqual(compare["winner"], "B")  # filtered retrieval wins, deterministically
                html = (d / "reports" / "report.html").read_text(encoding="utf-8")
                self.assertIn("<table", html)             # real render, not a <pre> dump
                self.assertIn("<!doctype html>", html)


if __name__ == "__main__":
    unittest.main()
