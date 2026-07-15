"""§5 StatePolicy execution (Auto Mode): isolated vs reset are behaviourally distinct.

The two state policies Auto v1 must support are *executable*, not just declarable:

  isolated  a fresh process and disposable working-tree copy per case; neither
            in-process nor filesystem state carries.
  reset     a fresh process per case in the shared declared working directory;
            in-process state resets, while filesystem state may carry.

We prove both boundaries with in-process and on-disk counter agents.
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli, scaffold

_EXE = sys.executable.replace("\\", "/")  # forward slashes → no YAML/shlex escaping

# local_cli agent that counts the sends it has seen IN THIS PROCESS and echoes the count.
_STATEFUL_COUNTER = (
    "import json,sys\n"
    "n=0\n"
    "for line in sys.stdin:\n"
    "    json.loads(line)\n"
    "    n+=1\n"
    "    sys.stdout.write(json.dumps({'response':'count:%d'%n})+'\\n')\n"
    "    sys.stdout.flush()\n"
)

_FILE_STATEFUL_COUNTER = (
    "import json,sys\n"
    "from pathlib import Path\n"
    "p=Path('state.txt')\n"
    "for line in sys.stdin:\n"
    "    json.loads(line)\n"
    "    n=int(p.read_text() if p.exists() else '0')+1\n"
    "    p.write_text(str(n))\n"
    "    sys.stdout.write(json.dumps({'response':'file-count:%d'%n})+'\\n')\n"
    "    sys.stdout.flush()\n"
)

_THREE_CASES = (
    '{"id":"c1","input":"a"}\n'
    '{"id":"c2","input":"b"}\n'
    '{"id":"c3","input":"c"}\n'
)


def _experiment_yaml(state_policy):
    return (
        "id: demo\nstatus: draft\ngoal_ref: ../../goal.md\nquestion: q\n"
        "run:\n  mode: auto\n"
        f"execution:\n  mode: ab\n  state_policy: {state_policy}\n"
        "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
        "agent_runtimes:\n  - id: runtime-a\n    harness: A\n    spec: agent-runtimes/runtime-a.yaml\n"
        "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
        "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: e1\n      method: benchmark\n"
        "collection:\n  traces: true\n  raw: true\n  artifacts: true\n  snapshots: false\n  scores: true\n"
        "reports:\n  formats:\n    - md\n"
    )


@contextmanager
def _workspace():
    import os
    tmp = tempfile.TemporaryDirectory()
    saved = os.getcwd()
    os.chdir(tmp.name)
    try:
        yield Path(tmp.name)
    finally:
        os.chdir(saved)
        tmp.cleanup()


def _setup(root, state_policy, agent_code=_STATEFUL_COUNTER):
    scaffold.init_workspace(root)
    exp = scaffold.new_experiment(root, "demo", run_mode="auto").experiment_dir
    (exp / "experiment.yaml").write_text(_experiment_yaml(state_policy), encoding="utf-8")
    (exp / "cases" / "cases.jsonl").write_text(_THREE_CASES, encoding="utf-8")
    (exp / "rt").mkdir(exist_ok=True)
    (exp / "rt" / "agent.py").write_text(agent_code, encoding="utf-8")
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(
        f"id: runtime-a\nconnector:\n  type: local_cli\n"
        f"  command: {_EXE} agent.py\n  working_dir: ./rt\n  timeout: 20\n",
        encoding="utf-8")
    return exp


def _run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(args)
    return rc, out.getvalue()


def _responses(exp):
    """The per-case 'response' values from the runtime trace, in case order."""
    tf = exp / "evidence" / "traces" / "runtime-a.jsonl"
    return [json.loads(ln)["response"]
            for ln in tf.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _issue_types(exp):
    p = exp / "evidence" / "issues.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln)["type"] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


class TestStatePolicyExecution(unittest.TestCase):
    def test_isolated_restarts_process_per_case(self):
        with _workspace() as ws:
            exp = _setup(ws, "isolated")
            rc, _ = _run(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertEqual(_responses(exp), ["count:1", "count:1", "count:1"])

    def test_reset_restarts_fresh_process_per_case_state_does_not_carry(self):
        with _workspace() as ws:
            exp = _setup(ws, "reset")
            rc, _ = _run(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            # fresh process before each case → the counter resets every time
            self.assertEqual(_responses(exp), ["count:1", "count:1", "count:1"])

    def test_isolated_discards_filesystem_state_between_cases(self):
        with _workspace() as ws:
            exp = _setup(ws, "isolated", _FILE_STATEFUL_COUNTER)
            self.assertEqual(_run(["run", "experiments/demo"])[0], 0)
            self.assertEqual(_responses(exp),
                             ["file-count:1", "file-count:1", "file-count:1"])
            self.assertFalse((exp / "rt" / "state.txt").exists())

    def test_reset_preserves_filesystem_state_between_cases(self):
        with _workspace() as ws:
            exp = _setup(ws, "reset", _FILE_STATEFUL_COUNTER)
            self.assertEqual(_run(["run", "experiments/demo"])[0], 0)
            self.assertEqual(_responses(exp),
                             ["file-count:1", "file-count:2", "file-count:3"])
            self.assertEqual((exp / "rt" / "state.txt").read_text(), "3")

    def test_reset_dispatches_all_cases_cleanly(self):
        with _workspace() as ws:
            exp = _setup(ws, "reset")
            self.assertEqual(_run(["run", "experiments/demo"])[0], 0)
            # all three cases ran, no connector/case issues on the happy path
            self.assertEqual(len(_responses(exp)), 3)
            self.assertEqual(_issue_types(exp), [])
