"""Unit tests for runtime probe (probe.py).

Covers spec docs/runtime-probe-mvp.md §6 (per-target probe), §7 (artifact),
§10 (error handling), §16 locked decisions (truncation, timeout).
"""
from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness_lab import probe
from agent_harness_lab.harness_package import Manifest
from agent_harness_lab.materialize import MaterializeContext
from agent_harness_lab.patch import HarnessPatch
from agent_harness_lab.runtime_source import RuntimeSource
from agent_harness_lab.version import Version


# ===========================================================================
# Helpers / fixtures
# ===========================================================================


def _ctx(exp_dir: Path, runtime_sources=None, variant_packages=None,
          fallback_connect=None):
    return MaterializeContext(
        run_id="",
        experiment_dir=exp_dir,
        fallback_connect=fallback_connect,
        runtime_sources=runtime_sources or [],
        variant_packages=variant_packages or {},
    )


def _v(version_id="V1", runtime_source=None, harness_package=None,
        patch_start=None, patch_env=None):
    patch = None
    if runtime_source is not None:
        patch = HarnessPatch(files=[], env=dict(patch_env or {}),
                              start_command=patch_start)
    return Version(
        path=Path("/fake/V1.md"),
        version_id=version_id, is_baseline=False, what="x",
        connect=None,
        runtime_source=runtime_source,
        patch=patch,
        harness_package=harness_package,
    )


def _src(name, type_, **config):
    return RuntimeSource(name=name, type=type_, config=dict(config))


def _manifest(pkg_id="test-pkg", version="0.1.0", payload_dir=None,
               files=None, env=None, start_cmd="python a.py",
               compat=None):
    payload_files = []
    if files:
        for target, src_path in files.items():
            payload_files.append({"target": target, "source": Path(src_path)})
    return Manifest(
        id=pkg_id,
        version=version,
        runtime_compatibility=compat or ["local_path", "git_repo"],
        description="test",
        payload_files=payload_files,
        payload_env=env or {},
        payload_start_command=start_cmd,
        manifest_path=Path("/fake/manifest.md"),
        pkg_dir=Path("/fake"),
    )


# ===========================================================================
# Group: aggregate_status / truncate
# ===========================================================================


class TestAggregateStatus(unittest.TestCase):

    def test_fail_wins(self):
        self.assertEqual(probe._aggregate_status(["ok", "fail", "ok"]),
                         "fail")

    def test_warn_when_no_fail(self):
        self.assertEqual(probe._aggregate_status(["ok", "warn", "ok"]),
                         "warn")

    def test_skip_promotes_to_warn(self):
        self.assertEqual(probe._aggregate_status(["ok", "skip"]), "warn")

    def test_all_ok(self):
        self.assertEqual(probe._aggregate_status(["ok", "ok", "ok"]),
                         "ok")

    def test_empty(self):
        self.assertEqual(probe._aggregate_status([]), "ok")


class TestTruncate(unittest.TestCase):

    def test_short_text_unchanged(self):
        self.assertEqual(probe._truncate("hello"), "hello")

    def test_long_text_truncated(self):
        text = "A" * 5000
        out = probe._truncate(text)
        self.assertTrue(out.endswith("(truncated)"))
        # main body ≤ 1024 bytes
        body = out[:-len("(truncated)")]
        self.assertLessEqual(len(body.encode("utf-8")), 1024)

    def test_empty(self):
        self.assertEqual(probe._truncate(""), "")

    def test_utf8_safe(self):
        # Chinese chars are 3 bytes each in utf-8
        text = "中" * 1000   # 3000 bytes
        out = probe._truncate(text)
        self.assertTrue(out.endswith("(truncated)"))


# ===========================================================================
# Group: probe_runtime_source — local_path
# ===========================================================================


class TestProbeLocalPath(unittest.TestCase):

    def test_ok(self):
        with TemporaryDirectory() as t:
            src_dir = Path(t) / "src"
            src_dir.mkdir()
            (src_dir / "a.py").write_text("x", encoding="utf-8")
            src = _src("local-src", "local_path", path=str(src_dir))
            v = _v(runtime_source="local-src")
            result = probe.probe_runtime_source(
                v, _ctx(Path(t), runtime_sources=[src]))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["type"], "local_path")
        self.assertIn("source_dir_hash", result)
        self.assertTrue(result["source_dir_hash"].startswith("sha256:"))

    def test_path_does_not_exist(self):
        with TemporaryDirectory() as t:
            src = _src("local-src", "local_path",
                       path=str(Path(t) / "missing"))
            v = _v(runtime_source="local-src")
            result = probe.probe_runtime_source(
                v, _ctx(Path(t), runtime_sources=[src]))
        self.assertEqual(result["status"], "fail")
        self.assertIn("does not exist", result["reasons"][0])

    def test_runtime_source_ref_unknown(self):
        with TemporaryDirectory() as t:
            v = _v(runtime_source="nonexistent")
            result = probe.probe_runtime_source(v, _ctx(Path(t)))
        self.assertEqual(result["status"], "fail")
        self.assertIn("not in runtime-sources.md", result["reasons"][0])

    def test_legacy_no_connect(self):
        with TemporaryDirectory() as t:
            v = _v(runtime_source=None)  # legacy path
            result = probe.probe_runtime_source(v, _ctx(Path(t)))
        self.assertEqual(result["type"], "legacy_connect")
        self.assertEqual(result["status"], "fail")
        self.assertIn("no connect", result["reasons"][0])


# ===========================================================================
# Group: probe_runtime_source — git_repo (uses local file:// repo, no network)
# ===========================================================================


@unittest.skipUnless(shutil.which("git"), "git 不在 PATH —— 跳过 git_repo probe 集成测试")
class TestProbeGitRepo(unittest.TestCase):

    def _make_git_repo(self, tmp: Path) -> str:
        """Create a local git repo with one commit on main; return file:// URL."""
        from tests.githelper import git  # bounded, non-interactive git (no hang)
        repo = tmp / "repo"
        repo.mkdir()
        git(["init", "-b", "main"], cwd=repo)
        git(["config", "user.email", "t@t"], cwd=repo)
        git(["config", "user.name", "T"], cwd=repo)
        (repo / "README.md").write_text("x", encoding="utf-8")
        git(["add", "."], cwd=repo)
        git(["commit", "-m", "init"], cwd=repo)
        return f"file://{repo.as_posix()}"

    def test_ok(self):
        import shutil
        if shutil.which("git") is None:
            self.skipTest("git not in PATH")
        with TemporaryDirectory() as t:
            tmp = Path(t)
            url = self._make_git_repo(tmp)
            src = _src("repo", "git_repo", url=url, ref="main")
            v = _v(runtime_source="repo")
            result = probe.probe_runtime_source(
                v, _ctx(tmp, runtime_sources=[src]))
        self.assertEqual(result["status"], "ok")
        self.assertIn("remote_commit_sha", result)
        self.assertEqual(len(result["remote_commit_sha"]), 40)


# Need os import for git repo test environment
import os  # noqa: E402


# ===========================================================================
# Group: probe_harness_package
# ===========================================================================


class TestProbeHarnessPackage(unittest.TestCase):

    def test_no_package(self):
        v = _v(runtime_source="x")  # no harness_package
        self.assertIsNone(probe.probe_harness_package(v, None))

    def test_unresolved_ref(self):
        v = _v(runtime_source="x", harness_package="missing@0.1.0")
        result = probe.probe_harness_package(v, None)
        self.assertEqual(result["status"], "fail")
        self.assertIn("not resolved", result["reasons"][0])

    def test_ok(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            payload = tmp / "payload" / "system.md"
            payload.parent.mkdir(parents=True)
            payload.write_text("x", encoding="utf-8")
            m = _manifest(files={"prompts/sys.md": str(payload)})
            v = _v(runtime_source="x", harness_package="test-pkg@0.1.0")
            result = probe.probe_harness_package(v, m)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ref"], "test-pkg@0.1.0")
        self.assertTrue(result["manifest_readable"])

    def test_payload_missing(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            # source path doesn't exist
            m = _manifest(files={"prompts/sys.md": str(tmp / "missing.md")})
            v = _v(runtime_source="x", harness_package="test-pkg@0.1.0")
            result = probe.probe_harness_package(v, m)
        self.assertEqual(result["status"], "fail")
        self.assertIn("payload files missing", result["reasons"][0])


# ===========================================================================
# Group: probe_start_command + smoke command
# ===========================================================================


class TestProbeStartCommand(unittest.TestCase):

    def test_patch_wins(self):
        v = _v(runtime_source="x", patch_start="patch-cmd")
        m = _manifest(start_cmd="manifest-cmd")
        result = probe.probe_start_command(v, m, smoke_cmd=None)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["command"], "patch-cmd")
        self.assertEqual(result["source"], "patch")

    def test_fallback_to_manifest(self):
        v = _v(runtime_source="x")  # patch has no start_command
        m = _manifest(start_cmd="manifest-cmd")
        result = probe.probe_start_command(v, m, smoke_cmd=None)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["command"], "manifest-cmd")
        self.assertEqual(result["source"], "manifest")

    def test_both_empty_fails(self):
        v = _v(runtime_source="x")
        result = probe.probe_start_command(v, None, smoke_cmd=None)
        self.assertEqual(result["status"], "fail")
        self.assertIsNone(result["command"])

    def test_smoke_ok(self):
        v = _v(runtime_source="x", patch_start="cmd")
        cmd = f'"{sys.executable}" -c "print(\'hi\')"'
        result = probe.probe_start_command(v, None, smoke_cmd=cmd, timeout=10)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["smoke_executed"])
        self.assertEqual(result["smoke_status"], "ok")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("hi", result["stdout_truncated"])

    def test_smoke_nonzero_exit_is_warn(self):
        v = _v(runtime_source="x", patch_start="cmd")
        cmd = f'"{sys.executable}" -c "import sys; sys.exit(3)"'
        result = probe.probe_start_command(v, None, smoke_cmd=cmd, timeout=10)
        self.assertEqual(result["smoke_status"], "warn")
        self.assertEqual(result["exit_code"], 3)
        # start_command status propagated to warn
        self.assertEqual(result["status"], "warn")

    def test_smoke_timeout(self):
        v = _v(runtime_source="x", patch_start="cmd")
        cmd = f'"{sys.executable}" -c "import time; time.sleep(5)"'
        result = probe.probe_start_command(v, None, smoke_cmd=cmd, timeout=1)
        self.assertEqual(result["smoke_status"], "fail")
        self.assertEqual(result["status"], "fail")
        self.assertIn("timed out", result["stderr_truncated"])

    def test_smoke_not_found(self):
        v = _v(runtime_source="x", patch_start="cmd")
        result = probe.probe_start_command(
            v, None, smoke_cmd="this-binary-does-not-exist-zzz", timeout=5)
        self.assertEqual(result["smoke_status"], "fail")
        # Either FileNotFoundError or OSError caught
        combined = (result.get("stderr_truncated", "") or "").lower()
        self.assertTrue(
            "not found" in combined or "no such file" in combined
            or "cannot find" in combined,
            f"unexpected stderr: {combined!r}")

    def test_smoke_stdout_truncated_to_1kb(self):
        v = _v(runtime_source="x", patch_start="cmd")
        # Output 5000 'A' chars
        cmd = (f'"{sys.executable}" -c "import sys; '
               f'sys.stdout.write(\'A\' * 5000); sys.stdout.flush()"')
        result = probe.probe_start_command(v, None, smoke_cmd=cmd, timeout=10)
        self.assertEqual(result["smoke_status"], "ok")
        out = result["stdout_truncated"]
        self.assertTrue(out.endswith("(truncated)"))
        # body ≤ 1024 bytes
        body = out[:-len("(truncated)")]
        self.assertLessEqual(len(body.encode("utf-8")), 1024)


# ===========================================================================
# Group: probe_variant aggregation
# ===========================================================================


class TestProbeVariantAggregation(unittest.TestCase):

    def test_materialized_local_path_no_package_ok(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            src = tmp / "src"
            src.mkdir()
            (src / "a.py").write_text("x", encoding="utf-8")
            rs = _src("local", "local_path", path=str(src))
            v = _v(runtime_source="local", patch_start="cmd")
            artifact = probe.probe_variant(
                v, _ctx(tmp, runtime_sources=[rs]))
        self.assertEqual(artifact["status"], "ok")
        self.assertIsNone(artifact["harness_package"])
        self.assertEqual(artifact["runtime_source"]["status"], "ok")
        self.assertEqual(artifact["start_command"]["status"], "ok")
        self.assertIn("read-only", " ".join(artifact["limitations"]))

    def test_package_missing_fails_variant(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            src = tmp / "src"
            src.mkdir()
            (src / "a.py").write_text("x", encoding="utf-8")
            rs = _src("local", "local_path", path=str(src))
            v = _v(runtime_source="local", patch_start="cmd",
                    harness_package="missing@0.1.0")
            # manifest is None (unresolved)
            artifact = probe.probe_variant(
                v, _ctx(tmp, runtime_sources=[rs]), manifest=None)
        self.assertEqual(artifact["status"], "fail")
        self.assertEqual(artifact["harness_package"]["status"], "fail")


# ===========================================================================
# Group: artifact write + evidence file write
# ===========================================================================


class TestWriteArtifact(unittest.TestCase):

    def test_writes_json(self):
        with TemporaryDirectory() as t:
            probe_dir = Path(t) / "probe-results" / "probe-X"
            art = {"probe_id": "X", "variant_id": "V1", "status": "ok",
                   "limitations": []}
            out = probe.write_artifact(probe_dir, "V1", art)
            self.assertTrue(out.exists())
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["variant_id"], "V1")


class TestWriteRuntimeEvidenceMd(unittest.TestCase):

    def _legacy_artifact(self, status="ok", smoke_executed=False):
        return {
            "probe_id": "probe-X",
            "variant_id": "V1",
            "status": status,
            "created_at": "2026-06-01T10:00:00+00:00",
            "runtime_source": {
                "type": "legacy_connect", "status": "ok",
                "reasons": ["legacy connect available"],
            },
            "harness_package": None,
            "start_command": {
                "status": "ok", "command": "cmd",
                "source": "patch",
                "smoke_executed": smoke_executed,
                "smoke_status": "ok" if smoke_executed else None,
                "exit_code": 0 if smoke_executed else None,
                "stdout_truncated": "Running" if smoke_executed else "",
                "stderr_truncated": "",
                "timeout_seconds": 30,
            },
            "limitations": [
                "probe is read-only; no sandbox created or modified",
                "smoke command output is supplied runtime evidence captured "
                "at probe time, not cloud attestation",
            ] if smoke_executed else [
                "probe is read-only; no sandbox created or modified",
            ],
        }

    def test_ok_writes_file(self):
        with TemporaryDirectory() as t:
            materials = Path(t) / "materials"
            artifacts = [self._legacy_artifact(status="ok")]
            out = probe.write_runtime_evidence_md(materials, artifacts)
            self.assertIsNotNone(out)
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("probe-X", content)
            self.assertIn("V1", content)
            self.assertIn("status", content)
            # 'not cloud attestation' may wrap across lines in markdown header;
            # check for 'cloud attestation' (unambiguous limitation phrase).
            self.assertIn("cloud attestation", content)

    def test_warn_writes_file(self):
        with TemporaryDirectory() as t:
            materials = Path(t) / "materials"
            artifacts = [self._legacy_artifact(status="warn")]
            out = probe.write_runtime_evidence_md(materials, artifacts)
            self.assertIsNotNone(out)
            self.assertTrue(out.exists())

    def test_fail_does_not_write(self):
        """Spec §7.4 correction: fail status MUST NOT write evidence file."""
        with TemporaryDirectory() as t:
            materials = Path(t) / "materials"
            artifacts = [self._legacy_artifact(status="fail")]
            out = probe.write_runtime_evidence_md(materials, artifacts)
            self.assertIsNone(out)
            if materials.exists():
                self.assertFalse((materials / "runtime-evidence.md").exists())

    def test_empty_list_does_not_write(self):
        with TemporaryDirectory() as t:
            materials = Path(t) / "materials"
            out = probe.write_runtime_evidence_md(materials, [])
            self.assertIsNone(out)

    def test_smoke_output_in_evidence(self):
        with TemporaryDirectory() as t:
            materials = Path(t) / "materials"
            artifacts = [self._legacy_artifact(status="ok",
                                                 smoke_executed=True)]
            out = probe.write_runtime_evidence_md(materials, artifacts)
            content = out.read_text(encoding="utf-8")
            self.assertIn("smoke command", content)
            self.assertIn("Running", content)
            self.assertIn("exit_code", content)

    def test_required_fields_in_evidence(self):
        """Spec §7.4 correction: evidence must include probe_id/variant_id/status/captured_at/checks/limitations."""
        with TemporaryDirectory() as t:
            materials = Path(t) / "materials"
            artifacts = [self._legacy_artifact(status="ok",
                                                 smoke_executed=True)]
            out = probe.write_runtime_evidence_md(materials, artifacts)
            content = out.read_text(encoding="utf-8")
            for required in ("probe_id", "variant", "status", "captured_at",
                              "checks performed", "limitations"):
                self.assertIn(required, content,
                              f"required field {required!r} missing from "
                              f"evidence file")


# ===========================================================================
# Group: find_latest_probe + summarize
# ===========================================================================


class TestSummarizeLatestProbe(unittest.TestCase):

    def test_no_probe_yet(self):
        with TemporaryDirectory() as t:
            result = probe.summarize_latest_probe(Path(t))
        self.assertIsNone(result)

    def test_empty_probe_results_dir(self):
        with TemporaryDirectory() as t:
            (Path(t) / "probe-results").mkdir()
            result = probe.summarize_latest_probe(Path(t))
        self.assertIsNone(result)

    def test_picks_latest(self):
        with TemporaryDirectory() as t:
            base = Path(t) / "probe-results"
            old = base / "probe-20260601-100000"
            new = base / "probe-20260602-100000"
            for d in (old, new):
                d.mkdir(parents=True)
                (d / "V1.json").write_text(
                    json.dumps({"status": "ok", "variant_id": "V1"}),
                    encoding="utf-8")
            result = probe.summarize_latest_probe(Path(t))
        self.assertEqual(result["probe_id"], "probe-20260602-100000")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["counts"]["ok"], 1)

    def test_counts_by_status(self):
        with TemporaryDirectory() as t:
            d = Path(t) / "probe-results" / "probe-X"
            d.mkdir(parents=True)
            for vid, status in [("V1", "ok"), ("V2", "warn"), ("V3", "fail")]:
                (d / f"{vid}.json").write_text(
                    json.dumps({"status": status, "variant_id": vid}),
                    encoding="utf-8")
            result = probe.summarize_latest_probe(Path(t))
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["counts"]["ok"], 1)
        self.assertEqual(result["counts"]["warn"], 1)
        self.assertEqual(result["counts"]["fail"], 1)


# ===========================================================================
# Redlines / sanity
# ===========================================================================


class TestRedlines(unittest.TestCase):

    def test_probe_module_no_third_party_imports(self):
        import importlib
        before = set(sys.modules.keys())
        importlib.reload(probe)
        added = set(sys.modules.keys()) - before
        third = [m for m in added
                 if "." not in m and m not in sys.stdlib_module_names
                 and not m.startswith("agent_harness_lab")
                 and not m.startswith("_")]
        self.assertEqual(third, [],
                         f"probe pulled third-party imports: {third}")


if __name__ == "__main__":
    unittest.main()
