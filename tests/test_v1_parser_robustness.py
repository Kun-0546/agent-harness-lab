"""Hardening: malformed-input robustness + schema type hygiene (v1)."""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import scaffold
from agent_harness_lab.experiment_spec import (
    ERROR,
    WARN,
    ExperimentSpecError,
    parse_experiment_yaml,
    validate_spec,
)
from agent_harness_lab.reviewer import ERROR as VERDICT_ERROR
from agent_harness_lab.reviewer import review_experiment

_HEAD = """id: demo
status: draft
goal_ref: ../../goal.md
question: q
run:
  mode: copilot
execution:
  mode: ab
  state_policy: isolated
harnesses:
  - id: A
    name: a
    path: harnesses/A/
  - id: B
    name: b
    path: harnesses/B/
agent_runtimes:
  - id: r-a
    harness: A
    spec: agent-runtimes/runtime-a.yaml
  - id: r-b
    harness: B
    spec: agent-runtimes/runtime-b.yaml
cases:
  root: cases/
  files:
    - cases.jsonl
evaluation:
  root: evaluation/
  methods:
    - type: llm_judge
"""
_TAIL = "reports:\n  formats:\n    - md\n"
GOOD_COLL = "collection:\n  traces: true\n  raw: true\n  artifacts: true\n  snapshots: false\n  scores: true"
GOOD_INSP = "inspection:\n  artifact_review: true\n  issue_checks:\n    - missing_artifact"


def _doc(collection=GOOD_COLL, inspection=GOOD_INSP):
    return _HEAD + collection + "\n" + inspection + "\n" + _TAIL


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scaffold.init_workspace(self.root)
        # scaffold provides the referenced dirs/files (harnesses/A,B; runtimes; cases; evaluation)
        self.exp = scaffold.new_experiment(self.root, "demo").experiment_dir
        self.y = self.exp / "experiment.yaml"

    def _write(self, text: str) -> None:
        self.y.write_text(text, encoding="utf-8")

    def _codes(self, level=None):
        return {p.code for p in validate_spec(parse_experiment_yaml(self.y), self.exp)
                if level is None or p.level == level}


class TestMalformedYamlNeverCrashes(_Base):
    def test_deeply_nested_yaml_is_clean_error_not_crash(self):
        nested = "x"
        for _ in range(600):
            nested = "{a: " + nested + "}"
        self._write("id: x\nstatus: draft\nquestion: q\njunk: " + nested + "\n")
        with self.assertRaises(ExperimentSpecError):
            parse_experiment_yaml(self.y)
        # review must yield a verdict, never an uncaught traceback
        self.assertEqual(review_experiment(self.exp).verdict, VERDICT_ERROR)

    def test_duplicate_keys_rejected(self):
        self._write("id: x\nstatus: draft\nstatus: ready\nquestion: q\n")
        with self.assertRaises(ExperimentSpecError):
            parse_experiment_yaml(self.y)


class TestListTypeGuards(_Base):
    def test_scalar_methods_single_error_no_char_flood(self):
        self._write(_doc().replace("  methods:\n    - type: llm_judge", "  methods: llm_judge"))
        codes = self._codes(ERROR)
        self.assertIn("bad_list_type", codes)
        self.assertNotIn("bad_evaluation_method", codes)

    def test_scalar_formats_single_error(self):
        self._write(_doc().replace("  formats:\n    - md", "  formats: md"))
        codes = self._codes(ERROR)
        self.assertIn("bad_list_type", codes)
        self.assertNotIn("bad_report_format", codes)

    def test_scalar_issue_checks_error(self):
        self._write(_doc(inspection="inspection:\n  issue_checks: missing_artifact"))
        self.assertIn("bad_issue_checks_type", self._codes(ERROR))


class TestTypeHygiene(_Base):
    def test_numeric_id_rejected(self):
        self._write(_doc().replace("id: demo", "id: 12345"))
        self.assertIn("bad_id", self._codes(ERROR))

    def test_unknown_toplevel_key_warns(self):
        self._write(_doc() + "totally_bogus_key: 1\n")
        self.assertIn("unknown_toplevel_key", self._codes(WARN))

    def test_inspection_as_list_errors(self):
        self._write(_doc(inspection="inspection:\n  - artifact_review"))
        self.assertIn("bad_inspection_type", self._codes(ERROR))

    def test_collection_as_list_errors(self):
        self._write(_doc(collection="collection:\n  - traces\n  - raw"))
        self.assertIn("bad_collection_type", self._codes(ERROR))

    def test_harness_missing_name_errors(self):
        self._write(_doc().replace("    name: a\n", ""))
        self.assertIn("bad_harness", self._codes(ERROR))

    def test_runtime_missing_harness_errors(self):
        self._write(_doc().replace("    harness: A\n", ""))
        self.assertIn("bad_agent_runtime", self._codes(ERROR))


class TestEmptyOutputNeedsRaw(_Base):
    def test_empty_output_check_needs_raw_collection(self):
        coll = "collection:\n  traces: true\n  raw: false\n  artifacts: true\n  scores: true"
        insp = "inspection:\n  issue_checks:\n    - empty_output"
        self._write(_doc(collection=coll, inspection=insp))
        self.assertIn("issue_check_needs_collection", self._codes(WARN))

    def test_empty_output_not_tied_to_artifacts(self):
        # artifacts off, raw on, only empty_output declared -> NO coherence warn
        coll = "collection:\n  traces: true\n  raw: true\n  artifacts: false\n  scores: true"
        insp = "inspection:\n  issue_checks:\n    - empty_output"
        self._write(_doc(collection=coll, inspection=insp))
        self.assertNotIn("issue_check_needs_collection", self._codes(WARN))


class TestEncoding(_Base):
    def test_non_utf8_is_clean_error_not_crash(self):
        self.y.write_bytes("id: café\nstatus: draft\nquestion: q\n".encode("latin-1"))
        with self.assertRaises(ExperimentSpecError):
            parse_experiment_yaml(self.y)
        self.assertEqual(review_experiment(self.exp).verdict, VERDICT_ERROR)


class TestListEntryValidation(_Base):
    _HARNESS_BLOCK = ("harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
                      "  - id: B\n    name: b\n    path: harnesses/B/")

    def test_bad_harness_entry_reported_not_dropped(self):
        self._write(_doc().replace("  - id: B\n    name: b\n    path: harnesses/B/", "  - just-a-string"))
        self.assertIn("bad_harness_entry", self._codes(ERROR))

    def test_bad_runtime_entry_reported(self):
        self._write(_doc().replace(
            "  - id: r-b\n    harness: B\n    spec: agent-runtimes/runtime-b.yaml", "  - 12345"))
        self.assertIn("bad_agent_runtime_entry", self._codes(ERROR))

    def test_scalar_harnesses_is_bad_list_type_not_missing(self):
        self._write(_doc().replace(self._HARNESS_BLOCK, "harnesses: somestring"))
        codes = self._codes(ERROR)
        self.assertIn("bad_list_type", codes)
        self.assertNotIn("missing_harnesses", codes)


class TestMergeKeys(_Base):
    def test_yaml_merge_key_resolves(self):
        doc = "defaults: &d\n  mode: auto\n" + _doc().replace("run:\n  mode: copilot", "run:\n  <<: *d")
        self._write(doc)
        spec = parse_experiment_yaml(self.y)
        self.assertEqual(spec.run_mode, "auto")  # << merge resolved


class TestPathTypes(_Base):
    def test_evaluation_root_as_file_errors(self):
        import shutil
        shutil.rmtree(self.exp / "evaluation")
        (self.exp / "evaluation").write_text("not a dir", encoding="utf-8")
        self.assertIn("evaluation_root_not_dir", self._codes(ERROR))

    def test_cases_root_as_file_errors(self):
        import shutil
        shutil.rmtree(self.exp / "cases")
        (self.exp / "cases").write_text("not a dir", encoding="utf-8")
        self.assertIn("cases_root_not_dir", self._codes(ERROR))

    def test_runtime_spec_as_dir_errors(self):
        (self.exp / "agent-runtimes" / "runtime-a.yaml").unlink()
        (self.exp / "agent-runtimes" / "runtime-a.yaml").mkdir()
        self.assertIn("runtime_spec_not_file", self._codes(ERROR))

    def test_goal_ref_to_dir_warns(self):
        self._write(_doc().replace("goal_ref: ../../goal.md", "goal_ref: harnesses"))
        self.assertIn("goal_ref_not_file", self._codes(WARN))


class TestTypeGuardsNoCrash(_Base):
    def test_unhashable_key_clean_error(self):
        self.y.write_text("? [a, b]\n: v\nid: x\nstatus: draft\nquestion: q\n", encoding="utf-8")
        with self.assertRaises(ExperimentSpecError):
            parse_experiment_yaml(self.y)
        self.assertEqual(review_experiment(self.exp).verdict, VERDICT_ERROR)

    def test_nonstr_harness_path_no_crash(self):
        self._write(_doc().replace("    path: harnesses/A/", "    path: 12345"))
        self.assertIn("bad_harness", self._codes(ERROR))  # must not raise

    def test_nonstr_runtime_spec_no_crash(self):
        self._write(_doc().replace("    spec: agent-runtimes/runtime-a.yaml", "    spec: 12345"))
        self.assertIn("bad_agent_runtime", self._codes(ERROR))

    def test_nonstr_cases_root_no_crash(self):
        self._write(_doc().replace("  root: cases/", "  root: 999"))
        self.assertIn("bad_cases_root", self._codes(ERROR))

    def test_nonstr_eval_root_no_crash(self):
        self._write(_doc().replace("  root: evaluation/", "  root: 999"))
        self.assertIn("bad_evaluation_root", self._codes(ERROR))

    def test_cli_review_nonstr_path_exits_1_not_crash(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from agent_harness_lab import cli
        self._write(_doc().replace("    path: harnesses/A/", "    path: 12345"))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(["review", str(self.exp)])
        self.assertEqual(rc, 1)


class TestMappingAndScalarTypes(_Base):
    def test_nonempty_mapping_harnesses_is_bad_list_type(self):
        self._write(_doc().replace(TestListEntryValidation._HARNESS_BLOCK,
                                   "harnesses:\n  A: harness-a"))
        self.assertIn("bad_list_type", self._codes(ERROR))

    def test_run_as_scalar_is_bad_run_type(self):
        self._write(_doc().replace("run:\n  mode: copilot", "run: copilot"))
        codes = self._codes(ERROR)
        self.assertIn("bad_run_type", codes)
        self.assertNotIn("missing_run_mode", codes)

    def test_execution_as_scalar_is_bad_execution_type(self):
        self._write(_doc().replace("execution:\n  mode: ab\n  state_policy: isolated", "execution: ab"))
        self.assertIn("bad_execution_type", self._codes(ERROR))

    def test_null_case_file_entry_errors(self):
        self._write(_doc().replace("    - cases.jsonl", "    - cases.jsonl\n    - null"))
        self.assertIn("bad_case_file", self._codes(ERROR))

    def test_html_only_warns_md_missing(self):
        self._write(_doc().replace("  formats:\n    - md", "  formats:\n    - html"))
        codes = {p.code for p in validate_spec(parse_experiment_yaml(self.y), self.exp)}
        self.assertIn("report_md_missing", codes)


class TestUnhashableItems(_Base):
    def test_unhashable_issue_check_clean_error(self):
        self._write(_doc(inspection="inspection:\n  issue_checks:\n    - {a: b}"))
        self.assertIn("bad_issue_check", self._codes(ERROR))  # must not raise TypeError

    def test_unhashable_method_type_clean_error(self):
        self._write(_doc().replace("    - type: llm_judge", "    - type: [a, b]"))
        self.assertIn("bad_evaluation_method_entry", self._codes(ERROR))  # must not raise

    def test_bare_list_method_flagged_not_dropped(self):
        self._write(_doc().replace("  methods:\n    - type: llm_judge", "  methods:\n    - [a, b]"))
        self.assertIn("bad_evaluation_method_entry", self._codes(ERROR))


class TestInspectionFalsy(_Base):
    def test_inspection_false_errors(self):
        self._write(_doc(inspection="inspection: false"))
        self.assertIn("bad_inspection_type", self._codes(ERROR))

    def test_inspection_empty_list_errors(self):
        self._write(_doc(inspection="inspection: []"))
        self.assertIn("bad_inspection_type", self._codes(ERROR))

    def test_inspection_null_is_ok(self):
        self._write(_doc(inspection="inspection: null"))
        self.assertNotIn("bad_inspection_type", self._codes(ERROR))


class TestHumanReviewRoot(_Base):
    def test_human_review_honors_custom_eval_root(self):
        import shutil
        shutil.move(str(self.exp / "evaluation"), str(self.exp / "custom-eval"))
        doc = _doc().replace("  root: evaluation/\n  methods:\n    - type: llm_judge",
                             "  root: custom-eval/\n  methods:\n    - type: human_annotation")
        self._write(doc)
        codes = {p.code for p in validate_spec(parse_experiment_yaml(self.y), self.exp)}
        self.assertNotIn("human_review_undocumented", codes)


class TestSectionShapeAndUnknownKeys(_Base):
    def test_cases_as_scalar_is_bad_cases_type(self):
        self._write(_doc().replace("cases:\n  root: cases/\n  files:\n    - cases.jsonl", "cases: cases/"))
        codes = self._codes(ERROR)
        self.assertIn("bad_cases_type", codes)
        self.assertNotIn("missing_cases_root", codes)

    def test_evaluation_as_scalar_is_bad_evaluation_type(self):
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge", "evaluation: evaluation/"))
        self.assertIn("bad_evaluation_type", self._codes(ERROR))

    def test_reports_as_scalar_is_bad_reports_type(self):
        self._write(_doc().replace("reports:\n  formats:\n    - md", "reports: md"))
        self.assertIn("bad_reports_type", self._codes(ERROR))

    def test_unknown_nested_key_warns(self):
        self._write(_doc().replace("run:\n  mode: copilot", "run:\n  mode: copilot\n  bogus: 1"))
        self.assertIn("unknown_key", self._codes(WARN))

    def test_unknown_harness_entry_key_warns(self):
        self._write(_doc().replace("    path: harnesses/A/", "    path: harnesses/A/\n    bogus: 1"))
        self.assertIn("unknown_key", self._codes(WARN))


class TestIdNewline(_Base):
    def test_id_block_scalar_trailing_newline_rejected(self):
        self._write(_doc().replace("id: demo", "id: |\n  baseline"))
        self.assertIn("bad_id", self._codes(ERROR))


class TestEmptyRuntimeSpec(_Base):
    def test_empty_runtime_spec_warns_in_copilot(self):
        (self.exp / "agent-runtimes" / "runtime-a.yaml").write_text("", encoding="utf-8")
        self.assertIn("runtime_no_connector", self._codes(WARN))


class TestEnumNonHashableNoCrash(_Base):
    def test_list_run_mode_clean_error(self):
        self._write(_doc().replace("run:\n  mode: copilot", "run:\n  mode: [copilot]"))
        self.assertIn("bad_run_mode", self._codes(ERROR))  # must not raise TypeError

    def test_list_execution_mode_clean_error(self):
        self._write(_doc().replace("execution:\n  mode: ab\n  state_policy: isolated",
                                   "execution:\n  mode: [ab]\n  state_policy: isolated"))
        self.assertIn("bad_execution_mode", self._codes(ERROR))

    def test_list_state_policy_clean_error(self):
        self._write(_doc().replace("  state_policy: isolated", "  state_policy: [isolated]"))
        self.assertIn("bad_state_policy", self._codes(ERROR))

    def test_list_connector_type_clean_error(self):
        (self.exp / "agent-runtimes" / "runtime-a.yaml").write_text(
            "id: runtime-a\nconnector:\n  type: [local_cli]\n", encoding="utf-8")
        self.assertIn("bad_connector_type", self._codes(ERROR))


class TestCollectionFalsy(_Base):
    def test_collection_false_is_bad_type(self):
        self._write(_doc(collection="collection: false"))
        self.assertIn("bad_collection_type", self._codes(ERROR))

    def test_collection_empty_list_is_bad_type(self):
        self._write(_doc(collection="collection: []"))
        self.assertIn("bad_collection_type", self._codes(ERROR))


class TestTracksMalformed(_Base):
    def test_non_mapping_track_flagged(self):
        # a track that is not a mapping (e.g. a bare string) is flagged, not dropped
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge",
            "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: a\n      method: benchmark\n"
            "  tracks:\n    - just-a-string"))
        self.assertIn("bad_evaluation_track_entry", self._codes(ERROR))

    def test_track_unknown_evaluator_errors(self):
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge",
            "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: a\n      method: benchmark\n"
            "  tracks:\n    - id: t1\n      evaluators: [nope]\n      evidence: [traces]"))
        self.assertIn("track_unknown_evaluator", self._codes(ERROR))

    def test_track_unknown_evidence_errors(self):
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge",
            "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: a\n      method: benchmark\n"
            "  tracks:\n    - id: t1\n      evaluators: [a]\n      evidence: [bogus]"))
        self.assertIn("bad_track_evidence", self._codes(ERROR))

    def test_duplicate_evaluator_id_errors(self):
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge",
            "evaluation:\n  root: evaluation/\n  evaluators:\n"
            "    - id: a\n      method: benchmark\n    - id: a\n      method: llm_judge"))
        self.assertIn("duplicate_evaluator_id", self._codes(ERROR))

    def test_unknown_evaluator_method_errors(self):
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge",
            "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: a\n      method: bogus"))
        self.assertIn("bad_evaluator_method", self._codes(ERROR))

    def test_no_evaluators_errors(self):
        # neither evaluators nor methods shorthand -> ERROR
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge",
            "evaluation:\n  root: evaluation/"))
        self.assertIn("no_evaluators", self._codes(ERROR))


class TestDuplicateIds(_Base):
    def test_duplicate_harness_id(self):
        self._write(_doc().replace("  - id: B\n    name: b\n    path: harnesses/B/",
                                   "  - id: A\n    name: b\n    path: harnesses/B/"))
        self.assertIn("duplicate_harness_id", self._codes(ERROR))

    def test_duplicate_runtime_id(self):
        self._write(_doc().replace("  - id: r-b\n    harness: B\n    spec: agent-runtimes/runtime-b.yaml",
                                   "  - id: r-a\n    harness: B\n    spec: agent-runtimes/runtime-b.yaml"))
        self.assertIn("duplicate_runtime_id", self._codes(ERROR))


class TestNonStrIdsAndNames(_Base):
    def test_int_harness_id_errors(self):
        self._write(_doc().replace("  - id: A\n    name: a", "  - id: 1\n    name: a"))
        self.assertIn("bad_harness", self._codes(ERROR))  # not silent PASS

    def test_duplicate_int_harness_ids_not_silent(self):
        doc = _doc().replace("  - id: A\n    name: a", "  - id: 1\n    name: a")
        doc = doc.replace("  - id: B\n    name: b", "  - id: 1\n    name: b")
        self._write(doc)
        self.assertIn("bad_harness", self._codes(ERROR))

    def test_int_harness_name_errors(self):
        self._write(_doc().replace("    name: a\n    path: harnesses/A/",
                                   "    name: 999\n    path: harnesses/A/"))
        self.assertIn("bad_harness", self._codes(ERROR))

    def test_int_runtime_id_errors(self):
        self._write(_doc().replace("  - id: r-a\n    harness: A", "  - id: 1\n    harness: A"))
        self.assertIn("bad_agent_runtime", self._codes(ERROR))

    def test_nonstr_runtime_harness_ref_errors(self):
        self._write(_doc().replace("    harness: A\n    spec: agent-runtimes/runtime-a.yaml",
                                   "    harness: 1\n    spec: agent-runtimes/runtime-a.yaml"))
        self.assertIn("bad_agent_runtime", self._codes(ERROR))


class TestTrackRefAndAutoState(_Base):
    def test_evaluator_missing_rubric_warns(self):
        # an evaluator whose rubric (relative to evaluation.root) is missing -> WARN
        ev = ("evaluation:\n  root: evaluation/\n  evaluators:\n"
              "    - id: q\n      method: llm_judge\n      rubric: rubrics/nope.md")
        self._write(_doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge", ev))
        self.assertIn("evaluator_ref_missing", self._codes(WARN))

    def test_auto_invalid_state_policy_no_unimplemented_warn(self):
        doc = _doc().replace("run:\n  mode: copilot", "run:\n  mode: auto")
        doc = doc.replace("  state_policy: isolated", "  state_policy: bogus")
        self._write(doc)
        codes = {p.code for p in validate_spec(parse_experiment_yaml(self.y), self.exp)}
        self.assertIn("bad_state_policy", codes)
        self.assertNotIn("auto_state_policy_unimplemented", codes)


class TestConnectorBoundary(_Base):
    """D: Copilot+manual allowed; Auto+manual/remote_devbox/api/bridge unsupported."""

    def _set_connectors(self, ctype):
        for rt in ("runtime-a", "runtime-b"):
            (self.exp / "agent-runtimes" / f"{rt}.yaml").write_text(
                f"id: {rt}\nconnector:\n  type: {ctype}\n  command: x\n", encoding="utf-8")

    def _auto(self):
        self._write(_doc().replace("  mode: copilot", "  mode: auto"))

    def test_copilot_manual_allowed(self):
        self._set_connectors("manual")  # scaffolded copilot runtimes are manual
        codes = self._codes(ERROR)
        self.assertNotIn("auto_connector_unsupported", codes)
        self.assertNotIn("bad_connector_type", codes)

    def test_auto_manual_errors(self):
        self._set_connectors("manual")
        self._auto()
        self.assertIn("auto_connector_unsupported", self._codes(ERROR))

    def test_auto_local_cli_ok(self):
        self._set_connectors("local_cli")
        self._auto()
        self.assertNotIn("auto_connector_unsupported", self._codes(ERROR))

    def test_auto_script_ok(self):
        self._set_connectors("script")
        self._auto()
        self.assertNotIn("auto_connector_unsupported", self._codes(ERROR))

    def test_auto_remote_devbox_unsupported(self):
        self._set_connectors("remote_devbox")
        self._auto()
        self.assertIn("auto_connector_unsupported", self._codes(ERROR))

    def test_unknown_connector_type_errors(self):
        self._set_connectors("telepathy")
        self.assertIn("bad_connector_type", self._codes(ERROR))


class TestStatePolicySemantics(_Base):
    """E: every StatePolicy value has explicit review semantics (none is inert)."""

    def _auto_with(self, state_policy, execution="ab"):
        for rt in ("runtime-a", "runtime-b"):
            (self.exp / "agent-runtimes" / f"{rt}.yaml").write_text(
                f"id: {rt}\nconnector:\n  type: local_cli\n  command: x\n", encoding="utf-8")
        doc = _doc().replace("  mode: copilot", "  mode: auto")
        doc = doc.replace("  mode: ab\n  state_policy: isolated",
                          f"  mode: {execution}\n  state_policy: {state_policy}")
        self._write(doc)

    def test_isolated_fully_supported_no_state_warn(self):
        self._auto_with("isolated")
        w = self._codes(WARN)
        self.assertNotIn("auto_state_policy_unimplemented", w)
        self.assertNotIn("state_policy_reset_pending", w)

    def test_reset_warns_pending(self):
        self._auto_with("reset")
        self.assertIn("state_policy_reset_pending", self._codes(WARN))

    def test_cumulative_warns_unimplemented(self):
        self._auto_with("cumulative")
        self.assertIn("auto_state_policy_unimplemented", self._codes(WARN))

    def test_snapshot_branch_warns_snapshots_and_unimplemented(self):
        self._auto_with("snapshot_branch")
        w = self._codes(WARN)
        self.assertIn("auto_state_policy_unimplemented", w)
        self.assertIn("snapshots_not_collected", w)

    def test_replay_warns_no_evidence(self):
        self._auto_with("replay", execution="replay")
        self.assertIn("replay_no_evidence", self._codes(WARN))


class TestSimulator(_Base):
    """F: simulator type validation + required fields + role_play boundary."""

    def _with_sim(self, block):
        self._write(_doc() + block)

    def test_single_turn_ok(self):
        self._with_sim("simulator:\n  type: single_turn\n")
        self.assertNotIn("bad_simulator_type", self._codes(ERROR))

    def test_unknown_type_errors(self):
        self._with_sim("simulator:\n  type: bogus\n")
        self.assertIn("bad_simulator_type", self._codes(ERROR))

    def test_non_mapping_simulator_errors(self):
        self._with_sim("simulator: just-a-string\n")
        self.assertIn("bad_simulator_type", self._codes(ERROR))

    def test_script_requires_script(self):
        self._with_sim("simulator:\n  type: script\n")
        self.assertIn("simulator_script_missing", self._codes(ERROR))

    def test_role_play_requires_fields(self):
        self._with_sim("simulator:\n  type: role_play\n  max_turns: 3\n")
        self.assertIn("simulator_field_missing", self._codes(ERROR))

    def test_role_play_under_auto_warns_unimplemented(self):
        doc = _doc().replace("  mode: copilot", "  mode: auto") + (
            "simulator:\n  type: role_play\n  actor: ceo\n  max_turns: 6\n  policy: cases/sim.md\n")
        self._write(doc)
        self.assertIn("simulator_roleplay_unimplemented", self._codes(WARN))


class TestAutoOptimizeSchema(_Base):
    """Auto Optimize objective/optimization schema + review boundary (loop NOT built)."""

    _STOP = "  stop_conditions:\n    - max_rounds: 3\n"

    def _with(self, extra):
        self._write(_doc() + extra)

    def test_optimization_parses(self):
        self._with("optimization:\n  enabled: false\n  editable_surface:\n    - harnesses/B/\n")
        spec = parse_experiment_yaml(self.y)
        self.assertIsNotNone(spec.optimization)
        self.assertFalse(spec.optimization.enabled)
        self.assertEqual(spec.optimization.editable_surface, ["harnesses/B/"])

    def test_editable_surface_protected_errors(self):
        self._with("optimization:\n  enabled: true\n  editable_surface:\n    - cases/\n" + self._STOP)
        self.assertIn("editable_surface_protected", self._codes(ERROR))

    def test_editable_surface_must_be_harness(self):
        self._with("optimization:\n  enabled: true\n  editable_surface:\n    - src/foo.py\n" + self._STOP)
        self.assertIn("editable_surface_not_harness", self._codes(ERROR))

    def test_enabled_requires_stop_conditions(self):
        self._with("optimization:\n  enabled: true\n  editable_surface:\n    - harnesses/B/\n")
        self.assertIn("missing_stop_conditions", self._codes(ERROR))

    def test_enabled_warns_loop_unimplemented(self):
        self._with("optimization:\n  enabled: true\n  editable_surface:\n    - harnesses/B/\n" + self._STOP)
        w = self._codes(WARN)
        self.assertIn("optimization_loop_unimplemented", w)
        self.assertNotIn("missing_stop_conditions", self._codes(ERROR))

    def test_promotion_policy_unknown_ref_errors(self):
        self._with("optimization:\n  enabled: true\n  editable_surface:\n    - harnesses/B/\n" + self._STOP
                   + "  promotion_policy:\n    promote_if_track: no-such-track\n")
        self.assertIn("promotion_policy_unknown_ref", self._codes(ERROR))

    def test_promotion_policy_known_issue_type_ok(self):
        self._with("optimization:\n  enabled: true\n  editable_surface:\n    - harnesses/B/\n" + self._STOP
                   + "  promotion_policy:\n    reject_if_issue: case_failure\n")
        self.assertNotIn("promotion_policy_unknown_ref", self._codes(ERROR))

    def test_objective_unknown_track_errors(self):
        self._with("objective:\n  primary_track: no-such-track\n  optimize_for: maximize\n")
        self.assertIn("objective_unknown_track", self._codes(ERROR))

    def test_objective_known_track_ok(self):
        doc = _doc().replace(
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge",
            "evaluation:\n  root: evaluation/\n  evaluators:\n    - id: a\n      method: benchmark\n"
            "  tracks:\n    - id: t1\n      evaluators: [a]\n      evidence: [traces]")
        self._write(doc + "objective:\n  primary_track: t1\n  optimize_for: maximize\n")
        self.assertNotIn("objective_unknown_track", self._codes(ERROR))

    def test_non_mapping_optimization_errors(self):
        self._with("optimization: nope\n")
        self.assertIn("bad_optimization_type", self._codes(ERROR))


if __name__ == "__main__":
    unittest.main()
