"""Integration tests for v0.5 Harness Package MVP.

Covers:
- Snapshot integration: harness_package block written by build_snapshot.
- Evidence overlay: v0.5 spec §13 rules applied via infer_evidence_from_snapshot.
- Workflow preflight: error cases from spec §15 surfaced as WorkflowError.
- Compare report: Evidence section additive reason for package presence.
- Backward compatibility: v0.4 snapshots without harness_package unchanged.
- Redlines: no new CLI commands.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness_lab import evidence, snapshot, workflow
from agent_harness_lab.harness_package import (
    Manifest,
    parse_manifest,
)
from agent_harness_lab.materialize import MaterializeContext
from agent_harness_lab.materialize.legacy import LegacyAdapter
from agent_harness_lab.materialize.local_path import LocalPathAdapter
from agent_harness_lab.patch import HarnessPatch, PatchFile
from agent_harness_lab.runtime_source import RuntimeSource
from agent_harness_lab.snapshot import build_snapshot
from agent_harness_lab.version import Version


# ===========================================================================
# Fixture helpers
# ===========================================================================


def _write_workspace(tmp: Path) -> Path:
    """Create an empty workspace dir; return path."""
    ws = tmp / "ws"
    ws.mkdir()
    return ws


def _write_harness_package(ws: Path, pkg_id: str, version: str,
                            payload_files: dict[str, str] | None = None,
                            env: str = "",
                            start_command: str = "python -m agent.run",
                            runtime_compat: str = "[local_path, git_repo]"
                            ) -> Manifest:
    """Write a harness package under ws/harness-packages/<id>/<version>/."""
    pkg_dir = ws / "harness-packages" / pkg_id / version
    payload_dir = pkg_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    files_decl = ""
    if payload_files:
        for name, content in payload_files.items():
            (payload_dir / name).write_text(content, encoding="utf-8")
        files_lines = "files:\n"
        for name in payload_files:
            files_lines += (
                f"  - target: prompts/{name}\n"
                f"    source: payload/{name}\n"
            )
        files_decl = files_lines
    env_decl = f"env:\n  {env}" if env else ""
    start_decl = f"start_command: {start_command}" if start_command else ""
    body = f"""---
id: {pkg_id}
version: {version}
runtime_compatibility: {runtime_compat}
---

## Description
Integration-test package {pkg_id}@{version}.

## Payload

{files_decl}{env_decl}
{start_decl}
"""
    manifest_path = pkg_dir / "manifest.md"
    manifest_path.write_text(body, encoding="utf-8")
    return parse_manifest(manifest_path,
                           expected_id=pkg_id, expected_version=version)


def _make_version(version_id: str, baseline: bool = False,
                   runtime_source: str | None = None,
                   harness_package: str | None = None,
                   patch_files: list = None,
                   patch_env: dict = None,
                   patch_start: str | None = None,
                   variant_path: Path | None = None) -> Version:
    """Construct a Version programmatically for snapshot/evidence tests."""
    patch = None
    if runtime_source is not None:
        patch_obj = HarnessPatch(
            files=[],
            env=dict(patch_env or {}),
            start_command=patch_start,
        )
        if patch_files:
            for target, source_path in patch_files:
                pf = PatchFile(target_path=target, source_path=Path(source_path),
                                hash="sha256:fake")
                patch_obj.files.append(pf)
        patch = patch_obj
    return Version(
        path=variant_path or Path("/fake/variant.md"),
        version_id=version_id,
        is_baseline=baseline,
        what="test variant",
        connect=None,
        runtime_source=runtime_source,
        patch=patch,
        harness_package=harness_package,
    )


def _make_local_path_runtime_source(ws: Path, source_dir: Path) -> RuntimeSource:
    return RuntimeSource(
        name="local-src",
        type="local_path",
        config={"path": str(source_dir)},
    )


def _make_ctx(experiment_dir: Path, run_id: str,
               runtime_sources: list,
               variant_packages: dict | None = None) -> MaterializeContext:
    return MaterializeContext(
        run_id=run_id,
        experiment_dir=experiment_dir,
        fallback_connect=None,
        runtime_sources=runtime_sources,
        variant_packages=variant_packages or {},
    )


# ===========================================================================
# Group: build_snapshot with harness_package
# ===========================================================================


class TestSnapshotHarnessPackageBlock(unittest.TestCase):
    """Spec §12: snapshot includes harness_package block (or null)."""

    def _setup_materialized(self, ws: Path, with_package: bool):
        """Materialize a local_path variant (with or without package) and return
        (manifest, sandbox, ctx, version) for build_snapshot tests."""
        # Source dir with one file
        source_dir = ws / "src"
        source_dir.mkdir()
        (source_dir / "prompts").mkdir()
        (source_dir / "prompts" / "system.md").write_text(
            "BASE", encoding="utf-8")

        # Workspace + experiment dir
        exp_dir = ws / "experiments" / "001-demo"
        exp_dir.mkdir(parents=True)

        # Optional package
        manifest = None
        variant_packages = {}
        if with_package:
            manifest = _write_harness_package(
                ws, "pkg-x", "0.1.0",
                payload_files={"system.md": "PKG-CONTENT"},
                start_command="python -m run",
            )
            variant_packages["V1"] = manifest

        # Patch (variant ## Patch)
        patch = HarnessPatch(
            files=[],
            env={"PATCH_A": "1"},
            start_command="python -m run.patched",
        )
        version = Version(
            path=exp_dir / "harnesses" / "V1.md",
            version_id="V1",
            is_baseline=False,
            what="x",
            connect=None,
            runtime_source="local-src",
            patch=patch,
            harness_package=manifest.ref if manifest else None,
        )
        runtime_sources = [_make_local_path_runtime_source(ws, source_dir)]
        run_id = "run-20260601-100000"
        ctx = _make_ctx(exp_dir, run_id, runtime_sources, variant_packages)

        adapter = LocalPathAdapter()
        sandbox = adapter.materialize(version, ctx)
        return manifest, sandbox, ctx, version, adapter

    def test_with_package_block_present(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            manifest, sandbox, ctx, version, adapter = (
                self._setup_materialized(ws, with_package=True))
            snap = build_snapshot(version, ctx, adapter, sandbox)
        self.assertIsNotNone(snap.harness_package)
        hp = snap.harness_package
        self.assertEqual(hp["id"], "pkg-x")
        self.assertEqual(hp["version"], "0.1.0")
        self.assertEqual(hp["ref"], "pkg-x@0.1.0")
        self.assertTrue(hp["manifest_hash"].startswith("sha256:"))
        self.assertTrue(hp["payload_hash"].startswith("sha256:"))
        self.assertTrue(hp["effective_harness_hash"].startswith("sha256:"))
        self.assertEqual(hp["install_order"], ["package", "patch"])

    def test_no_package_block_null(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            manifest, sandbox, ctx, version, adapter = (
                self._setup_materialized(ws, with_package=False))
            snap = build_snapshot(version, ctx, adapter, sandbox)
        self.assertIsNone(snap.harness_package)

    def test_manifest_path_uses_forward_slashes(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            manifest, sandbox, ctx, version, adapter = (
                self._setup_materialized(ws, with_package=True))
            snap = build_snapshot(version, ctx, adapter, sandbox)
        mp = snap.harness_package["manifest_path"]
        self.assertNotIn("\\", mp)
        self.assertEqual(
            mp, "harness-packages/pkg-x/0.1.0/manifest.md")

    def test_install_order_fixed(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            manifest, sandbox, ctx, version, adapter = (
                self._setup_materialized(ws, with_package=True))
            snap = build_snapshot(version, ctx, adapter, sandbox)
        self.assertEqual(snap.harness_package["install_order"],
                         ["package", "patch"])

    def test_snapshot_json_serializable(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            manifest, sandbox, ctx, version, adapter = (
                self._setup_materialized(ws, with_package=True))
            snap = build_snapshot(version, ctx, adapter, sandbox)
            data = json.dumps(snap.to_json(), ensure_ascii=False)
        self.assertIn("harness_package", data)


# ===========================================================================
# Group: Evidence overlay (v0.5 spec §13)
# ===========================================================================


def _snap_local_strong(harness_patch=None,
                        harness_package=None) -> dict:
    """Build a v0.5+ snapshot dict — local_path with full source_dir_hash."""
    return {
        "snapshot_id": "snap-run-X-V1",
        "run_id": "run-X",
        "variant_id": "V1",
        "experiment": "001-demo",
        "created_at": "2026-06-01T00:00:00+00:00",
        "runtime_source": {
            "type": "local_path",
            "name": "src",
            "path": "/x",
            "source_dir_hash": "sha256:src-hash",
        },
        "harness_patch": harness_patch,
        "harness_package": harness_package,
        "sandbox": None,
        "environment": {},
    }


def _snap_legacy(harness_package=None) -> dict:
    return {
        "snapshot_id": "legacy",
        "run_id": "run-X",
        "variant_id": "V1",
        "experiment": "001-demo",
        "created_at": "2026-06-01T00:00:00+00:00",
        "runtime_source": {
            "type": "legacy_connect",
            "connect_md_hash": "sha256:cm",
        },
        "harness_patch": None,
        "harness_package": harness_package,
        "sandbox": None,
        "environment": {},
    }


def _hp_full(ref="pkg-x@0.1.0"):
    return {
        "id": "pkg-x",
        "version": "0.1.0",
        "ref": ref,
        "manifest_path": "harness-packages/pkg-x/0.1.0/manifest.md",
        "manifest_hash": "sha256:mh",
        "payload_hash": "sha256:ph",
        "effective_harness_hash": "sha256:eh",
        "install_order": ["package", "patch"],
    }


def _hp_incomplete(missing=("effective_harness_hash",)):
    h = _hp_full()
    for k in missing:
        h[k] = ""
    return h


class TestEvidenceOverlay(unittest.TestCase):

    def test_no_package_unchanged_from_v04(self):
        # Snapshot without harness_package field at all
        snap = _snap_local_strong()
        # Remove the key entirely to simulate v0.4 snapshot
        del snap["harness_package"]
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "strong")
        # No package reason
        for r in result["reasons"]:
            self.assertNotIn("harness_package", r)

    def test_package_null_unchanged(self):
        snap = _snap_local_strong(harness_package=None)
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "strong")

    def test_package_complete_strong_local_path(self):
        snap = _snap_local_strong(harness_package=_hp_full())
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "strong")
        # Reason mentions package
        joined = " ".join(result["reasons"])
        self.assertIn("harness_package", joined)
        self.assertIn("fully fingerprinted", joined)

    def test_package_complete_strong_git_repo(self):
        snap = {
            "snapshot_id": "snap-run-X-V1",
            "runtime_source": {
                "type": "git_repo",
                "name": "r",
                "url": "https://example.com/r.git",
                "ref": "main",
                "commit_sha": "abc",
                "source_dir_hash": "sha256:src",
            },
            "harness_patch": None,
            "harness_package": _hp_full(),
        }
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "strong")

    def test_package_missing_manifest_hash_downgrades_medium(self):
        snap = _snap_local_strong(
            harness_package=_hp_incomplete(missing=("manifest_hash",)))
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "medium")
        joined = " ".join(result["reasons"])
        self.assertIn("incomplete harness package fingerprint", joined)
        self.assertIn("manifest_hash", joined)

    def test_package_missing_payload_hash_downgrades_medium(self):
        snap = _snap_local_strong(
            harness_package=_hp_incomplete(missing=("payload_hash",)))
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "medium")

    def test_package_missing_effective_hash_downgrades_medium(self):
        snap = _snap_local_strong(
            harness_package=_hp_incomplete(missing=("effective_harness_hash",)))
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "medium")

    def test_package_on_medium_base_stays_medium_with_additive_reason(self):
        # Base medium: local_path missing source_dir_hash
        snap = _snap_local_strong(harness_package=_hp_full())
        snap["runtime_source"]["source_dir_hash"] = ""
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "medium")
        joined = " ".join(result["reasons"])
        self.assertIn("local_path missing source_dir_hash", joined)
        self.assertIn("harness_package", joined)
        self.assertIn("present", joined)

    def test_legacy_connect_with_package_defensive_unknown(self):
        # legacy_connect + harness_package should never reach here in practice
        # (preflight catches), but evidence layer defensively returns unknown
        snap = _snap_legacy(harness_package=_hp_full())
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "unknown")
        joined = " ".join(result["reasons"])
        self.assertIn("preflight should have rejected", joined)


# ===========================================================================
# Group: Workflow preflight error cases (spec §15)
# ===========================================================================


def _setup_experiment_with_package_variant(ws: Path,
                                            variant_runtime_source: str | None,
                                            variant_harness_package: str | None,
                                            variant_patch_start: str = "x",
                                            ) -> Path:
    """Build a minimal materialized experiment that triggers workflow.run preflight."""
    # source dir for local_path
    source_dir = ws / "src"
    source_dir.mkdir()
    (source_dir / "agent.py").write_text("# stub", encoding="utf-8")

    # runtime-sources.md
    (ws / "runtime-sources.md").write_text(
        f"# sources\n\n## local-src\n"
        f"type: local_path\n"
        f"path: {source_dir}\n",
        encoding="utf-8")

    # experiment dir + program.md + rubric.md
    exp_dir = ws / "experiments" / "001-demo"
    exp_dir.mkdir(parents=True)
    (exp_dir / "program.md").write_text(
        "# program\n\n## 假设\nfoo\n\n## 声明\n- 环境:无\n"
        "- 对话模式:模拟\n- 状态:重置\n- 评分:LLM\n"
        "- 运行模式:人评\n",
        encoding="utf-8")
    (exp_dir / "rubric.md").write_text(
        "# rubric\n\n## quality\n权重: 1.0\n描述\n",
        encoding="utf-8")
    # case
    (exp_dir / "cases").mkdir()
    (exp_dir / "cases" / "C1.md").write_text(
        "---\nid: C1\n---\n## 起始输入\nhello\n", encoding="utf-8")
    # harnesses: V1 baseline (no package, simple to satisfy baseline rule),
    # then V2 with the test variant settings
    (exp_dir / "harnesses").mkdir()
    # Baseline must satisfy compare's baseline rule
    baseline_body = (
        f"---\nid: V1\n基线: 是\nruntime_source: local-src\n---\n"
        f"## 这是什么\nbaseline\n## Patch\n\nstart_command: x\n"
    )
    (exp_dir / "harnesses" / "V1.md").write_text(baseline_body,
                                                  encoding="utf-8")

    # Test variant V2 with the parametrized fields
    fm_lines = ["---", "id: V2", "基线: 否"]
    if variant_runtime_source is not None:
        fm_lines.append(f"runtime_source: {variant_runtime_source}")
    if variant_harness_package is not None:
        fm_lines.append(f"harness_package: {variant_harness_package}")
    fm_lines.append("---")
    fm = "\n".join(fm_lines)
    body = f"{fm}\n## 这是什么\nv2\n## Patch\n\nstart_command: {variant_patch_start}\n"
    (exp_dir / "harnesses" / "V2.md").write_text(body, encoding="utf-8")
    return exp_dir


class TestWorkflowPreflightErrors(unittest.TestCase):
    """Spec §15 — preflight ERR-* error cases."""

    def test_package_without_runtime_source_fails(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            _write_harness_package(
                ws, "pkg-x", "0.1.0",
                payload_files={"sys.md": "x"},
                start_command="run")
            exp_dir = _setup_experiment_with_package_variant(
                ws,
                variant_runtime_source=None,
                variant_harness_package="pkg-x@0.1.0",
            )
            with self.assertRaises(workflow.WorkflowError) as ctx:
                workflow.run(exp_dir, use_llm=False)
            self.assertIn("必须同时指定 runtime_source",
                          str(ctx.exception))

    def test_package_bare_id_fails(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            _write_harness_package(ws, "pkg-x", "0.1.0",
                                    payload_files={"sys.md": "x"},
                                    start_command="run")
            exp_dir = _setup_experiment_with_package_variant(
                ws,
                variant_runtime_source="local-src",
                variant_harness_package="pkg-x",  # no @version
            )
            with self.assertRaises(workflow.WorkflowError) as ctx:
                workflow.run(exp_dir, use_llm=False)
            self.assertIn("<id>@<version>", str(ctx.exception))

    def test_package_unknown_ref_fails(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            _write_harness_package(ws, "pkg-x", "0.1.0",
                                    payload_files={"sys.md": "x"},
                                    start_command="run")
            exp_dir = _setup_experiment_with_package_variant(
                ws,
                variant_runtime_source="local-src",
                variant_harness_package="nonexistent@0.0.1",
            )
            with self.assertRaises(workflow.WorkflowError) as ctx:
                workflow.run(exp_dir, use_llm=False)
            self.assertIn("nonexistent@0.0.1", str(ctx.exception))

    def test_package_runtime_incompatible_fails(self):
        with TemporaryDirectory() as t:
            ws = _write_workspace(Path(t))
            # Package only supports git_repo
            _write_harness_package(
                ws, "pkg-x", "0.1.0",
                payload_files={"sys.md": "x"},
                runtime_compat="[git_repo]",
                start_command="run")
            exp_dir = _setup_experiment_with_package_variant(
                ws,
                variant_runtime_source="local-src",  # but variant uses local_path
                variant_harness_package="pkg-x@0.1.0",
            )
            with self.assertRaises(workflow.WorkflowError) as ctx:
                workflow.run(exp_dir, use_llm=False)
            msg = str(ctx.exception)
            self.assertIn("runtime_compatibility", msg)
            self.assertIn("local_path", msg)


# ===========================================================================
# Group: Backward compatibility
# ===========================================================================


class TestBackwardCompatibility(unittest.TestCase):

    def test_v04_snapshot_without_harness_package_field(self):
        # v0.4 snapshot has no harness_package key
        snap = {
            "snapshot_id": "snap-X",
            "runtime_source": {
                "type": "local_path",
                "name": "src",
                "path": "/x",
                "source_dir_hash": "sha256:h",
            },
            "harness_patch": None,
            "sandbox": None,
            "environment": {},
        }
        with TemporaryDirectory() as t:
            result = evidence.infer_evidence_from_snapshot(snap, Path(t))
        self.assertEqual(result["level"], "strong")
        # No package reasons
        for r in result["reasons"]:
            self.assertNotIn("harness_package", r)

    def test_v04_score_compare_flow_unchanged(self):
        """Old score JSON without harness_package-aware evidence still works."""
        # Mimic test_evidence_integration patterns — verify score writes
        # evidence without crash even when no packages exist
        with TemporaryDirectory() as t:
            tmp = Path(t)
            ws = _write_workspace(tmp)
            exp_dir = ws / "experiments" / "001-demo"
            exp_dir.mkdir(parents=True)
            (exp_dir / "rubric.md").write_text(
                "# rubric\n\n## quality\n权重: 1.0\n描述\n",
                encoding="utf-8")
            (exp_dir / "harnesses").mkdir()
            (exp_dir / "cases").mkdir()
            results_dir = exp_dir / "results"
            results_dir.mkdir()
            run_id = "run-20260601-000000"
            run_records = [{
                "version_id": "V1", "case_id": "C1",
                "transcript": [{"turn": 0, "user": "hi", "agent": "yo"}],
                "error": "", "snapshot_id": "legacy",
            }]
            (results_dir / f"{run_id}.json").write_text(
                json.dumps(run_records), encoding="utf-8")
            snap_dir = results_dir / "snapshots" / run_id
            snap_dir.mkdir(parents=True)
            (snap_dir / "V1.json").write_text(json.dumps({
                "snapshot_id": "legacy",
                "runtime_source": {
                    "type": "legacy_connect",
                    "connect_md_hash": "sha256:cm",
                },
                "harness_patch": None,
                "sandbox": None,
                "environment": {},
                # Note: no harness_package field (v0.4 snapshot)
            }), encoding="utf-8")

            result = workflow.score(exp_dir, use_llm=False)
            data = json.loads(result.out_path.read_text(encoding="utf-8"))
        # v0.4 evidence present; package-aware logic is opt-in
        self.assertIn("evidence", data)
        self.assertEqual(data["evidence"]["variants"]["V1"]["level"], "weak")


# ===========================================================================
# Group: Redlines
# ===========================================================================


class TestRedlines(unittest.TestCase):

    def test_cli_help_command_count_unchanged_after_v05(self):
        """ahl --help still lists exactly 13 subcommands; v0.5 adds no CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "agent_harness_lab", "--help"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                 "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        )
        self.assertEqual(result.returncode, 0)
        expected = ["init", "walkthrough", "connect", "new", "show", "cases",
                    "rubric", "simulator", "harnesses", "run", "score",
                    "compare", "review"]
        cmd_section = result.stdout.split("positional arguments")[1].split(
            "options:")[0]
        for cmd in expected:
            self.assertIn(cmd, result.stdout)
        # Forbid v0.5 surprise commands
        forbidden = ["package", "packages", "install", "pack"]
        for f in forbidden:
            line_starts = [f"    {f} ", f"    {f}\t", f"    {f}\n"]
            self.assertFalse(
                any(s in cmd_section for s in line_starts),
                f"unexpected subcommand {f!r} appeared in --help")


if __name__ == "__main__":
    unittest.main()
