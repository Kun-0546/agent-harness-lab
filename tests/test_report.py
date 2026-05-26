"""Tests for report.build_compare_report Evidence section (v0.4).

Covers Group C: rendering, 3-tier warning, compare math preserved.
"""
from __future__ import annotations

import unittest

from agent_harness_lab.comparator import Comparison, VersionSummary
from agent_harness_lab.report import build_compare_report


def _comparison_two_variants():
    """Fake Comparison: V1 baseline + V2 with +0.5 delta on d1."""
    v1 = VersionSummary(
        version_id="V1", is_baseline=True, case_count=2, total=7.5,
        dimensions={"d1": 7.5},
    )
    v2 = VersionSummary(
        version_id="V2", is_baseline=False, case_count=2, total=8.0,
        dimensions={"d1": 8.0},
        total_delta=0.5, dimension_delta={"d1": 0.5}, regressed=[],
        compared_to="V1",
    )
    return Comparison(versions=[v1, v2], mode="对基线",
                      basis_cases=["C1", "C2"], coverage_even=True)


def _make_evidence(level_v1="strong", level_v2="strong",
                    warning=None, note=None):
    levels = {"strong": 0, "medium": 0, "weak": 0, "unknown": 0}
    levels[level_v1] += 1
    levels[level_v2] += 1
    return {
        "variants": {
            "V1": {"level": level_v1, "runtime_source_type": "local_path",
                   "snapshot_id": "snap-X-V1", "snapshot_available": True,
                   "materials_evidence": [],
                   "reasons": [f"local_path → {level_v1}"]},
            "V2": {"level": level_v2, "runtime_source_type": "legacy_connect",
                   "snapshot_id": "legacy", "snapshot_available": True,
                   "materials_evidence": [],
                   "reasons": [f"legacy → {level_v2}"]},
        },
        "summary": {"levels": levels, "warning": warning, "note": note},
    }


class TestEvidenceSectionRendering(unittest.TestCase):
    def test_section_present_when_evidence_provided(self):
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(), _make_evidence())
        self.assertIn("## Evidence", text)
        self.assertIn("| variant |", text)
        self.assertIn("V1", text)
        self.assertIn("V2", text)
        self.assertIn("local_path", text)
        self.assertIn("legacy_connect", text)

    def test_no_section_when_evidence_none(self):
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(), None)
        self.assertNotIn("## Evidence", text)

    def test_no_section_when_variants_empty(self):
        ev = {"variants": {},
              "summary": {"levels": {"strong": 0, "medium": 0,
                                      "weak": 0, "unknown": 0},
                          "warning": None, "note": None}}
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(), ev)
        self.assertNotIn("## Evidence", text)


class TestWarningTiers(unittest.TestCase):
    """Adjustment 3 — three tiers."""

    def test_all_strong_no_warning_no_note(self):
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="strong", level_v2="strong"))
        ev_section = text.split("## Evidence")[1].split("版本总分")[0]
        self.assertNotIn("⚠", ev_section)
        self.assertNotIn("ℹ", ev_section)

    def test_all_medium_no_warning_no_note(self):
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="medium", level_v2="medium"))
        ev_section = text.split("## Evidence")[1].split("版本总分")[0]
        self.assertNotIn("⚠", ev_section)
        self.assertNotIn("ℹ", ev_section)

    def test_note_when_strong_vs_medium(self):
        note = ("evidence levels differ; comparison is useful but not "
                "equally grounded")
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="strong", level_v2="medium", note=note))
        self.assertIn("ℹ", text)
        self.assertIn("differ", text)
        # warning must NOT show when only note is set
        ev_section = text.split("## Evidence")[1].split("版本总分")[0]
        self.assertNotIn("⚠", ev_section)

    def test_warning_when_weak_present(self):
        warning = ("weak/unknown evidence may be behavioral-only or missing "
                   "metadata; do not treat this as fully reproducible "
                   "harness comparison")
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="strong", level_v2="weak",
                            warning=warning))
        self.assertIn("⚠", text)
        self.assertIn("weak/unknown", text)

    def test_warning_when_unknown_present(self):
        warning = ("weak/unknown evidence may be behavioral-only or missing "
                   "metadata; do not treat this as fully reproducible "
                   "harness comparison")
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="strong", level_v2="unknown",
                            warning=warning))
        self.assertIn("⚠", text)

    def test_warning_when_all_weak(self):
        # Blocker 1: weak/weak (uniform weak) must still warn
        warning = ("weak/unknown evidence may be behavioral-only or missing "
                   "metadata; do not treat this as fully reproducible "
                   "harness comparison")
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="weak", level_v2="weak",
                            warning=warning))
        self.assertIn("⚠", text)
        ev_section = text.split("## Evidence")[1].split("版本总分")[0]
        self.assertNotIn("ℹ", ev_section)  # warning, not note

    def test_warning_when_all_unknown(self):
        # Blocker 1: unknown/unknown (uniform unknown) must still warn
        warning = ("weak/unknown evidence may be behavioral-only or missing "
                   "metadata; do not treat this as fully reproducible "
                   "harness comparison")
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="unknown", level_v2="unknown",
                            warning=warning))
        self.assertIn("⚠", text)

    def test_warning_when_weak_plus_medium(self):
        # Blocker 1: any weak triggers warning, not note (even with mixed levels)
        warning = ("weak/unknown evidence may be behavioral-only or missing "
                   "metadata; do not treat this as fully reproducible "
                   "harness comparison")
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="medium", level_v2="weak",
                            warning=warning))
        self.assertIn("⚠", text)
        ev_section = text.split("## Evidence")[1].split("版本总分")[0]
        self.assertNotIn("ℹ", ev_section)

    def test_warning_when_unknown_plus_medium(self):
        # Blocker 1: any unknown triggers warning, not note
        warning = ("weak/unknown evidence may be behavioral-only or missing "
                   "metadata; do not treat this as fully reproducible "
                   "harness comparison")
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(),
            _make_evidence(level_v1="medium", level_v2="unknown",
                            warning=warning))
        self.assertIn("⚠", text)


class TestCompareMathUnchanged(unittest.TestCase):
    """Adjustment 3 — Evidence section must NOT affect 版本总分 / 维度变化."""

    def test_version_totals_still_rendered(self):
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(), _make_evidence())
        self.assertIn("V1  7.5", text)
        self.assertIn("V2  8.0", text)
        self.assertIn("vs V1 +0.5", text)

    def test_dimension_changes_still_rendered(self):
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(), _make_evidence())
        self.assertIn("维度变化:", text)
        self.assertIn("d1+0.5", text)

    def test_no_evidence_keeps_old_format(self):
        """v0.3.x callers passing no evidence get the old report shape."""
        text = build_compare_report(
            "exp", "score-X.json", "stub", "V1",
            _comparison_two_variants(), None)
        # Old required sections still present
        self.assertIn("版本总分:", text)
        self.assertIn("维度变化:", text)
        self.assertIn("V1  7.5", text)
        self.assertIn("V2  8.0", text)


if __name__ == "__main__":
    unittest.main()
