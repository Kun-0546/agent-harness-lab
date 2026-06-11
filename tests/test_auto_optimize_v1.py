"""Auto Optimize (Section 4): bounded, deterministic candidate→evaluate→promote loop.

Copy-only + mutation_script candidate generation; protected surface is enforced;
promotion_policy gates promotion; stop_conditions (max_iterations / no_improvement)
bound the loop; optimization/history.jsonl is written. No LLM mutation.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_harness_lab import auto_optimize
from agent_harness_lab.experiment_spec import parse_experiment_yaml
from tests.test_auto_v1 import _workspace

_EXE = sys.executable.replace("\\", "/")

# local_cli agent: echoes "BASE:<input>" — the benchmark fails (needs GOOD)
_AGENT_ECHO = (
    "import json,sys\n"
    "for line in sys.stdin:\n"
    "    d=json.loads(line)\n"
    "    sys.stdout.write(json.dumps({'response':'BASE:'+d.get('input','')})+'\\n')\n"
    "    sys.stdout.flush()\n"
)
# benchmark: passes iff some trace response contains 'GOOD'
_BENCH_NEEDS_GOOD = (
    "import json,sys\n"
    "ctx=json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "ok=any('GOOD' in (r.get('response') or '') "
    "for recs in ctx.get('traces',{}).values() for r in recs)\n"
    "print(json.dumps({'passed':ok,'score':1.0 if ok else 0.0}))\n"
)
# mutation: rewrite the candidate's agent.py BASE->GOOD (so the benchmark passes)
_MUT_MAKE_GOOD = (
    "import sys,os\n"
    "cand=sys.argv[2]\n"
    "p=os.path.join(cand,'agent.py')\n"
    "src=open(p,encoding='utf-8').read()\n"
    "open(p,'w',encoding='utf-8').write(src.replace('BASE:','GOOD:'))\n"
)
# mutation: illegally append to the protected cases/ file (and also mutate agent)
_MUT_VIOLATE = (
    "import sys,os\n"
    "cand=sys.argv[2]\n"
    "exp=os.path.dirname(os.path.dirname(os.path.dirname(cand)))\n"
    "open(os.path.join(exp,'cases','cases.jsonl'),'a',encoding='utf-8').write('{\"id\":\"hax\"}\\n')\n"
    "p=os.path.join(cand,'agent.py')\n"
    "src=open(p,encoding='utf-8').read()\n"
    "open(p,'w',encoding='utf-8').write(src.replace('BASE:','GOOD:'))\n"
)

_ARTIFACT_REQUIRED = ("artifacts:\n  collect:\n    - id: out\n      glob: \"produced/**\"\n"
                       "      required: true\n")


def _setup(ws, *, max_iterations=2, patience=None, mutation_script=None,
           promotion_policy="", artifacts="", evaluator=_BENCH_NEEDS_GOOD):
    exp = ws / "experiments" / "demo"
    (exp / "harnesses" / "base").mkdir(parents=True, exist_ok=True)
    (exp / "harnesses" / "base" / "agent.py").write_text(_AGENT_ECHO, encoding="utf-8")
    (exp / "cases").mkdir(parents=True, exist_ok=True)
    (exp / "cases" / "cases.jsonl").write_text('{"id":"case-001","input":"x"}\n', encoding="utf-8")
    (exp / "agent-runtimes").mkdir(parents=True, exist_ok=True)
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(
        f"id: runtime-a\nconnector:\n  type: local_cli\n  command: {_EXE} agent.py\n"
        f"  working_dir: ./harnesses/base\n  timeout: 20\n" + artifacts, encoding="utf-8")
    (exp / "evaluation" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (exp / "evaluation" / "benchmarks" / "b.py").write_text(evaluator, encoding="utf-8")
    stops = f"  stop_conditions:\n    - type: max_iterations\n      value: {max_iterations}\n"
    if patience:
        stops += f"    - type: no_improvement\n      patience: {patience}\n"
    mut = f"  mutation_script: {mutation_script}\n" if mutation_script else ""
    yaml = ("id: demo\nstatus: draft\nquestion: q\n"
            "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
            "harnesses:\n  - id: base\n    name: base\n    path: harnesses/base/\n"
            "agent_runtimes:\n  - id: runtime-a\n    harness: base\n"
            "    spec: agent-runtimes/runtime-a.yaml\n"
            "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
            "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: e1\n"
            "      method: benchmark\n      script: benchmarks/b.py\n"
            "  tracks:\n    - id: quality\n      evaluators: [e1]\n      evidence: [traces]\n"
            "objective:\n  primary_track: quality\n  optimize_for: maximize\n"
            "optimization:\n  enabled: true\n  editable_surface:\n    - harnesses/base\n"
            + stops + promotion_policy + mut)
    (exp / "experiment.yaml").write_text(yaml, encoding="utf-8")
    return exp


def _spec(exp):
    return parse_experiment_yaml(exp / "experiment.yaml")


def _write_mut(exp, body):
    (exp / "mutate.py").write_text(body, encoding="utf-8")


class TestAutoOptimize(unittest.TestCase):
    def test_copy_only_bounded_loop_runs_and_writes_history(self):
        with _workspace() as ws:
            exp = _setup(ws, max_iterations=2)  # copy-only: base never passes
            res = auto_optimize.run_optimization(exp, _spec(exp))
            self.assertEqual(len(res.iterations), 2)
            self.assertEqual(res.promotions, 0)
            self.assertEqual(res.stopped_by, "max_iterations")
            hist = exp / "optimization" / "history.jsonl"
            self.assertTrue(hist.is_file())
            self.assertEqual(len([ln for ln in hist.read_text(encoding="utf-8").splitlines()
                                  if ln.strip()]), 2)

    def test_mutation_script_creates_changed_candidate(self):
        with _workspace() as ws:
            exp = _setup(ws, max_iterations=1, mutation_script="mutate.py")
            _write_mut(exp, _MUT_MAKE_GOOD)
            auto_optimize.run_optimization(exp, _spec(exp))
            cand = exp / "harnesses" / "candidates" / "iter-001" / "agent.py"
            self.assertTrue(cand.is_file())
            self.assertIn("GOOD:", cand.read_text(encoding="utf-8"))

    def test_primary_track_pass_promotes_candidate(self):
        with _workspace() as ws:
            exp = _setup(ws, max_iterations=1, mutation_script="mutate.py")
            _write_mut(exp, _MUT_MAKE_GOOD)
            res = auto_optimize.run_optimization(exp, _spec(exp))
            self.assertEqual(res.promotions, 1)
            self.assertTrue(res.iterations[0].promoted)
            inc = exp / "harnesses" / "incumbent" / "agent.py"
            self.assertIn("GOOD:", inc.read_text(encoding="utf-8"))  # incumbent updated

    def test_protected_surface_cannot_be_modified(self):
        with _workspace() as ws:
            exp = _setup(ws, max_iterations=1, mutation_script="mutate.py")
            _write_mut(exp, _MUT_VIOLATE)
            cases_before = (exp / "cases" / "cases.jsonl").read_text(encoding="utf-8")
            res = auto_optimize.run_optimization(exp, _spec(exp))
            self.assertEqual(res.promotions, 0)
            self.assertIn("protected", res.iterations[0].reason)
            # the protected cases file was rolled back, not left mutated
            self.assertEqual((exp / "cases" / "cases.jsonl").read_text(encoding="utf-8"),
                             cases_before)

    def test_block_on_issues_prevents_promotion(self):
        with _workspace() as ws:
            # mutation makes the benchmark pass, but a required artifact is never
            # produced → missing_artifact (error) → promotion blocked
            exp = _setup(ws, max_iterations=1, mutation_script="mutate.py",
                         artifacts=_ARTIFACT_REQUIRED)
            _write_mut(exp, _MUT_MAKE_GOOD)
            res = auto_optimize.run_optimization(exp, _spec(exp))
            self.assertEqual(res.promotions, 0)
            self.assertIn("blocking", res.iterations[0].reason)
            self.assertEqual(res.iterations[0].primary_status, "passed")  # eval passed...
            self.assertGreater(res.iterations[0].issues, 0)               # ...but issue blocks

    def test_max_iterations_stops_loop(self):
        with _workspace() as ws:
            exp = _setup(ws, max_iterations=3)  # copy-only, never promotes
            res = auto_optimize.run_optimization(exp, _spec(exp))
            self.assertEqual(len(res.iterations), 3)
            self.assertEqual(res.stopped_by, "max_iterations")

    def test_no_improvement_stops_loop(self):
        with _workspace() as ws:
            exp = _setup(ws, max_iterations=5, patience=2)  # copy-only never improves
            res = auto_optimize.run_optimization(exp, _spec(exp))
            self.assertEqual(res.stopped_by, "no_improvement")
            self.assertEqual(len(res.iterations), 2)


class TestConfigFormPinning(unittest.TestCase):
    """Pin the previously untested stop_conditions / promotion_policy config forms
    (R3 precondition: nailed down BEFORE the exit-code change consumes the
    severity chain)."""

    def test_parse_stops_no_improvement_value_key_fallback(self):
        # {type: no_improvement, value: K} — `value` is the fallback for `patience`
        opt = SimpleNamespace(stop_conditions=[{"type": "no_improvement", "value": 3}])
        self.assertEqual(auto_optimize._parse_stops(opt), (auto_optimize._SAFETY_CAP, 3))

    def test_parse_stops_single_key_forms(self):
        # {max_iterations: N} / {no_improvement: K} single-key shorthand
        opt = SimpleNamespace(stop_conditions=[{"max_iterations": 4}, {"no_improvement": 2}])
        self.assertEqual(auto_optimize._parse_stops(opt), (4, 2))

    def test_parse_promotion_block_on_issues_list_and_false(self):
        got = auto_optimize._parse_promotion(
            SimpleNamespace(promotion_policy={"block_on_issues": ["case_failure"]}))
        self.assertEqual(got, (True, False, ["case_failure"]))
        got = auto_optimize._parse_promotion(
            SimpleNamespace(promotion_policy={"block_on_issues": False}))
        self.assertEqual(got, (True, False, False))

    def test_count_blocking_list_form_counts_by_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp)
            (ev / "issues.jsonl").write_text(
                '{"type":"case_failure","severity":"error"}\n'
                '{"type":"empty_output","severity":"error"}\n'
                '{"type":"missing_trace","severity":"warn"}\n', encoding="utf-8")
            self.assertEqual(auto_optimize._count_blocking(ev, ["case_failure"]), 1)
            self.assertEqual(
                auto_optimize._count_blocking(ev, ["case_failure", "empty_output"]), 2)

    def test_count_blocking_explicit_false_ignores_error_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp)
            (ev / "issues.jsonl").write_text(
                '{"type":"case_failure","severity":"error"}\n', encoding="utf-8")
            self.assertEqual(auto_optimize._count_blocking(ev, False), 0)

    def test_count_blocking_truthy_counts_error_severity_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp)
            (ev / "issues.jsonl").write_text(
                '{"type":"case_failure","severity":"error"}\n'
                '{"type":"missing_trace","severity":"warn"}\n', encoding="utf-8")
            self.assertEqual(auto_optimize._count_blocking(ev, True), 1)


if __name__ == "__main__":
    unittest.main()
