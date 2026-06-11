"""ReportBuilder (Section 3): hlab report → reports/report.md.

Verifies the report includes issues, evaluation tracks, objective, and Auto Optimize
state; honestly marks pending llm/human evaluation and an unrun optimize loop; and
never fabricates a conclusion. Exit 0 when generated.
"""
import json
import unittest

from agent_harness_lab import report_builder
from agent_harness_lab.experiment_spec import parse_experiment_yaml
from tests.test_auto_v1 import _workspace

_EVAL = ("evaluation:\n  root: evaluation/\n  evaluators:\n"
         "    - id: e1\n      method: llm_judge\n      rubric: r.md\n"
         "  tracks:\n    - id: quality\n      evaluators: [e1]\n      evidence: [traces]\n")
_OBJECTIVE = "objective:\n  primary_track: quality\n  optimize_for: maximize\n"
_OPTIMIZE_ON = "optimization:\n  enabled: true\n  editable_surface:\n    - harnesses\n"
_HTML = "reports:\n  formats:\n    - md\n    - html\n"


def _exp(ws, extra=""):
    exp = ws / "experiments" / "demo"
    (exp / "evidence" / "scores" / "tracks").mkdir(parents=True, exist_ok=True)
    yaml = ("id: demo\nstatus: draft\nquestion: does it work?\n"
            "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
            "harnesses:\n  - id: A\n    name: alpha\n    path: harnesses/A/\n"
            "agent_runtimes:\n  - id: runtime-a\n    harness: A\n"
            "    spec: agent-runtimes/runtime-a.yaml\n"
            "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n" + extra)
    (exp / "experiment.yaml").write_text(yaml, encoding="utf-8")
    return exp


def _spec(exp):
    return parse_experiment_yaml(exp / "experiment.yaml")


def _seed_issues(exp, *issues):
    (exp / "evidence").mkdir(parents=True, exist_ok=True)
    (exp / "evidence" / "issues.jsonl").write_text(
        "".join(json.dumps(i) + "\n" for i in issues), encoding="utf-8")


def _seed_track(exp, track_id, status, evaluators=None):
    d = exp / "evidence" / "scores" / "tracks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{track_id}.json").write_text(json.dumps(
        {"track_id": track_id, "question": "q", "status": status,
         "evaluators": evaluators or []}), encoding="utf-8")


class TestReportBuilder(unittest.TestCase):
    def test_report_md_generated(self):
        with _workspace() as ws:
            exp = _exp(ws)
            p = report_builder.build_report(exp, _spec(exp))
            self.assertTrue(p.is_file())
            text = p.read_text(encoding="utf-8")
            self.assertIn("# Experiment Report: demo", text)
            self.assertIn("## Known limitations", text)

    def test_report_includes_issues(self):
        with _workspace() as ws:
            exp = _exp(ws)
            _seed_issues(exp, {"type": "missing_artifact", "severity": "error",
                               "message": "no files", "runtime_id": "runtime-a",
                               "case_id": "c1"})
            text = report_builder.build_report(exp, _spec(exp)).read_text(encoding="utf-8")
            self.assertIn("## Issues", text)
            self.assertIn("missing_artifact", text)
            self.assertIn("Total:** 1", text)

    def test_report_includes_evaluation_tracks(self):
        with _workspace() as ws:
            exp = _exp(ws, _EVAL)
            _seed_track(exp, "quality", "passed",
                        [{"evaluator_id": "e1", "method": "benchmark", "status": "passed", "score": 1.0}])
            text = report_builder.build_report(exp, _spec(exp)).read_text(encoding="utf-8")
            self.assertIn("## Evaluation", text)
            self.assertIn("**quality**: passed", text)
            self.assertIn("`e1`", text)

    def test_report_marks_pending_llm_human_honestly(self):
        with _workspace() as ws:
            exp = _exp(ws, _EVAL)
            _seed_track(exp, "quality", "pending",
                        [{"evaluator_id": "e1", "method": "llm_judge", "status": "pending"}])
            text = report_builder.build_report(exp, _spec(exp)).read_text(encoding="utf-8")
            self.assertIn("pending", text)
            self.assertIn("AHL_JUDGE", text)  # honest: pending unless a judge key is set

    def test_report_objective_summary(self):
        with _workspace() as ws:
            exp = _exp(ws, _EVAL + _OBJECTIVE)
            _seed_track(exp, "quality", "passed")
            text = report_builder.build_report(exp, _spec(exp)).read_text(encoding="utf-8")
            self.assertIn("## Objective", text)
            self.assertIn("`quality`", text)
            self.assertIn("passed", text)

    def test_report_optimization_enabled_but_not_run(self):
        with _workspace() as ws:
            exp = _exp(ws, _EVAL + _OBJECTIVE + _OPTIMIZE_ON)
            text = report_builder.build_report(exp, _spec(exp)).read_text(encoding="utf-8")
            self.assertIn("## Auto Optimize", text)
            self.assertIn("not run", text)  # enabled but no history

    def test_report_does_not_fabricate_conclusion(self):
        with _workspace() as ws:
            exp = _exp(ws)
            report_builder.build_report(exp, _spec(exp))
            self.assertFalse((exp / "conclusion.md").exists())  # never auto-written

    def test_report_html_when_requested(self):
        with _workspace() as ws:
            exp = _exp(ws, _HTML)
            report_builder.build_report(exp, _spec(exp))
            self.assertTrue((exp / "reports" / "report.html").is_file())

    def test_report_methodology_section(self):
        # R7: Methodology lists each track's evaluators+methods, the status
        # meanings (pending/error), and the score semantics per method.
        with _workspace() as ws:
            exp = _exp(ws, _EVAL)
            text = report_builder.build_report(exp, _spec(exp)).read_text(encoding="utf-8")
            self.assertIn("## Methodology", text)
            self.assertIn("Track `quality` — evaluators: `e1` (llm_judge)", text)
            self.assertIn("Status meanings", text)
            self.assertIn("`pending`", text)
            self.assertIn("`error`", text)
            self.assertIn("stdout", text)      # benchmark score source (stdout JSON)
            self.assertIn("0-100", text)       # llm_judge score scale
            self.assertIn("human_annotation", text)

    def test_report_methodology_without_tracks_is_honest(self):
        with _workspace() as ws:
            exp = _exp(ws)
            text = report_builder.build_report(exp, _spec(exp)).read_text(encoding="utf-8")
            self.assertIn("## Methodology", text)
            self.assertIn("No evaluation tracks configured", text)


if __name__ == "__main__":
    unittest.main()
