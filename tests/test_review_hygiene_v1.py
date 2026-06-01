"""Schema hygiene + actionable review messages (no silently-ignored fields)."""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import scaffold
from agent_harness_lab.experiment_spec import ERROR, WARN, parse_experiment_yaml, validate_spec


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scaffold.init_workspace(self.root)
        self.exp = scaffold.new_experiment(self.root, "demo").experiment_dir
        self.yaml = self.exp / "experiment.yaml"

    def _edit(self, old: str, new: str) -> None:
        self.yaml.write_text(self.yaml.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def _problems(self):
        return validate_spec(parse_experiment_yaml(self.yaml), self.exp)

    def _codes(self, level=None):
        return {p.code for p in self._problems() if level is None or p.level == level}


class TestSchemaHygiene(_Base):
    def test_bad_collection_value_errors(self):
        self._edit("  traces: true", "  traces: 3")
        self.assertIn("bad_collection_value", self._codes(ERROR))

    def test_unknown_collection_key_warns(self):
        self._edit("  scores: true", "  scores: true\n  bogus: true")
        self.assertIn("unknown_collection_key", self._codes(WARN))

    def test_unknown_inspection_key_warns(self):
        self._edit("  context_review: false", "  context_review: false\n  weird_review: true")
        self.assertIn("unknown_inspection_key", self._codes(WARN))

    def test_bad_inspection_value_errors(self):
        self._edit("  artifact_review: true", "  artifact_review: 5")
        self.assertIn("bad_inspection_value", self._codes(ERROR))

    def test_goal_ref_missing_warns(self):
        self._edit("goal_ref: ../../goal.md", "goal_ref: ../../nope.md")
        self.assertIn("goal_ref_missing", self._codes(WARN))

    def test_fresh_has_no_errors(self):
        self.assertEqual([p for p in self._problems() if p.level == ERROR], [])


class TestCollectionInspectionCoherence(_Base):
    """collection/inspection VALUES take effect now (review coherence)."""

    def test_fresh_has_no_coherence_warnings(self):
        codes = self._codes(WARN)
        self.assertNotIn("collection_inspection_mismatch", codes)
        self.assertNotIn("issue_check_needs_collection", codes)

    def test_artifact_review_without_artifact_collection_warns(self):
        self._edit("  artifacts: true", "  artifacts: false")
        self.assertIn("collection_inspection_mismatch", self._codes(WARN))

    def test_issue_check_without_its_evidence_warns(self):
        # add a trace-dependent check while disabling trace collection
        self._edit("    - case_failure", "    - case_failure\n    - missing_trace")
        self._edit("  traces: true", "  traces: false")
        self.assertIn("issue_check_needs_collection", self._codes(WARN))

    def test_artifact_review_with_artifacts_key_ABSENT_warns(self):
        # an OFF collection key includes the ABSENT case, not just explicit false:
        # removing the key entirely still means no artifacts are collected.
        self._edit("  artifacts: true\n", "")
        self.assertIn("collection_inspection_mismatch", self._codes(WARN))

    def test_issue_check_with_evidence_key_ABSENT_warns(self):
        self._edit("    - case_failure", "    - case_failure\n    - missing_trace")
        self._edit("  traces: true\n", "")  # remove the key rather than set it false
        self.assertIn("issue_check_needs_collection", self._codes(WARN))


class TestArtifactCollection(_Base):
    """agent-runtime artifacts.collect[] (no source/target public concept)."""

    def _rt(self):
        return self.exp / "agent-runtimes" / "runtime-a.yaml"

    def test_artifact_collect_rule_parses_clean(self):
        # the scaffolded artifacts.collect rule reviews with no ERROR
        self.assertNotIn("bad_artifact_rule", self._codes(ERROR))
        self.assertNotIn("bad_artifact_glob", self._codes(ERROR))

    def test_duplicate_artifact_id_errors(self):
        rt = self._rt()
        rt.write_text(rt.read_text(encoding="utf-8").replace(
            "  collect:\n    - id: generated_skill\n      kind: skill\n"
            "      glob: \"outputs/skill/**\"\n      required: true",
            "  collect:\n    - id: dup\n      glob: a/**\n    - id: dup\n      glob: b/**"),
            encoding="utf-8")
        self.assertIn("duplicate_artifact_id", self._codes(ERROR))

    def test_artifact_missing_glob_errors(self):
        rt = self._rt()
        rt.write_text(rt.read_text(encoding="utf-8").replace(
            "  collect:\n    - id: generated_skill\n      kind: skill\n"
            "      glob: \"outputs/skill/**\"\n      required: true",
            "  collect:\n    - id: a\n      kind: skill"),
            encoding="utf-8")
        self.assertIn("bad_artifact_glob", self._codes(ERROR))

    def test_artifact_source_target_warns(self):
        rt = self._rt()
        rt.write_text(rt.read_text(encoding="utf-8").replace(
            "      glob: \"outputs/skill/**\"\n      required: true",
            "      glob: \"outputs/skill/**\"\n      target: evidence/artifacts/x/"),
            encoding="utf-8")
        self.assertIn("artifact_source_target_ignored", self._codes(WARN))


class TestActionableMessages(_Base):
    def test_harness_path_message_is_actionable(self):
        import shutil
        shutil.rmtree(self.exp / "harnesses" / "A")
        msgs = [p.message for p in self._problems() if p.code == "harness_path_missing"]
        self.assertTrue(msgs)
        m = msgs[0]
        self.assertIn("create", m.lower())
        self.assertIn("experiment.yaml", m)

    def test_runtime_spec_message_is_actionable(self):
        (self.exp / "agent-runtimes" / "runtime-a.yaml").unlink()
        msgs = [p.message for p in self._problems() if p.code == "runtime_spec_missing"]
        self.assertTrue(msgs)
        self.assertIn("create", msgs[0].lower())

    def test_missing_field_message_points_to_yaml(self):
        # blank out `question:` -> actionable message naming experiment.yaml
        self._edit('question: "<one-line question for experiment demo>"', "")
        msgs = [p.message for p in self._problems() if p.code == "missing_question"]
        self.assertTrue(msgs)
        self.assertIn("experiment.yaml", msgs[0])


if __name__ == "__main__":
    unittest.main()
