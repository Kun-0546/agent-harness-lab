"""Tests for experiment.yaml parsing + validation (v1)."""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import scaffold
from agent_harness_lab.experiment_spec import (
    ERROR,
    WARN,
    ExperimentSpecError,
    load_agent_runtime_spec,
    load_cases,
    make_experiment_id,
    parse_experiment_yaml,
    validate_spec,
)


class TestParse(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _write(self, text: str) -> Path:
        p = self.dir / "experiment.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_parse_valid(self):
        p = self._write(
            "id: demo\nstatus: draft\nquestion: q\n"
            "run:\n  mode: copilot\n"
            "execution:\n  mode: ab\n  state_policy: isolated\n"
            "harnesses:\n  - id: A\n    name: a\n    path: harnesses/A/\n"
            "agent_runtimes:\n  - id: r-a\n    harness: A\n    spec: agent-runtimes/r-a.yaml\n"
            "cases:\n  root: cases/\n  files:\n    - cases.jsonl\n"
            "evaluation:\n  root: evaluation/\n  methods:\n    - type: llm_judge\n"
            "collection:\n  traces: true\n"
            "reports:\n  formats:\n    - md\n")
        spec = parse_experiment_yaml(p)
        self.assertEqual(spec.id, "demo")
        self.assertEqual(spec.run_mode, "copilot")
        self.assertEqual(spec.execution_mode, "ab")
        self.assertEqual(spec.state_policy, "isolated")
        self.assertEqual(len(spec.harnesses), 1)
        self.assertEqual(spec.harnesses[0].path, "harnesses/A/")
        self.assertEqual(len(spec.agent_runtimes), 1)
        self.assertEqual(spec.cases_root, "cases/")
        self.assertEqual(spec.cases_files, ["cases.jsonl"])
        self.assertEqual(spec.evaluation_methods, ["llm_judge"])
        self.assertEqual(spec.report_formats, ["md"])

    def test_invalid_yaml_raises(self):
        p = self._write("id: demo\n  : : bad indent :\n- nope\n")
        with self.assertRaises(ExperimentSpecError):
            parse_experiment_yaml(p)

    def test_top_level_non_mapping_raises(self):
        p = self._write("- just\n- a\n- list\n")
        with self.assertRaises(ExperimentSpecError):
            parse_experiment_yaml(p)

    def test_missing_file_raises(self):
        with self.assertRaises(ExperimentSpecError):
            parse_experiment_yaml(self.dir / "nope.yaml")

    def test_empty_agent_runtimes_map_coerced(self):
        # schema shows `agent_runtimes: {}` as an empty placeholder
        p = self._write("id: demo\nagent_runtimes: {}\nharnesses: []\n")
        spec = parse_experiment_yaml(p)
        self.assertEqual(spec.agent_runtimes, [])
        self.assertEqual(spec.harnesses, [])

    def test_evaluators_and_tracks_parse(self):
        p = self._write(
            "id: d\nevaluation:\n  root: evaluation/\n"
            "  evaluators:\n    - id: a\n      method: benchmark\n      script: b/a.py\n"
            "  tracks:\n    - id: t1\n      evaluators: [a]\n      evidence: [traces, raw]\n")
        spec = parse_experiment_yaml(p)
        self.assertEqual(spec.evaluators[0].id, "a")
        self.assertEqual(spec.evaluators[0].method, "benchmark")
        self.assertEqual(spec.tracks[0].id, "t1")
        self.assertEqual(spec.tracks[0].evaluators, ["a"])
        self.assertEqual(spec.tracks[0].evidence, ["traces", "raw"])

    def test_methods_shorthand_still_parses(self):
        p = self._write(
            "id: d\nevaluation:\n  root: evaluation/\n  methods:\n    - type: benchmark\n")
        spec = parse_experiment_yaml(p)
        self.assertIn("benchmark", spec.evaluation_methods)  # backward-compat shorthand


class TestAgentRuntimeSpec(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_nested_connector_type(self):
        p = self.dir / "rt.yaml"
        p.write_text("id: r\nconnector:\n  type: local_cli\n  command: x\n", encoding="utf-8")
        rt = load_agent_runtime_spec(p)
        self.assertEqual(rt.connector_type, "local_cli")

    def test_top_level_type(self):
        p = self.dir / "rt.yaml"
        p.write_text("id: r\ntype: script\ncommand: x\n", encoding="utf-8")
        rt = load_agent_runtime_spec(p)
        self.assertEqual(rt.connector_type, "script")


class TestLoadCases(unittest.TestCase):
    def test_load_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cases.jsonl").write_text(
                '{"id":"c1","input":"a"}\n\n{"id":"c2","input":"b"}\n', encoding="utf-8")
            cases = load_cases(root, ["cases.jsonl"])
            self.assertEqual([c["id"] for c in cases], ["c1", "c2"])

    def test_bad_jsonl_raises(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cases.jsonl").write_text('{"id":"c1"}\n{bad json}\n', encoding="utf-8")
            with self.assertRaises(ExperimentSpecError):
                load_cases(root, ["cases.jsonl"])


class TestValidateScaffolded(unittest.TestCase):
    """A freshly scaffolded experiment must validate with no ERRORs."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scaffold.init_workspace(self.root)
        self.res = scaffold.new_experiment(self.root, "demo-exp")
        self.exp = self.res.experiment_dir

    def _spec(self):
        return parse_experiment_yaml(self.exp / "experiment.yaml")

    def test_fresh_experiment_no_errors(self):
        problems = validate_spec(self._spec(), self.exp)
        errors = [p for p in problems if p.level == ERROR]
        self.assertEqual(errors, [], f"unexpected errors: {[str(p) for p in errors]}")

    def test_missing_harness_path_errors(self):
        import shutil
        shutil.rmtree(self.exp / "harnesses" / "A")
        problems = validate_spec(self._spec(), self.exp)
        codes = {p.code for p in problems if p.level == ERROR}
        self.assertIn("harness_path_missing", codes)

    def test_missing_runtime_spec_errors(self):
        (self.exp / "agent-runtimes" / "runtime-a.yaml").unlink()
        problems = validate_spec(self._spec(), self.exp)
        codes = {p.code for p in problems if p.level == ERROR}
        self.assertIn("runtime_spec_missing", codes)

    def test_missing_cases_file_errors(self):
        (self.exp / "cases" / "cases.jsonl").unlink()
        problems = validate_spec(self._spec(), self.exp)
        codes = {p.code for p in problems if p.level == ERROR}
        self.assertIn("case_file_missing", codes)

    def test_conclusion_missing_warns(self):
        (self.exp / "conclusion.md").unlink()
        problems = validate_spec(self._spec(), self.exp)
        warns = {p.code for p in problems if p.level == WARN}
        self.assertIn("conclusion_missing", warns)


class TestValidateEnums(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp = Path(self._tmp.name)

    def _spec(self, text: str):
        p = self.exp / "experiment.yaml"
        p.write_text(text, encoding="utf-8")
        return parse_experiment_yaml(p)

    def test_bad_run_mode(self):
        spec = self._spec("id: d\nstatus: draft\nquestion: q\nrun:\n  mode: turbo\n")
        codes = {p.code for p in validate_spec(spec, self.exp) if p.level == ERROR}
        self.assertIn("bad_run_mode", codes)

    def test_bad_execution_mode(self):
        spec = self._spec("id: d\nstatus: draft\nquestion: q\nrun:\n  mode: auto\n"
                          "execution:\n  mode: zigzag\n")
        codes = {p.code for p in validate_spec(spec, self.exp) if p.level == ERROR}
        self.assertIn("bad_execution_mode", codes)

    def test_non_kebab_id(self):
        spec = self._spec("id: Demo_Exp\nstatus: draft\nquestion: q\n")
        codes = {p.code for p in validate_spec(spec, self.exp) if p.level == ERROR}
        self.assertIn("bad_id", codes)

    def test_bad_status(self):
        spec = self._spec("id: d\nstatus: wip\nquestion: q\n")
        codes = {p.code for p in validate_spec(spec, self.exp) if p.level == ERROR}
        self.assertIn("bad_status", codes)


class TestValidateAutoConnector(unittest.TestCase):
    """Auto Mode must reject unsupported connector types (schema §18)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scaffold.init_workspace(self.root)
        self.exp = scaffold.new_experiment(self.root, "auto-x", run_mode="auto").experiment_dir

    def test_supported_connector_ok(self):
        # scaffold uses local_cli -> supported under auto
        spec = parse_experiment_yaml(self.exp / "experiment.yaml")
        codes = {p.code for p in validate_spec(spec, self.exp) if p.level == ERROR}
        self.assertNotIn("auto_connector_unsupported", codes)

    def test_unsupported_connector_errors(self):
        (self.exp / "agent-runtimes" / "runtime-a.yaml").write_text(
            "id: runtime-a\nconnector:\n  type: api\n  command: x\n", encoding="utf-8")
        spec = parse_experiment_yaml(self.exp / "experiment.yaml")
        codes = {p.code for p in validate_spec(spec, self.exp) if p.level == ERROR}
        self.assertIn("auto_connector_unsupported", codes)


class TestMakeId(unittest.TestCase):
    def test_kebab(self):
        self.assertEqual(make_experiment_id("Skill Creator AB"), "skill-creator-ab")
        self.assertEqual(make_experiment_id("memory_comparison!!"), "memory-comparison")
        self.assertEqual(make_experiment_id("  --x--  "), "x")


if __name__ == "__main__":
    unittest.main()
