"""Unit tests for evidence inference rules (docs/evidence-aware-result.md §3).

Covers Group A from the v0.4 test plan plus helpers and summary tier rules.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness_lab import evidence


def _snap_local(source_dir_hash="sha256:aaa", harness_patch=None, snap_id="snap-X-V1"):
    return {
        "snapshot_id": snap_id,
        "runtime_source": {
            "type": "local_path",
            "name": "src",
            "path": "/x",
            "source_dir_hash": source_dir_hash,
        },
        "harness_patch": harness_patch,
        "sandbox": None,
        "environment": {},
    }


def _snap_git(source_dir_hash="sha256:aaa", commit_sha="abc123",
               harness_patch=None, snap_id="snap-X-V1"):
    return {
        "snapshot_id": snap_id,
        "runtime_source": {
            "type": "git_repo",
            "name": "repo",
            "url": "https://example.com/x.git",
            "ref": "main",
            "commit_sha": commit_sha,
            "source_dir_hash": source_dir_hash,
        },
        "harness_patch": harness_patch,
        "sandbox": None,
        "environment": {},
    }


def _snap_legacy():
    return {
        "snapshot_id": "legacy",
        "runtime_source": {"type": "legacy_connect", "connect_md_hash": "sha256:def"},
        "harness_patch": None,
        "sandbox": None,
        "environment": {},
    }


def _patch_dict(patch_hash="sha256:bbb"):
    return {"patch_hash": patch_hash, "applied": [], "env": {},
            "start_command": "x"}


class TestLocalPathInference(unittest.TestCase):
    """spec §3.1 — local_path."""

    def test_strong_with_source_dir_hash_no_patch(self):
        # local_path + source_dir_hash, no harness_patch → strong
        # Kun adjustment 1: absence of harness_patch must NOT downgrade
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_local(source_dir_hash="sha256:aaa", harness_patch=None),
                Path(t))
        self.assertEqual(result["level"], "strong")
        self.assertIn("no harness_patch declared", result["reasons"][0])
        self.assertEqual(result["runtime_source_type"], "local_path")

    def test_strong_with_source_dir_hash_and_patch_hash(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_local(source_dir_hash="sha256:aaa",
                            harness_patch=_patch_dict("sha256:bbb")),
                Path(t))
        self.assertEqual(result["level"], "strong")
        self.assertIn("patch_hash", result["reasons"][0])

    def test_medium_when_patch_present_but_patch_hash_empty(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_local(source_dir_hash="sha256:aaa",
                            harness_patch=_patch_dict(patch_hash="")),
                Path(t))
        self.assertEqual(result["level"], "medium")
        self.assertIn("missing patch_hash", result["reasons"][0])

    def test_medium_when_source_dir_hash_missing(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_local(source_dir_hash="", harness_patch=None), Path(t))
        self.assertEqual(result["level"], "medium")
        self.assertIn("source_dir_hash", result["reasons"][0])


class TestGitRepoInference(unittest.TestCase):
    """spec §3.2 — git_repo."""

    def test_strong_with_commit_and_dir_hash_no_patch(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_git(commit_sha="abc", source_dir_hash="sha256:aaa",
                          harness_patch=None), Path(t))
        self.assertEqual(result["level"], "strong")
        self.assertIn("no harness_patch declared", result["reasons"][0])
        self.assertEqual(result["runtime_source_type"], "git_repo")

    def test_strong_with_commit_dir_hash_and_patch_hash(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_git(commit_sha="abc", source_dir_hash="sha256:aaa",
                          harness_patch=_patch_dict()), Path(t))
        self.assertEqual(result["level"], "strong")

    def test_medium_when_commit_sha_missing(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_git(commit_sha="", source_dir_hash="sha256:aaa",
                          harness_patch=None), Path(t))
        self.assertEqual(result["level"], "medium")
        self.assertIn("commit_sha", result["reasons"][0])

    def test_medium_when_source_dir_hash_missing(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_git(commit_sha="abc", source_dir_hash="",
                          harness_patch=None), Path(t))
        self.assertEqual(result["level"], "medium")
        self.assertIn("source_dir_hash", result["reasons"][0])

    def test_medium_when_patch_hash_empty(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_git(commit_sha="abc", source_dir_hash="sha256:aaa",
                          harness_patch=_patch_dict(patch_hash="")), Path(t))
        self.assertEqual(result["level"], "medium")


class TestLegacyConnectInference(unittest.TestCase):
    """spec §3.3 — legacy_connect."""

    def _materials(self, tmp: Path, files=()):
        mat = tmp / "materials"
        mat.mkdir()
        for f in files:
            (mat / f).write_text("dummy", encoding="utf-8")
        return mat

    def test_weak_when_no_materials_evidence(self):
        with TemporaryDirectory() as t:
            mat = self._materials(Path(t))
            result = evidence.infer_evidence_from_snapshot(_snap_legacy(), mat)
        self.assertEqual(result["level"], "weak")
        self.assertIn("no materials evidence", result["reasons"][0])

    def test_medium_when_runtime_evidence_present(self):
        with TemporaryDirectory() as t:
            mat = self._materials(Path(t), files=["runtime-evidence.md"])
            result = evidence.infer_evidence_from_snapshot(_snap_legacy(), mat)
        self.assertEqual(result["level"], "medium")
        self.assertIn("runtime-evidence.md", result["reasons"][0])

    def test_medium_when_harness_evidence_present(self):
        with TemporaryDirectory() as t:
            mat = self._materials(Path(t), files=["harness-evidence.md"])
            result = evidence.infer_evidence_from_snapshot(_snap_legacy(), mat)
        self.assertEqual(result["level"], "medium")
        self.assertIn("harness-evidence.md", result["reasons"][0])

    def test_medium_when_cloud_evidence_present(self):
        with TemporaryDirectory() as t:
            mat = self._materials(Path(t), files=["cloud-evidence.md"])
            result = evidence.infer_evidence_from_snapshot(_snap_legacy(), mat)
        self.assertEqual(result["level"], "medium")
        self.assertIn("cloud-evidence.md", result["reasons"][0])

    def test_weak_when_materials_dir_missing(self):
        # manual 模式默认无 materials/ 目录
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(
                _snap_legacy(), Path(t) / "no-materials")
        self.assertEqual(result["level"], "weak")
        self.assertEqual(result["materials_evidence"], [])

    def test_lists_all_present_evidence_files(self):
        with TemporaryDirectory() as t:
            mat = self._materials(Path(t),
                                   files=["runtime-evidence.md",
                                          "cloud-evidence.md"])
            result = evidence.infer_evidence_from_snapshot(_snap_legacy(), mat)
        self.assertEqual(sorted(result["materials_evidence"]),
                         ["cloud-evidence.md", "runtime-evidence.md"])


class TestUnknownInference(unittest.TestCase):
    """spec §3.4 — unknown cases."""

    def test_unknown_when_snapshot_dict_none(self):
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(None, Path(t))
        self.assertEqual(result["level"], "unknown")
        self.assertFalse(result["snapshot_available"])
        self.assertIn("missing or unreadable", result["reasons"][0])

    def test_unknown_when_runtime_source_type_unrecognized(self):
        snap = {
            "snapshot_id": "weird",
            "runtime_source": {"type": "docker_image"},  # M2+
            "harness_patch": None,
            "sandbox": None,
        }
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "unknown")
        self.assertIn("docker_image", result["reasons"][0])


class TestSummaryTierRules(unittest.TestCase):
    """spec §5.1 — three-tier warning strategy (Kun adjustment 3)."""

    def test_all_strong_no_warning_no_note(self):
        s = evidence._build_summary(
            {"strong": 2, "medium": 0, "weak": 0, "unknown": 0})
        self.assertIsNone(s["warning"])
        self.assertIsNone(s["note"])

    def test_all_medium_no_warning_no_note(self):
        s = evidence._build_summary(
            {"strong": 0, "medium": 2, "weak": 0, "unknown": 0})
        self.assertIsNone(s["warning"])
        self.assertIsNone(s["note"])

    def test_strong_plus_medium_emits_note_only(self):
        s = evidence._build_summary(
            {"strong": 1, "medium": 1, "weak": 0, "unknown": 0})
        self.assertIsNone(s["warning"])
        self.assertIsNotNone(s["note"])
        self.assertIn("differ", s["note"])

    def test_any_weak_emits_warning(self):
        s = evidence._build_summary(
            {"strong": 1, "medium": 0, "weak": 1, "unknown": 0})
        self.assertIsNotNone(s["warning"])
        self.assertIn("weak/unknown", s["warning"])
        self.assertIsNone(s["note"])

    def test_any_unknown_emits_warning(self):
        s = evidence._build_summary(
            {"strong": 0, "medium": 0, "weak": 0, "unknown": 1})
        self.assertIsNotNone(s["warning"])

    def test_all_weak_emits_warning_not_note(self):
        # Blocker 1: weak/weak must warn (overrides "uniform level = no warn")
        s = evidence._build_summary(
            {"strong": 0, "medium": 0, "weak": 2, "unknown": 0})
        self.assertIsNotNone(s["warning"])
        self.assertIsNone(s["note"])

    def test_all_unknown_emits_warning_not_note(self):
        # Blocker 1: unknown/unknown must warn (overrides "uniform level = no warn")
        s = evidence._build_summary(
            {"strong": 0, "medium": 0, "weak": 0, "unknown": 2})
        self.assertIsNotNone(s["warning"])
        self.assertIsNone(s["note"])

    def test_weak_plus_medium_emits_warning_not_note(self):
        # Blocker 1: any weak triggers warning even when levels differ
        s = evidence._build_summary(
            {"strong": 0, "medium": 1, "weak": 1, "unknown": 0})
        self.assertIsNotNone(s["warning"])
        self.assertIsNone(s["note"])

    def test_unknown_plus_medium_emits_warning_not_note(self):
        # Blocker 1: any unknown triggers warning even when levels differ
        s = evidence._build_summary(
            {"strong": 0, "medium": 1, "weak": 0, "unknown": 1})
        self.assertIsNotNone(s["warning"])
        self.assertIsNone(s["note"])


class TestLoadSnapshotForVariant(unittest.TestCase):
    """Snapshot file loader degrades gracefully."""

    def test_missing_file_returns_none(self):
        with TemporaryDirectory() as t:
            result = evidence._load_snapshot_for_variant(
                Path(t), "run-X", "V1")
        self.assertIsNone(result)

    def test_empty_run_id_returns_none(self):
        with TemporaryDirectory() as t:
            result = evidence._load_snapshot_for_variant(Path(t), "", "V1")
        self.assertIsNone(result)

    def test_corrupt_json_returns_none(self):
        with TemporaryDirectory() as t:
            snap_dir = Path(t) / "results" / "snapshots" / "run-X"
            snap_dir.mkdir(parents=True)
            (snap_dir / "V1.json").write_text("{ not valid",
                                               encoding="utf-8")
            result = evidence._load_snapshot_for_variant(
                Path(t), "run-X", "V1")
        self.assertIsNone(result)

    def test_valid_json_returns_dict(self):
        with TemporaryDirectory() as t:
            snap_dir = Path(t) / "results" / "snapshots" / "run-X"
            snap_dir.mkdir(parents=True)
            (snap_dir / "V1.json").write_text(
                json.dumps({"snapshot_id": "snap-run-X-V1"}),
                encoding="utf-8")
            result = evidence._load_snapshot_for_variant(
                Path(t), "run-X", "V1")
        self.assertEqual(result, {"snapshot_id": "snap-run-X-V1"})


class TestRunIdFromFilename(unittest.TestCase):
    def test_standard_filename(self):
        self.assertEqual(
            evidence._run_id_from_filename("run-20260525-160000.json"),
            "run-20260525-160000")

    def test_without_json_extension(self):
        self.assertEqual(
            evidence._run_id_from_filename("run-20260525-160000"),
            "run-20260525-160000")

    def test_empty(self):
        self.assertEqual(evidence._run_id_from_filename(""), "")


class TestSummarizeEvidenceForRun(unittest.TestCase):
    """End-to-end summary builder for the score-flow path."""

    def test_empty_records_yields_empty_variants(self):
        with TemporaryDirectory() as t:
            result = evidence.summarize_evidence_for_run([], "run-X", Path(t))
        self.assertEqual(result["variants"], {})
        self.assertIsNone(result["summary"]["warning"])
        self.assertIsNone(result["summary"]["note"])

    def test_legacy_records_without_snapshot_file_unknown(self):
        # run records reference snapshots but the files don't exist on disk
        records = [
            {"version_id": "V1", "case_id": "C1", "snapshot_id": "legacy"},
            {"version_id": "V2", "case_id": "C1", "snapshot_id": "legacy"},
        ]
        with TemporaryDirectory() as t:
            result = evidence.summarize_evidence_for_run(
                records, "run-missing", Path(t))
        for vid in ("V1", "V2"):
            self.assertEqual(result["variants"][vid]["level"], "unknown")
        # weak/unknown count → warning
        self.assertIsNotNone(result["summary"]["warning"])

    def test_mixed_levels_strong_and_weak(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            run_id = "run-Y"
            snap_dir = tmp / "results" / "snapshots" / run_id
            snap_dir.mkdir(parents=True)
            (snap_dir / "V1.json").write_text(
                json.dumps(_snap_local(source_dir_hash="sha256:aaa",
                                       harness_patch=None)),
                encoding="utf-8")
            (snap_dir / "V2.json").write_text(
                json.dumps(_snap_legacy()), encoding="utf-8")
            records = [
                {"version_id": "V1", "case_id": "C1",
                 "snapshot_id": "snap-run-Y-V1"},
                {"version_id": "V2", "case_id": "C1",
                 "snapshot_id": "legacy"},
            ]
            result = evidence.summarize_evidence_for_run(records, run_id, tmp)
        self.assertEqual(result["variants"]["V1"]["level"], "strong")
        self.assertEqual(result["variants"]["V2"]["level"], "weak")
        self.assertIsNotNone(result["summary"]["warning"])

    def test_skips_non_dict_records_and_dedups_variants(self):
        records = [
            "not a dict", 42,
            {"version_id": "V1", "snapshot_id": "legacy"},
            {"version_id": "V1", "snapshot_id": "legacy"},  # dedup
            {"version_id": "", "snapshot_id": "legacy"},     # empty vid skip
        ]
        with TemporaryDirectory() as t:
            result = evidence.summarize_evidence_for_run(
                records, "run-X", Path(t))
        self.assertEqual(set(result["variants"].keys()), {"V1"})


class TestSummarizeEvidenceForScore(unittest.TestCase):
    """Compare-flow fallback path."""

    def test_score_without_run_field_empty(self):
        with TemporaryDirectory() as t:
            result = evidence.summarize_evidence_for_score({}, Path(t))
        self.assertEqual(result["variants"], {})
        self.assertEqual(result["summary"]["levels"]["strong"], 0)

    def test_run_file_missing(self):
        with TemporaryDirectory() as t:
            result = evidence.summarize_evidence_for_score(
                {"run": "run-XYZ.json"}, Path(t))
        self.assertEqual(result["variants"], {})

    def test_resolves_via_run_filename(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            results_dir = tmp / "results"
            results_dir.mkdir()
            records = [{"version_id": "V1", "case_id": "C1",
                        "snapshot_id": "legacy"}]
            (results_dir / "run-Z.json").write_text(
                json.dumps(records), encoding="utf-8")
            result = evidence.summarize_evidence_for_score(
                {"run": "run-Z.json"}, tmp)
        self.assertIn("V1", result["variants"])
        # snapshot file missing → unknown
        self.assertEqual(result["variants"]["V1"]["level"], "unknown")

    def test_synthesize_unknown_when_run_missing_with_score_entries(self):
        """Blocker 2: missing run file + score has entries → synthesize unknown per variant."""
        with TemporaryDirectory() as t:
            score_data = {
                "run": "run-GONE.json",  # file does not exist
                "scores": [
                    {"version_id": "V1", "case_id": "C1",
                     "dimensions": {"q": 7.0}, "total": 7.0},
                    {"version_id": "V2", "case_id": "C1",
                     "dimensions": {"q": 8.0}, "total": 8.0},
                ],
            }
            result = evidence.summarize_evidence_for_score(score_data,
                                                            Path(t))
        self.assertEqual(set(result["variants"].keys()), {"V1", "V2"})
        for vid in ("V1", "V2"):
            entry = result["variants"][vid]
            self.assertEqual(entry["level"], "unknown")
            self.assertIsNone(entry["runtime_source_type"])
            self.assertIsNone(entry["snapshot_id"])
            self.assertFalse(entry["snapshot_available"])
            self.assertIn("no evidence metadata", entry["reasons"][0])
        # All unknown → warning
        self.assertIsNotNone(result["summary"]["warning"])
        self.assertEqual(result["summary"]["levels"]["unknown"], 2)

    def test_synthesize_unknown_when_no_run_field_but_score_entries(self):
        """Blocker 2: no run field + score has entries → still synthesize."""
        with TemporaryDirectory() as t:
            score_data = {
                "scores": [
                    {"version_id": "V1", "case_id": "C1", "total": 5.0},
                ],
            }
            result = evidence.summarize_evidence_for_score(score_data,
                                                            Path(t))
        self.assertIn("V1", result["variants"])
        self.assertEqual(result["variants"]["V1"]["level"], "unknown")
        self.assertIsNotNone(result["summary"]["warning"])

    def test_synthesize_dedups_and_ignores_non_dict_entries(self):
        with TemporaryDirectory() as t:
            score_data = {
                "run": "run-MISSING.json",
                "scores": [
                    "not a dict",
                    42,
                    {"version_id": "V1", "total": 1.0},
                    {"version_id": "V1", "total": 2.0},  # dup vid
                    {"version_id": "", "total": 3.0},     # empty vid
                ],
            }
            result = evidence.summarize_evidence_for_score(score_data,
                                                            Path(t))
        self.assertEqual(set(result["variants"].keys()), {"V1"})
        self.assertEqual(result["summary"]["levels"]["unknown"], 1)

    def test_synthesize_run_file_corrupt_falls_back(self):
        """Run file exists but corrupt JSON → synthesize from score entries."""
        with TemporaryDirectory() as t:
            tmp = Path(t)
            results_dir = tmp / "results"
            results_dir.mkdir()
            (results_dir / "run-CORRUPT.json").write_text(
                "{ not valid json", encoding="utf-8")
            score_data = {
                "run": "run-CORRUPT.json",
                "scores": [{"version_id": "V1", "total": 5.0}],
            }
            result = evidence.summarize_evidence_for_score(score_data, tmp)
        self.assertEqual(result["variants"]["V1"]["level"], "unknown")
        self.assertIsNotNone(result["summary"]["warning"])


class TestEvidenceWarningExtraction(unittest.TestCase):
    def test_with_warning(self):
        summary = {"summary": {"warning": "W", "note": None}}
        self.assertEqual(evidence.evidence_warning(summary),
                         {"warning": "W", "note": None})

    def test_with_note(self):
        summary = {"summary": {"warning": None, "note": "N"}}
        self.assertEqual(evidence.evidence_warning(summary),
                         {"warning": None, "note": "N"})

    def test_none_input(self):
        self.assertEqual(evidence.evidence_warning(None),
                         {"warning": None, "note": None})

    def test_empty_dict(self):
        self.assertEqual(evidence.evidence_warning({}),
                         {"warning": None, "note": None})


if __name__ == "__main__":
    unittest.main()
