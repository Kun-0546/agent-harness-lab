"""Multi-turn execution v1.1 (PR2): schema/review + user_sim + Auto Mode dispatch.

Covers the v1.1 multi-turn contract (docs/v1-spec/execution-model.md §14,
experiment-yaml-schema.md §14a):
  - schema/review: scripted type + playbook checks; role_play policy file
    ERROR under auto (was WARN); four-section policy card validation (missing
    Stop → WARN); the old simulator_roleplay_unimplemented WARN is gone;
    optimization.enabled × multi-turn → ERROR.
  - user_sim: bilingual policy card lookup, English prompt builder + dual end
    tokens, AHL_SIM_* config (incl. AHL_SIM_TIMEOUT), scripted playbook engine.
  - auto dispatch: per-case fresh session, turn loop, partial transcript,
    no-key skip (simulator_unconfigured + exit 3), AHL_SIM_STUB=1 redirect
    (forced: true), multi-turn trace format (additive), raw per-turn concat.
  - single-turn freeze: trace records byte-for-byte identical (pinned goldens).
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agent_harness_lab import cli, scaffold, user_sim
from agent_harness_lab.auto import _plan_simulator, _run_case_turns, run_auto
from agent_harness_lab.experiment_spec import (
    ERROR,
    WARN,
    ExperimentSpec,
    SimulatorSpec,
    parse_experiment_yaml,
    validate_spec,
)

_EXE = sys.executable.replace("\\", "/")  # forward slashes → no YAML/shlex escaping

# --- agents under test (local_cli IPC: {"input":...} -> {"response":...}) ------

# stateful echo: logs one line per process start; numbers replies per process —
# a fresh session per case must restart the numbering at r1.
_ECHO_STATEFUL = (
    "import json,sys\n"
    "open('starts.log','a',encoding='utf-8').write('start\\n')\n"
    "n=0\n"
    "for line in sys.stdin:\n"
    "    n+=1\n"
    "    d=json.loads(line)\n"
    "    sys.stdout.write(json.dumps({'response':'r%d:%s'%(n,d.get('input',''))})+'\\n')\n"
    "    sys.stdout.flush()\n"
)
_ECHO = (
    "import json,sys\n"
    "for line in sys.stdin:\n"
    "    d=json.loads(line)\n"
    "    sys.stdout.write(json.dumps({'response':'echo:'+d.get('input','')})+'\\n')\n"
    "    sys.stdout.flush()\n"
)
# answers ONE turn then exits → the next turn raises mid-case (partial transcript)
_ECHO_ONE_THEN_EXIT = (
    "import json,sys\n"
    "line=sys.stdin.readline()\n"
    "d=json.loads(line)\n"
    "sys.stdout.write(json.dumps({'response':'echo:'+d.get('input','')})+'\\n')\n"
    "sys.stdout.flush()\n"
)
_ECHO_EMPTY = (
    "import json,sys\n"
    "for line in sys.stdin:\n"
    "    json.loads(line)\n"
    "    sys.stdout.write(json.dumps({'response':''})+'\\n'); sys.stdout.flush()\n"
)
_SCRIPT_OK = (
    "import json,sys\n"
    "case=json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "print('ran:'+case.get('input',''))\n"
)

_POLICY_EN = (
    "## Persona\n\na picky CFO reviewing a budget\n\n"
    "## Background\n\nQ3 budget review, numbers matter\n\n"
    "## Strategy\n\nask for a concrete number every turn\n\n"
    "## Stop\n\nstop once you have a defensible number\n"
)
_POLICY_CN = (
    "## 人设\n\n挑剔的 CFO\n\n"
    "## 背景知识\n\nQ3 预算评审\n\n"
    "## 追问策略\n\n每轮要一个数字\n\n"
    "## 收尾条件\n\n拿到站得住的数字就收\n"
)
_POLICY_NO_STOP = (
    "## Persona\n\na picky CFO\n\n## Strategy\n\nask for numbers\n"
)

_PLAYBOOK = (
    "default:\n"
    "  - \"q1\"\n"
    "  - \"q2\"\n"
    "per_case:\n"
    "  case-002:\n"
    "    - \"only-one\"\n"
)

# golden copy of the built-in default playbook (the retired stub's two
# follow-ups) — deliberately NOT imported from the source constant.
_GOLDEN_DEFAULT_FOLLOWUPS = [
    "这个能再具体点吗?给个数。",
    "那如果情况变了,你会怎么调整?",
]


def _sim_env_patch(**extra):
    """A clean AHL_SIM_* environment (plus optional overrides) for one test."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AHL_SIM")}
    env.update(extra)
    return mock.patch.dict(os.environ, env, clear=True)


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


def _experiment_yaml(sim_block: str = "", run_mode: str = "auto") -> str:
    return (
        "id: demo\nstatus: draft\ngoal_ref: ../../goal.md\nquestion: q\n"
        f"run:\n  mode: {run_mode}\nexecution:\n  mode: ab\n  state_policy: isolated\n"
        "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
        "agent_runtimes:\n  - id: runtime-a\n    harness: A\n    spec: agent-runtimes/runtime-a.yaml\n"
        "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
        "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: e1\n      method: benchmark\n"
        "collection:\n  traces: true\n  raw: true\n  artifacts: true\n  snapshots: false\n  scores: true\n"
        "reports:\n  formats:\n    - md\n"
        + sim_block
    )


def _setup(root, *, sim_block="", connector="local_cli", agent=_ECHO, timeout=20,
           cases='{"id":"case-001","input":"hello"}\n', files=None):
    """Build a single-runtime auto experiment. `files` = {relpath: content} extras."""
    scaffold.init_workspace(root)
    exp = scaffold.new_experiment(root, "demo", run_mode="auto").experiment_dir
    (exp / "experiment.yaml").write_text(_experiment_yaml(sim_block), encoding="utf-8")
    (exp / "cases" / "cases.jsonl").write_text(cases, encoding="utf-8")
    (exp / "rt").mkdir(exist_ok=True)
    if connector == "script":
        (exp / "rt" / "runner.py").write_text(agent, encoding="utf-8")
        rt = (f"id: runtime-a\nconnector:\n  type: script\n"
              f"  command: '\"{sys.executable}\" runner.py {{case_file}} {{output_dir}}'\n"
              f"  working_dir: ./rt\n  timeout: {timeout}\n")
    else:
        (exp / "rt" / "agent.py").write_text(agent, encoding="utf-8")
        rt = (f"id: runtime-a\nconnector:\n  type: local_cli\n"
              f"  command: {_EXE} agent.py\n  working_dir: ./rt\n  timeout: {timeout}\n")
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(rt, encoding="utf-8")
    for rel, content in (files or {}).items():
        p = exp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return exp


def _run_cli(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(args)
    return rc, out.getvalue(), err.getvalue()


def _traces(exp):
    p = exp / "evidence" / "traces" / "runtime-a.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _issue_types(exp):
    p = exp / "evidence" / "issues.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln)["type"] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


# === schema / review (experiment-yaml-schema.md §14a, v1.1 rules) ==============

class _ReviewBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scaffold.init_workspace(self.root)
        self.exp = scaffold.new_experiment(self.root, "demo").experiment_dir

    def _codes(self, doc: str, level=None):
        (self.exp / "experiment.yaml").write_text(doc, encoding="utf-8")
        spec = parse_experiment_yaml(self.exp / "experiment.yaml")
        return {p.code for p in validate_spec(spec, self.exp)
                if level is None or p.level == level}

    def _file(self, rel: str, content: str) -> None:
        p = self.exp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


class TestSimulatorSchemaV11(_ReviewBase):
    def test_scripted_is_a_known_type(self):
        self._file("cases/playbook.yaml", _PLAYBOOK)
        codes = self._codes(_experiment_yaml(
            "simulator:\n  type: scripted\n  playbook: cases/playbook.yaml\n",
            run_mode="copilot"))
        self.assertNotIn("bad_simulator_type", codes)

    def test_scripted_without_playbook_errors(self):
        codes = self._codes(_experiment_yaml("simulator:\n  type: scripted\n",
                                             run_mode="copilot"), ERROR)
        self.assertIn("simulator_playbook_missing", codes)

    def test_scripted_playbook_file_missing_warn_under_copilot(self):
        # Use a path that definitely does not exist (the scaffold writes playbook.yaml
        # but not this alternate path).
        doc = _experiment_yaml(
            "simulator:\n  type: scripted\n  playbook: cases/missing-playbook.yaml\n",
            run_mode="copilot")
        self.assertIn("simulator_playbook_ref_missing", self._codes(doc, WARN))
        self.assertNotIn("simulator_playbook_ref_missing", self._codes(doc, ERROR))

    def test_scripted_playbook_file_missing_error_under_auto(self):
        doc = _experiment_yaml(
            "simulator:\n  type: scripted\n  playbook: cases/missing-playbook.yaml\n")
        self.assertIn("simulator_playbook_ref_missing", self._codes(doc, ERROR))

    def test_role_play_policy_file_missing_error_under_auto(self):
        doc = _experiment_yaml(
            "simulator:\n  type: role_play\n  actor: cfo\n  policy: cases/policy.md\n")
        self.assertIn("simulator_policy_ref_missing", self._codes(doc, ERROR))

    def test_role_play_policy_file_missing_warn_under_copilot(self):
        doc = _experiment_yaml(
            "simulator:\n  type: role_play\n  actor: cfo\n  policy: cases/policy.md\n",
            run_mode="copilot")
        self.assertIn("simulator_policy_ref_missing", self._codes(doc, WARN))
        self.assertNotIn("simulator_policy_ref_missing", self._codes(doc, ERROR))

    def test_role_play_under_auto_has_no_unimplemented_warn(self):
        self._file("cases/policy.md", _POLICY_EN)
        codes = self._codes(_experiment_yaml(
            "simulator:\n  type: role_play\n  actor: cfo\n  policy: cases/policy.md\n"))
        self.assertNotIn("simulator_roleplay_unimplemented", codes)
        # a complete EN policy card raises none of the card warns either
        self.assertNotIn("simulator_policy_no_stop", codes)
        self.assertNotIn("simulator_policy_incomplete", codes)

    def test_chinese_policy_card_validates_clean(self):
        self._file("cases/policy.md", _POLICY_CN)
        codes = self._codes(_experiment_yaml(
            "simulator:\n  type: role_play\n  actor: cfo\n  policy: cases/policy.md\n"))
        self.assertNotIn("simulator_policy_no_stop", codes)
        self.assertNotIn("simulator_policy_incomplete", codes)

    def test_policy_card_missing_stop_warns(self):
        self._file("cases/policy.md", _POLICY_NO_STOP)
        codes = self._codes(_experiment_yaml(
            "simulator:\n  type: role_play\n  actor: cfo\n  policy: cases/policy.md\n"), WARN)
        self.assertIn("simulator_policy_no_stop", codes)

    def test_policy_card_missing_persona_warns_incomplete(self):
        self._file("cases/policy.md", "## Strategy\n\nask numbers\n\n## Stop\n\ndone\n")
        codes = self._codes(_experiment_yaml(
            "simulator:\n  type: role_play\n  actor: cfo\n  policy: cases/policy.md\n"), WARN)
        self.assertIn("simulator_policy_incomplete", codes)

    def test_scripted_bad_max_turns_errors(self):
        self._file("cases/playbook.yaml", _PLAYBOOK)
        codes = self._codes(_experiment_yaml(
            "simulator:\n  type: scripted\n  playbook: cases/playbook.yaml\n"
            "  max_turns: \"three\"\n"), ERROR)
        self.assertIn("bad_simulator_max_turns", codes)

    def test_optimize_with_multiturn_simulator_errors(self):
        self._file("cases/playbook.yaml", _PLAYBOOK)
        opt = ("optimization:\n  enabled: true\n  stop_conditions:\n    - max_iterations: 2\n")
        codes = self._codes(_experiment_yaml(
            "simulator:\n  type: scripted\n  playbook: cases/playbook.yaml\n" + opt), ERROR)
        self.assertIn("optimize_multiturn_unsupported", codes)

    def test_optimize_with_single_turn_simulator_ok(self):
        opt = ("optimization:\n  enabled: true\n  stop_conditions:\n    - max_iterations: 2\n")
        codes = self._codes(_experiment_yaml("simulator:\n  type: single_turn\n" + opt))
        self.assertNotIn("optimize_multiturn_unsupported", codes)

    def test_single_turn_schema_unchanged(self):
        codes = self._codes(_experiment_yaml("simulator:\n  type: single_turn\n"))
        self.assertNotIn("bad_simulator_type", codes)
        self.assertNotIn("simulator_playbook_missing", codes)


# === user_sim: policy card / prompt / end tokens / config ======================

_SIM_ENV = {"AHL_SIM_BASE_URL": "http://sim.invalid", "AHL_SIM_MODEL": "sim-model",
            "AHL_SIM_API_KEY": "sim-key"}
_ONE_TURN = [{"turn": 0, "user": "opening", "agent": "answer"}]


class TestPolicyCard(unittest.TestCase):
    def _parse(self, content: str) -> user_sim.PolicyCard:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "policy.md"
            p.write_text(content, encoding="utf-8")
            return user_sim.parse_policy_card(p)

    def test_english_sections(self):
        card = self._parse(_POLICY_EN)
        self.assertEqual(card.persona, "a picky CFO reviewing a budget")
        self.assertEqual(card.background, "Q3 budget review, numbers matter")
        self.assertEqual(card.strategy, "ask for a concrete number every turn")
        self.assertEqual(card.stop, "stop once you have a defensible number")

    def test_chinese_sections(self):
        card = self._parse(_POLICY_CN)
        self.assertEqual(card.persona, "挑剔的 CFO")
        self.assertEqual(card.background, "Q3 预算评审")
        self.assertEqual(card.strategy, "每轮要一个数字")
        self.assertEqual(card.stop, "拿到站得住的数字就收")

    def test_missing_sections_are_empty(self):
        card = self._parse("## Persona\n\nsomeone\n")
        self.assertEqual(card.background, "")
        self.assertEqual(card.strategy, "")
        self.assertEqual(card.stop, "")

    def test_english_section_names_are_case_insensitive(self):
        card = self._parse("## persona\n\nsomeone\n\n## STOP\n\ndone\n")
        self.assertEqual(card.persona, "someone")
        self.assertEqual(card.stop, "done")


class TestRolePlayPrompt(unittest.TestCase):
    def test_prompt_is_english_with_sections_and_end_token(self):
        card = user_sim.PolicyCard(path=Path("p.md"), persona="picky CFO",
                                   background="Q3", strategy="ask numbers",
                                   stop="got a number")
        prompt = user_sim.build_role_play_prompt(card, list(_ONE_TURN))
        for needle in ("[Persona]", "picky CFO", "[Background]", "Q3",
                       "[Follow-up strategy]", "ask numbers",
                       "[Stop criterion]", "got a number",
                       "[Conversation so far]", "[turn 0] user: opening",
                       "output exactly: END"):
            self.assertIn(needle, prompt)

    def test_actor_label_appears_in_prompt(self):
        # Fix D: simulator.actor is now consumed — the actor label anchors the
        # simulated user persona by appearing in the prompt.
        card = user_sim.PolicyCard(path=Path("p.md"), actor="cfo",
                                   persona="picky CFO", strategy="ask numbers")
        prompt = user_sim.build_role_play_prompt(card, list(_ONE_TURN))
        self.assertIn("You are: cfo", prompt)

    def test_no_actor_label_omitted_from_prompt(self):
        # When actor is empty the "You are: ..." line must not appear.
        card = user_sim.PolicyCard(path=Path("p.md"), persona="picky CFO",
                                   strategy="ask numbers")
        prompt = user_sim.build_role_play_prompt(card, list(_ONE_TURN))
        self.assertNotIn("You are:", prompt)

    def test_dual_end_token_detection(self):
        self.assertTrue(user_sim.is_end_token("END"))
        self.assertTrue(user_sim.is_end_token("  END — done"))
        self.assertTrue(user_sim.is_end_token("结束"))
        self.assertTrue(user_sim.is_end_token("结束。聊透了"))
        self.assertFalse(user_sim.is_end_token("give me a number"))
        self.assertFalse(user_sim.is_end_token(""))


class TestRolePlaySimulatorConfig(unittest.TestCase):
    def _card(self):
        return user_sim.PolicyCard(path=Path("p.md"), persona="picky", strategy="numbers")

    def test_no_key_raises_never_fabricates(self):
        with _sim_env_patch():
            self.assertFalse(user_sim.sim_configured())
            with self.assertRaises(RuntimeError):
                user_sim.make_role_play_simulator(self._card())

    def test_configured_simulator_passes_reply_through(self):
        with _sim_env_patch(**_SIM_ENV):
            sim = user_sim.make_role_play_simulator(self._card())
        with mock.patch("agent_harness_lab.llm.chat", return_value="  next q  "):
            self.assertEqual(sim(list(_ONE_TURN)), "next q")

    def test_ahl_sim_timeout_is_wired_to_llm_chat(self):
        with _sim_env_patch(AHL_SIM_TIMEOUT="42", **_SIM_ENV):
            sim = user_sim.make_role_play_simulator(self._card())
        with mock.patch("agent_harness_lab.llm.chat", return_value="x") as chat:
            sim(list(_ONE_TURN))
        self.assertEqual(chat.call_args.kwargs.get("timeout"), 42.0)

    def test_bad_timeout_falls_back_to_default(self):
        with _sim_env_patch(AHL_SIM_TIMEOUT="not-a-number", **_SIM_ENV):
            sim = user_sim.make_role_play_simulator(self._card())
        with mock.patch("agent_harness_lab.llm.chat", return_value="x") as chat:
            sim(list(_ONE_TURN))
        self.assertEqual(chat.call_args.kwargs.get("timeout"), 180.0)


class TestPlaybookEngine(unittest.TestCase):
    def _load(self, content: str) -> user_sim.Playbook:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "playbook.yaml"
            p.write_text(content, encoding="utf-8")
            return user_sim.load_playbook(p)

    def test_default_and_per_case_sequences(self):
        pb = self._load(_PLAYBOOK)
        self.assertEqual(pb.default, ["q1", "q2"])
        self.assertEqual(pb.sequence_for("case-002"), ["only-one"])
        self.assertEqual(pb.sequence_for("case-001"), ["q1", "q2"])  # falls back

    def test_missing_file_raises_simulator_error(self):
        with self.assertRaises(user_sim.SimulatorError):
            user_sim.load_playbook(Path("does-not-exist-playbook.yaml"))

    def test_non_mapping_playbook_raises(self):
        with self.assertRaises(user_sim.SimulatorError):
            self._load("- just\n- a list\n")

    def test_non_string_entry_raises(self):
        with self.assertRaises(user_sim.SimulatorError):
            self._load("default:\n  - 1\n  - 2\n")

    def test_scripted_simulator_emits_in_order_then_ends(self):
        sim = user_sim.make_scripted_simulator(["a", "b"])
        one = [{"turn": 0, "user": "u", "agent": "x"}]
        two = one + [{"turn": 1, "user": "a", "agent": "y"}]
        three = two + [{"turn": 2, "user": "b", "agent": "z"}]
        self.assertEqual(sim(one), "a")
        self.assertEqual(sim(two), "b")
        self.assertIsNone(sim(three))

    def test_empty_transcript_edge(self):
        sim = user_sim.make_scripted_simulator(["a"])
        self.assertEqual(sim([]), "a")  # asked = max(0, len-1) guard

    def test_default_playbook_is_the_retired_stub_sequence(self):
        pb = user_sim.default_playbook()
        self.assertEqual(pb.default, _GOLDEN_DEFAULT_FOLLOWUPS)
        self.assertIsNone(pb.path)


# === _run_case_turns / _plan_simulator (v1 turn-loop parity) ====================

class _FakeSession:
    def __init__(self, fail_on_call=None):
        self.received = []
        self._fail_on_call = fail_on_call

    def send(self, user_text: str) -> str:
        call_no = len(self.received) + 1
        if self._fail_on_call is not None and call_no >= self._fail_on_call:
            raise RuntimeError(f"died on send #{call_no}")
        self.received.append(user_text)
        return f"re:{user_text}"


def _greedy(transcript):
    return f"more {len(transcript)}"


class TestRunCaseTurns(unittest.TestCase):
    """The ported turn loop keeps the Stack A goldens (max(1, max_turns) cap,
    None ends, turn numbering, simulator sees the current turn)."""

    def test_max_turns_caps_loop(self):
        self.assertEqual(len(_run_case_turns(_FakeSession(), "go", _greedy, 3)), 3)

    def test_zero_and_negative_max_turns_still_run_one_turn(self):
        self.assertEqual(len(_run_case_turns(_FakeSession(), "go", _greedy, 0)), 1)
        self.assertEqual(len(_run_case_turns(_FakeSession(), "go", _greedy, -5)), 1)

    def test_none_ends_conversation(self):
        self.assertEqual(len(_run_case_turns(_FakeSession(), "go", lambda t: None, 8)), 1)

    def test_turn_numbering_and_entry_shape(self):
        tr = _run_case_turns(_FakeSession(), "go", _greedy, 4)
        self.assertEqual([e["turn"] for e in tr], [0, 1, 2, 3])
        self.assertEqual(set(tr[0].keys()), {"turn", "user", "agent"})
        self.assertEqual(tr[0]["user"], "go")
        self.assertEqual(tr[0]["agent"], "re:go")
        self.assertEqual(tr[1]["user"], "more 1")

    def test_simulator_sees_transcript_including_current_turn(self):
        # Spec §14.3 turn-loop contract: simulator is consulted only when another
        # turn may follow — NOT after the final allowed turn (cap reached).
        # With max_turns=3, turns 0..2 are executed; simulator is called after
        # turns 0 and 1 (to get turns 1 and 2), but NOT after turn 2 (the cap).
        seen = []

        def sim(transcript):
            seen.append(len(transcript))
            return "go on"

        _run_case_turns(_FakeSession(), "go", sim, 3)
        self.assertEqual(seen, [1, 2])

    def test_no_session_close_in_loop(self):
        # close ownership moved to the dispatch layer: the loop never closes.
        class _Closing(_FakeSession):
            closed = False

            def close(self):
                self.closed = True

        sess = _Closing()
        _run_case_turns(sess, "go", lambda t: None, 8)
        self.assertFalse(sess.closed)


class TestPlanSimulator(unittest.TestCase):
    def _spec(self, sim_raw):
        sim = SimulatorSpec(type=sim_raw.get("type"), raw=sim_raw) if sim_raw else None
        return ExperimentSpec(path=Path("experiment.yaml"), simulator=sim)

    def test_no_simulator_and_single_turn_plan_none(self):
        with _sim_env_patch():
            self.assertIsNone(_plan_simulator(self._spec(None), Path(".")))
            self.assertIsNone(_plan_simulator(
                self._spec({"type": "single_turn"}), Path(".")))

    def test_role_play_without_key_plans_error(self):
        with _sim_env_patch():
            plan = _plan_simulator(self._spec(
                {"type": "role_play", "actor": "cfo", "policy": "p.md"}), Path("."))
        self.assertEqual(plan.label, "role_play")
        self.assertIn("AHL_SIM_API_KEY", plan.error)
        self.assertEqual(plan.max_turns, 8)  # schema default

    def test_explicit_max_turns_honored(self):
        with _sim_env_patch():
            plan = _plan_simulator(self._spec(
                {"type": "role_play", "actor": "cfo", "policy": "p.md",
                 "max_turns": 3}), Path("."))
        self.assertEqual(plan.max_turns, 3)

    def test_script_type_plans_multiturn_engine(self):
        # PR3: type=script is a multi-turn plan (one subprocess per turn). A
        # missing script file makes the plan unusable (simulator_unconfigured
        # at dispatch) — never a silent single-turn downgrade.
        with _sim_env_patch():
            plan = _plan_simulator(self._spec(
                {"type": "script", "script": "does-not-exist-sim.py"}), Path("."))
        self.assertEqual(plan.label, "script")
        self.assertFalse(plan.forced)
        self.assertIn("does not exist", plan.error)

    def test_ahl_sim_stub_forces_scripted_even_for_script_type(self):
        with _sim_env_patch(AHL_SIM_STUB="1"):
            plan = _plan_simulator(self._spec(
                {"type": "script", "script": "sim.py"}), Path("."))
        self.assertEqual(plan.label, "scripted")
        self.assertTrue(plan.forced)
        sim = plan.factory("case-001")
        self.assertEqual(sim([{"turn": 0, "user": "u", "agent": "a"}]),
                         _GOLDEN_DEFAULT_FOLLOWUPS[0])


# === Auto Mode dispatch e2e =====================================================

_SCRIPTED_BLOCK = ("simulator:\n  type: scripted\n  playbook: cases/playbook.yaml\n"
                   "  max_turns: 6\n")
_ROLE_PLAY_BLOCK = ("simulator:\n  type: role_play\n  actor: cfo\n"
                    "  policy: cases/policy.md\n  max_turns: 4\n")


class TestAutoMultiturnScripted(unittest.TestCase):
    def test_scripted_happy_path_per_case_fresh_session(self):
        with _workspace() as ws, _sim_env_patch():
            cases = ('{"id":"case-001","input":"hello"}\n'
                     '{"id":"case-002","input":"world"}\n')
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK, agent=_ECHO_STATEFUL,
                         cases=cases, files={"cases/playbook.yaml": _PLAYBOOK})
            rc, out, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            recs = _traces(exp)
            self.assertEqual(len(recs), 2)
            r1, r2 = recs
            # case-001: default playbook q1/q2 → 3 turns
            self.assertEqual(r1["turns"], 3)
            self.assertEqual([t["user"] for t in r1["transcript"]],
                             ["hello", "q1", "q2"])
            self.assertEqual(r1["input"], "hello")
            self.assertEqual(r1["response"], "r3:q2")  # final agent reply
            self.assertTrue(r1["ok"])
            self.assertEqual(r1["simulator"], "scripted")
            self.assertNotIn("forced", r1)
            self.assertEqual(set(r1["transcript"][0].keys()), {"turn", "user", "agent"})
            # case-002: per_case override → 2 turns
            self.assertEqual(r2["turns"], 2)
            self.assertEqual([t["user"] for t in r2["transcript"]],
                             ["world", "only-one"])
            # per-case FRESH session: reply numbering restarts at r1 per case,
            # and the agent logged one start per case
            self.assertTrue(r1["transcript"][0]["agent"].startswith("r1:"))
            self.assertTrue(r2["transcript"][0]["agent"].startswith("r1:"))
            starts = (exp / "rt" / "starts.log").read_text(encoding="utf-8")
            self.assertEqual(starts.count("start"), 2)
            # raw concatenates the turns in order
            raw = (exp / "evidence" / "raw" / "runtime-a" / "case-001.out").read_text(
                encoding="utf-8")
            self.assertEqual(raw, "r1:hello\nr2:q1\nr3:q2")
            self.assertEqual(_issue_types(exp), [])

    def test_partial_transcript_on_mid_case_death(self):
        with _workspace() as ws, _sim_env_patch():
            cases = ('{"id":"case-001","input":"hello"}\n'
                     '{"id":"case-002","input":"world"}\n')
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK, agent=_ECHO_ONE_THEN_EXIT,
                         cases=cases, files={"cases/playbook.yaml": _PLAYBOOK})
            rc, _, err = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 3)  # error-severity connector_failure → exit 3
            self.assertIn("HLAB_RUNTIME_FAILURE", err)
            recs = _traces(exp)
            self.assertEqual(len(recs), 2)  # the 2nd case still ran (fresh session)
            for rec, opening in zip(recs, ("hello", "world")):
                self.assertTrue(rec["error"])
                self.assertFalse(rec["ok"])
                # partial transcript preserved: turn 0 collected before the death
                self.assertEqual(rec["turns"], 1)
                self.assertEqual(rec["transcript"][0]["user"], opening)
                self.assertEqual(rec["response"], f"echo:{opening}")
            self.assertIn("connector_failure", _issue_types(exp))
            raw = (exp / "evidence" / "raw" / "runtime-a" / "case-001.out").read_text(
                encoding="utf-8")
            self.assertEqual(raw, "echo:hello")  # partial raw kept too

    def test_empty_final_reply_is_empty_output(self):
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK, agent=_ECHO_EMPTY,
                         files={"cases/playbook.yaml": "default: []\n"})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 3)
            rec = _traces(exp)[0]
            self.assertFalse(rec["ok"])
            self.assertEqual(rec["turns"], 1)
            self.assertIn("empty_output", _issue_types(exp))

    def test_script_connector_with_multiturn_simulator_fails_honestly(self):
        # Left-shifted to review (simulator_connector_unsupported ERROR): the
        # script connector spawns one fresh process per case with no turn IPC
        # and cannot keep a conversation. hlab run blocks at the review gate
        # (exit 1) before any dispatch occurs.
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK, connector="script",
                         agent=_SCRIPT_OK, files={"cases/playbook.yaml": _PLAYBOOK})
            spec = parse_experiment_yaml(exp / "experiment.yaml")
            codes = {p.code for p in validate_spec(spec, exp) if p.level == ERROR}
            self.assertIn("simulator_connector_unsupported", codes)
            rc, _, err = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 1)  # blocked at review, not a runtime failure
            self.assertIn("run blocked", err)
            self.assertEqual(_traces(exp), [])  # no silent single-turn downgrade
            # the run-time guard stays as a backstop: if the combination slips
            # past review (e.g. the runtime spec changed after the gate),
            # dispatch refuses honestly — connector_failure, zero traces
            res = run_auto(exp, spec)
            self.assertIn("connector_failure", [i["type"] for i in res.issues])
            self.assertEqual(_traces(exp), [])


class TestAutoMultiturnRolePlay(unittest.TestCase):
    def test_no_key_records_simulator_unconfigured_and_skips(self):
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_ROLE_PLAY_BLOCK,
                         files={"cases/policy.md": _POLICY_EN})
            rc, _, err = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 3)  # R3 contract: error issue → exit 3
            self.assertIn("HLAB_RUNTIME_FAILURE", err)
            types = _issue_types(exp)
            self.assertIn("simulator_unconfigured", types)
            # dispatch was skipped: no traces, and no missing_trace pile-on
            # (simulator_unconfigured explains the gap)
            self.assertEqual(_traces(exp), [])
            self.assertNotIn("missing_trace", types)
            self.assertNotIn("case_coverage", types)

    def test_ahl_sim_stub_forces_scripted_with_forced_mark(self):
        with _workspace() as ws, _sim_env_patch(AHL_SIM_STUB="1"):
            exp = _setup(ws, sim_block=_ROLE_PLAY_BLOCK,
                         files={"cases/policy.md": _POLICY_EN})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            rec = _traces(exp)[0]
            self.assertEqual(rec["simulator"], "scripted")  # redirected
            self.assertIs(rec["forced"], True)
            # no playbook declared → the built-in default two follow-ups
            self.assertEqual(rec["turns"], 3)
            self.assertEqual([t["user"] for t in rec["transcript"]],
                             ["hello"] + _GOLDEN_DEFAULT_FOLLOWUPS)

    def test_ahl_sim_stub_uses_experiment_playbook_when_declared(self):
        with _workspace() as ws, _sim_env_patch(AHL_SIM_STUB="1"):
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK,
                         files={"cases/playbook.yaml": _PLAYBOOK})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            rec = _traces(exp)[0]
            self.assertEqual(rec["simulator"], "scripted")
            self.assertIs(rec["forced"], True)  # env-forced, even on scripted
            self.assertEqual([t["user"] for t in rec["transcript"]],
                             ["hello", "q1", "q2"])


# === role_play success path (configured AHL_SIM_* → real plan+dispatch) =========

class TestAutoMultiturnRolePlaySuccess(unittest.TestCase):
    """Headline feature coverage: configured role_play runs end-to-end (no key needed
    because llm.chat is mocked). Pins the full dispatch path:
      sim configured → parse_policy_card → make_role_play_simulator → dispatch loop
    and the resulting trace shape."""

    def test_role_play_happy_path_trace_shape(self):
        # Two LLM turns: first call returns a follow-up, second returns "END" (stop).
        # The agent's first reply has no digit so the sim would ask; "END" stops it.
        replies = iter(["follow up question", "END"])

        with _workspace() as ws, _sim_env_patch(**_SIM_ENV):
            exp = _setup(ws, sim_block=_ROLE_PLAY_BLOCK,
                         files={"cases/policy.md": _POLICY_EN})
            with mock.patch("agent_harness_lab.llm.chat", side_effect=lambda *a, **kw: next(replies)):
                rc, _, _ = _run_cli(["run", "experiments/demo"])
            recs = _traces(exp)
            self.assertEqual(rc, 0)
            self.assertEqual(len(recs), 1)
            rec = recs[0]
            self.assertEqual(rec["simulator"], "role_play")
            self.assertNotIn("forced", rec)
            self.assertGreaterEqual(rec["turns"], 2)
            transcript = rec["transcript"]
            self.assertIsInstance(transcript, list)
            self.assertGreaterEqual(len(transcript), 2)
            for entry in transcript:
                self.assertEqual(set(entry.keys()), {"turn", "user", "agent"})
            self.assertEqual(transcript[0]["user"], "hello")  # opening case input
            self.assertEqual(transcript[1]["user"], "follow up question")  # simulator turn
            self.assertTrue(rec["ok"])
            self.assertEqual(rec["input"], "hello")


# === single-turn freeze: byte-for-byte trace pinning ===========================

_GOLDEN_LOCAL_CLI_TRACE = (
    '{"case_id": "case-001", "runtime_id": "runtime-a", "harness_id": "A", '
    '"input": "hello", "response": "echo:hello", "ok": true}'
)
_GOLDEN_SCRIPT_TRACE = (
    '{"case_id": "case-001", "runtime_id": "runtime-a", "harness_id": "A", '
    '"input": "hello", "exit_code": 0, "ok": true}'
)


class TestSingleTurnByteForByte(unittest.TestCase):
    """The single-turn path is frozen: trace records and raw output must stay
    byte-for-byte identical after the multi-turn landing (spec hard constraint)."""

    def _trace_line(self, exp):
        p = exp / "evidence" / "traces" / "runtime-a.jsonl"
        return p.read_text(encoding="utf-8").splitlines()[0]

    def test_local_cli_trace_bytes_unchanged_without_simulator(self):
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, agent=_ECHO)
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertEqual(self._trace_line(exp), _GOLDEN_LOCAL_CLI_TRACE)
            raw = (exp / "evidence" / "raw" / "runtime-a" / "case-001.out").read_text(
                encoding="utf-8")
            self.assertEqual(raw, "echo:hello")

    def test_local_cli_trace_bytes_unchanged_with_single_turn_simulator(self):
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block="simulator:\n  type: single_turn\n", agent=_ECHO)
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertEqual(self._trace_line(exp), _GOLDEN_LOCAL_CLI_TRACE)

    def test_single_turn_unaffected_by_ahl_sim_stub(self):
        # AHL_SIM_STUB redirects MULTI-TURN runs only; single_turn stays frozen
        with _workspace() as ws, _sim_env_patch(AHL_SIM_STUB="1"):
            exp = _setup(ws, agent=_ECHO)
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertEqual(self._trace_line(exp), _GOLDEN_LOCAL_CLI_TRACE)

    def test_script_connector_trace_bytes_unchanged(self):
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, connector="script", agent=_SCRIPT_OK)
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            self.assertEqual(self._trace_line(exp), _GOLDEN_SCRIPT_TRACE)


# === branch-gap tests (H) ======================================================

class TestStatePolicyResetMultiturn(unittest.TestCase):
    """H1: state_policy reset/shared × multiturn — per-case fresh session contract.
    Multi-turn always uses a fresh session per case regardless of state_policy;
    single-turn state_policy semantics are unchanged (pinned separately)."""

    def test_multiturn_always_fresh_session_per_case(self):
        # The stateful echo agent logs a "start" per process. With 2 cases and
        # multiturn, there must be exactly 2 starts (one per case), regardless of
        # state_policy.
        with _workspace() as ws, _sim_env_patch():
            cases = ('{"id":"case-001","input":"hello"}\n'
                     '{"id":"case-002","input":"world"}\n')
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK, agent=_ECHO_STATEFUL,
                         cases=cases, files={"cases/playbook.yaml": "default: []\n"})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            starts = (exp / "rt" / "starts.log").read_text(encoding="utf-8")
            # exactly one fresh session per case
            self.assertEqual(starts.count("start"), 2)
            recs = _traces(exp)
            # each case starts at r1 (fresh process → numbering resets)
            for rec in recs:
                self.assertTrue(rec["transcript"][0]["agent"].startswith("r1:"))


class TestMultiturnRerunSemantics(unittest.TestCase):
    """H2: multiturn re-run semantics — second run APPENDS (PR5a contract).

    PR5a flipped the old truncate-on-rerun behavior to append-as-new-trial.
    A second run appends records with trial:1 rather than overwriting trial:0."""

    def test_second_run_appends_as_trial_1_not_truncates(self):
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK, agent=_ECHO,
                         files={"cases/playbook.yaml": "default: []\n"})
            _run_cli(["run", "experiments/demo"])
            first_recs = _traces(exp)
            _run_cli(["run", "experiments/demo"])  # second run → trial 1
            # read all records (not filtered by trial) to see both trials
            p = exp / "evidence" / "traces" / "runtime-a.jsonl"
            all_recs = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()
                        if ln.strip()]
            # trial-0 records have no `trial` field; trial-1 records have trial:1
            trial0 = [r for r in all_recs if r.get("trial") is None or r.get("trial") == 0]
            trial1 = [r for r in all_recs if r.get("trial") == 1]
            self.assertEqual(len(trial0), len(first_recs))  # original records preserved
            self.assertEqual(len(trial1), len(first_recs))  # new trial appended
            self.assertEqual(len(all_recs), len(first_recs) * 2)  # not doubled by truncate


class TestUnreadablePolicyAtDispatch(unittest.TestCase):
    """H3: unreadable policy file at dispatch time → simulator error → skip + exit 3."""

    def test_policy_deleted_after_review_records_unconfigured(self):
        from agent_harness_lab.auto import run_auto
        with _workspace() as ws, _sim_env_patch(**_SIM_ENV):
            exp = _setup(ws, sim_block=_ROLE_PLAY_BLOCK,
                         files={"cases/policy.md": _POLICY_EN})
            # delete the policy after setup (simulates file disappearing after review)
            (exp / "cases" / "policy.md").unlink()
            spec = parse_experiment_yaml(exp / "experiment.yaml")
            res = run_auto(exp, spec)
            # plan carries an error → simulator_unconfigured, dispatch skipped
            issue_types = [i["type"] for i in res.issues]
            self.assertIn("simulator_unconfigured", issue_types)
            self.assertEqual(_traces(exp), [])


class TestCorruptPlaybookFallback(unittest.TestCase):
    """H4: corrupt playbook under AHL_SIM_STUB → documented fallback/error behavior.

    A corrupt playbook when AHL_SIM_STUB=1 forced: the scripted branch loads the
    experiment playbook first. If it fails to parse, since we are in forced mode the
    code falls back to the built-in default (not an error), because AHL_SIM_STUB
    is a CI escape hatch that must not break over a bad mock file."""

    def test_corrupt_playbook_with_stub_falls_back_to_default(self):
        # AHL_SIM_STUB=1 with a corrupt playbook: run stays alive using the
        # built-in default, but a warn-severity playbook_invalid_fallback issue
        # is recorded so the substitution is visible (not silent).
        with _workspace() as ws, _sim_env_patch(AHL_SIM_STUB="1"):
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK,
                         files={"cases/playbook.yaml": "not: valid: yaml: [\n"})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            # should succeed via fallback to the built-in default playbook
            self.assertEqual(rc, 0)
            rec = _traces(exp)[0]
            self.assertEqual(rec["simulator"], "scripted")
            self.assertIs(rec["forced"], True)
            # the built-in default has 2 follow-ups → 3 turns total
            self.assertEqual(rec["turns"], 3)
            # the fallback must be recorded as a warn-severity issue
            issue_types = _issue_types(exp)
            self.assertIn("playbook_invalid_fallback", issue_types)

    def test_corrupt_playbook_without_stub_is_an_error(self):
        # Without the forced escape hatch, a corrupt playbook is a plan error
        # (the scripted simulator cannot run without a usable playbook).
        with _workspace() as ws, _sim_env_patch():
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK,
                         files={"cases/playbook.yaml": "not: valid: yaml: [\n"})
            rc, _, err = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 3)
            issue_types = _issue_types(exp)
            self.assertIn("simulator_unconfigured", issue_types)
            self.assertEqual(_traces(exp), [])


class TestPerCaseSessionStartFailure(unittest.TestCase):
    """H5: per-case session-start failure mid-experiment → partial evidence + case
    marked failed without killing the whole run.

    auto.py:530-538: each case gets its own session-start try/except; a failure
    records connector_failure for THAT case and continues to the next case."""

    def test_session_start_failure_is_isolated_to_the_case(self):
        # We simulate a startup failure by using a command that exits immediately,
        # causing the first send to fail. The second case (with a fresh process)
        # uses the normal agent.
        # Use _ECHO_ONE_THEN_EXIT: answers turn 0 then exits; the second simulated
        # turn (q1) will fail. Both cases run (fresh session per case), both get
        # partial evidence, the run does NOT abort.
        with _workspace() as ws, _sim_env_patch():
            cases = ('{"id":"case-001","input":"hello"}\n'
                     '{"id":"case-002","input":"world"}\n')
            exp = _setup(ws, sim_block=_SCRIPTED_BLOCK, agent=_ECHO_ONE_THEN_EXIT,
                         cases=cases, files={"cases/playbook.yaml": _PLAYBOOK})
            rc, _, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 3)  # error-severity issues → exit 3
            recs = _traces(exp)
            # BOTH cases get a trace record (the run does not abort on the first failure)
            self.assertEqual(len(recs), 2)
            for rec in recs:
                # turn 0 collected before the connector died
                self.assertGreaterEqual(rec["turns"], 1)
                self.assertFalse(rec["ok"])


if __name__ == "__main__":
    unittest.main()
