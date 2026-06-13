"""script simulator (v1.1 PR3): protocol A — one subprocess per turn.

Covers the script-type simulator contract (execution-model.md §14.8,
experiment-yaml-schema.md §14a "script simulator"):
  - engine: stdin {"transcript": [...]} -> stdout {"next": str|null}; UTF-8
    safe on Windows; anti-hang hardening (timeout + sweep); every protocol
    violation raises (never a fabricated turn).
  - plan wiring: type=script builds a multi-turn _SimPlan; a missing/undeclared
    script file plans an error (simulator_unconfigured at dispatch).
  - review: script file missing — run.mode auto → ERROR, copilot → WARN.
  - dispatch e2e: trace simulator="script", conditional follow-ups, partial
    transcript on simulator failure, AHL_SIM_STUB redirect, honest failure on
    the script connector.
"""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab.auto import _make_script_simulator, _plan_simulator, run_auto
from agent_harness_lab.experiment_spec import (
    ERROR,
    WARN,
    ExperimentSpec,
    SimulatorSpec,
    parse_experiment_yaml,
)
from tests.test_multiturn_v1 import (
    _ECHO,
    _ECHO_STATEFUL,
    _SCRIPT_OK,
    _experiment_yaml,
    _issue_types,
    _ReviewBase,
    _run_cli,
    _setup,
    _sim_env_patch,
    _traces,
    _workspace,
)

# --- simulator scripts (protocol A: stdin transcript JSON -> stdout next JSON) --

# counting: q1 / q2 follow-ups, then null (sequence-style, but computed)
_SIM_COUNTING = (
    "import json,sys\n"
    "tr=json.load(sys.stdin)['transcript']\n"
    "nxt='q%d'%len(tr) if len(tr)<3 else None\n"
    "print(json.dumps({'next':nxt}))\n"
)
# conditional: the script type's reason to exist — follow up only while the
# agent's last reply lacks a digit
_SIM_NEEDS_NUMBER = (
    "import json,sys,re\n"
    "tr=json.load(sys.stdin)['transcript']\n"
    "nxt=None if re.search(r'\\d',tr[-1]['agent']) else 'give me a number'\n"
    "print(json.dumps({'next':nxt}))\n"
)
# echoes what arrived on stdin back as the next turn (transcript roundtrip)
_SIM_ECHO_LAST = (
    "import json,sys\n"
    "tr=json.load(sys.stdin)['transcript']\n"
    "if len(tr)>=2: print(json.dumps({'next':None}))\n"
    "else: print(json.dumps({'next':'saw:'+tr[-1]['user']+'/'+tr[-1]['agent']},"
    "ensure_ascii=False))\n"
)
_SIM_EXIT_2 = "import sys\nsys.exit(2)\n"
_SIM_NOT_JSON = "print('not json at all')\n"
_SIM_NO_NEXT_KEY = "print('{}')\n"
_SIM_BAD_NEXT_TYPE = "print('{\"next\": 5}')\n"
_SIM_EXTRA_KEYS = "print('{\"next\": null, \"note\": \"extra is fine\"}')\n"
_SIM_SLEEPER = "import time\ntime.sleep(30)\n"

_ONE_TURN = [{"turn": 0, "user": "hello", "agent": "echo:hello"}]


def _turns(n: int) -> list:
    return [{"turn": i, "user": f"u{i}", "agent": f"a{i}"} for i in range(n)]


# === engine: _make_script_simulator =============================================

class TestScriptSimulatorEngine(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _sim(self, body: str, timeout=None):
        p = self.dir / "sim.py"
        p.write_text(body, encoding="utf-8")
        return _make_script_simulator(p, self.dir, timeout=timeout)

    def test_next_string_and_null_end(self):
        sim = self._sim(_SIM_COUNTING)
        self.assertEqual(sim(_turns(1)), "q1")
        self.assertEqual(sim(_turns(2)), "q2")
        self.assertIsNone(sim(_turns(3)))

    def test_transcript_arrives_on_stdin_utf8(self):
        # the whole transcript-so-far is the stdin payload; Chinese must
        # round-trip on Windows (PYTHONIOENCODING=utf-8, never locale stdio)
        sim = self._sim(_SIM_ECHO_LAST)
        out = sim([{"turn": 0, "user": "你好", "agent": "回答：给个数字"}])
        self.assertEqual(out, "saw:你好/回答：给个数字")

    def test_extra_json_keys_tolerated(self):
        sim = self._sim(_SIM_EXTRA_KEYS)
        self.assertIsNone(sim(_turns(1)))

    def test_nonzero_exit_raises(self):
        sim = self._sim(_SIM_EXIT_2)
        with self.assertRaises(RuntimeError) as cm:
            sim(_turns(1))
        self.assertIn("exited 2", str(cm.exception))

    def test_non_json_stdout_raises(self):
        sim = self._sim(_SIM_NOT_JSON)
        with self.assertRaises(RuntimeError) as cm:
            sim(_turns(1))
        self.assertIn("not JSON", str(cm.exception))

    def test_missing_next_key_raises(self):
        sim = self._sim(_SIM_NO_NEXT_KEY)
        with self.assertRaises(RuntimeError) as cm:
            sim(_turns(1))
        self.assertIn('{"next": str|null}', str(cm.exception))

    def test_non_string_next_raises(self):
        sim = self._sim(_SIM_BAD_NEXT_TYPE)
        with self.assertRaises(RuntimeError) as cm:
            sim(_turns(1))
        self.assertIn("string or null", str(cm.exception))

    def test_timeout_raises_instead_of_hanging(self):
        sim = self._sim(_SIM_SLEEPER, timeout=1.0)
        with self.assertRaises(RuntimeError) as cm:
            sim(_turns(1))
        self.assertIn("timed out after 1s", str(cm.exception))

    def test_ahl_sim_timeout_read_at_build_time(self):
        with _sim_env_patch(AHL_SIM_TIMEOUT="1"):
            sim = self._sim(_SIM_SLEEPER)  # no explicit timeout → env knob
        with self.assertRaises(RuntimeError) as cm:
            sim(_turns(1))
        self.assertIn("timed out after 1s", str(cm.exception))


# === plan wiring: _plan_simulator with type=script ==============================

class TestScriptSimPlan(unittest.TestCase):
    def _spec(self, sim_raw):
        sim = SimulatorSpec(type=sim_raw.get("type"), raw=sim_raw)
        return ExperimentSpec(path=Path("experiment.yaml"), simulator=sim)

    def test_existing_script_plans_multiturn_factory(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "sim.py").write_text(_SIM_COUNTING, encoding="utf-8")
            with _sim_env_patch():
                plan = _plan_simulator(self._spec(
                    {"type": "script", "script": "sim.py", "max_turns": 5}), Path(td))
            self.assertEqual(plan.label, "script")
            self.assertEqual(plan.max_turns, 5)
            self.assertFalse(plan.forced)
            self.assertEqual(plan.error, "")
            fn = plan.factory("case-001")
            self.assertEqual(fn(_turns(1)), "q1")

    def test_undeclared_script_field_plans_error(self):
        with _sim_env_patch():
            plan = _plan_simulator(self._spec({"type": "script"}), Path("."))
        self.assertEqual(plan.label, "script")
        self.assertIn("`script:`", plan.error)


# === review: script file existence (auto → ERROR, copilot → WARN) ===============

class TestScriptSimReview(_ReviewBase):
    _BLOCK = "simulator:\n  type: script\n  script: cases/sim.py\n"

    def test_script_file_missing_error_under_auto(self):
        self.assertIn("simulator_script_ref_missing",
                      self._codes(_experiment_yaml(self._BLOCK), ERROR))

    def test_script_file_missing_warn_under_copilot(self):
        doc = _experiment_yaml(self._BLOCK, run_mode="copilot")
        self.assertIn("simulator_script_ref_missing", self._codes(doc, WARN))
        self.assertNotIn("simulator_script_ref_missing", self._codes(doc, ERROR))

    def test_script_file_present_validates_clean(self):
        self._file("cases/sim.py", _SIM_COUNTING)
        codes = self._codes(_experiment_yaml(self._BLOCK))
        self.assertNotIn("simulator_script_ref_missing", codes)
        self.assertNotIn("simulator_script_missing", codes)


# === Auto Mode dispatch e2e =====================================================

_SCRIPT_SIM_BLOCK = ("simulator:\n  type: script\n  script: cases/sim.py\n"
                     "  max_turns: 6\n")


class TestAutoMultiturnScriptSim(unittest.TestCase):
    def test_script_sim_happy_path(self):
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_SCRIPT_SIM_BLOCK, agent=_ECHO,
                         files={"cases/sim.py": _SIM_COUNTING})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            rec = _traces(exp)[0]
            self.assertEqual(rec["simulator"], "script")
            self.assertNotIn("forced", rec)
            self.assertEqual(rec["turns"], 3)
            self.assertEqual([t["user"] for t in rec["transcript"]],
                             ["hello", "q1", "q2"])
            self.assertEqual(rec["input"], "hello")
            self.assertEqual(rec["response"], "echo:q2")  # final agent reply
            self.assertTrue(rec["ok"])
            raw = (exp / "evidence" / "raw" / "runtime-a" / "case-001.out").read_text(
                encoding="utf-8")
            self.assertEqual(raw, "echo:hello\necho:q1\necho:q2")
            self.assertEqual(_issue_types(exp), [])

    def test_conditional_follow_up_ends_when_satisfied(self):
        # the script type's purpose: follow up only while the answer lacks a
        # digit — _ECHO_STATEFUL replies "r1:hello" (has one) → 1 turn and done
        with _sim_env_patch(), _workspace() as ws:
            exp = _setup(ws, sim_block=_SCRIPT_SIM_BLOCK, agent=_ECHO_STATEFUL,
                         files={"cases/sim.py": _SIM_NEEDS_NUMBER})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            rec = _traces(exp)[0]
            self.assertEqual(rec["turns"], 1)
            self.assertTrue(rec["ok"])

    def test_conditional_follow_up_capped_by_max_turns(self):
        # _ECHO never produces a digit → the simulator would ask forever;
        # max(1, max_turns) caps the loop
        block = ("simulator:\n  type: script\n  script: cases/sim.py\n"
                 "  max_turns: 2\n")
        with _sim_env_patch(), _workspace() as ws:
            exp = _setup(ws, sim_block=block, agent=_ECHO,
                         files={"cases/sim.py": _SIM_NEEDS_NUMBER})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            rec = _traces(exp)[0]
            self.assertEqual(rec["turns"], 2)
            self.assertEqual([t["user"] for t in rec["transcript"]],
                             ["hello", "give me a number"])

    def test_sim_failure_keeps_partial_transcript_and_later_cases_run(self):
        with _workspace() as ws, _sim_env_patch():
            cases = ('{"id":"case-001","input":"hello"}\n'
                     '{"id":"case-002","input":"world"}\n')
            exp = _setup(ws, sim_block=_SCRIPT_SIM_BLOCK, agent=_ECHO, cases=cases,
                         files={"cases/sim.py": _SIM_EXIT_2})
            rc, _, err = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 3)  # error-severity connector_failure → exit 3
            self.assertIn("HLAB_RUNTIME_FAILURE", err)
            recs = _traces(exp)
            self.assertEqual(len(recs), 2)  # the 2nd case still ran
            for rec, opening in zip(recs, ("hello", "world")):
                self.assertIn("exited 2", rec["error"])
                self.assertFalse(rec["ok"])
                # turn 0 was collected before the simulator died → kept (§14.4)
                self.assertEqual(rec["turns"], 1)
                self.assertEqual(rec["transcript"][0]["user"], opening)
                self.assertEqual(rec["simulator"], "script")
            self.assertIn("connector_failure", _issue_types(exp))

    def test_missing_script_file_records_unconfigured_and_skips(self):
        # review already blocks this under auto; if it still reaches dispatch
        # (file deleted after review), the run records simulator_unconfigured
        # and skips — never a fabricated turn, never a single-turn downgrade
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_SCRIPT_SIM_BLOCK, agent=_ECHO)  # no sim.py
            spec = parse_experiment_yaml(exp / "experiment.yaml")
            res = run_auto(exp, spec)
            self.assertIn("simulator_unconfigured",
                          [i["type"] for i in res.issues])
            self.assertEqual(_traces(exp), [])

    def test_ahl_sim_stub_redirects_script_type_to_scripted(self):
        with _workspace() as ws, _sim_env_patch(AHL_SIM_STUB="1"):
            exp = _setup(ws, sim_block=_SCRIPT_SIM_BLOCK, agent=_ECHO,
                         files={"cases/sim.py": _SIM_COUNTING})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            rec = _traces(exp)[0]
            self.assertEqual(rec["simulator"], "scripted")  # redirected
            self.assertIs(rec["forced"], True)

    def test_script_connector_cannot_drive_script_simulator(self):
        # Left-shifted to review (simulator_connector_unsupported ERROR): the
        # script connector spawns one process per case with no turn IPC and
        # cannot keep a multi-turn conversation — this always fails at run time.
        # hlab run blocks at review (exit 1) before any dispatch occurs.
        from agent_harness_lab.experiment_spec import ERROR, validate_spec, parse_experiment_yaml
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_SCRIPT_SIM_BLOCK, connector="script",
                         agent=_SCRIPT_OK, files={"cases/sim.py": _SIM_COUNTING})
            # review emits simulator_connector_unsupported ERROR
            spec = parse_experiment_yaml(exp / "experiment.yaml")
            problems = validate_spec(spec, exp)
            codes = [p.code for p in problems if p.level == ERROR]
            self.assertIn("simulator_connector_unsupported", codes)
            # hlab run is blocked at review stage (exit 1), not runtime failure (exit 3)
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 1)
            self.assertEqual(_traces(exp), [])  # honest failure, no dispatch


if __name__ == "__main__":
    unittest.main()
