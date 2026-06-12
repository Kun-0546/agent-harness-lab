"""Auto Mode (run.mode=auto): AutoRunner + local_cli/script connectors + EvidenceCollector.

Each test builds a minimal valid auto experiment with ONE runtime pointing at a real
agent/script in a working dir, then runs it and inspects evidence/ + issues.jsonl.
"""
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import auto, cli, scaffold
from agent_harness_lab.experiment_spec import parse_experiment_yaml

_EXE = sys.executable.replace("\\", "/")  # forward slashes → no YAML/shlex escaping

# local_cli echo agent that also writes an artifact under produced/
_ECHO_ARTIFACT = (
    "import json,sys,os\n"
    "os.makedirs('produced', exist_ok=True)\n"
    "for line in sys.stdin:\n"
    "    d=json.loads(line)\n"
    "    open('produced/out.txt','w',encoding='utf-8').write('art:'+d.get('input',''))\n"
    "    sys.stdout.write(json.dumps({'response':'echo:'+d.get('input','')})+'\\n')\n"
    "    sys.stdout.flush()\n"
)
_ECHO_NO_ARTIFACT = (
    "import json,sys\n"
    "for line in sys.stdin:\n"
    "    d=json.loads(line)\n"
    "    sys.stdout.write(json.dumps({'response':'echo:'+d.get('input','')})+'\\n')\n"
    "    sys.stdout.flush()\n"
)
_ECHO_EMPTY = (  # responds, but with empty content → empty_output
    "import json,sys\n"
    "for line in sys.stdin:\n"
    "    json.loads(line)\n"
    "    sys.stdout.write(json.dumps({'response':''})+'\\n'); sys.stdout.flush()\n"
)
_GARBAGE = (  # non-JSON output → connector_failure (parse error)
    "import sys\n"
    "for line in sys.stdin:\n"
    "    sys.stdout.write('not json at all\\n'); sys.stdout.flush()\n"
)
_SLEEP = "import time\ntime.sleep(5)\n"  # ignores stdin, never responds → timeout

# script connector runner: reads {case_file}, writes an artifact, prints stdout, exits 0
_SCRIPT_OK = (
    "import json,sys,os\n"
    "case=json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "os.makedirs('produced', exist_ok=True)\n"
    "open('produced/out.txt','w',encoding='utf-8').write('art:'+case.get('input',''))\n"
    "print('ran:'+case.get('input',''))\n"
)
_SCRIPT_FAIL = "import sys\nsys.exit(3)\n"   # non-zero exit → case_failure
_SCRIPT_SLEEP = "import time\ntime.sleep(8)\n"  # ignores everything → connector timeout (small blast radius)
# writes an artifact only for cases with make_artifact:true (per-case isolation test)
_SCRIPT_COND = (
    "import json,sys,os\n"
    "case=json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "if case.get('make_artifact'):\n"
    "    os.makedirs('produced', exist_ok=True)\n"
    "    open('produced/out.txt','w',encoding='utf-8').write('from '+case.get('id',''))\n"
    "print('ran:'+case.get('id',''))\n"
)
# local_cli echo that writes an artifact only when input == 'make'
_ECHO_COND = (
    "import json,sys,os\n"
    "for line in sys.stdin:\n"
    "    d=json.loads(line)\n"
    "    if d.get('input')=='make':\n"
    "        os.makedirs('produced', exist_ok=True)\n"
    "        open('produced/out.txt','w',encoding='utf-8').write('art')\n"
    "    sys.stdout.write(json.dumps({'response':'ok'})+'\\n'); sys.stdout.flush()\n"
)
# Script whose DIRECT child exits at once but backgrounds a worker that INHERITS
# the child's stdout/stderr and lives far longer than the connector timeout. Under
# the old PIPE+communicate path this worker held the pipe open, so communicate()
# could not see EOF and parked the main thread (the canonical hang). It writes its
# pid (so a test can verify reaping) and would write survivor_finished.txt only if
# it survives its full sleep.
_SCRIPT_BG_SURVIVOR = (
    "import json,sys,os,subprocess\n"
    "case=json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "out_dir=sys.argv[2]\n"
    "grand=\"import time,sys\\ntime.sleep(20)\\nopen(sys.argv[1],'w').write('x')\\n\"\n"
    "marker=os.path.join(out_dir,'survivor_finished.txt')\n"
    "p=subprocess.Popen([sys.executable,'-c',grand,marker])\n"
    "open(os.path.join(out_dir,'survivor.pid'),'w',encoding='utf-8').write(str(p.pid))\n"
    "print('ran:'+str(case.get('id','')))\n"
)


def _survivor_pid(exp):
    p = exp / "evidence" / "raw" / "runtime-a" / "case-001" / "survivor.pid"
    return int(p.read_text(encoding="utf-8").strip()) if p.exists() else None


def _alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # POSIX: signal 0 just probes existence
        return True
    except OSError:
        return False


def _kill(pid):
    if pid is None:
        return
    try:
        if hasattr(os, "killpg"):
            os.kill(pid, signal.SIGKILL)
        else:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=False)
    except OSError:
        pass


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


def _experiment_yaml(connector_spec_ok=True):
    return (
        "id: demo\nstatus: draft\ngoal_ref: ../../goal.md\nquestion: q\n"
        "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
        "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
        "agent_runtimes:\n  - id: runtime-a\n    harness: A\n    spec: agent-runtimes/runtime-a.yaml\n"
        "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
        "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: e1\n      method: benchmark\n"
        "collection:\n  traces: true\n  raw: true\n  artifacts: true\n  snapshots: false\n  scores: true\n"
        "reports:\n  formats:\n    - md\n"
    )


def _setup(root, *, connector="local_cli", agent=_ECHO_ARTIFACT, required_artifact=True,
           timeout=20, cases='{"id":"case-001","input":"hello"}\n'):
    """Build a single-runtime auto experiment ready to run. Returns the experiment dir."""
    scaffold.init_workspace(root)
    exp = scaffold.new_experiment(root, "demo", run_mode="auto").experiment_dir
    (exp / "experiment.yaml").write_text(_experiment_yaml(), encoding="utf-8")
    (exp / "cases" / "cases.jsonl").write_text(cases, encoding="utf-8")
    (exp / "rt").mkdir(exist_ok=True)
    art = ("artifacts:\n  collect:\n    - id: out\n      glob: \"produced/**\"\n"
           f"      required: {'true' if required_artifact else 'false'}\n")
    if connector == "manual":
        rt = "id: runtime-a\nconnector:\n  type: manual\n"
    elif connector == "script":
        (exp / "rt" / "runner.py").write_text(agent, encoding="utf-8")
        # script connector runs via shell=True; native double-quoted exe works in
        # both /bin/sh and cmd.exe. Whole command is one (single-quoted) YAML scalar.
        rt = (f"id: runtime-a\nconnector:\n  type: script\n"
              f"  command: '\"{sys.executable}\" runner.py {{case_file}} {{output_dir}}'\n"
              f"  working_dir: ./rt\n  timeout: {timeout}\n" + art)
    else:  # local_cli
        (exp / "rt" / "agent.py").write_text(agent, encoding="utf-8")
        rt = (f"id: runtime-a\nconnector:\n  type: local_cli\n"
              f"  command: {_EXE} agent.py\n  working_dir: ./rt\n  timeout: {timeout}\n" + art)
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(rt, encoding="utf-8")
    return exp


def _run_cli(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(args)
    return rc, out.getvalue(), err.getvalue()


def _issue_types(exp):
    p = exp / "evidence" / "issues.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln)["type"] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


class TestAutoLocalCli(unittest.TestCase):
    def test_happy_path_writes_evidence_exit_0(self):
        with _workspace() as ws:
            _setup(ws, connector="local_cli")
            rc, out, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            exp = ws / "experiments" / "demo"
            tf = exp / "evidence" / "traces" / "runtime-a.jsonl"
            self.assertTrue(tf.is_file())
            rec = json.loads(tf.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rec["response"], "echo:hello")
            self.assertTrue(rec["ok"])
            self.assertEqual((exp / "evidence" / "raw" / "runtime-a" / "case-001.out")
                             .read_text(encoding="utf-8").strip(), "echo:hello")
            self.assertTrue((exp / "evidence" / "artifacts" / "runtime-a" / "case-001"
                             / "produced" / "out.txt").is_file())
            self.assertEqual(_issue_types(exp), [])  # no issues on the happy path
            self.assertIn("Auto Mode", out)

    def test_evidence_dirs_and_issues_file_created(self):
        with _workspace() as ws:
            _setup(ws)
            _run_cli(["run", "experiments/demo"])
            exp = ws / "experiments" / "demo"
            for sub in ("traces", "raw", "artifacts"):
                self.assertTrue((exp / "evidence" / sub).is_dir())
            self.assertTrue((exp / "evidence" / "issues.jsonl").is_file())

    def test_required_artifact_missing_issue(self):
        with _workspace() as ws:
            _setup(ws, agent=_ECHO_NO_ARTIFACT, required_artifact=True)
            _run_cli(["run", "experiments/demo"])
            self.assertIn("missing_artifact", _issue_types(ws / "experiments" / "demo"))

    def test_empty_output_issue(self):
        with _workspace() as ws:
            _setup(ws, agent=_ECHO_EMPTY, required_artifact=False)
            _run_cli(["run", "experiments/demo"])
            self.assertIn("empty_output", _issue_types(ws / "experiments" / "demo"))

    def test_invalid_json_output_connector_failure(self):
        with _workspace() as ws:
            _setup(ws, agent=_GARBAGE, required_artifact=False)
            _run_cli(["run", "experiments/demo"])
            self.assertIn("connector_failure", _issue_types(ws / "experiments" / "demo"))

    def test_rerun_appends_as_trial_1(self):
        # PR5a: re-run appends as new trial instead of truncating.
        with _workspace() as ws:
            _setup(ws, connector="local_cli")  # 1 case
            _run_cli(["run", "experiments/demo"])
            _run_cli(["run", "experiments/demo"])  # re-run → trial 1
            tf = ws / "experiments" / "demo" / "evidence" / "traces" / "runtime-a.jsonl"
            lines = [ln for ln in tf.read_text(encoding="utf-8").splitlines() if ln.strip()]
            # 1 case × 2 trials = 2 records; trial-0 has no `trial` field,
            # trial-1 carries `trial: 1`
            self.assertEqual(len(lines), 2)
            import json as _j
            recs = [_j.loads(ln) for ln in lines]
            self.assertNotIn("trial", recs[0])  # trial 0 stays byte-identical
            self.assertEqual(recs[1].get("trial"), 1)

    def test_fresh_flag_wipes_and_starts_trial_0(self):
        with _workspace() as ws:
            _setup(ws, connector="local_cli")  # 1 case
            _run_cli(["run", "experiments/demo"])
            _run_cli(["run", "--fresh", "experiments/demo"])  # wipe + clean trial 0
            tf = ws / "experiments" / "demo" / "evidence" / "traces" / "runtime-a.jsonl"
            lines = [ln for ln in tf.read_text(encoding="utf-8").splitlines() if ln.strip()]
            # --fresh wipes then runs trial 0 → exactly 1 record, no trial field
            self.assertEqual(len(lines), 1)
            import json as _j
            rec = _j.loads(lines[0])
            self.assertNotIn("trial", rec)

    def test_connector_timeout_failure(self):
        with _workspace() as ws:
            _setup(ws, agent=_SLEEP, required_artifact=False, timeout=1)
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            # exit-code contract (R3): an error-severity connector_failure is a
            # runtime failure → exit 3 (the issue is still recorded as evidence)
            self.assertEqual(rc, 3)
            self.assertIn("connector_failure", _issue_types(ws / "experiments" / "demo"))


class TestAutoScript(unittest.TestCase):
    def test_script_happy_path(self):
        with _workspace() as ws:
            _setup(ws, connector="script", agent=_SCRIPT_OK)
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            exp = ws / "experiments" / "demo"
            rec = json.loads((exp / "evidence" / "traces" / "runtime-a.jsonl")
                             .read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rec["exit_code"], 0)
            self.assertTrue(rec["ok"])
            self.assertEqual((exp / "evidence" / "raw" / "runtime-a" / "case-001.out")
                             .read_text(encoding="utf-8").strip(), "ran:hello")
            self.assertTrue((exp / "evidence" / "artifacts" / "runtime-a" / "case-001"
                             / "produced" / "out.txt").is_file())
            self.assertEqual(_issue_types(exp), [])

    def test_script_nonzero_exit_case_failure(self):
        with _workspace() as ws:
            _setup(ws, connector="script", agent=_SCRIPT_FAIL, required_artifact=False)
            _run_cli(["run", "experiments/demo"])
            self.assertIn("case_failure", _issue_types(ws / "experiments" / "demo"))

    def test_script_timeout_bounded_and_failure(self):
        import time
        with _workspace() as ws:
            _setup(ws, connector="script", agent=_SCRIPT_SLEEP, required_artifact=False, timeout=1)
            t0 = time.monotonic()
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            elapsed = time.monotonic() - t0
            # exit-code contract (R3): the timeout is an error-severity
            # connector_failure → exit 3 (still bounded, still recorded)
            self.assertEqual(rc, 3)
            self.assertLess(elapsed, 25, "script timeout must be bounded, not wait the full sleep")
            self.assertIn("connector_failure", _issue_types(ws / "experiments" / "demo"))


class TestAutoScriptProcessHygiene(unittest.TestCase):
    """Canonical-hang regression. A worker the script backgrounds inherits the
    direct child's stdout/stderr; the run must finish on the DIRECT child's exit
    (never wait on pipe-EOF) and must not leave that worker running. Fails on the
    old PIPE+communicate path; passes with file-redirected stdout + proc.wait +
    process-group sweep."""

    def test_backgrounded_worker_does_not_hang_or_misclassify(self):
        with _workspace() as ws:
            exp = _setup(ws, connector="script", agent=_SCRIPT_BG_SURVIVOR,
                         required_artifact=False, timeout=20)
            t0 = time.monotonic()
            try:
                rc, _, _ = _run_cli(["run", "experiments/demo"])
                elapsed = time.monotonic() - t0
                self.assertEqual(rc, 0)
                # must return on the direct child's exit (~instant), NOT wait the
                # 20s worker holding the inherited stdout/stderr (old: ~timeout).
                self.assertLess(elapsed, 15,
                                "run parked on pipe-EOF held by a backgrounded worker (the hang)")
                rec = json.loads((exp / "evidence" / "traces" / "runtime-a.jsonl")
                                 .read_text(encoding="utf-8").splitlines()[0])
                self.assertTrue(rec["ok"])  # direct child exited 0 → not a false timeout
                self.assertNotIn("connector_failure", _issue_types(exp))
            finally:
                _kill(_survivor_pid(exp))  # release inherited handles for cleanup

    @unittest.skipUnless(hasattr(os, "killpg"), "process-group reaping is POSIX-only")
    def test_backgrounded_worker_is_reaped(self):
        with _workspace() as ws:
            exp = _setup(ws, connector="script", agent=_SCRIPT_BG_SURVIVOR,
                         required_artifact=False, timeout=20)
            _run_cli(["run", "experiments/demo"])
            pid = _survivor_pid(exp)
            self.assertIsNotNone(pid, "script did not record the worker pid")
            deadline = time.monotonic() + 2  # allow a beat for SIGKILL + reap
            while _alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            still = _alive(pid)
            _kill(pid)  # belt-and-suspenders if the assertion is about to fail
            self.assertFalse(still, "backgrounded worker was not reaped (leftover process)")


class TestAutoArtifactIsolation(unittest.TestCase):
    """Per-case artifact isolation: a prior case's leftover must not leak into a later
    case's evidence or mask its required missing_artifact (verified-real major bug)."""

    def test_script_stale_artifact_does_not_leak_or_mask(self):
        with _workspace() as ws:
            cases = ('{"id":"case-001","make_artifact":true}\n'
                     '{"id":"case-002","make_artifact":false}\n')
            _setup(ws, connector="script", agent=_SCRIPT_COND, required_artifact=True, cases=cases)
            _run_cli(["run", "experiments/demo"])
            exp = ws / "experiments" / "demo"
            self.assertIn("missing_artifact", _issue_types(exp))  # case-002 produced nothing
            self.assertFalse((exp / "evidence" / "artifacts" / "runtime-a" / "case-002"
                              / "produced" / "out.txt").exists(), "stale artifact leaked into case-002")
            self.assertTrue((exp / "evidence" / "artifacts" / "runtime-a" / "case-001"
                             / "produced" / "out.txt").is_file())  # case-001 genuinely produced

    def test_local_cli_stale_artifact_does_not_leak_or_mask(self):
        with _workspace() as ws:
            cases = ('{"id":"case-001","input":"make"}\n'
                     '{"id":"case-002","input":"skip"}\n')
            _setup(ws, connector="local_cli", agent=_ECHO_COND, required_artifact=True, cases=cases)
            _run_cli(["run", "experiments/demo"])
            exp = ws / "experiments" / "demo"
            self.assertIn("missing_artifact", _issue_types(exp))
            self.assertFalse((exp / "evidence" / "artifacts" / "runtime-a" / "case-002"
                              / "produced" / "out.txt").exists())
            self.assertTrue((exp / "evidence" / "artifacts" / "runtime-a" / "case-001"
                             / "produced" / "out.txt").is_file())


class TestAutoBoundaries(unittest.TestCase):
    def test_auto_manual_blocks_run_no_evidence(self):
        with _workspace() as ws:
            _setup(ws, connector="manual")
            rc, _, err = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 1)  # review ERROR (auto+manual) blocks the run
            self.assertIn("run blocked", err)
            # AutoRunner never ran → no traces written
            self.assertFalse((ws / "experiments" / "demo" / "evidence" / "traces"
                              / "runtime-a.jsonl").exists())

    def test_copilot_run_unchanged(self):
        # Auto Mode landing must not change Copilot Mode
        with _workspace() as ws:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cli.main(["init"])
                cli.main(["new", "cop", "--mode", "copilot"])
            rc, out, _ = _run_cli(["run", "experiments/cop"])
            self.assertEqual(rc, 0)
            self.assertTrue((ws / "experiments" / "cop" / "agent-task.md").is_file())
            self.assertIn("agent-task.md was generated", out)
            self.assertIn("no Agent Runtime was directly executed", out)


if __name__ == "__main__":
    unittest.main()
