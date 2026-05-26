"""Integration tests for evidence in score/compare workflows + CLI (v0.4).

Covers:
- Group B: score result includes top-level evidence; missing snapshot graceful.
- Group C2: compare reads evidence; fallback recompute when score lacks it.
- Group D: CLI compare stdout adds warning/note line when applicable.
- Group E: red lines (--mode auto exits 2; copilot default does not create
  evidence files; CLI command count unchanged).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness_lab import workflow
from agent_harness_lab.cli import cmd_compare


def _write_exp_with_legacy_run(tmp_root: Path):
    """Build a tiny experiment with a single legacy variant V1 and one case.

    Uses the inline-library agent type (no subprocess) for a self-contained run.
    Returns the experiment directory.
    """
    # Workspace root needs connect.md (legacy fallback) + experiment dir
    # We'll fabricate a run-*.json + snapshots/ directly instead of calling
    # workflow.run, to keep the test fast and not depend on agentconn.
    exp = tmp_root / "experiments" / "001-demo"
    exp.mkdir(parents=True)
    (exp / "harnesses").mkdir()
    (exp / "cases").mkdir()
    return exp


def _write_rubric(exp: Path):
    (exp / "rubric.md").write_text(
        "# rubric\n\n## quality\n权重: 1.0\n质量\n",
        encoding="utf-8")


def _write_run_file(exp: Path, run_id: str,
                     records: list,
                     snapshots: dict | None = None):
    results_dir = exp / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / f"{run_id}.json").write_text(
        json.dumps(records), encoding="utf-8")
    if snapshots:
        snap_dir = results_dir / "snapshots" / run_id
        snap_dir.mkdir(parents=True, exist_ok=True)
        for vid, snap in snapshots.items():
            (snap_dir / f"{vid}.json").write_text(
                json.dumps(snap), encoding="utf-8")


def _legacy_snapshot(run_id, vid):
    return {
        "snapshot_id": "legacy",
        "run_id": run_id,
        "variant_id": vid,
        "experiment": "001-demo",
        "created_at": "2026-05-25T00:00:00+00:00",
        "runtime_source": {"type": "legacy_connect",
                            "connect_md_hash": "sha256:abc"},
        "harness_patch": None,
        "sandbox": None,
        "environment": {},
    }


def _local_path_snapshot(run_id, vid, source_dir_hash="sha256:src",
                          patch_hash="sha256:pat"):
    return {
        "snapshot_id": f"snap-{run_id}-{vid}",
        "run_id": run_id,
        "variant_id": vid,
        "experiment": "001-demo",
        "created_at": "2026-05-25T00:00:00+00:00",
        "runtime_source": {"type": "local_path", "name": "src",
                            "path": "/x", "source_dir_hash": source_dir_hash},
        "harness_patch": {"applied": [], "env": {}, "start_command": "x",
                          "patch_hash": patch_hash},
        "sandbox": {"type": "copy_dir", "path": "sb", "start_command": "x"},
        "environment": {},
    }


# Group B — score integration


class TestScoreEvidenceWritten(unittest.TestCase):
    """workflow.score writes top-level 'evidence' into score JSON."""

    def test_score_json_contains_evidence_for_legacy_run(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            run_id = "run-20260525-000000"
            records = [
                {"version_id": "V1", "case_id": "C1",
                 "transcript": [{"turn": 0, "user": "hi", "agent": "yo"}],
                 "error": "", "snapshot_id": "legacy"},
            ]
            _write_run_file(exp, run_id, records,
                             snapshots={"V1": _legacy_snapshot(run_id, "V1")})

            # Call score
            result = workflow.score(exp, use_llm=False)

            data = json.loads(result.out_path.read_text(encoding="utf-8"))
            self.assertIn("evidence", data)
            self.assertIn("variants", data["evidence"])
            self.assertIn("V1", data["evidence"]["variants"])
            self.assertEqual(data["evidence"]["variants"]["V1"]["level"],
                             "weak")  # legacy + no materials evidence
            self.assertIsNotNone(data["evidence"]["summary"]["warning"])

    def test_score_json_contains_strong_evidence_for_materialized(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            run_id = "run-20260525-000001"
            records = [
                {"version_id": "V1", "case_id": "C1",
                 "transcript": [{"turn": 0, "user": "hi", "agent": "yo"}],
                 "error": "", "snapshot_id": f"snap-{run_id}-V1"},
            ]
            _write_run_file(
                exp, run_id, records,
                snapshots={"V1": _local_path_snapshot(run_id, "V1")})

            result = workflow.score(exp, use_llm=False)
            data = json.loads(result.out_path.read_text(encoding="utf-8"))
            self.assertEqual(data["evidence"]["variants"]["V1"]["level"],
                             "strong")
            # all strong → no warning, no note
            self.assertIsNone(data["evidence"]["summary"]["warning"])
            self.assertIsNone(data["evidence"]["summary"]["note"])

    def test_score_does_not_crash_when_snapshot_file_missing(self):
        # Run record exists but snapshot file is gone → evidence = unknown
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            run_id = "run-20260525-000002"
            records = [
                {"version_id": "V1", "case_id": "C1",
                 "transcript": [{"turn": 0, "user": "hi", "agent": "yo"}],
                 "error": "", "snapshot_id": "legacy"},
            ]
            # No snapshots dir → snapshot file missing
            _write_run_file(exp, run_id, records, snapshots=None)

            result = workflow.score(exp, use_llm=False)
            data = json.loads(result.out_path.read_text(encoding="utf-8"))
            self.assertEqual(data["evidence"]["variants"]["V1"]["level"],
                             "unknown")


# Group C2 — compare reads / falls back


class TestCompareEvidenceFlow(unittest.TestCase):

    def _write_baseline_harness(self, exp: Path):
        # Need a harness V1 marked baseline for compare to work
        (exp / "harnesses" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线\n## 类型\n外部命令行\n"
            "## 配置\n命令:py\n",
            encoding="utf-8")
        # Program for compare_mode
        (exp / "program.md").write_text(
            "# program\n\n## 假设\nfoo\n\n## 声明\n- 环境:无\n"
            "- 对话模式:模拟\n- 状态:重置\n- 评分:LLM 打 1-10\n"
            "- 运行模式:人评\n", encoding="utf-8")

    def test_compare_uses_evidence_from_v04_score(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            self._write_baseline_harness(exp)
            run_id = "run-20260525-000003"
            records = [
                {"version_id": "V1", "case_id": "C1",
                 "transcript": [{"turn": 0, "user": "hi", "agent": "ok"}],
                 "error": "", "snapshot_id": "legacy"},
            ]
            _write_run_file(exp, run_id, records,
                             snapshots={"V1": _legacy_snapshot(run_id, "V1")})

            workflow.score(exp, use_llm=False)
            result = workflow.compare(exp)

            self.assertIsNotNone(result.evidence)
            self.assertIn("V1", result.evidence["variants"])
            self.assertEqual(result.evidence["variants"]["V1"]["level"],
                             "weak")
            # Compare report contains Evidence section
            self.assertIn("## Evidence", result.report_text)
            self.assertIn("⚠", result.report_text)  # weak triggers warning

    def test_compare_fallback_for_old_score_without_evidence(self):
        """v0.3.x score JSON (no 'evidence' field) → compare recomputes on the fly."""
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            self._write_baseline_harness(exp)
            run_id = "run-20260525-000004"
            records = [
                {"version_id": "V1", "case_id": "C1",
                 "transcript": [{"turn": 0, "user": "hi", "agent": "ok"}],
                 "error": "", "snapshot_id": "legacy"},
            ]
            _write_run_file(exp, run_id, records,
                             snapshots={"V1": _legacy_snapshot(run_id, "V1")})

            # Manually craft a v0.3.x-style score JSON (no 'evidence' key)
            score_path = exp / "results" / "score-20260525-000004.json"
            score_path.write_text(json.dumps({
                "run": f"{run_id}.json",
                "rubric": "rubric.md",
                "grader": "本地桩",
                "scores": [{"version_id": "V1", "case_id": "C1",
                            "dimensions": {"quality": 7.0}, "total": 7.0}],
                # NOTE: no 'evidence' field
            }), encoding="utf-8")

            result = workflow.compare(exp)
            self.assertIsNotNone(result.evidence)
            self.assertEqual(result.evidence["variants"]["V1"]["level"],
                             "weak")  # recomputed from snapshot

    def test_compare_synthesizes_unknown_when_run_file_missing(self):
        """Blocker 2: old score refs missing run-*.json → synthesize unknown per variant.

        Evidence section + warning must still appear (not empty, not skipped).
        """
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            self._write_baseline_harness(exp)
            results_dir = exp / "results"
            results_dir.mkdir(exist_ok=True)
            score_path = results_dir / "score-20260525-000005.json"
            score_path.write_text(json.dumps({
                "run": "run-MISSING.json",
                "rubric": "rubric.md",
                "grader": "stub",
                "scores": [{"version_id": "V1", "case_id": "C1",
                            "dimensions": {"quality": 7.0}, "total": 7.0}],
                # NOTE: no top-level "evidence" field
            }), encoding="utf-8")

            # Should not raise
            result = workflow.compare(exp)
            self.assertIsNotNone(result.evidence)
            # Variants populated from score entries, each as unknown
            self.assertEqual(set(result.evidence["variants"].keys()), {"V1"})
            self.assertEqual(result.evidence["variants"]["V1"]["level"],
                             "unknown")
            self.assertFalse(
                result.evidence["variants"]["V1"]["snapshot_available"])
            self.assertIn(
                "no evidence metadata",
                result.evidence["variants"]["V1"]["reasons"][0])
            # Evidence section MUST be in report
            self.assertIn("## Evidence", result.report_text)
            # Warning MUST appear (all unknown)
            self.assertIn("⚠", result.report_text)
            self.assertIn("weak/unknown", result.report_text)
            # Compare math unchanged — version total still rendered
            self.assertIn("V1  7.0", result.report_text)

    def test_compare_synthesizes_unknown_when_run_file_corrupt(self):
        """Blocker 2: corrupt run-*.json → synthesize unknown from score entries."""
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            self._write_baseline_harness(exp)
            results_dir = exp / "results"
            results_dir.mkdir(exist_ok=True)
            # Write a corrupt run file
            (results_dir / "run-CORRUPT.json").write_text(
                "{ not valid", encoding="utf-8")
            (results_dir / "score-20260525-000006.json").write_text(
                json.dumps({
                    "run": "run-CORRUPT.json",
                    "rubric": "rubric.md",
                    "grader": "stub",
                    "scores": [{"version_id": "V1", "case_id": "C1",
                                "dimensions": {"quality": 5.0},
                                "total": 5.0}],
                }), encoding="utf-8")

            result = workflow.compare(exp)
            self.assertEqual(result.evidence["variants"]["V1"]["level"],
                             "unknown")
            self.assertIn("## Evidence", result.report_text)
            self.assertIn("⚠", result.report_text)


# Group D — CLI compare stdout


def _run_compare_cli(exp_id: str, workspace: Path) -> tuple:
    """Invoke cmd_compare with stdout/stderr captured (in-process; cwd switched)."""
    args = argparse.Namespace(experiment=exp_id)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    orig_cwd = Path.cwd()
    os.chdir(workspace)
    try:
        with contextlib.redirect_stdout(out_buf), \
             contextlib.redirect_stderr(err_buf):
            rc = cmd_compare(args)
    finally:
        os.chdir(orig_cwd)
    return rc, out_buf.getvalue(), err_buf.getvalue()


class TestCliCompareStdout(unittest.TestCase):

    def _setup_with_levels(self, tmp: Path, level: str):
        """Build a workspace + score/compare flow yielding all variants at `level`."""
        exp = _write_exp_with_legacy_run(tmp)
        _write_rubric(exp)
        (exp / "harnesses" / "V1.md").write_text(
            "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线\n## 类型\n外部命令行\n"
            "## 配置\n命令:py\n", encoding="utf-8")
        (exp / "program.md").write_text(
            "# program\n\n## 假设\nfoo\n\n## 声明\n- 环境:无\n"
            "- 对话模式:模拟\n- 状态:重置\n- 评分:LLM 打 1-10\n"
            "- 运行模式:人评\n", encoding="utf-8")
        run_id = "run-20260525-100000"
        records = [
            {"version_id": "V1", "case_id": "C1",
             "transcript": [{"turn": 0, "user": "hi", "agent": "ok"}],
             "error": "", "snapshot_id":
                 "legacy" if level == "weak" else f"snap-{run_id}-V1"},
        ]
        snap = (_legacy_snapshot(run_id, "V1") if level == "weak"
                else _local_path_snapshot(run_id, "V1"))
        _write_run_file(exp, run_id, records, snapshots={"V1": snap})
        workflow.score(exp, use_llm=False)
        return exp

    def test_weak_triggers_warning_line_in_stdout(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            self._setup_with_levels(tmp, level="weak")
            rc, out, _err = _run_compare_cli("001", tmp)
        self.assertEqual(rc, 0)
        self.assertIn("⚠", out)
        self.assertIn("weak/unknown", out)
        self.assertIn("Evidence 段", out)

    def test_all_strong_does_not_emit_warning_line(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            self._setup_with_levels(tmp, level="strong")
            rc, out, _err = _run_compare_cli("001", tmp)
        self.assertEqual(rc, 0)
        # Compare report itself has no warning section; stdout extra line
        # should also be absent.
        # The character ⚠ should not appear AFTER the "对比报告存到" line.
        after_path = out.split("对比报告存到")[-1]
        self.assertNotIn("⚠", after_path)
        self.assertNotIn("ℹ", after_path)

    def test_unknown_synthesis_triggers_cli_warning(self):
        """Blocker 2 end-to-end: score without evidence + missing run →
        compare exits 0, stdout shows warning line, report has Evidence + ⚠."""
        with TemporaryDirectory() as t:
            tmp = Path(t)
            exp = _write_exp_with_legacy_run(tmp)
            _write_rubric(exp)
            (exp / "harnesses" / "V1.md").write_text(
                "---\nid: V1\n基线: 是\n---\n## 这是什么\n基线\n"
                "## 类型\n外部命令行\n## 配置\n命令:py\n",
                encoding="utf-8")
            (exp / "program.md").write_text(
                "# program\n\n## 假设\nfoo\n\n## 声明\n- 环境:无\n"
                "- 对话模式:模拟\n- 状态:重置\n- 评分:LLM\n"
                "- 运行模式:人评\n", encoding="utf-8")
            results_dir = exp / "results"
            results_dir.mkdir(exist_ok=True)
            (results_dir / "score-20260525-130000.json").write_text(
                json.dumps({
                    "run": "run-MISSING.json",
                    "rubric": "rubric.md",
                    "grader": "stub",
                    "scores": [{"version_id": "V1", "case_id": "C1",
                                "dimensions": {"quality": 7.0},
                                "total": 7.0}],
                }), encoding="utf-8")

            rc, out, _err = _run_compare_cli("001", tmp)
        self.assertEqual(rc, 0)
        self.assertIn("## Evidence", out)
        # Extra stdout warning line must appear after the report path
        after_path = out.split("对比报告存到")[-1]
        self.assertIn("⚠", after_path)
        self.assertIn("weak/unknown", after_path)


# Group E — red lines


class TestV04RedLines(unittest.TestCase):

    def test_cli_help_command_count_unchanged(self):
        """ahl --help still lists exactly 13 subcommands (no new CLI added)."""
        result = subprocess.run(
            [sys.executable, "-m", "agent_harness_lab", "--help"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                 "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        )
        self.assertEqual(result.returncode, 0,
                         f"--help failed: {result.stderr!r}")
        expected = ["init", "walkthrough", "connect", "new", "show", "cases",
                    "rubric", "simulator", "harnesses", "run", "score",
                    "compare", "review"]
        for cmd in expected:
            self.assertIn(cmd, result.stdout,
                          f"missing subcommand {cmd!r} in --help output")
        # No surprise new commands. v0.6 explicitly adds 'probe' (spec
        # docs/runtime-probe-mvp.md §9), so it's removed from forbidden.
        forbidden = ["evidence", "pack", "iterate", "auto"]
        # 'auto' is allowed as --mode value but not as top-level subcommand —
        # parse the positional <command> section only.
        cmd_section = result.stdout.split("positional arguments")[1].split(
            "options:")[0]
        for f in forbidden:
            # Subcommand entries look like:  "    <cmd>   description"
            line_starts = [f"    {f} ", f"    {f}\t", f"    {f}\n"]
            self.assertFalse(
                any(s in cmd_section for s in line_starts),
                f"unexpected subcommand {f!r} appeared in --help")

    def test_evidence_module_is_stdlib_only(self):
        """Sanity: importing evidence.py must not pull any third-party deps."""
        before = set(sys.modules.keys())
        import importlib

        import agent_harness_lab.evidence  # noqa: F401
        importlib.reload(agent_harness_lab.evidence)
        added = set(sys.modules.keys()) - before
        third_party = [
            m for m in added
            if "." not in m
            and m not in sys.stdlib_module_names
            and not m.startswith("agent_harness_lab")
            and not m.startswith("_")
        ]
        self.assertEqual(third_party, [],
                         f"evidence.py pulled third-party imports: "
                         f"{third_party}")


if __name__ == "__main__":
    unittest.main()
