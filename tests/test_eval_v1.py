"""PR4: hlab eval — run/eval split.

Tests:
  1. eval recomputes benchmark scores from existing evidence without touching
     traces (assert trace file mtime/bytes unchanged)
  2. human_annotation backflow: run → pending → write annotation → eval → scored
  3. eval with no evidence dir → exit 1 + HLAB_MISSING_EVIDENCE on stderr
  4. eval with empty traces dir → exit 1 + HLAB_MISSING_EVIDENCE on stderr
  5. eval with a track status:error → exit 3 + HLAB_EVAL_ERROR on stderr
  6. eval idempotence: run eval twice, second scores match first
  7. multiturn evidence eval parity: eval on multiturn evidence produces same
     scores as run's inline evaluation pass
  8. CLI surface: eval in the 9-command set, help text, Next hints
"""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli, evaluation, scaffold
from agent_harness_lab.experiment_spec import parse_experiment_yaml

_EXE = sys.executable.replace("\\", "/")

# --- benchmark evaluator scripts ---

_BENCH_PASS = (
    "import json,sys\n"
    "ctx=json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "ok=bool(ctx.get('experiment_id'))\n"
    "print(json.dumps({'passed':ok,'score':1.0,'detail':'ctx received'}))\n"
)
_BENCH_FAIL = (
    "import json,sys\n"
    "json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "print(json.dumps({'passed':False,'score':0.0,'detail':'nope'}))\n"
)
_BENCH_CRASH = "import sys\nsys.exit(3)\n"

# --- echo agent (local_cli IPC) ---
_ECHO = (
    "import json,sys\n"
    "for line in sys.stdin:\n"
    "    d=json.loads(line)\n"
    "    sys.stdout.write(json.dumps({'response':'echo:'+d.get('input','')})+'\\n')\n"
    "    sys.stdout.flush()\n"
)


@contextmanager
def _workspace():
    tmp = tempfile.TemporaryDirectory()
    saved = os.getcwd()
    os.chdir(tmp.name)
    try:
        yield Path(tmp.name)
    finally:
        os.chdir(saved)
        tmp.cleanup()


def _run_cli(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(args)
    return rc, out.getvalue(), err.getvalue()


def _experiment_yaml(eval_section: str = "", objective_section: str = "") -> str:
    return (
        "id: demo\nstatus: draft\nquestion: q\n"
        "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
        "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
        "agent_runtimes:\n  - id: runtime-a\n    harness: A\n    spec: agent-runtimes/runtime-a.yaml\n"
        "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
        "collection:\n  traces: true\n  raw: true\n  artifacts: true\n  snapshots: false\n  scores: true\n"
        "reports:\n  formats:\n    - md\n"
        + eval_section + objective_section
    )


def _setup_auto_exp(ws, eval_section="", objective_section="", scripts=None,
                    agent=_ECHO, timeout=20):
    """Build a minimal auto experiment with a real runtime and seed evidence."""
    scaffold.init_workspace(ws)
    exp = scaffold.new_experiment(ws, "demo", run_mode="auto").experiment_dir
    (exp / "experiment.yaml").write_text(
        _experiment_yaml(eval_section, objective_section), encoding="utf-8")
    (exp / "cases" / "cases.jsonl").write_text(
        '{"id":"case-001","input":"hello"}\n', encoding="utf-8")
    (exp / "rt").mkdir(exist_ok=True)
    (exp / "rt" / "agent.py").write_text(agent, encoding="utf-8")
    rt = (f"id: runtime-a\nconnector:\n  type: local_cli\n"
          f"  command: {_EXE} agent.py\n  working_dir: ./rt\n  timeout: {timeout}\n")
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(rt, encoding="utf-8")
    for name, body in (scripts or {}).items():
        dest = exp / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
    return exp


def _seed_trace(exp):
    """Write a minimal trace record (without running the agent)."""
    traces_dir = exp / "evidence" / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    (traces_dir / "runtime-a.jsonl").write_text(
        json.dumps({"case_id": "case-001", "runtime_id": "runtime-a",
                    "harness_id": "A", "input": "hello", "response": "echo:hello",
                    "ok": True}) + "\n",
        encoding="utf-8")


def _eval_yaml(ev_lines: str, track_lines: str) -> str:
    return ("evaluation:\n  root: evaluation/\n  evaluators:\n"
            + ev_lines + "  tracks:\n" + track_lines)


_EV_BENCH = "    - id: e1\n      method: benchmark\n      script: benchmarks/pass.py\n"
_EV_CRASH = "    - id: e1\n      method: benchmark\n      script: benchmarks/crash.py\n"
_TRACK = "    - id: quality\n      evaluators: [e1]\n      evidence: [traces]\n"


# ===========================================================================
# 1. eval recomputes benchmark without touching traces
# ===========================================================================

class TestEvalBenchmarkNoTracesTouch(unittest.TestCase):
    def test_eval_rewrites_scores_but_leaves_traces_unchanged(self):
        with _workspace() as ws:
            exp = _setup_auto_exp(
                ws,
                eval_section=_eval_yaml(_EV_BENCH, _TRACK),
                scripts={"evaluation/benchmarks/pass.py": _BENCH_PASS},
            )
            _seed_trace(exp)
            trace_path = exp / "evidence" / "traces" / "runtime-a.jsonl"
            original_bytes = trace_path.read_bytes()
            original_mtime = trace_path.stat().st_mtime

            rc, out, err = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc, 0, f"stderr: {err}")
            self.assertIn("re-evaluated", out)
            self.assertIn("passed", out)

            # trace file must be unchanged
            self.assertEqual(trace_path.read_bytes(), original_bytes,
                             "trace file bytes must not change after eval")
            self.assertAlmostEqual(trace_path.stat().st_mtime, original_mtime,
                                   places=1, msg="trace file mtime must not change")

            # scores were written
            agg_path = exp / "evidence" / "scores" / "tracks" / "quality.json"
            self.assertTrue(agg_path.is_file())
            agg = json.loads(agg_path.read_text(encoding="utf-8"))
            self.assertEqual(agg["status"], "passed")


# ===========================================================================
# 2. human_annotation backflow
# ===========================================================================

class TestHumanAnnotationBackflow(unittest.TestCase):
    """run → pending → write annotation file → eval → scored."""

    def _human_eval(self):
        ev = "    - id: h1\n      method: human_annotation\n"
        tr = "    - id: review\n      evaluators: [h1]\n      evidence: [traces]\n"
        return _eval_yaml(ev, tr)

    def test_backflow_end_to_end(self):
        with _workspace() as ws:
            exp = _setup_auto_exp(ws, eval_section=self._human_eval())
            _seed_trace(exp)

            # first eval: no annotation → pending
            rc, _, _ = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc, 0)
            agg = json.loads(
                (exp / "evidence" / "scores" / "tracks" / "review.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(agg["status"], "pending")

            # human writes annotation alongside the score record
            ann = exp / "evidence" / "scores" / "review" / "h1.annotation.json"
            ann.parent.mkdir(parents=True, exist_ok=True)
            ann.write_text(json.dumps({"passed": True, "score": 0.9, "detail": "lgtm"}),
                           encoding="utf-8")

            # eval adopts annotation → scored
            trace_path = exp / "evidence" / "traces" / "runtime-a.jsonl"
            original_bytes = trace_path.read_bytes()
            rc2, out2, err2 = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc2, 0, f"stderr: {err2}")
            agg2 = json.loads(
                (exp / "evidence" / "scores" / "tracks" / "review.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(agg2["status"], "passed")

            # traces untouched through both eval calls
            self.assertEqual(trace_path.read_bytes(), original_bytes)

    def test_backflow_passed_false_becomes_failed(self):
        with _workspace() as ws:
            exp = _setup_auto_exp(ws, eval_section=self._human_eval())
            _seed_trace(exp)
            ann = exp / "evidence" / "scores" / "review" / "h1.annotation.json"
            ann.parent.mkdir(parents=True, exist_ok=True)
            ann.write_text(json.dumps({"passed": False, "detail": "rejected"}),
                           encoding="utf-8")
            rc, out, err = _run_cli(["eval", "experiments/demo"])
            # failed is a legitimate result — exit 0
            self.assertEqual(rc, 0)
            agg = json.loads(
                (exp / "evidence" / "scores" / "tracks" / "review.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(agg["status"], "failed")


# ===========================================================================
# 3 & 4. Missing/empty evidence → exit 1 + HLAB_MISSING_EVIDENCE
# ===========================================================================

class TestEvalMissingEvidence(unittest.TestCase):
    def test_no_evidence_dir_exits_1_with_code(self):
        with _workspace() as ws:
            exp = _setup_auto_exp(ws, eval_section=_eval_yaml(_EV_BENCH, _TRACK),
                                  scripts={"evaluation/benchmarks/pass.py": _BENCH_PASS})
            # deliberately do NOT seed any evidence
            rc, _, err = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc, 1)
            self.assertIn("HLAB_MISSING_EVIDENCE", err)

    def test_empty_traces_dir_exits_1_with_code(self):
        with _workspace() as ws:
            exp = _setup_auto_exp(ws, eval_section=_eval_yaml(_EV_BENCH, _TRACK),
                                  scripts={"evaluation/benchmarks/pass.py": _BENCH_PASS})
            # create evidence dir with empty traces/ but no .jsonl files
            (exp / "evidence" / "traces").mkdir(parents=True, exist_ok=True)
            rc, _, err = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc, 1)
            self.assertIn("HLAB_MISSING_EVIDENCE", err)

    def test_experiment_not_found_exits_1(self):
        with _workspace() as ws:
            scaffold.init_workspace(ws)
            rc, _, err = _run_cli(["eval", "no-such-experiment"])
            self.assertEqual(rc, 1)


# ===========================================================================
# 5. Track status:error → exit 3 + HLAB_EVAL_ERROR
# ===========================================================================

class TestEvalTrackError(unittest.TestCase):
    def test_crashing_benchmark_exits_3_with_code(self):
        with _workspace() as ws:
            exp = _setup_auto_exp(
                ws,
                eval_section=_eval_yaml(_EV_CRASH, _TRACK),
                scripts={"evaluation/benchmarks/crash.py": _BENCH_CRASH},
            )
            _seed_trace(exp)
            rc, _, err = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc, 3)
            self.assertIn("HLAB_EVAL_ERROR", err)
            self.assertIn("scores/tracks/", err)

    def test_failed_track_exits_0(self):
        """A failed track (definite experiment failure) is a legitimate result — exit 0."""
        ev = "    - id: e1\n      method: benchmark\n      script: benchmarks/fail.py\n"
        with _workspace() as ws:
            exp = _setup_auto_exp(
                ws,
                eval_section=_eval_yaml(ev, _TRACK),
                scripts={"evaluation/benchmarks/fail.py": _BENCH_FAIL},
            )
            _seed_trace(exp)
            rc, _, err = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertNotIn("HLAB_EVAL_ERROR", err)

    def test_pending_track_exits_0(self):
        """A pending llm_judge (no key) is not a failure — exit 0."""
        ev = "    - id: j1\n      method: llm_judge\n      rubric: rubrics/r.md\n"
        tr = "    - id: judged\n      evaluators: [j1]\n      evidence: [traces]\n"
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL")}
        with unittest.mock.patch.dict(os.environ, env_clean, clear=True):
            with _workspace() as ws:
                exp = _setup_auto_exp(
                    ws,
                    eval_section=_eval_yaml(ev, tr),
                    scripts={"evaluation/rubrics/r.md": "# rubric\n"},
                )
                _seed_trace(exp)
                rc, _, err = _run_cli(["eval", "experiments/demo"])
                self.assertEqual(rc, 0)


# ===========================================================================
# 6. Idempotence: eval twice → same scores
# ===========================================================================

class TestEvalIdempotence(unittest.TestCase):
    def test_second_eval_same_scores_as_first(self):
        with _workspace() as ws:
            exp = _setup_auto_exp(
                ws,
                eval_section=_eval_yaml(_EV_BENCH, _TRACK),
                scripts={"evaluation/benchmarks/pass.py": _BENCH_PASS},
            )
            _seed_trace(exp)
            _run_cli(["eval", "experiments/demo"])
            agg1 = json.loads(
                (exp / "evidence" / "scores" / "tracks" / "quality.json")
                .read_text(encoding="utf-8"))
            _run_cli(["eval", "experiments/demo"])
            agg2 = json.loads(
                (exp / "evidence" / "scores" / "tracks" / "quality.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(agg1["status"], agg2["status"])
            self.assertEqual(agg1["evaluators"][0]["score"],
                             agg2["evaluators"][0]["score"])


# ===========================================================================
# 7. Multi-turn evidence eval parity
# ===========================================================================

class TestEvalMultiturnParity(unittest.TestCase):
    """eval on a multiturn evidence tree produces the same scores as run's inline pass."""

    def _multiturn_trace(self, exp: Path) -> None:
        """Seed a multiturn trace record: transcript with two turns."""
        traces_dir = exp / "evidence" / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "case_id": "case-001", "runtime_id": "runtime-a", "harness_id": "A",
            "input": "hello", "response": "final answer", "ok": True,
            "turns": 2,
            "transcript": [
                {"turn": 0, "user": "hello", "agent": "hi there"},
                {"turn": 1, "user": "follow up", "agent": "final answer"},
            ],
            "simulator": "scripted",
        }
        (traces_dir / "runtime-a.jsonl").write_text(
            json.dumps(record) + "\n", encoding="utf-8")

    def test_eval_multiturn_produces_same_result_as_inline_evaluation(self):
        """run_evaluation (inline) and eval CLI on the same multiturn evidence match."""
        with _workspace() as ws:
            exp = _setup_auto_exp(
                ws,
                eval_section=_eval_yaml(_EV_BENCH, _TRACK),
                scripts={"evaluation/benchmarks/pass.py": _BENCH_PASS},
            )
            self._multiturn_trace(exp)
            spec = parse_experiment_yaml(exp / "experiment.yaml")

            # inline evaluation (same code path as run)
            inline = evaluation.run_evaluation(exp, spec)
            inline_status = inline.tracks[0].status

            # reset scores/ and re-evaluate via eval CLI
            import shutil
            shutil.rmtree(exp / "evidence" / "scores", ignore_errors=True)

            rc, out, err = _run_cli(["eval", "experiments/demo"])
            self.assertEqual(rc, 0 if inline_status != "error" else 3, err)
            agg = json.loads(
                (exp / "evidence" / "scores" / "tracks" / "quality.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(agg["status"], inline_status,
                             "eval and inline evaluation must agree on multiturn evidence")

    def test_eval_multiturn_trace_not_modified(self):
        """eval must not touch the trace file even when the record has a transcript."""
        with _workspace() as ws:
            exp = _setup_auto_exp(
                ws,
                eval_section=_eval_yaml(_EV_BENCH, _TRACK),
                scripts={"evaluation/benchmarks/pass.py": _BENCH_PASS},
            )
            self._multiturn_trace(exp)
            trace_path = exp / "evidence" / "traces" / "runtime-a.jsonl"
            original_bytes = trace_path.read_bytes()
            _run_cli(["eval", "experiments/demo"])
            self.assertEqual(trace_path.read_bytes(), original_bytes)


# ===========================================================================
# 8. CLI surface: eval in 9-command set, help text, Next hints
# ===========================================================================

class TestEvalCliSurface(unittest.TestCase):
    """eval is the 9th command; it appears in the loop stage grouping and its
    help line names its <experiment> object."""

    def test_eval_in_nine_command_set(self):
        from agent_harness_lab.cli import build_parser
        import argparse
        parser = build_parser()
        choices: set[str] = set()
        for a in parser._actions:
            if isinstance(a, argparse._SubParsersAction):
                choices = set(a.choices.keys())
        self.assertIn("eval", choices)
        self.assertEqual(len(choices), 9, f"expected 9 commands, got {sorted(choices)}")

    def test_eval_in_gate_execute_stage_in_epilog(self):
        text = cli.build_parser().format_help()
        self.assertIn("eval", text)
        self.assertIn("gate & execute", text)

    def test_eval_help_line_names_experiment(self):
        import re
        text = cli.build_parser().format_help()
        self.assertRegex(text, r"eval\s+<experiment>:")

    def test_eval_subcommand_usage_shows_experiment_metavar(self):
        import argparse
        for a in cli.build_parser()._actions:
            if isinstance(a, argparse._SubParsersAction):
                usage = a.choices["eval"].format_usage()
                self.assertIn("<experiment>", usage)

    def test_eval_next_hint_points_at_report(self):
        """eval's output must include a Next: hint pointing toward report."""
        with _workspace() as ws:
            exp = _setup_auto_exp(
                ws,
                eval_section=_eval_yaml(_EV_BENCH, _TRACK),
                scripts={"evaluation/benchmarks/pass.py": _BENCH_PASS},
            )
            _seed_trace(exp)
            _, out, _ = _run_cli(["eval", "experiments/demo"])
            self.assertIn("Next:", out)
            self.assertIn("report", out)

    def test_run_next_hint_mentions_eval_when_pending(self):
        """run's Next hint mentions eval when evaluation tracks are pending."""
        ev = "    - id: j1\n      method: llm_judge\n      rubric: rubrics/r.md\n"
        tr = "    - id: judged\n      evaluators: [j1]\n      evidence: [traces]\n"
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL")}
        with unittest.mock.patch.dict(os.environ, env_clean, clear=True):
            with _workspace() as ws:
                exp = _setup_auto_exp(
                    ws,
                    eval_section=_eval_yaml(ev, tr),
                    scripts={"evaluation/rubrics/r.md": "# rubric\n"},
                )
                rc, out, _ = _run_cli(["run", "experiments/demo"])
                # exit 0 (pending track is not a failure)
                self.assertEqual(rc, 0)
                self.assertIn("eval", out)


# Need unittest.mock imported for TestEvalTrackError.test_pending_track_exits_0
import unittest.mock


if __name__ == "__main__":
    unittest.main()
