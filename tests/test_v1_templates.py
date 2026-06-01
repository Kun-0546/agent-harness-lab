"""Hardened v1 templates guide the user (not bare placeholders)."""
import tempfile
import unittest
from pathlib import Path

from agent_harness_lab import scaffold
from agent_harness_lab.experiment_spec import load_agent_runtime_spec


class TestTemplates(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scaffold.init_workspace(self.root)
        self.exp = scaffold.new_experiment(self.root, "demo").experiment_dir

    def test_conclusion_sections(self):
        t = (self.exp / "conclusion.md").read_text(encoding="utf-8")
        for h in ("## Human conclusion", "## Rationale", "## Evidence relied on",
                  "## Evidence not trusted", "## Next step"):
            self.assertIn(h, t)
        self.assertNotIn("## Decision", t)

    def test_harness_readme_prompts(self):
        t = (self.exp / "harnesses" / "A" / "README.md").read_text(encoding="utf-8")
        for h in ("What this harness changes",
                  "Source / config / prompt / skill location",
                  "How it is applied to the Agent Runtime",
                  "Expected artifacts",
                  "Known risks"):
            self.assertIn(h, t)

    def test_agent_runtime_comments_and_parses(self):
        path = self.exp / "agent-runtimes" / "runtime-a.yaml"
        t = path.read_text(encoding="utf-8")
        self.assertIn("relative to the experiment dir", t)
        self.assertIn("stdin_json", t)
        self.assertIn("timeout:", t)
        # artifact collection declares id/kind/glob/required — never source/target
        self.assertIn("artifacts:", t)
        self.assertIn("collect:", t)
        self.assertIn("glob:", t)
        self.assertNotIn("source:", t)
        self.assertNotIn("target:", t)
        rt = load_agent_runtime_spec(path)  # must still be valid YAML
        self.assertEqual(rt.connector_type, "manual")          # copilot default
        self.assertEqual(rt.artifacts[0]["id"], "generated_skill")

    def test_auto_scaffold_uses_local_cli(self):
        exp = scaffold.new_experiment(self.root, "autodemo", run_mode="auto").experiment_dir
        rt = load_agent_runtime_spec(exp / "agent-runtimes" / "runtime-a.yaml")
        self.assertEqual(rt.connector_type, "local_cli")       # auto default

    def test_evaluation_md_explains_three_methods(self):
        t = (self.exp / "evaluation" / "evaluation.md").read_text(encoding="utf-8")
        for m in ("human_annotation", "llm_judge", "benchmark"):
            self.assertIn(m, t)

    def test_experiment_md_is_guidance(self):
        t = (self.exp / "experiment.md").read_text(encoding="utf-8")
        self.assertIn("no signal", t)  # guidance about choosing separating cases


if __name__ == "__main__":
    unittest.main()
