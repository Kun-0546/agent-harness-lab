"""Inspector (Section 2): completeness checks over Auto Run evidence.

Each test seeds a minimal experiment + evidence and calls run_inspection directly,
asserting the expected issue types, severities, dedup, and inspection.json output.
"""
import json
import unittest

from agent_harness_lab import inspector
from agent_harness_lab.experiment_spec import parse_experiment_yaml
from tests.test_auto_v1 import _workspace

_REQUIRED = ("artifacts:\n  collect:\n    - id: out\n      glob: \"produced/**\"\n"
             "      required: true\n")
_ESCAPING = ("artifacts:\n  collect:\n    - id: esc\n      glob: \"../outside/**\"\n"
             "      required: false\n")
_TRACK = "    - id: quality\n      evaluators: [e1]\n      evidence: [traces]\n"
_EVALUATORS = "    - id: e1\n      method: benchmark\n      script: b.py\n"


def _build(ws, *, cases='{"id":"case-001","input":"x"}\n', artifacts="", tracks="", evaluators=""):
    exp = ws / "experiments" / "demo"
    for d in ("cases", "agent-runtimes", "evidence/traces", "evidence/artifacts",
              "evidence/scores/tracks", "rt"):
        (exp / d).mkdir(parents=True, exist_ok=True)
    (exp / "cases" / "cases.jsonl").write_text(cases, encoding="utf-8")
    rt = ("id: runtime-a\nconnector:\n  type: local_cli\n  command: echo hi\n"
          "  working_dir: ./rt\n" + artifacts)
    (exp / "agent-runtimes" / "runtime-a.yaml").write_text(rt, encoding="utf-8")
    eval_block = ""
    if evaluators or tracks:
        eval_block = "evaluation:\n  root: evaluation/\n"
        if evaluators:
            eval_block += "  evaluators:\n" + evaluators
        if tracks:
            eval_block += "  tracks:\n" + tracks
    yaml = ("id: demo\nstatus: draft\nquestion: q\n"
            "run:\n  mode: auto\nexecution:\n  mode: ab\n  state_policy: isolated\n"
            "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
            "agent_runtimes:\n  - id: runtime-a\n    harness: A\n"
            "    spec: agent-runtimes/runtime-a.yaml\n"
            "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n" + eval_block)
    (exp / "experiment.yaml").write_text(yaml, encoding="utf-8")
    return exp


def _trace(exp, *records):
    (exp / "evidence" / "traces").mkdir(parents=True, exist_ok=True)
    (exp / "evidence" / "traces" / "runtime-a.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _spec(exp):
    return parse_experiment_yaml(exp / "experiment.yaml")


def _added_types(res):
    return sorted({i["type"] for i in res.added})


class TestInspectorChecks(unittest.TestCase):
    def test_missing_trace_when_fewer_traces_than_cases(self):
        with _workspace() as ws:
            exp = _build(ws, cases='{"id":"c1"}\n{"id":"c2"}\n')
            _trace(exp, {"case_id": "c1", "runtime_id": "runtime-a", "ok": True})  # 1 of 2
            res = inspector.run_inspection(exp, _spec(exp))
            self.assertIn("missing_trace", _added_types(res))

    def test_runtime_mismatch_for_unknown_runtime(self):
        with _workspace() as ws:
            exp = _build(ws)
            _trace(exp, {"case_id": "case-001", "runtime_id": "ghost", "ok": True})
            res = inspector.run_inspection(exp, _spec(exp))
            self.assertIn("runtime_mismatch", _added_types(res))

    def test_path_drift_for_escaping_glob(self):
        with _workspace() as ws:
            exp = _build(ws, artifacts=_ESCAPING)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            res = inspector.run_inspection(exp, _spec(exp))
            self.assertIn("path_drift", _added_types(res))

    def test_missing_artifact_for_empty_required_dir(self):
        with _workspace() as ws:
            exp = _build(ws, artifacts=_REQUIRED)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            # no evidence/artifacts/runtime-a/case-001/ files → required artifact missing
            res = inspector.run_inspection(exp, _spec(exp))
            self.assertIn("missing_artifact", _added_types(res))
            ma = next(i for i in res.added if i["type"] == "missing_artifact")
            self.assertEqual(ma["severity"], "error")

    def test_missing_artifact_not_flagged_when_present(self):
        with _workspace() as ws:
            exp = _build(ws, artifacts=_REQUIRED)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            art = exp / "evidence" / "artifacts" / "runtime-a" / "case-001" / "produced"
            art.mkdir(parents=True, exist_ok=True)
            (art / "out.txt").write_text("x", encoding="utf-8")
            res = inspector.run_inspection(exp, _spec(exp))
            self.assertNotIn("missing_artifact", _added_types(res))

    def test_missing_score_when_track_has_no_aggregate(self):
        with _workspace() as ws:
            exp = _build(ws, evaluators=_EVALUATORS, tracks=_TRACK)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            res = inspector.run_inspection(exp, _spec(exp))
            self.assertIn("missing_score", _added_types(res))
            ms = next(i for i in res.added if i["type"] == "missing_score")
            self.assertEqual(ms["severity"], "warn")

    def test_pending_track_is_info_not_warn(self):
        with _workspace() as ws:
            exp = _build(ws, evaluators=_EVALUATORS, tracks=_TRACK)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            agg = exp / "evidence" / "scores" / "tracks" / "quality.json"
            agg.write_text(json.dumps({"track_id": "quality", "status": "pending"}),
                           encoding="utf-8")
            res = inspector.run_inspection(exp, _spec(exp))
            ms = next(i for i in res.added if i["type"] == "missing_score")
            self.assertEqual(ms["severity"], "info")


class TestInspectorMergeAndOutput(unittest.TestCase):
    def test_no_duplicate_issues_on_rerun(self):
        with _workspace() as ws:
            exp = _build(ws, evaluators=_EVALUATORS, tracks=_TRACK, artifacts=_REQUIRED)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            first = inspector.run_inspection(exp, _spec(exp))
            self.assertGreater(len(first.added), 0)
            total_after_first = first.issue_total
            second = inspector.run_inspection(exp, _spec(exp))
            self.assertEqual(second.added, [])  # nothing new on rerun
            self.assertEqual(second.issue_total, total_after_first)  # no accumulation
            # issues.jsonl line count matches and ids are sequential
            lines = [json.loads(ln) for ln in (exp / "evidence" / "issues.jsonl")
                     .read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), total_after_first)
            self.assertEqual([r["id"] for r in lines],
                             [f"issue-{n:03d}" for n in range(1, len(lines) + 1)])

    def test_merges_with_autorunner_issues_without_duplicating(self):
        with _workspace() as ws:
            exp = _build(ws, artifacts=_REQUIRED)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            # AutoRunner already wrote a missing_artifact for the same (rt, case)
            (exp / "evidence" / "issues.jsonl").write_text(json.dumps({
                "id": "issue-001", "type": "missing_artifact", "severity": "error",
                "runtime_id": "runtime-a", "case_id": "case-001", "created_by": "AutoRunner"}) + "\n",
                encoding="utf-8")
            res = inspector.run_inspection(exp, _spec(exp))
            ma = [i for i in res.issues if i["type"] == "missing_artifact"]
            self.assertEqual(len(ma), 1)  # not duplicated

    def test_inspection_json_created(self):
        with _workspace() as ws:
            exp = _build(ws, evaluators=_EVALUATORS, tracks=_TRACK)
            _trace(exp, {"case_id": "case-001", "runtime_id": "runtime-a", "ok": True})
            res = inspector.run_inspection(exp, _spec(exp))
            p = exp / "evidence" / "inspections" / "inspection.json"
            self.assertTrue(p.is_file())
            summary = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(summary["created_by"], "Inspector")
            self.assertIn("checks", summary)
            self.assertEqual(summary["issues_total"], res.issue_total)


if __name__ == "__main__":
    unittest.main()
