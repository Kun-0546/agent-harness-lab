"""E2E acceptance test for examples/sample-workspace/ (v0.7).

Spec: docs/product-flow-completion.md §13-§14.

Drives the full product flow via subprocess (ahl probe → run → score →
compare) against a temporary copy of examples/sample-workspace, then
asserts:
- all exits are 0
- expected artifacts exist (probe-results, run/score/compare files,
  snapshots)
- V2 snapshot has harness_package block with all 3 hashes
- score JSON has top-level `evidence`
- compare md has `## Evidence` section
- V1 vs V2 score totals differ (package install changed agent behavior)
- two consecutive runs produce identical scores (deterministic)
- the committed examples/sample-workspace contains NO generated artifacts
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
SAMPLE_WORKSPACE = REPO_ROOT / "examples" / "sample-workspace"


def _env() -> dict:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(SRC_PATH)
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def _run_cli(workspace: Path, *args: str, expect_exit: int = 0,
              timeout: int = 120) -> subprocess.CompletedProcess:
    """Invoke `python -m agent_harness_lab <args>` in workspace."""
    r = subprocess.run(
        [sys.executable, "-m", "agent_harness_lab", *args],
        cwd=workspace, env=_env(), text=True,
        capture_output=True, encoding="utf-8", timeout=timeout,
    )
    assert r.returncode == expect_exit, (
        f"`ahl {' '.join(args)}` expected {expect_exit}, got "
        f"{r.returncode}\nstdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
    return r


def _patch_python_executable(workspace: Path) -> None:
    """Replace `python agent.py` with `"<sys.executable>" agent.py`.

    Sample workspace ships `python agent.py` for cross-platform
    readability. Tests inject sys.executable so they run on systems
    where `python` is not on PATH (e.g. Windows with only `py`).
    """
    quoted_exe = f'"{sys.executable}"'
    targets = [
        workspace / "experiments" / "001-faq-conciseness" / "harnesses" / "V1.md",
        workspace / "harness-packages" / "concise-prompt" / "0.1.0" / "manifest.md",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        text = text.replace("python agent.py", f"{quoted_exe} agent.py")
        path.write_text(text, encoding="utf-8")


def _copy_sample(tmp: Path) -> Path:
    """Copy examples/sample-workspace to tmp/sample-workspace and patch agent
    start_command for cross-platform Python invocation."""
    ws = tmp / "sample-workspace"
    shutil.copytree(SAMPLE_WORKSPACE, ws)
    _patch_python_executable(ws)
    return ws


def _exp_dir(ws: Path) -> Path:
    return ws / "experiments" / "001-faq-conciseness"


# ===========================================================================
# Group 1: Full product flow acceptance
# ===========================================================================


class TestSampleWorkspaceFullFlow(unittest.TestCase):

    def test_full_product_flow(self):
        with TemporaryDirectory() as t:
            ws = _copy_sample(Path(t))
            exp = _exp_dir(ws)

            # Run full flow
            probe = _run_cli(ws, "probe", "001")
            self.assertIn("probe_id", probe.stdout)
            self.assertIn("status=ok", probe.stdout)

            run = _run_cli(ws, "run", "001")
            self.assertIn("V1", run.stdout)
            self.assertIn("V2", run.stdout)

            score = _run_cli(ws, "score", "001")
            self.assertIn("V1", score.stdout)
            self.assertIn("V2", score.stdout)

            compare = _run_cli(ws, "compare", "001")
            self.assertIn("Evidence", compare.stdout)

            # Probe-results exist
            probe_root = exp / "probe-results"
            self.assertTrue(probe_root.exists())
            probe_dirs = sorted(probe_root.iterdir())
            self.assertEqual(len(probe_dirs), 1)
            probe_dir = probe_dirs[0]
            self.assertTrue((probe_dir / "V1.json").exists())
            self.assertTrue((probe_dir / "V2.json").exists())

            # Run records exist
            run_files = sorted((exp / "results").glob("run-*.json"))
            self.assertEqual(len(run_files), 1)
            run_records = json.loads(run_files[0].read_text(encoding="utf-8"))
            # 2 variants × 2 cases = 4 records
            self.assertEqual(len(run_records), 4)
            for r in run_records:
                self.assertIn(r["version_id"], ("V1", "V2"))
                self.assertIn(r["case_id"], ("C1", "C2"))
                self.assertEqual(r.get("error", ""), "")
                self.assertGreater(len(r.get("transcript", [])), 0)

            # Score JSON has evidence
            score_files = sorted((exp / "results").glob("score-*.json"))
            self.assertEqual(len(score_files), 1)
            score_data = json.loads(score_files[0].read_text(encoding="utf-8"))
            self.assertIn("evidence", score_data)
            ev = score_data["evidence"]
            self.assertIn("variants", ev)
            self.assertIn("V1", ev["variants"])
            self.assertIn("V2", ev["variants"])

            # Compare md has ## Evidence
            compare_files = sorted((exp / "results").glob("compare-*.md"))
            self.assertEqual(len(compare_files), 1)
            compare_text = compare_files[0].read_text(encoding="utf-8")
            self.assertIn("## Evidence", compare_text)

            # V2 snapshot has harness_package block with all 3 hashes
            snap_root = exp / "results" / "snapshots"
            snap_run_dirs = list(snap_root.iterdir())
            self.assertEqual(len(snap_run_dirs), 1)
            snap_run_dir = snap_run_dirs[0]
            v2_snap = json.loads(
                (snap_run_dir / "V2.json").read_text(encoding="utf-8"))
            hp = v2_snap.get("harness_package")
            self.assertIsNotNone(hp)
            self.assertEqual(hp["id"], "concise-prompt")
            self.assertEqual(hp["version"], "0.1.0")
            self.assertEqual(hp["ref"], "concise-prompt@0.1.0")
            self.assertTrue(hp["manifest_hash"].startswith("sha256:"))
            self.assertTrue(hp["payload_hash"].startswith("sha256:"))
            self.assertTrue(hp["effective_harness_hash"].startswith("sha256:"))
            self.assertEqual(hp["install_order"], ["package", "patch"])

            # V1 snapshot has harness_package: null (no package)
            v1_snap = json.loads(
                (snap_run_dir / "V1.json").read_text(encoding="utf-8"))
            self.assertIsNone(v1_snap.get("harness_package"))

            # V1 vs V2 score totals differ
            scores_by_vid: dict[str, list[float]] = {}
            for s in score_data["scores"]:
                scores_by_vid.setdefault(s["version_id"], []).append(s["total"])
            v1_total = sum(scores_by_vid["V1"]) / len(scores_by_vid["V1"])
            v2_total = sum(scores_by_vid["V2"]) / len(scores_by_vid["V2"])
            self.assertNotEqual(
                v1_total, v2_total,
                f"V1 ({v1_total}) vs V2 ({v2_total}) totals should differ — "
                f"concise-prompt package must change agent behavior; if equal, "
                f"the sample no longer demonstrates a measurable delta.")

            # Compare report should mention the package
            self.assertTrue(
                "concise-prompt" in compare_text
                or "harness_package" in compare_text,
                f"compare report should mention concise-prompt or "
                f"harness_package: first 600 chars = {compare_text[:600]!r}")


# ===========================================================================
# Group 2: Score determinism across consecutive runs
# ===========================================================================


class TestSampleWorkspaceDeterminism(unittest.TestCase):

    def _flow_and_collect_scores(self, ws: Path) -> list[tuple]:
        """Run probe→run→score→compare; return sorted (vid, cid, total) tuples
        from the LATEST score file."""
        _run_cli(ws, "probe", "001")
        _run_cli(ws, "run", "001")
        _run_cli(ws, "score", "001")
        _run_cli(ws, "compare", "001")
        exp = _exp_dir(ws)
        score_files = sorted((exp / "results").glob("score-*.json"))
        self.assertGreaterEqual(len(score_files), 1)
        data = json.loads(score_files[-1].read_text(encoding="utf-8"))
        return sorted(
            (s["version_id"], s["case_id"], s["total"]) for s in data["scores"])

    def test_two_runs_yield_identical_scores(self):
        with TemporaryDirectory() as t:
            ws = _copy_sample(Path(t))

            # Run 1
            scores1 = self._flow_and_collect_scores(ws)

            # Sleep ≥1s so the second run's timestamp differs (avoids run_id
            # collision in sandbox/<run_id>/ directory naming).
            time.sleep(1.1)

            # Run 2
            scores2 = self._flow_and_collect_scores(ws)

            self.assertEqual(scores1, scores2,
                              f"Scores should be deterministic across runs.\n"
                              f"Run 1: {scores1}\nRun 2: {scores2}")


# ===========================================================================
# Group 3: Repo sample workspace stays clean (no generated artifacts committed)
# ===========================================================================


class TestRepoSampleWorkspaceClean(unittest.TestCase):

    def test_no_generated_artifacts_in_committed_sample(self):
        """Per Kun decision 6 + .gitignore: examples/sample-workspace must
        not contain generated results/probe-results/sandbox/materials-evidence."""
        exp = SAMPLE_WORKSPACE / "experiments" / "001-faq-conciseness"
        forbidden = [
            (exp / "results", "results/ — generated by ahl run / score / compare"),
            (exp / "probe-results", "probe-results/ — generated by ahl probe"),
            (exp / "sandbox", "sandbox/ — generated by ahl run (materialize)"),
            (exp / "materials" / "runtime-evidence.md",
             "materials/runtime-evidence.md — generated by ahl probe --write-evidence"),
        ]
        for path, why in forbidden:
            self.assertFalse(
                path.exists(),
                f"committed sample workspace must not contain {path.name} "
                f"({why}); add to .gitignore or delete before committing.")


if __name__ == "__main__":
    unittest.main()
