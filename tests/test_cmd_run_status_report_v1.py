"""run: Copilot Mode generates agent-task.md (exit 0); Auto Mode runs (exit 0);
report generates reports/report.md (exit 0); a config ERROR blocks run/report
(exit 1); status works. Plus the exit-code contract (R3): 0 success / 1 config
or preflight error / 2 not implemented / 3 runtime failure, for both the Auto
Run and Auto Optimize exits."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agent_harness_lab import cli, scaffold

_EXE = sys.executable.replace("\\", "/")  # forward slashes → no YAML/shlex escaping


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


@contextmanager
def _no_judge_env():
    """No AHL_JUDGE_* in the environment: llm_judge stays pending (never network)."""
    with mock.patch.dict(os.environ, {}, clear=False):
        for k in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL"):
            os.environ.pop(k, None)
        yield


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
        # Auto Mode is implemented and the fresh scaffold is runnable (R4): the
        # PLACEHOLDER echo agents respond, evidence is written, and the only
        # non-passed evaluation state is pending (llm_judge/human without a key),
        # which the exit-code contract exempts — exit 0, no HLAB_* failure code.
        with workspace_with_experiment(name="autox", run_mode="auto") as ws, _no_judge_env():
            rc, out, err = _invoke(["run", "experiments/autox"])
            self.assertEqual(rc, 0, err)
            self.assertIn("Auto Mode", out)
            self.assertTrue((ws / "experiments" / "autox" / "evidence" / "issues.jsonl").is_file())
            self.assertNotIn("HLAB_RUNTIME_FAILURE", err)
            self.assertNotIn("HLAB_EVAL_ERROR", err)

    def test_run_blocked_on_review_error_exit_1(self):
        with workspace_with_experiment() as ws:
            shutil.rmtree(ws / "experiments" / "demo" / "cases")
            rc, _out, _err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 1, "config error must block run with exit 1, not 2")

    def test_run_not_found_exit_1(self):
        with workspace_with_experiment() as _ws:
            rc, _out, _err = _invoke(["run", "experiments/nope"])
            self.assertEqual(rc, 1)


class TestRunExitContract(unittest.TestCase):
    """R3: the Auto Run exit — exit 3 on any error-severity issue or any errored
    evaluation track; pending / failed evaluations and warn-only issues exit 0."""

    def test_connector_failure_exits_3_with_named_code(self):
        # working_dir exists (so the review preflight passes), but harness A's
        # agent script is gone → the connector dies at run time → an
        # error-severity connector_failure issue → exit 3 + HLAB_RUNTIME_FAILURE.
        with workspace_with_experiment(name="autox", run_mode="auto") as ws, _no_judge_env():
            (ws / "experiments" / "autox" / "harnesses" / "A" / "agent.py").unlink()
            rc, _out, err = _invoke(["run", "experiments/autox"])
            self.assertEqual(rc, 3)
            self.assertIn("HLAB_RUNTIME_FAILURE", err)
            self.assertIn("connector_failure", err)

    def test_benchmark_nonzero_exit_track_error_exits_3(self):
        # the benchmark script exits non-zero → its evaluator reports `error` →
        # the track aggregates to `error` → exit 3 + HLAB_EVAL_ERROR (and no
        # HLAB_RUNTIME_FAILURE: the agents themselves ran fine).
        with workspace_with_experiment(name="autox", run_mode="auto") as ws, _no_judge_env():
            bench = (ws / "experiments" / "autox" / "evaluation" / "benchmarks"
                     / "check_artifact_exists.py")
            bench.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
            rc, _out, err = _invoke(["run", "experiments/autox"])
            self.assertEqual(rc, 3)
            self.assertIn("HLAB_EVAL_ERROR", err)
            self.assertNotIn("HLAB_RUNTIME_FAILURE", err)

    def test_pending_evaluation_without_judge_key_exits_0(self):
        # no AHL_JUDGE_API_KEY → llm_judge/human stay pending; pending is exempt
        # (otherwise every offline run would "fail") → exit 0.
        with workspace_with_experiment(name="autox", run_mode="auto") as ws, _no_judge_env():
            rc, _out, err = _invoke(["run", "experiments/autox"])
            self.assertEqual(rc, 0, err)
            agg = json.loads((ws / "experiments" / "autox" / "evidence" / "scores"
                              / "tracks" / "skill-artifact.json").read_text(encoding="utf-8"))
            self.assertEqual(agg["status"], "pending")  # really pending, not passed
            self.assertNotIn("HLAB_EVAL_ERROR", err)

    def test_warn_only_issues_exit_0(self):
        # an artifact glob that escapes the working dir yields a warn-severity
        # path_drift issue from the Inspector — warn-level issues never exit 3.
        with workspace_with_experiment(name="autox", run_mode="auto") as ws, _no_judge_env():
            rt = ws / "experiments" / "autox" / "agent-runtimes" / "runtime-a.yaml"
            rt.write_text(rt.read_text(encoding="utf-8").replace(
                'glob: "produced/**"', 'glob: "../outside/**"'), encoding="utf-8")
            rc, _out, err = _invoke(["run", "experiments/autox"])
            self.assertEqual(rc, 0, err)
            issues_file = ws / "experiments" / "autox" / "evidence" / "issues.jsonl"
            issues = [json.loads(ln) for ln in issues_file.read_text(encoding="utf-8")
                      .splitlines() if ln.strip()]
            self.assertTrue(any(i["type"] == "path_drift" and i["severity"] == "warn"
                                for i in issues), issues)  # the warn issue IS there
            self.assertNotIn("HLAB_RUNTIME_FAILURE", err)

    def test_copilot_mode_exits_0_without_failure_codes(self):
        # Copilot Mode executes nothing — the exit-code contract never fires.
        with workspace_with_experiment() as _ws:
            rc, _out, err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertNotIn("HLAB_", err)


# --- Auto Optimize exit (judged on the FINAL incumbent's evidence) -------------

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
# mutation: break iteration 1 (delete the agent → connector_failure), fix iteration 2
_MUT_BREAK_THEN_GOOD = (
    "import sys,os\n"
    "cand=sys.argv[2]; it=int(sys.argv[3])\n"
    "p=os.path.join(cand,'agent.py')\n"
    "if it==1:\n"
    "    os.remove(p)\n"
    "else:\n"
    "    src=open(p,encoding='utf-8').read()\n"
    "    open(p,'w',encoding='utf-8').write(src.replace('BASE:','GOOD:'))\n"
)

_ARTIFACT_REQUIRED = ("artifacts:\n  collect:\n    - id: out\n      glob: \"produced/**\"\n"
                      "      required: true\n")


def _optimize_experiment(root, *, max_iterations=1, mutation_script=None, artifacts=""):
    """A review-clean (no ERROR) single-runtime Auto Optimize experiment."""
    exp = root / "experiments" / "demo"
    (exp / "harnesses" / "base").mkdir(parents=True, exist_ok=True)
    (exp / "harnesses" / "base" / "agent.py").write_text(_AGENT_ECHO, encoding="utf-8")
    (exp / "cases").mkdir(parents=True, exist_ok=True)
    (exp / "cases" / "cases.jsonl").write_text('{"id":"case-001","input":"x"}\n',
                                               encoding="utf-8")
    (exp / "agent-runtimes").mkdir(parents=True, exist_ok=True)
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(
        f"id: runtime-a\nconnector:\n  type: local_cli\n  command: {_EXE} agent.py\n"
        f"  working_dir: ./harnesses/base\n  timeout: 20\n" + artifacts, encoding="utf-8")
    (exp / "evaluation" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (exp / "evaluation" / "benchmarks" / "b.py").write_text(_BENCH_NEEDS_GOOD,
                                                            encoding="utf-8")
    mut = "  mutation_script: mutate.py\n" if mutation_script else ""
    if mutation_script:
        (exp / "mutate.py").write_text(mutation_script, encoding="utf-8")
    yaml = ("id: demo\nstatus: draft\nquestion: q\n"
            "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
            "harnesses:\n  - id: base\n    name: base\n    path: harnesses/base/\n"
            "agent_runtimes:\n  - id: runtime-a\n    harness: base\n"
            "    spec: agent-runtimes/runtime-a.yaml\n"
            "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
            "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: e1\n"
            "      method: benchmark\n      script: benchmarks/b.py\n"
            "  tracks:\n    - id: quality\n      evaluators: [e1]\n      evidence: [traces]\n"
            "collection:\n  traces: true\n  raw: true\n  artifacts: true\n"
            "  snapshots: false\n  scores: true\n"
            "reports:\n  formats:\n    - md\n"
            "objective:\n  primary_track: quality\n  optimize_for: maximize\n"
            "optimization:\n  enabled: true\n  editable_surface:\n    - harnesses/base\n"
            "  stop_conditions:\n    - type: max_iterations\n"
            f"      value: {max_iterations}\n" + mut)
    (exp / "experiment.yaml").write_text(yaml, encoding="utf-8")
    return exp


@contextmanager
def _optimize_workspace(**kw):
    tmp = tempfile.TemporaryDirectory()
    saved = os.getcwd()
    os.chdir(tmp.name)
    try:
        root = Path(tmp.name)
        scaffold.init_workspace(root)
        _optimize_experiment(root, **kw)
        yield root
    finally:
        os.chdir(saved)
        tmp.cleanup()


class TestOptimizeExitContract(unittest.TestCase):
    """R3: the Auto Optimize exit judges the FINAL incumbent's evidence — never
    the union of all iterations."""

    def test_promoted_final_incumbent_clean_exits_0(self):
        with _optimize_workspace(mutation_script=_MUT_MAKE_GOOD) as _ws, _no_judge_env():
            rc, out, err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 0, err)
            self.assertIn("Auto Optimize", out)
            self.assertIn("1 promotion(s)", out)
            self.assertNotIn("HLAB_", err)

    def test_failed_evaluation_is_a_legitimate_answer_exits_0(self):
        # copy-only: the candidate never passes the benchmark → rejected — but a
        # FAILED evaluation is a legitimate experiment result, not a runtime failure.
        with _optimize_workspace() as _ws, _no_judge_env():
            rc, out, err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 0, err)
            self.assertIn("0 promotion(s)", out)
            self.assertNotIn("HLAB_", err)

    def test_final_evidence_error_issue_exits_3(self):
        # a required artifact is never produced → missing_artifact (error) in the
        # loop's final evidence → exit 3 + HLAB_RUNTIME_FAILURE.
        with _optimize_workspace(mutation_script=_MUT_MAKE_GOOD,
                                 artifacts=_ARTIFACT_REQUIRED) as _ws, _no_judge_env():
            rc, _out, err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 3)
            self.assertIn("HLAB_RUNTIME_FAILURE", err)
            self.assertIn("missing_artifact", err)

    def test_judges_final_incumbent_not_iteration_union(self):
        # iteration 1 breaks the candidate (connector_failure, error) and is
        # rejected; iteration 2 is promoted clean. Judging the union would exit 3;
        # the final-incumbent contract exits 0.
        with _optimize_workspace(max_iterations=2,
                                 mutation_script=_MUT_BREAK_THEN_GOOD) as _ws, _no_judge_env():
            rc, out, err = _invoke(["run", "experiments/demo"])
            self.assertEqual(rc, 0, err)
            self.assertIn("1 promotion(s)", out)
            self.assertNotIn("HLAB_", err)


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
