"""EvaluationRunner (Section 1): three-layer evaluation over Auto Run evidence.

Evaluators run within tracks; benchmark executes a script, human_annotation/llm_judge
are honest pending stubs; tracks aggregate; the objective's primary track is reflected.
v1.1 (PR3): a multi-turn trace record (carries `transcript`) is judged over the whole
conversation; the single-turn judge prompt is frozen byte-for-byte (golden-pinned).
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_harness_lab import evaluation, llm
from agent_harness_lab.experiment_spec import parse_experiment_yaml
from tests.test_auto_v1 import _ECHO_NO_ARTIFACT, _run_cli, _setup, _workspace

# benchmark evaluator scripts: read the context JSON (argv[1]), print a JSON verdict
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
_BENCH_CRASH = "import sys\nsys.exit(3)\n"          # non-zero exit → status error
_BENCH_NOTJSON = "print('not json at all')\n"        # bad stdout → status error
_BENCH_RECORDS = (
    "import json,sys\n"
    "json.load(open(sys.argv[1],encoding='utf-8'))\n"
    "print(json.dumps({'records':["
    "{'case_id':'c1','passed':True,'score':1},"
    "{'case_id':'c2','passed':True,'score':1}]}))\n"
)


def _eval_section(evaluators: str, tracks: str) -> str:
    return "evaluation:\n  root: evaluation/\n  evaluators:\n" + evaluators + "  tracks:\n" + tracks


def _setup_exp(ws, eval_section, objective_section="", scripts=None):
    """Write a parseable auto experiment + optional benchmark scripts + a seed trace."""
    exp = ws / "experiments" / "demo"
    (exp / "evaluation" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (exp / "evidence" / "traces").mkdir(parents=True, exist_ok=True)
    for name, body in (scripts or {}).items():
        dest = exp / "evaluation" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
    (exp / "evidence" / "traces" / "runtime-a.jsonl").write_text(
        json.dumps({"case_id": "case-001", "runtime_id": "runtime-a", "ok": True}) + "\n",
        encoding="utf-8")
    yaml = ("id: demo\nstatus: draft\nquestion: q\n"
            "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
            + eval_section + objective_section)
    (exp / "experiment.yaml").write_text(yaml, encoding="utf-8")
    return exp


def _spec(exp):
    return parse_experiment_yaml(exp / "experiment.yaml")


_EV_BENCH = "    - id: e1\n      method: benchmark\n      script: benchmarks/{}.py\n"
_TRACK = "    - id: quality\n      evaluators: [e1]\n      evidence: [traces]\n"


class TestBenchmarkEvaluator(unittest.TestCase):
    def test_happy_path_passed_and_scores_written(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, _eval_section(_EV_BENCH.format("pass"), _TRACK),
                             scripts={"benchmarks/pass.py": _BENCH_PASS})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertTrue(res.ran)
            self.assertEqual(res.tracks[0].status, "passed")
            recs = (exp / "evidence" / "scores" / "quality" / "e1.jsonl")
            self.assertTrue(recs.is_file())
            rec = json.loads(recs.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rec["status"], "passed")
            agg = json.loads((exp / "evidence" / "scores" / "tracks" / "quality.json")
                             .read_text(encoding="utf-8"))
            self.assertEqual(agg["status"], "passed")
            self.assertEqual(agg["evaluators"][0]["evaluator_id"], "e1")

    def test_failure_track_failed(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, _eval_section(_EV_BENCH.format("fail"), _TRACK),
                             scripts={"benchmarks/fail.py": _BENCH_FAIL})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "failed")

    def test_script_nonzero_exit_is_error(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, _eval_section(_EV_BENCH.format("crash"), _TRACK),
                             scripts={"benchmarks/crash.py": _BENCH_CRASH})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "error")

    def test_script_non_json_is_error(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, _eval_section(_EV_BENCH.format("nj"), _TRACK),
                             scripts={"benchmarks/nj.py": _BENCH_NOTJSON})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "error")

    def test_records_mode_writes_per_case_lines(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, _eval_section(_EV_BENCH.format("rec"), _TRACK),
                             scripts={"benchmarks/rec.py": _BENCH_RECORDS})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "passed")
            lines = [ln for ln in (exp / "evidence" / "scores" / "quality" / "e1.jsonl")
                     .read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2)

    def test_missing_script_is_error(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, _eval_section(_EV_BENCH.format("ghost"), _TRACK))  # no script file
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "error")


class TestHumanAndLlm(unittest.TestCase):
    def _human_section(self):
        ev = "    - id: h1\n      method: human_annotation\n"
        tr = "    - id: review\n      evaluators: [h1]\n      evidence: [traces]\n"
        return _eval_section(ev, tr)

    def test_human_annotation_pending_when_absent(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, self._human_section())
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "pending")
            rec = json.loads((exp / "evidence" / "scores" / "review" / "h1.jsonl")
                             .read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rec["status"], "pending")

    def test_human_annotation_ingested_when_present(self):
        with _workspace() as ws:
            exp = _setup_exp(ws, self._human_section())
            ann = exp / "evidence" / "scores" / "review" / "h1.annotation.json"
            ann.parent.mkdir(parents=True, exist_ok=True)
            ann.write_text(json.dumps({"passed": True, "score": 0.9, "detail": "looks good"}),
                           encoding="utf-8")
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "passed")

    def test_human_annotation_passed_false_is_failed(self):
        # explicit false is a real verdict (FAILED), not an error
        with _workspace() as ws:
            exp = _setup_exp(ws, self._human_section())
            ann = exp / "evidence" / "scores" / "review" / "h1.annotation.json"
            ann.parent.mkdir(parents=True, exist_ok=True)
            ann.write_text(json.dumps({"passed": False, "detail": "rejected"}),
                           encoding="utf-8")
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "failed")

    def test_human_annotation_missing_passed_is_error(self):
        # a score alone is not a verdict — missing `passed` must surface as ERROR
        with _workspace() as ws:
            exp = _setup_exp(ws, self._human_section())
            ann = exp / "evidence" / "scores" / "review" / "h1.annotation.json"
            ann.parent.mkdir(parents=True, exist_ok=True)
            ann.write_text(json.dumps({"score": 0.9}), encoding="utf-8")
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "error")
            rec = json.loads((exp / "evidence" / "scores" / "review" / "h1.jsonl")
                             .read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rec["status"], "error")
            self.assertIn('missing boolean "passed"', rec["detail"])
            self.assertIn("h1.annotation.json", rec["detail"])  # file path named
            self.assertIn('"passed": bool', rec["detail"])      # expected schema named

    def test_human_annotation_non_bool_passed_is_error(self):
        # truthy strings like "yes" must NOT silently pass — type matters
        with _workspace() as ws:
            exp = _setup_exp(ws, self._human_section())
            ann = exp / "evidence" / "scores" / "review" / "h1.annotation.json"
            ann.parent.mkdir(parents=True, exist_ok=True)
            ann.write_text(json.dumps({"passed": "yes", "score": 1.0}), encoding="utf-8")
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "error")
            rec = json.loads((exp / "evidence" / "scores" / "review" / "h1.jsonl")
                             .read_text(encoding="utf-8").splitlines()[0])
            self.assertIn('missing boolean "passed"', rec["detail"])

    def test_llm_judge_pending_without_key(self):
        # No AHL_JUDGE_API_KEY -> llm_judge stays pending (never a fabricated verdict).
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("AHL_JUDGE_API_KEY", "AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL"):
                os.environ.pop(k, None)
            with _workspace() as ws:
                ev = "    - id: j1\n      method: llm_judge\n      rubric: rubrics/q.md\n"
                tr = "    - id: judged\n      evaluators: [j1]\n      evidence: [traces]\n"
                exp = _setup_exp(ws, _eval_section(ev, tr),
                                 scripts={"rubrics/q.md": "# rubric\njudge quality\n"})
                res = evaluation.run_evaluation(exp, _spec(exp))
                self.assertEqual(res.tracks[0].status, "pending")
                rec = json.loads((exp / "evidence" / "scores" / "judged" / "j1.jsonl")
                                 .read_text(encoding="utf-8").splitlines()[0])
                self.assertEqual(rec["status"], "pending")
                self.assertIn("AHL_JUDGE_API_KEY", rec["detail"])


# golden copy of the frozen single-turn judge prompt — deliberately hand-written,
# NOT built from the source constants (the pinning is the point: a multi-turn
# landing must leave the single-turn prompt byte-for-byte unchanged).
_GOLDEN_SINGLE_TURN_PROMPT = (
    "You are a strict evaluator. Judge the agent's OUTPUT for the given CASE "
    "against the RUBRIC. Be conservative: only 'pass' when the output clearly "
    "satisfies the rubric.\n\n"
    "[RUBRIC]\nbe right\n\n"
    "[CASE INPUT]\nq\n\n"
    "[AGENT OUTPUT]\nan answer\n\n"
    "[EVIDENCE SUMMARY]\ncase_id=c1, harness_id=A, ok=True\n\n"
    "Reply with ONLY one JSON object and nothing else:\n"
    '{"verdict": "pass" | "fail", "score": <integer 0-100>, "reason": "<one sentence>"}'
)


class TestJudgePromptTranscript(unittest.TestCase):
    """v1.1 PR3: multi-turn records are judged over the WHOLE conversation
    ([CONVERSATION], turn by turn); without a transcript the prompt is frozen."""

    _TR = [{"turn": 0, "user": "hello", "agent": "hi"},
           {"turn": 1, "user": "q1", "agent": "a1"}]

    def test_single_turn_prompt_bytes_unchanged(self):
        got = evaluation._build_judge_prompt(
            "be right", "q", "an answer", "case_id=c1, harness_id=A, ok=True")
        self.assertEqual(got, _GOLDEN_SINGLE_TURN_PROMPT)

    def test_none_and_empty_transcript_keep_single_turn_prompt(self):
        base = evaluation._build_judge_prompt("r", "q", "a", "s")
        self.assertEqual(
            evaluation._build_judge_prompt("r", "q", "a", "s", transcript=None), base)
        self.assertEqual(
            evaluation._build_judge_prompt("r", "q", "a", "s", transcript=[]), base)

    def test_transcript_prompt_expands_conversation(self):
        got = evaluation._build_judge_prompt("be right", "hello", "a1", "s",
                                             transcript=self._TR)
        self.assertIn("[CONVERSATION]", got)
        self.assertIn("[turn 0] user: hello", got)
        self.assertIn("agent: hi", got)
        self.assertIn("[turn 1] user: q1", got)
        self.assertNotIn("[CASE INPUT]", got)
        self.assertNotIn("[AGENT OUTPUT]", got)
        # the frame is unchanged: rubric, evidence summary, verdict instruction
        self.assertIn("[RUBRIC]\nbe right", got)
        self.assertIn("[EVIDENCE SUMMARY]\ns", got)
        self.assertIn('{"verdict": "pass" | "fail"', got)
        # the judge is told the unit is the whole conversation
        self.assertIn("conversation as a whole", got)


class TestLlmJudgeTranscript(unittest.TestCase):
    """_run_llm_judge feeds the transcript through to the prompt (and only then)."""

    def _judge_capture(self, traces):
        prompts: list[str] = []

        def chat(base, model, key, prompt, **kw):
            prompts.append(prompt)
            return '{"verdict": "pass", "score": 80, "reason": "ok"}'

        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            ev = SimpleNamespace(id="j1", method="llm_judge", rubric=None)
            env = {"AHL_JUDGE_API_KEY": "k", "AHL_JUDGE_BASE_URL": "http://x",
                   "AHL_JUDGE_MODEL": "m"}
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(llm, "chat", chat):
                out = evaluation._run_llm_judge(ev, "t", Path(tmp), Path(tmp), scores,
                                                traces=traces, cases=[])
        return out, prompts

    def test_multiturn_record_judged_over_conversation(self):
        rec = {"case_id": "c1", "harness_id": "A", "input": "hello",
               "response": "a1", "ok": True, "turns": 2,
               "transcript": [{"turn": 0, "user": "hello", "agent": "hi"},
                              {"turn": 1, "user": "q1", "agent": "a1"}],
               "simulator": "scripted"}
        out, prompts = self._judge_capture({"runtime-a": [rec]})
        self.assertEqual(out.status, "passed")  # scoring math unchanged
        self.assertEqual(len(prompts), 1)
        self.assertIn("[CONVERSATION]", prompts[0])
        self.assertIn("[turn 1] user: q1", prompts[0])
        self.assertNotIn("[CASE INPUT]", prompts[0])

    def test_single_turn_record_keeps_original_prompt(self):
        rec = {"case_id": "c1", "harness_id": "A", "input": "q",
               "response": "an answer", "ok": True}
        out, prompts = self._judge_capture({"runtime-a": [rec]})
        self.assertEqual(out.status, "passed")
        self.assertIn("[CASE INPUT]", prompts[0])
        self.assertNotIn("[CONVERSATION]", prompts[0])


class TestAggregationAndObjective(unittest.TestCase):
    def test_pending_evaluator_makes_track_pending(self):
        with _workspace() as ws:
            ev = (_EV_BENCH.format("pass")
                  + "    - id: j1\n      method: llm_judge\n      rubric: rubrics/q.md\n")
            tr = "    - id: quality\n      evaluators: [e1, j1]\n      evidence: [traces]\n"
            exp = _setup_exp(ws, _eval_section(ev, tr),
                             scripts={"benchmarks/pass.py": _BENCH_PASS,
                                      "rubrics/q.md": "# rubric\n"})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "pending")  # one passed + one pending → pending

    def test_failure_dominates_pending(self):
        with _workspace() as ws:
            ev = (_EV_BENCH.format("fail")
                  + "    - id: j1\n      method: llm_judge\n      rubric: rubrics/q.md\n")
            tr = "    - id: quality\n      evaluators: [e1, j1]\n      evidence: [traces]\n"
            exp = _setup_exp(ws, _eval_section(ev, tr),
                             scripts={"benchmarks/fail.py": _BENCH_FAIL, "rubrics/q.md": "# r\n"})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.tracks[0].status, "failed")  # failed > pending

    def test_objective_primary_track_reflected(self):
        with _workspace() as ws:
            obj = "objective:\n  primary_track: quality\n  optimize_for: maximize\n"
            exp = _setup_exp(ws, _eval_section(_EV_BENCH.format("pass"), _TRACK), obj,
                             scripts={"benchmarks/pass.py": _BENCH_PASS})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertEqual(res.objective_track, "quality")
            self.assertEqual(res.objective_status, "passed")

    def test_no_tracks_is_noop(self):
        with _workspace() as ws:
            ev = "    - id: e1\n      method: benchmark\n      script: benchmarks/pass.py\n"
            # evaluators but no tracks (the default test-experiment shape)
            exp = _setup_exp(ws, "evaluation:\n  root: evaluation/\n  evaluators:\n" + ev,
                             scripts={"benchmarks/pass.py": _BENCH_PASS})
            res = evaluation.run_evaluation(exp, _spec(exp))
            self.assertFalse(res.ran)
            self.assertFalse((exp / "evidence" / "scores" / "tracks").exists())


class TestRunWiring(unittest.TestCase):
    """hlab run (auto) runs evaluation after evidence; hlab status reflects it."""

    def test_run_auto_runs_evaluation_and_status_shows_it(self):
        with _workspace() as ws:
            exp = _setup(ws, connector="local_cli", agent=_ECHO_NO_ARTIFACT,
                         required_artifact=False)
            (exp / "evaluation" / "benchmarks").mkdir(parents=True, exist_ok=True)
            (exp / "evaluation" / "benchmarks" / "pass.py").write_text(_BENCH_PASS, encoding="utf-8")
            yaml = (exp / "experiment.yaml").read_text(encoding="utf-8")
            yaml = yaml.replace(
                "    - id: e1\n      method: benchmark\n",
                "    - id: e1\n      method: benchmark\n      script: benchmarks/pass.py\n"
                "  tracks:\n    - id: quality\n      evaluators: [e1]\n      evidence: [traces]\n")
            yaml += "objective:\n  primary_track: quality\n  optimize_for: maximize\n"
            (exp / "experiment.yaml").write_text(yaml, encoding="utf-8")

            rc, out, _ = _run_cli(["run", "experiments/demo"])
            self.assertEqual(rc, 0)
            agg = json.loads((exp / "evidence" / "scores" / "tracks" / "quality.json")
                             .read_text(encoding="utf-8"))
            self.assertEqual(agg["status"], "passed")
            self.assertIn("objective primary track 'quality': passed", out)

            _, sout, _ = _run_cli(["status", "experiments/demo"])
            self.assertIn("quality=passed", sout)


if __name__ == "__main__":
    unittest.main()
