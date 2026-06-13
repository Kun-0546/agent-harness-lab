"""v1.1 PR1 doc-face pinning: multi-turn contract docs + migration guide.

The v1.1 multi-turn execution contract is spec-first (PR1 ships the docs before
the dispatch code). These tests pin the load-bearing statements so a later edit
cannot silently drop a contract clause, and verify the internal links of every
doc this PR touches actually resolve.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class TestExecutionModelMultiTurn(unittest.TestCase):
    """execution-model.md §14 — the multi-turn execution contract (v1.1)."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCS / "v1-spec" / "execution-model.md")

    def test_multiturn_chapter_exists(self):
        self.assertIn("## 15. Multi-turn Execution (v1.1)", self.text)

    def test_three_simulator_types(self):
        for t in ("role_play", "scripted", "script"):
            self.assertIn(t, self.text, f"simulator type {t} must be specified")

    def test_per_case_fresh_session_and_isolated_redefinition(self):
        self.assertIn("fresh connector session per case", self.text)
        self.assertIn("isolation unit", self.text)
        self.assertIn("redefined as the **case**", self.text)

    def test_turn_loop_contract(self):
        self.assertIn("turn 0", self.text)
        self.assertIn("simulator(transcript)", self.text)
        self.assertIn("max(1, max_turns)", self.text)
        # the schema owns the default turn budget
        self.assertIn("the default is defined by the schema", self.text)

    def test_partial_transcript_contract(self):
        self.assertIn("Partial transcript contract", self.text)
        self.assertIn("**not** discarded", self.text)
        self.assertIn("`error` field", self.text)

    def test_no_key_behavior_and_stub_escape_hatch(self):
        self.assertIn("simulator_unconfigured", self.text)
        self.assertIn("never a fabricated follow-up", self.text)
        self.assertIn("AHL_SIM_STUB", self.text)
        self.assertIn("forced: true", self.text)

    def test_single_turn_path_frozen(self):
        self.assertIn("byte-for-byte", self.text)

    def test_auto_optimize_single_turn_only(self):
        self.assertIn("optimization loop supports `single_turn` only", self.text)

    def test_multiturn_connector_constraint_documented(self):
        self.assertIn("simulator_connector_unsupported", self.text)
        self.assertIn("never a silent single-turn downgrade", self.text)


class TestSchemaSimulatorSection(unittest.TestCase):
    """experiment-yaml-schema.md §14a + execution.trials/aggregation preview."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(DOCS / "v1-spec" / "experiment-yaml-schema.md")

    def test_scripted_type_and_playbook(self):
        self.assertIn("type: scripted", self.text)
        self.assertIn("playbook", self.text)
        self.assertIn("per_case", self.text)

    def test_role_play_policy_card_four_sections_bilingual(self):
        for en, cn in (("## Persona", "## 人设"), ("## Background", "## 背景知识"),
                       ("## Strategy", "## 追问策略"), ("## Stop", "## 收尾条件")):
            self.assertIn(en, self.text, f"policy card section {en} must be documented")
            self.assertIn(cn, self.text, f"policy card section {cn} must be documented")

    def test_default_max_turns_is_eight(self):
        self.assertIn("defaults to 8 when omitted", self.text)

    def test_script_connector_multiturn_rejection_documented(self):
        self.assertIn("simulator_connector_unsupported", self.text)

    def test_trials_and_aggregation_shipped_as_real_contract(self):
        # PR5: schema preview replaced by the real contract; preview labels removed
        self.assertIn("execution.trials / execution.aggregation", self.text)
        self.assertNotIn("schema preview", self.text)
        self.assertNotIn("later v1.1 PR", self.text)
        self.assertIn("win_rate", self.text)
        self.assertIn("bad_trials", self.text)
        self.assertIn("bad_aggregation", self.text)


class TestMigrationGuide(unittest.TestCase):
    """docs/migrating-from-ahl.md — the v0.x → v1 mapping (spec §0.2-3)."""

    @classmethod
    def setUpClass(cls):
        cls.path = DOCS / "migrating-from-ahl.md"
        cls.text = _read(cls.path)

    def test_guide_exists(self):
        self.assertTrue(self.path.is_file())

    def test_core_mappings_present(self):
        for old, new in (("cases/*.md", "cases.jsonl"),
                         ("program.md", "experiment.yaml"),
                         ("connect.md", "agent-runtimes"),
                         ("simulator.md", "role_play"),
                         ("ahl compare", "hlab compare")):
            self.assertIn(old, self.text, f"old-format term {old} missing")
            self.assertIn(new, self.text, f"v1 equivalent {new} missing")

    def test_max_turns_moves_to_simulator_with_default_8(self):
        self.assertIn("simulator.max_turns", self.text)
        self.assertIn("defaulted to 8 turns", self.text)

    def test_simulator_three_sections_map_to_four(self):
        for cn in ("人设", "背景知识", "追问策略"):
            self.assertIn(cn, self.text)
        self.assertIn("## Stop", self.text)

    def test_score_has_no_standalone_verb(self):
        self.assertIn("ahl score", self.text)
        self.assertIn("evaluation runs inside hlab run", self.text)


class TestDocLinksResolve(unittest.TestCase):
    """Every relative link in the docs this PR touches must resolve."""

    DOCS_TO_CHECK = (
        DOCS / "migrating-from-ahl.md",
        DOCS / "v1-spec" / "execution-model.md",
        DOCS / "v1-spec" / "experiment-yaml-schema.md",
        DOCS / "v1-spec" / "cli.md",
    )

    def test_relative_links_resolve(self):
        dead: list[str] = []
        for doc in self.DOCS_TO_CHECK:
            for target in _LINK_RE.findall(_read(doc)):
                target = target.split("#", 1)[0].strip()
                if not target or "://" in target:
                    continue  # same-file anchor or external URL
                if not (doc.parent / target).exists():
                    dead.append(f"{doc.relative_to(ROOT)} -> {target}")
        self.assertEqual(dead, [], f"dead doc links: {dead}")

    def test_readme_parity_points_at_migration_guide(self):
        for name in ("README.md", "README.zh-CN.md"):
            text = _read(ROOT / name)
            self.assertIn("docs/migrating-from-ahl.md", text,
                          f"{name} must point at the shipped migration guide")
            self.assertNotIn("planned for v1.1", text)
            self.assertNotIn("计划在 v1.1", text)


if __name__ == "__main__":
    unittest.main()
