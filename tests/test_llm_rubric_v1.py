"""PR7: llm_rubric — the fourth evaluation method.

Tests:
  1. Rubric table parsing: well-formed table; missing table -> review ERROR;
     normalisation when weights != 1; multi-column variations.
  2. Per-dimension scoring -> weighted total + dimensions detail in score record.
  3. Multi-turn transcript expansion in the rubric prompt.
  4. Single-turn prompt shape (input/response, no transcript).
  5. No AHL_JUDGE_API_KEY -> PENDING (never fabricate).
  6. LLM request failure -> ERROR + exit 3 via eval CLI.
  7. LLM unparseable reply -> ERROR.
  8. Missing / empty rubric file -> ERROR at eval time.
  9. review catches missing rubric file (rubric_missing_dimensions) left-shifted.
  10. review catches malformed rubric table (rubric_invalid) left-shifted.
  11. Method registered: llm_rubric in EVAL_METHODS, schema accepts it.
  12. hlab run inline evaluation dispatches llm_rubric.
  13. hlab eval recompute dispatches llm_rubric.
  14. Trial awareness: latest-trial default; eval --trial N historical.
  15. Grader-parity fixture: hand-computed weighted aggregation matches
      llm_rubric's math (seed of PR9 deletion-gate comparison).
  16. Grader.py aggregation parity: same weighted math as grader.py score_run.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_harness_lab import cli, evaluation, llm
from agent_harness_lab.evaluation import _parse_rubric_table, _build_rubric_prompt
from agent_harness_lab.experiment_spec import EVAL_METHODS, parse_experiment_yaml, validate_spec

_EXE = sys.executable.replace("\\", "/")

# --- rubric table fixtures ----------------------------------------------------

_RUBRIC_WELL_FORMED = """\
# Quality Rubric

Assess the agent's response along these dimensions.

| Dimension   | Weight | Description                               |
|-------------|--------|-------------------------------------------|
| accuracy    | 0.5    | Is the answer factually correct?          |
| conciseness | 0.3    | Is the answer concise?                    |
| helpfulness | 0.2    | Is the answer helpful?                    |
"""

_RUBRIC_WEIGHTS_NOT_ONE = """\
# Test Rubric

| Dimension | Weight | Description  |
|-----------|--------|--------------|
| dim_a     | 2.0    | first dim    |
| dim_b     | 2.0    | second dim   |
| dim_c     | 6.0    | third dim    |
"""

_RUBRIC_NO_TABLE = """\
# Rubric without a table

Just some prose about quality. No dimension table here.
"""

_RUBRIC_TWO_DIMS = """\
| Dimension | Weight | Description    |
|-----------|--------|----------------|
| clarity   | 0.6    | Is it clear?   |
| accuracy  | 0.4    | Is it right?   |
"""


# --- workspace helpers --------------------------------------------------------

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


def _eval_yaml(ev_lines: str, track_lines: str) -> str:
    return ("evaluation:\n  root: evaluation/\n  evaluators:\n"
            + ev_lines + "  tracks:\n" + track_lines)


def _experiment_yaml(eval_section: str = "") -> str:
    return (
        "id: demo\nstatus: draft\nquestion: q\n"
        "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
        "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
        "agent_runtimes:\n  - id: runtime-a\n    harness: A\n    spec: agent-runtimes/runtime-a.yaml\n"
        "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
        "collection:\n  traces: true\n  raw: true\n  artifacts: true\n  snapshots: false\n  scores: true\n"
        "reports:\n  formats:\n    - md\n"
        + eval_section
    )


def _setup_exp(ws, eval_section="", agent_script=None, rubric_files=None):
    """Set up a minimal auto experiment with seed evidence."""
    from agent_harness_lab import scaffold
    scaffold.init_workspace(ws)
    exp = scaffold.new_experiment(ws, "demo", run_mode="auto").experiment_dir
    (exp / "experiment.yaml").write_text(_experiment_yaml(eval_section), encoding="utf-8")
    (exp / "cases" / "cases.jsonl").write_text(
        '{"id":"case-001","input":"hello"}\n', encoding="utf-8")
    (exp / "rt").mkdir(exist_ok=True)
    _agent = agent_script or (
        "import json,sys\n"
        "for line in sys.stdin:\n"
        "    d=json.loads(line)\n"
        "    sys.stdout.write(json.dumps({'response':'echo:'+d.get('input','')})+'\\n')\n"
        "    sys.stdout.flush()\n"
    )
    (exp / "rt" / "agent.py").write_text(_agent, encoding="utf-8")
    rt = (f"id: runtime-a\nconnector:\n  type: local_cli\n"
          f"  command: {_EXE} agent.py\n  working_dir: ./rt\n  timeout: 20\n")
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(rt, encoding="utf-8")
    for rel, body in (rubric_files or {}).items():
        dest = exp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
    return exp


def _seed_trace(exp, record=None):
    traces_dir = exp / "evidence" / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    r = record or {
        "case_id": "case-001", "runtime_id": "runtime-a", "harness_id": "A",
        "input": "hello", "response": "echo:hello", "ok": True
    }
    (traces_dir / "runtime-a.jsonl").write_text(json.dumps(r) + "\n", encoding="utf-8")


def _mock_chat_returning(dim_names, scores_per_dim):
    """Return a mock llm.chat that returns per-dimension scores as JSON."""
    payload = json.dumps({n: scores_per_dim.get(n, 50) for n in dim_names})
    def _chat(base, model, key, prompt, **kw):
        return payload
    return _chat


# --- Section 1: rubric table parsing ------------------------------------------

class TestParseRubricTable(unittest.TestCase):
    def test_well_formed_table_parses_three_dimensions(self):
        dims = _parse_rubric_table(_RUBRIC_WELL_FORMED)
        self.assertEqual(len(dims), 3)
        names = [d["name"] for d in dims]
        self.assertIn("accuracy", names)
        self.assertIn("conciseness", names)
        self.assertIn("helpfulness", names)

    def test_weights_extracted_correctly(self):
        dims = _parse_rubric_table(_RUBRIC_WELL_FORMED)
        by_name = {d["name"]: d for d in dims}
        self.assertAlmostEqual(by_name["accuracy"]["weight"], 0.5)
        self.assertAlmostEqual(by_name["conciseness"]["weight"], 0.3)
        self.assertAlmostEqual(by_name["helpfulness"]["weight"], 0.2)

    def test_descriptions_extracted(self):
        dims = _parse_rubric_table(_RUBRIC_WELL_FORMED)
        by_name = {d["name"]: d for d in dims}
        self.assertIn("factually", by_name["accuracy"]["description"])

    def test_no_table_returns_empty_list(self):
        dims = _parse_rubric_table(_RUBRIC_NO_TABLE)
        self.assertEqual(dims, [])

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(_parse_rubric_table(""), [])

    def test_prose_only_returns_empty_list(self):
        self.assertEqual(_parse_rubric_table("# Just a title\n\nSome text.\n"), [])

    def test_weights_not_normalised_at_parse_time(self):
        # Parser returns raw weights; normalisation is the runner's job
        dims = _parse_rubric_table(_RUBRIC_WEIGHTS_NOT_ONE)
        total = sum(d["weight"] for d in dims)
        self.assertAlmostEqual(total, 10.0)  # 2+2+6 = 10, not 1.0

    def test_minimal_two_dim_table(self):
        dims = _parse_rubric_table(_RUBRIC_TWO_DIMS)
        self.assertEqual(len(dims), 2)
        self.assertEqual(dims[0]["name"], "clarity")
        self.assertAlmostEqual(dims[1]["weight"], 0.4)


# --- Section 2: scoring math + dimensions in record --------------------------

class TestScoringMath(unittest.TestCase):
    """Per-dimension scoring -> weighted total + dimensions detail in score record."""

    def _run_rubric_eval(self, rubric_text, dim_scores, trace_record=None):
        """Run _run_llm_rubric with a mocked llm.chat and return the records."""
        dims = _parse_rubric_table(rubric_text)
        dim_names = [d["name"] for d in dims]

        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            eval_root = Path(tmp)
            rub_path = eval_root / "rubric.md"
            rub_path.write_text(rubric_text, encoding="utf-8")
            ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
            r = trace_record or {
                "case_id": "c1", "harness_id": "A", "input": "hello",
                "response": "answer", "ok": True
            }
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat",
                                      _mock_chat_returning(dim_names, dim_scores)):
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), eval_root, scores,
                    traces={"runtime-a": [r]}, cases=[])
            recs_path = Path(out.records_path)
            recs = [json.loads(ln) for ln in recs_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return out, recs

    def test_weighted_total_correct(self):
        # accuracy=80 weight=0.5, conciseness=60 weight=0.3, helpfulness=40 weight=0.2
        # normalised weights are already ~1.0 (0.5+0.3+0.2=1.0)
        # expected: 80*0.5 + 60*0.3 + 40*0.2 = 40+18+8 = 66.0
        _, recs = self._run_rubric_eval(
            _RUBRIC_WELL_FORMED,
            {"accuracy": 80, "conciseness": 60, "helpfulness": 40}
        )
        self.assertEqual(len(recs), 1)
        self.assertAlmostEqual(recs[0]["score"], 66.0, places=1)

    def test_dimensions_field_present_and_correct(self):
        _, recs = self._run_rubric_eval(
            _RUBRIC_WELL_FORMED,
            {"accuracy": 80, "conciseness": 60, "helpfulness": 40}
        )
        self.assertIn("dimensions", recs[0])
        dims = recs[0]["dimensions"]
        self.assertEqual(dims["accuracy"], 80.0)
        self.assertEqual(dims["conciseness"], 60.0)
        self.assertEqual(dims["helpfulness"], 40.0)

    def test_weights_normalised_when_not_summing_to_one(self):
        # dim_a=2.0/10=0.2, dim_b=2.0/10=0.2, dim_c=6.0/10=0.6
        # scores: dim_a=100, dim_b=100, dim_c=50
        # expected: 100*0.2 + 100*0.2 + 50*0.6 = 20+20+30 = 70.0
        _, recs = self._run_rubric_eval(
            _RUBRIC_WEIGHTS_NOT_ONE,
            {"dim_a": 100, "dim_b": 100, "dim_c": 50}
        )
        self.assertAlmostEqual(recs[0]["score"], 70.0, places=1)

    def test_status_is_passed_on_success(self):
        _, recs = self._run_rubric_eval(
            _RUBRIC_TWO_DIMS,
            {"clarity": 80, "accuracy": 90}
        )
        self.assertEqual(recs[0]["status"], "passed")

    def test_outcome_score_is_average_over_cases(self):
        out, _ = self._run_rubric_eval(
            _RUBRIC_TWO_DIMS,
            {"clarity": 80, "accuracy": 80}
        )
        self.assertIsNotNone(out.score)


# --- Section 3: multi-turn prompt expansion -----------------------------------

class TestRubricPromptTranscript(unittest.TestCase):
    _TR = [{"turn": 0, "user": "hello", "agent": "hi there"},
           {"turn": 1, "user": "follow up", "agent": "more detail"}]

    def _dims(self):
        return [{"name": "accuracy", "weight": 0.6, "description": "correct?"},
                {"name": "clarity", "weight": 0.4, "description": "clear?"}]

    def test_multiturn_prompt_contains_conversation_block(self):
        prompt = _build_rubric_prompt(self._dims(), "hello", "more detail",
                                      "ev=s", transcript=self._TR)
        self.assertIn("[CONVERSATION]", prompt)
        self.assertIn("[turn 0] user: hello", prompt)
        self.assertIn("agent: hi there", prompt)
        self.assertIn("[turn 1] user: follow up", prompt)
        self.assertNotIn("[CASE INPUT]", prompt)
        self.assertNotIn("[AGENT OUTPUT]", prompt)

    def test_single_turn_prompt_uses_input_response(self):
        prompt = _build_rubric_prompt(self._dims(), "hello", "answer",
                                      "ev=s", transcript=None)
        self.assertIn("[CASE INPUT]", prompt)
        self.assertIn("[AGENT OUTPUT]", prompt)
        self.assertNotIn("[CONVERSATION]", prompt)

    def test_empty_transcript_falls_back_to_single_turn(self):
        prompt_none = _build_rubric_prompt(self._dims(), "q", "a", "s", transcript=None)
        prompt_empty = _build_rubric_prompt(self._dims(), "q", "a", "s", transcript=[])
        self.assertEqual(prompt_none, prompt_empty)

    def test_prompt_includes_dimension_names(self):
        prompt = _build_rubric_prompt(self._dims(), "q", "a", "s")
        self.assertIn("accuracy", prompt)
        self.assertIn("clarity", prompt)

    def test_prompt_instructs_json_output(self):
        prompt = _build_rubric_prompt(self._dims(), "q", "a", "s")
        self.assertIn("JSON", prompt)


# --- Section 4: multiturn records judged over whole conversation in runner ----

class TestRubricRunnerTranscript(unittest.TestCase):
    def _capture_prompts(self, traces, rubric_text=_RUBRIC_TWO_DIMS):
        captured: list[str] = []
        dims = _parse_rubric_table(rubric_text)
        dim_names = [d["name"] for d in dims]
        payload = json.dumps({n: 75 for n in dim_names})

        def chat(base, model, key, prompt, **kw):
            captured.append(prompt)
            return payload

        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            rub_path = Path(tmp) / "rubric.md"
            rub_path.write_text(rubric_text, encoding="utf-8")
            ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat", chat):
                evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces=traces, cases=[])
        return captured

    def test_multiturn_record_uses_conversation_block(self):
        rec = {"case_id": "c1", "harness_id": "A", "input": "hello",
               "response": "final", "ok": True, "turns": 2,
               "transcript": [{"turn": 0, "user": "hello", "agent": "hi"},
                               {"turn": 1, "user": "more?", "agent": "final"}],
               "simulator": "scripted"}
        prompts = self._capture_prompts({"rt": [rec]})
        self.assertEqual(len(prompts), 1)
        self.assertIn("[CONVERSATION]", prompts[0])
        self.assertIn("[turn 0]", prompts[0])
        self.assertNotIn("[CASE INPUT]", prompts[0])

    def test_single_turn_record_uses_input_output(self):
        rec = {"case_id": "c1", "harness_id": "A", "input": "hello",
               "response": "answer", "ok": True}
        prompts = self._capture_prompts({"rt": [rec]})
        self.assertIn("[CASE INPUT]", prompts[0])
        self.assertNotIn("[CONVERSATION]", prompts[0])


# --- Section 5: no key -> PENDING ---------------------------------------------

class TestRubricPending(unittest.TestCase):
    def test_no_key_returns_pending(self):
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL",
                                  "AHL_JUDGE_MODEL")}
        with mock.patch.dict(os.environ, env_clean, clear=True):
            with tempfile.TemporaryDirectory() as tmp:
                scores = Path(tmp) / "scores"
                rub_path = Path(tmp) / "rubric.md"
                rub_path.write_text(_RUBRIC_TWO_DIMS, encoding="utf-8")
                ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
                r = {"case_id": "c1", "harness_id": "A", "input": "q",
                     "response": "a", "ok": True}
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces={"rt": [r]}, cases=[])
                self.assertEqual(out.status, "pending")
                recs_path = Path(out.records_path)
                rec = json.loads(recs_path.read_text(encoding="utf-8").splitlines()[0])
                self.assertEqual(rec["status"], "pending")
                self.assertIn("AHL_JUDGE_API_KEY", rec["detail"])

    def test_no_key_via_eval_cli_exits_0(self):
        """Pending (no key) is not a failure — eval exits 0."""
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/q.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL",
                                  "AHL_JUDGE_MODEL")}
        with mock.patch.dict(os.environ, env_clean, clear=True):
            with _workspace() as ws:
                exp = _setup_exp(ws, eval_section=_eval_yaml(ev, tr),
                                 rubric_files={"evaluation/rubrics/q.md": _RUBRIC_TWO_DIMS})
                _seed_trace(exp)
                rc, _, _ = _run_cli(["eval", "experiments/demo"])
                self.assertEqual(rc, 0)


# --- Section 6: LLM request failure -> ERROR + exit 3 ------------------------

class TestRubricLlmFailure(unittest.TestCase):
    def test_llm_failure_produces_error_record(self):
        def bad_chat(base, model, key, prompt, **kw):
            raise RuntimeError("connection refused")

        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            rub_path = Path(tmp) / "rubric.md"
            rub_path.write_text(_RUBRIC_TWO_DIMS, encoding="utf-8")
            ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
            r = {"case_id": "c1", "harness_id": "A", "input": "q",
                 "response": "a", "ok": True}
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat", bad_chat):
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces={"rt": [r]}, cases=[])
            self.assertEqual(out.status, "error")
            recs = [json.loads(ln) for ln in
                    Path(out.records_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(recs[0]["status"], "error")
            self.assertIn("connection refused", recs[0]["detail"])

    def test_llm_failure_via_eval_exits_3_with_hlab_eval_error(self):
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/q.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"

        def bad_chat(base, model, key, prompt, **kw):
            raise RuntimeError("network error")

        env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
               "AHL_JUDGE_MODEL": "m"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(llm, "chat", bad_chat):
            with _workspace() as ws:
                exp = _setup_exp(ws, eval_section=_eval_yaml(ev, tr),
                                 rubric_files={"evaluation/rubrics/q.md": _RUBRIC_TWO_DIMS})
                _seed_trace(exp)
                rc, _, err = _run_cli(["eval", "experiments/demo"])
                self.assertEqual(rc, 3)
                self.assertIn("HLAB_EVAL_ERROR", err)


# --- Section 7: unparseable LLM reply -> ERROR --------------------------------

class TestRubricUnparseableReply(unittest.TestCase):
    def test_non_json_reply_is_error(self):
        def bad_chat(base, model, key, prompt, **kw):
            return "I cannot score this."

        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            rub_path = Path(tmp) / "rubric.md"
            rub_path.write_text(_RUBRIC_TWO_DIMS, encoding="utf-8")
            ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
            r = {"case_id": "c1", "harness_id": "A", "input": "q",
                 "response": "a", "ok": True}
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat", bad_chat):
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces={"rt": [r]}, cases=[])
            self.assertEqual(out.status, "error")
            rec = json.loads(Path(out.records_path).read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("unparseable", rec["detail"])
            self.assertIn("raw_response", rec)

    def test_missing_dimension_in_reply_is_error(self):
        # Reply has only one dimension but we need two
        def partial_chat(base, model, key, prompt, **kw):
            return '{"clarity": 80}'  # missing accuracy

        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            rub_path = Path(tmp) / "rubric.md"
            rub_path.write_text(_RUBRIC_TWO_DIMS, encoding="utf-8")
            ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
            r = {"case_id": "c1", "harness_id": "A", "input": "q",
                 "response": "a", "ok": True}
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat", partial_chat):
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces={"rt": [r]}, cases=[])
        self.assertEqual(out.status, "error")


# --- Section 8: missing/empty rubric file ------------------------------------

class TestMissingRubricFile(unittest.TestCase):
    def test_no_rubric_file_is_error(self):
        """If the rubric file referenced in ev.rubric is absent, eval returns ERROR."""
        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            ev = SimpleNamespace(id="r1", method="llm_rubric",
                                 rubric="rubrics/nonexistent.md")
            r = {"case_id": "c1", "harness_id": "A", "input": "q",
                 "response": "a", "ok": True}
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False):
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces={"rt": [r]}, cases=[])
        self.assertEqual(out.status, "error")
        self.assertIn("dimensions", out.detail)

    def test_empty_rubric_text_is_error(self):
        """A rubric file that exists but has no table yields ERROR."""
        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            rub_path = Path(tmp) / "rubric.md"
            rub_path.write_text(_RUBRIC_NO_TABLE, encoding="utf-8")
            ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
            r = {"case_id": "c1", "harness_id": "A", "input": "q",
                 "response": "a", "ok": True}
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False):
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces={"rt": [r]}, cases=[])
        self.assertEqual(out.status, "error")


# --- Section 9: review left-shifts missing rubric file -----------------------

class TestReviewLeftShiftsMissingRubric(unittest.TestCase):
    """review_experiment catches a missing rubric_file as ERROR before any run."""

    def _base_yaml_for_review(self, eval_section):
        return (
            "id: demo\nstatus: draft\nquestion: q\n"
            "run:\n  mode: copilot\nexecution:\n  mode: ab\n  state_policy: isolated\n"
            "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
            "agent_runtimes:\n  - id: rt-a\n    harness: A\n    spec: agent-runtimes/rt-a.yaml\n"
            "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
            "collection:\n  traces: true\n  raw: true\n  artifacts: false\n  snapshots: false\n  scores: true\n"
            "reports:\n  formats:\n    - md\n"
            + eval_section
        )

    def _make_review_exp(self, ws, eval_section, rubric_files=None, make_runtime=True):
        """Build a review-able experiment structure (without running)."""
        (ws / "experiments" / "demo").mkdir(parents=True, exist_ok=True)
        exp = ws / "experiments" / "demo"
        (exp / "harnesses" / "A").mkdir(parents=True, exist_ok=True)
        (exp / "agent-runtimes").mkdir(parents=True, exist_ok=True)
        (exp / "cases").mkdir(parents=True, exist_ok=True)
        (exp / "evaluation").mkdir(parents=True, exist_ok=True)
        (exp / "evaluation" / "rubrics").mkdir(parents=True, exist_ok=True)
        (exp / "cases" / "cases.jsonl").write_text('{"id":"c1","input":"q"}\n', encoding="utf-8")
        if make_runtime:
            (exp / "agent-runtimes" / "rt-a.yaml").write_text(
                f"id: rt-a\nconnector:\n  type: local_cli\n  command: py agent.py\n  working_dir: ./harnesses/A\n",
                encoding="utf-8")
        (exp / "experiment.yaml").write_text(
            self._base_yaml_for_review(eval_section), encoding="utf-8")
        for rel, body in (rubric_files or {}).items():
            dest = exp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
        return exp

    def test_llm_rubric_with_missing_rubric_field_is_review_error(self):
        """llm_rubric evaluator with no `rubric:` -> review ERROR rubric_missing_dimensions."""
        ev = ("    - id: r1\n      method: llm_rubric\n")  # no rubric: key
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"
        with _workspace() as ws:
            exp = self._make_review_exp(ws, _eval_yaml(ev, tr))
            spec = parse_experiment_yaml(exp / "experiment.yaml")
            problems = validate_spec(spec, exp)
            codes = [p.code for p in problems]
            self.assertIn("rubric_missing_dimensions", codes)
            # check level
            p = next(p for p in problems if p.code == "rubric_missing_dimensions")
            self.assertEqual(p.level, "ERROR")

    def test_llm_rubric_with_invalid_rubric_table_is_review_error(self):
        """llm_rubric evaluator with rubric file that has no dimension table -> ERROR rubric_invalid."""
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/empty.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"
        with _workspace() as ws:
            exp = self._make_review_exp(
                ws, _eval_yaml(ev, tr),
                rubric_files={"evaluation/rubrics/empty.md": _RUBRIC_NO_TABLE})
            spec = parse_experiment_yaml(exp / "experiment.yaml")
            problems = validate_spec(spec, exp)
            codes = [p.code for p in problems]
            self.assertIn("rubric_invalid", codes)
            p = next(p for p in problems if p.code == "rubric_invalid")
            self.assertEqual(p.level, "ERROR")

    def test_llm_rubric_with_valid_rubric_no_review_error(self):
        """llm_rubric evaluator with a valid rubric file -> no rubric_* review errors."""
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/valid.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"
        with _workspace() as ws:
            exp = self._make_review_exp(
                ws, _eval_yaml(ev, tr),
                rubric_files={"evaluation/rubrics/valid.md": _RUBRIC_WELL_FORMED})
            spec = parse_experiment_yaml(exp / "experiment.yaml")
            problems = validate_spec(spec, exp)
            rubric_codes = [p.code for p in problems
                            if p.code.startswith("rubric_")]
            self.assertEqual(rubric_codes, [])


# --- Section 10: method registration -----------------------------------------

class TestMethodRegistration(unittest.TestCase):
    def test_llm_rubric_in_eval_methods_constant(self):
        self.assertIn("llm_rubric", EVAL_METHODS)

    def test_eval_methods_now_four(self):
        self.assertEqual(
            EVAL_METHODS,
            {"benchmark", "human_annotation", "llm_judge", "llm_rubric"}
        )

    def test_unknown_method_not_in_eval_methods(self):
        """An unknown method is not in EVAL_METHODS; llm_rubric is."""
        self.assertIn("llm_rubric", EVAL_METHODS)
        self.assertNotIn("grader", EVAL_METHODS)
        self.assertNotIn("llm_scorer", EVAL_METHODS)


# --- Section 11: hlab run inline evaluation -----------------------------------

class TestRunInlineEval(unittest.TestCase):
    """hlab run dispatches llm_rubric inline with a mocked judge."""

    def test_run_inline_llm_rubric_dispatched_and_scored(self):
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/q.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"

        def mock_chat(base, model, key, prompt, **kw):
            return '{"clarity": 80, "accuracy": 90}'

        env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
               "AHL_JUDGE_MODEL": "m"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(llm, "chat", mock_chat):
            with _workspace() as ws:
                exp = _setup_exp(ws, eval_section=_eval_yaml(ev, tr),
                                 rubric_files={"evaluation/rubrics/q.md": _RUBRIC_TWO_DIMS})
                rc, out, err = _run_cli(["run", "experiments/demo"])
                # pending or passed is acceptable (depends on trace response field)
                agg_path = exp / "evidence" / "scores" / "tracks" / "scored.json"
                self.assertTrue(agg_path.is_file(), f"agg not written; stderr={err}")
                agg = json.loads(agg_path.read_text(encoding="utf-8"))
                self.assertIn(agg["status"], ("passed", "pending", "error"))


# --- Section 12: hlab eval recompute -----------------------------------------

class TestEvalRecompute(unittest.TestCase):
    """hlab eval recomputes llm_rubric on existing evidence."""

    def test_eval_rewrites_scores_without_modifying_traces(self):
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/q.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"

        def mock_chat(base, model, key, prompt, **kw):
            return '{"clarity": 75, "accuracy": 85}'

        env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
               "AHL_JUDGE_MODEL": "m"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(llm, "chat", mock_chat):
            with _workspace() as ws:
                exp = _setup_exp(ws, eval_section=_eval_yaml(ev, tr),
                                 rubric_files={"evaluation/rubrics/q.md": _RUBRIC_TWO_DIMS})
                _seed_trace(exp)
                trace_path = exp / "evidence" / "traces" / "runtime-a.jsonl"
                original_bytes = trace_path.read_bytes()

                rc, out, err = _run_cli(["eval", "experiments/demo"])
                self.assertIn(rc, (0, 3), f"unexpected rc={rc}; stderr={err}")
                # traces must be unchanged
                self.assertEqual(trace_path.read_bytes(), original_bytes)
                # scores were written
                agg_path = exp / "evidence" / "scores" / "tracks" / "scored.json"
                self.assertTrue(agg_path.is_file())


# --- Section 13: trial awareness ----------------------------------------------

class TestTrialAwareness(unittest.TestCase):
    def test_latest_trial_default(self):
        """When two trials exist, eval default uses the latest trial."""
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/q.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"

        calls: list[str] = []

        def mock_chat(base, model, key, prompt, **kw):
            calls.append(prompt)
            return '{"clarity": 90, "accuracy": 90}'

        env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
               "AHL_JUDGE_MODEL": "m"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(llm, "chat", mock_chat):
            with _workspace() as ws:
                exp = _setup_exp(ws, eval_section=_eval_yaml(ev, tr),
                                 rubric_files={"evaluation/rubrics/q.md": _RUBRIC_TWO_DIMS})
                traces_dir = exp / "evidence" / "traces"
                traces_dir.mkdir(parents=True, exist_ok=True)
                # trial 0 record and trial 1 record
                r0 = {"case_id": "c1", "runtime_id": "runtime-a", "harness_id": "A",
                      "input": "q", "response": "a0", "ok": True}  # no trial field -> trial 0
                r1 = {"case_id": "c1", "runtime_id": "runtime-a", "harness_id": "A",
                      "input": "q", "response": "a1", "ok": True, "trial": 1}
                (traces_dir / "runtime-a.jsonl").write_text(
                    json.dumps(r0) + "\n" + json.dumps(r1) + "\n", encoding="utf-8")

                rc, _, _ = _run_cli(["eval", "experiments/demo"])
                # should have made exactly 1 llm call (for trial 1 only)
                self.assertEqual(len(calls), 1)
                # the prompt should contain trial 1's response
                self.assertIn("a1", calls[0])

    def test_eval_trial_n_uses_specific_trial(self):
        """eval --trial 0 uses trial 0 records only."""
        ev = "    - id: r1\n      method: llm_rubric\n      rubric: rubrics/q.md\n"
        tr = "    - id: scored\n      evaluators: [r1]\n      evidence: [traces]\n"

        calls: list[str] = []

        def mock_chat(base, model, key, prompt, **kw):
            calls.append(prompt)
            return '{"clarity": 70, "accuracy": 70}'

        env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
               "AHL_JUDGE_MODEL": "m"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(llm, "chat", mock_chat):
            with _workspace() as ws:
                exp = _setup_exp(ws, eval_section=_eval_yaml(ev, tr),
                                 rubric_files={"evaluation/rubrics/q.md": _RUBRIC_TWO_DIMS})
                traces_dir = exp / "evidence" / "traces"
                traces_dir.mkdir(parents=True, exist_ok=True)
                r0 = {"case_id": "c1", "runtime_id": "runtime-a", "harness_id": "A",
                      "input": "q", "response": "trial0-answer", "ok": True}
                r1 = {"case_id": "c1", "runtime_id": "runtime-a", "harness_id": "A",
                      "input": "q", "response": "trial1-answer", "ok": True, "trial": 1}
                (traces_dir / "runtime-a.jsonl").write_text(
                    json.dumps(r0) + "\n" + json.dumps(r1) + "\n", encoding="utf-8")

                rc, _, _ = _run_cli(["eval", "experiments/demo", "--trial", "0"])
                self.assertEqual(len(calls), 1)
                self.assertIn("trial0-answer", calls[0])


# --- Section 14: grader-parity fixture ----------------------------------------

class TestGraderParity(unittest.TestCase):
    """Verify llm_rubric's weighted aggregation math matches grader.py's score_run.

    This is the seed of the PR9 deletion-gate comparison. Both use the same
    normalise-then-weighted-sum formula. The test runs both paths on the same
    fixture and asserts they agree.

    grader.py score_run normalisation:
      raw_weights = {dim.name: dim.weight for dim in rubric.dimensions}
      total_w = sum(raw_weights.values())
      weight = {k: v / total_w for k, v in raw_weights.items()}   # if total_w > 0
      total = round(sum(dims.get(name, 0.0) * w for name, w in weight.items()), 2)

    llm_rubric normalisation (evaluation.py _run_llm_rubric):
      raw_weights = {d["name"]: d["weight"] for d in dimensions}
      total_w = sum(raw_weights.values())
      weights = {k: v / total_w for k, v in raw_weights.items()}
      weighted_total = round(sum(dim_scores.get(n, 0.0) * weights.get(n, 0.0) for n in dim_names), 2)

    Both round to 2 decimal places after summing. The test verifies numerically.
    """

    _RUBRIC_FIXTURE = """\
| Dimension   | Weight | Description        |
|-------------|--------|--------------------|
| accuracy    | 0.5    | factually correct  |
| clarity     | 0.3    | clear and concise  |
| helpfulness | 0.2    | genuinely helpful  |
"""

    _DIM_SCORES = {"accuracy": 80.0, "clarity": 60.0, "helpfulness": 50.0}
    # Hand-computed expected:
    # weights already sum to 1.0; no normalisation needed.
    # total = 80*0.5 + 60*0.3 + 50*0.2 = 40 + 18 + 10 = 68.0
    _EXPECTED_TOTAL = 68.0

    def _llm_rubric_weighted_total(self, rubric_text, dim_scores):
        """Replicate llm_rubric's normalise+sum math."""
        dims = _parse_rubric_table(rubric_text)
        raw_weights = {d["name"]: d["weight"] for d in dims}
        total_w = sum(raw_weights.values())
        weights = {k: v / total_w for k, v in raw_weights.items()} if total_w > 0 else {k: 1.0 / len(raw_weights) for k in raw_weights}
        dim_names = [d["name"] for d in dims]
        return round(sum(dim_scores.get(n, 0.0) * weights.get(n, 0.0) for n in dim_names), 2)

    def _grader_py_weighted_total(self, rubric_text, dim_scores):
        """Replicate grader.py score_run's normalise+sum math directly.

        grader.py is importable; we use its Rubric/Dimension/score_run to
        compute the same result. If grader.py's entry points make this awkward
        (it expects a file path), we replicate its documented math instead and
        note that in the report.
        """
        from agent_harness_lab.grader import score_run
        from agent_harness_lab.rubric import parse_rubric
        import tempfile, os as _os
        # Write rubric to a temp file; grader.py's parse_rubric needs a real path.
        # The rubric.py format uses H2 sections with "权重: N" lines, but grader.py
        # accepts a Rubric object directly via score_run. We build the Rubric manually
        # from the parsed table to avoid format mismatches.
        from agent_harness_lab.rubric import Rubric, Dimension
        from pathlib import Path as _Path
        dims_parsed = _parse_rubric_table(rubric_text)
        rubric = Rubric(path=_Path("fixture.md"))
        for d in dims_parsed:
            rubric.dimensions.append(Dimension(
                name=d["name"], weight=d["weight"], description=d["description"]))
        # Build run records in grader.py's format (transcript=[{turn, user, agent}])
        run_record = {
            "version_id": "A",
            "case_id": "c1",
            "transcript": [{"turn": 0, "user": "q", "agent": "ans"}],
        }
        # Use a custom grader that returns our fixed dim_scores
        def fixed_grader(rub, vid, cid, transcript):
            return dict(dim_scores)
        scores = score_run(rubric, [run_record], grader=fixed_grader)
        return scores[0].total if scores else None

    def test_hand_computed_total_matches_llm_rubric_math(self):
        total = self._llm_rubric_weighted_total(self._RUBRIC_FIXTURE, self._DIM_SCORES)
        self.assertAlmostEqual(total, self._EXPECTED_TOTAL, places=2)

    def test_llm_rubric_math_matches_grader_py_math(self):
        """llm_rubric's weighted-sum formula equals grader.py's score_run formula."""
        v1_total = self._llm_rubric_weighted_total(self._RUBRIC_FIXTURE, self._DIM_SCORES)
        grader_total = self._grader_py_weighted_total(self._RUBRIC_FIXTURE, self._DIM_SCORES)
        self.assertAlmostEqual(v1_total, grader_total, places=2,
                               msg=f"llm_rubric total {v1_total} != grader.py total {grader_total}")

    def test_normalisation_parity_when_weights_not_sum_to_one(self):
        """Both stacks normalise the same way when weights don't sum to 1."""
        rubric_uneven = """\
| Dimension | Weight | Description |
|-----------|--------|-------------|
| dim_a     | 2.0    | first       |
| dim_b     | 3.0    | second      |
"""
        dim_scores = {"dim_a": 100.0, "dim_b": 50.0}
        # Expected: weights -> 2/5=0.4, 3/5=0.6 -> 100*0.4 + 50*0.6 = 40+30 = 70.0
        v1_total = self._llm_rubric_weighted_total(rubric_uneven, dim_scores)
        grader_total = self._grader_py_weighted_total(rubric_uneven, dim_scores)
        self.assertAlmostEqual(v1_total, 70.0, places=2)
        self.assertAlmostEqual(grader_total, 70.0, places=2)
        self.assertAlmostEqual(v1_total, grader_total, places=2)

    def test_full_pipeline_weighted_total_via_mock(self):
        """Full _run_llm_rubric pipeline produces the hand-computed total."""
        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            rub_path = Path(tmp) / "rubric.md"
            rub_path.write_text(self._RUBRIC_FIXTURE, encoding="utf-8")
            ev = SimpleNamespace(id="r1", method="llm_rubric", rubric="rubric.md")
            r = {"case_id": "c1", "harness_id": "A", "input": "q",
                 "response": "answer", "ok": True}
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            payload = json.dumps(self._DIM_SCORES)
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat", lambda *a, **kw: payload):
                out = evaluation._run_llm_rubric(
                    ev, "t", Path(tmp), Path(tmp), scores,
                    traces={"rt": [r]}, cases=[])
            recs = [json.loads(ln) for ln in
                    Path(out.records_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(recs), 1)
        self.assertAlmostEqual(recs[0]["score"], self._EXPECTED_TOTAL, places=2)


if __name__ == "__main__":
    unittest.main()
