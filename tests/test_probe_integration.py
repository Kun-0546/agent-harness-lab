"""Integration tests for v0.6 Runtime Probe MVP.

Covers:
- workflow.probe() orchestration end-to-end
- --write-evidence behavior (ok/warn writes, fail does NOT)
- review.probe_summary read-only display
- CLI surface (subprocess): ahl probe --help, ahl probe full flow
- Redlines: 14 subcommands (init/walk/connect/new/show/cases/rubric/simulator/
  harnesses/run/score/compare/review/**probe**), probe doesn't mutate source
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness_lab import workflow

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"


def _env() -> dict:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(SRC_PATH)
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def _run_cli(workspace: Path, *args: str, expect_exit: int | None = 0,
              timeout: int = 60) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [sys.executable, "-m", "agent_harness_lab", *args],
        cwd=workspace, env=_env(), text=True,
        capture_output=True, encoding="utf-8", timeout=timeout,
    )
    if expect_exit is not None:
        assert r.returncode == expect_exit, (
            f"`ahl {' '.join(args)}` expected {expect_exit}, got "
            f"{r.returncode}\nstdout: {r.stdout!r}\nstderr: {r.stderr!r}"
        )
    return r


# ===========================================================================
# Helpers
# ===========================================================================


def _write_minimal_experiment(workspace: Path, name: str = "probe-demo",
                                with_runtime: bool = True,
                                with_package: bool = False):
    """Create a minimal experiment via CLI; optionally add runtime + package fixtures."""
    _run_cli(workspace, "init")
    _run_cli(workspace, "new", name, "--mode", "manual")
    exp_dir = workspace / "experiments" / f"001-{name}"

    if with_runtime:
        # tiny local runtime
        rt = workspace / "tiny-rt"
        rt.mkdir()
        (rt / "agent.py").write_text("print('hi')\n", encoding="utf-8")
        (workspace / "runtime-sources.md").write_text(
            f"# sources\n\n## local-rt\ntype: local_path\npath: {rt}\n",
            encoding="utf-8")

    if with_package:
        pkg = workspace / "harness-packages" / "smoke-pkg" / "0.1.0"
        (pkg / "payload").mkdir(parents=True)
        (pkg / "payload" / "sys.md").write_text("PKG\n", encoding="utf-8")
        (pkg / "manifest.md").write_text("""---
id: smoke-pkg
version: 0.1.0
runtime_compatibility: [local_path, git_repo]
---

## Description
probe integration test pkg

## Payload

files:
  - target: prompts/sys.md
    source: payload/sys.md
start_command: python agent.py
""", encoding="utf-8")

    return exp_dir


def _write_baseline_variant(exp_dir: Path):
    """Write a minimal V1 baseline."""
    (exp_dir / "harnesses" / "V1.md").write_text("""---
id: V1
基线: 是
runtime_source: local-rt
---

## 这是什么
baseline

## Patch

start_command: python agent.py
""", encoding="utf-8")


def _write_packaged_variant(exp_dir: Path, vid: str = "V2"):
    (exp_dir / "harnesses" / f"{vid}.md").write_text(f"""---
id: {vid}
基线: 否
runtime_source: local-rt
harness_package: smoke-pkg@0.1.0
---

## 这是什么
packaged variant
""", encoding="utf-8")


def _write_legacy_variant(exp_dir: Path, workspace: Path, vid: str = "V3"):
    (workspace / "connect.md").write_text("""# connect

## 类型
外部命令行

## 配置
命令:python -c "print('ok')"
""", encoding="utf-8")
    (exp_dir / "harnesses" / f"{vid}.md").write_text(f"""---
id: {vid}
基线: 否
---

## 这是什么
legacy connect variant
""", encoding="utf-8")


# ===========================================================================
# Group: workflow.probe() orchestration
# ===========================================================================


class TestWorkflowProbe(unittest.TestCase):

    def test_materialized_variant_probe_ok(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            result = workflow.probe(exp_dir)
            self.assertEqual(result.overall_status, "ok")
            self.assertEqual(result.counts["ok"], 1)
            self.assertEqual(result.counts["fail"], 0)
            self.assertIn("V1", result.variants)
            v1 = result.variants["V1"]
            self.assertEqual(v1["runtime_source"]["status"], "ok")
            self.assertEqual(v1["runtime_source"]["type"], "local_path")
            self.assertIsNone(v1["harness_package"])  # no package
            artifact_path = result.probe_dir / "V1.json"
            self.assertTrue(artifact_path.exists())

    def test_packaged_variant_probe_ok(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(
                ws, with_runtime=True, with_package=True)
            _write_baseline_variant(exp_dir)
            _write_packaged_variant(exp_dir, "V2")
            result = workflow.probe(exp_dir)
            self.assertEqual(result.overall_status, "ok")
            v2 = result.variants["V2"]
            self.assertIsNotNone(v2["harness_package"])
            self.assertEqual(v2["harness_package"]["status"], "ok")
            self.assertEqual(v2["harness_package"]["ref"], "smoke-pkg@0.1.0")

    def test_missing_package_fails_variant_but_probe_continues(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(
                ws, with_runtime=True, with_package=False)
            _write_baseline_variant(exp_dir)
            _write_packaged_variant(exp_dir, "V2")  # smoke-pkg not created
            result = workflow.probe(exp_dir)
            self.assertEqual(result.overall_status, "fail")
            self.assertEqual(result.variants["V1"]["status"], "ok")
            self.assertEqual(result.variants["V2"]["status"], "fail")
            self.assertEqual(
                result.variants["V2"]["harness_package"]["status"], "fail")
            self.assertTrue((result.probe_dir / "V1.json").exists())
            self.assertTrue((result.probe_dir / "V2.json").exists())

    def test_probe_does_not_create_sandbox(self):
        """Probe is read-only; must not create sandbox/ dir."""
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            sandbox_before = (exp_dir / "sandbox").exists()
            workflow.probe(exp_dir)
            sandbox_after = (exp_dir / "sandbox").exists()
        self.assertEqual(sandbox_before, sandbox_after,
                         "probe must not create sandbox dir")
        self.assertFalse(sandbox_after, "no sandbox should exist after probe")

    def test_probe_does_not_create_snapshot(self):
        """Probe is read-only; must not write to results/snapshots/."""
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            workflow.probe(exp_dir)
            snap_dir = exp_dir / "results" / "snapshots"
            self.assertFalse(
                snap_dir.exists(),
                "probe must not create results/snapshots/ dir")

    def test_probe_writes_artifact_at_versioned_path(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            result = workflow.probe(exp_dir)
        # probe_results/<probe_id>/V1.json
        parts = result.probe_dir.relative_to(exp_dir).parts
        self.assertEqual(parts[0], "probe-results")
        self.assertTrue(parts[1].startswith("probe-"))


# ===========================================================================
# Group: --write-evidence behavior
# ===========================================================================


class TestWriteEvidenceFlag(unittest.TestCase):

    def test_legacy_ok_writes_runtime_evidence_md(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=False)
            _write_legacy_variant(exp_dir, ws, "V1")
            result = workflow.probe(exp_dir, write_evidence=True)
            self.assertEqual(len(result.evidence_writes), 1,
                              f"expected 1 evidence write; "
                              f"V1 status: {result.variants['V1']['status']}")
            ev_path = Path(result.evidence_writes[0])
            self.assertTrue(ev_path.exists())
            self.assertEqual(ev_path.name, "runtime-evidence.md")
            content = ev_path.read_text(encoding="utf-8")
            self.assertIn("V1", content)
            self.assertIn("cloud attestation", content)
            self.assertIn(result.probe_id, content)

    def test_legacy_fail_does_not_write_evidence(self):
        """Spec §7.4 correction: fail status MUST NOT write materials evidence."""
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=False)
            # legacy variant but NO connect.md → fail status
            (exp_dir / "harnesses" / "V1.md").write_text("""---
id: V1
基线: 是
---

## 这是什么
legacy with no connect (should fail probe)
""", encoding="utf-8")
            result = workflow.probe(exp_dir, write_evidence=True)
        self.assertEqual(result.variants["V1"]["status"], "fail")
        self.assertEqual(result.evidence_writes, [],
                         "fail status must NOT write materials/runtime-evidence.md")
        materials = exp_dir / "materials"
        if materials.exists():
            self.assertFalse((materials / "runtime-evidence.md").exists())

    def test_materialized_write_evidence_skipped(self):
        """--write-evidence on materialized variants → no-op, tracked in skipped list."""
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            result = workflow.probe(exp_dir, write_evidence=True)
        # V1 is materialized → not eligible for materials evidence write
        self.assertEqual(result.evidence_writes, [])
        self.assertIn("V1", result.materialized_write_skipped)


# ===========================================================================
# Group: review.probe_summary read-only display
# ===========================================================================


class TestReviewProbeDisplay(unittest.TestCase):

    def test_review_with_no_probe_artifact(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            result = workflow.review(exp_dir)
        self.assertIsNone(result.probe_summary)

    def test_review_after_probe_shows_summary(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            workflow.probe(exp_dir)
            result = workflow.review(exp_dir)
        self.assertIsNotNone(result.probe_summary)
        s = result.probe_summary
        self.assertIn("probe_id", s)
        self.assertEqual(s["counts"]["ok"], 1)

    def test_review_does_not_trigger_probe(self):
        """review must be read-only — calling review must NOT create probe-results."""
        with TemporaryDirectory() as t:
            ws = Path(t)
            exp_dir = _write_minimal_experiment(ws, with_runtime=True)
            _write_baseline_variant(exp_dir)
            probe_root = exp_dir / "probe-results"
            self.assertFalse(probe_root.exists())
            workflow.review(exp_dir)
            self.assertFalse(probe_root.exists(),
                              "review must not create probe-results")


# ===========================================================================
# Group: CLI surface
# ===========================================================================


class TestCliProbeSurface(unittest.TestCase):

    def test_probe_help_exists(self):
        r = subprocess.run(
            [sys.executable, "-m", "agent_harness_lab", "probe", "--help"],
            capture_output=True, text=True, encoding="utf-8",
            env=_env(),
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("--command", r.stdout)
        self.assertIn("--write-evidence", r.stdout)
        self.assertIn("--timeout", r.stdout)

    def test_help_lists_probe_subcommand(self):
        r = subprocess.run(
            [sys.executable, "-m", "agent_harness_lab", "--help"],
            capture_output=True, text=True, encoding="utf-8",
            env=_env(),
        )
        self.assertEqual(r.returncode, 0)
        cmd_section = r.stdout.split("positional arguments")[1].split(
            "options:")[0]
        # 14 subcommands now (13 v0.5 + probe)
        expected = ["init", "walkthrough", "connect", "new", "show", "cases",
                    "rubric", "simulator", "harnesses", "run", "score",
                    "compare", "review", "probe"]
        for cmd in expected:
            self.assertTrue(
                any(line.strip().startswith(cmd) for line in cmd_section.splitlines()),
                f"missing subcommand {cmd!r} in --help")

    def test_probe_cli_e2e_with_materialized_variant(self):
        with TemporaryDirectory() as t:
            ws = Path(t)
            _run_cli(ws, "init")
            _run_cli(ws, "new", "demo", "--mode", "manual")
            # runtime-sources
            rt = ws / "tiny-rt"
            rt.mkdir()
            (rt / "a.py").write_text("x", encoding="utf-8")
            (ws / "runtime-sources.md").write_text(
                f"# sources\n\n## local-rt\ntype: local_path\npath: {rt}\n",
                encoding="utf-8")
            # baseline variant
            (ws / "experiments" / "001-demo" / "harnesses" / "V1.md").write_text("""---
id: V1
基线: 是
runtime_source: local-rt
---

## 这是什么
baseline

## Patch
start_command: python a.py
""", encoding="utf-8")
            # ahl probe → exit 0, prints "ok"
            r = _run_cli(ws, "probe", "001-demo")
            self.assertIn("status=ok", r.stdout)
            self.assertIn("probe_id", r.stdout)
            self.assertIn("artifact:", r.stdout)

    def test_probe_exit_1_on_fail(self):
        """Per spec §16 locked decision 4: any variant fail → exit 1."""
        with TemporaryDirectory() as t:
            ws = Path(t)
            _run_cli(ws, "init")
            _run_cli(ws, "new", "demo", "--mode", "manual")
            # runtime-sources.md references a non-existent path → probe fail
            (ws / "runtime-sources.md").write_text(
                f"# sources\n\n## local-rt\ntype: local_path\npath: "
                f"{ws / 'definitely-not-here'}\n",
                encoding="utf-8")
            (ws / "experiments" / "001-demo" / "harnesses" / "V1.md").write_text("""---
id: V1
基线: 是
runtime_source: local-rt
---

## 这是什么
baseline

## Patch
start_command: python a.py
""", encoding="utf-8")
            r = _run_cli(ws, "probe", "001-demo", expect_exit=1)
        self.assertIn("status=fail", r.stdout)
        # Reason should be printed
        self.assertIn("does not exist", r.stdout)


# ===========================================================================
# Group: Redlines (v0.6 must not break v0.5 / no scoring/comparator change)
# ===========================================================================


class TestV06Redlines(unittest.TestCase):

    def test_no_new_cli_beyond_probe(self):
        """ahl --help shows exactly 14 subcommands (13 v0.5 + probe)."""
        r = subprocess.run(
            [sys.executable, "-m", "agent_harness_lab", "--help"],
            capture_output=True, text=True, encoding="utf-8",
            env=_env(),
        )
        self.assertEqual(r.returncode, 0)
        cmd_section = r.stdout.split("positional arguments")[1].split(
            "options:")[0]
        # Forbid v0.6 surprise commands
        forbidden = ["packages", "pack", "inspect", "iterate", "auto"]
        for f in forbidden:
            line_starts = [f"    {f} ", f"    {f}\t", f"    {f}\n"]
            self.assertFalse(
                any(s in cmd_section for s in line_starts),
                f"unexpected subcommand {f!r} appeared in --help")


if __name__ == "__main__":
    unittest.main()
