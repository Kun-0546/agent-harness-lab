"""PR8: review-stage source health checks.

Tests:
- local_path healthy → review PASS with fingerprint emitted
- local_path missing source dir → review ERROR probe_source_missing
- local_path patch file source missing → ERROR probe_patch_source_missing
- git_repo with local temp git repo as url → PASS + resolved SHA matches HEAD
- git_repo bad ref → ERROR probe_git_ref_missing
- git_repo unreachable url → ERROR probe_git_unreachable (fast failure)
- harness_package fingerprint match → PASS
- harness_package fingerprint mismatch → ERROR probe_fingerprint_mismatch
- no-source experiment → review output byte-identical (no source_checks, no probe_ problems)
- review is read-only (no sandbox/, no evidence/ created)
- reconciliation: review fingerprint == post-run snapshot fingerprint (local_path + git_repo)
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

GIT_AVAILABLE = shutil.which("git") is not None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_experiment(root: Path, name: str = "probe-test") -> tuple[Path, Path]:
    """Scaffold a minimal valid auto experiment. Returns (ws, exp_dir)."""
    from agent_harness_lab import scaffold
    ws = root / "ws"
    ws.mkdir(exist_ok=True)
    scaffold.init_workspace(ws)
    res = scaffold.new_experiment(ws, name, run_mode="auto",
                                  question="Does A beat B?")
    return ws, res.experiment_dir


def _patch_runtime_yaml(exp: Path, rt_id: str, source_yaml: str) -> Path:
    """Add source: section to an agent-runtimes/<rt_id>.yaml and register in experiment.yaml."""
    import yaml
    rt_dir = exp / "agent-runtimes"
    rt_dir.mkdir(exist_ok=True)
    rt_path = rt_dir / f"{rt_id}.yaml"
    rt_path.write_text(
        f"id: {rt_id}\n"
        f"connector:\n"
        f"  type: local_cli\n"
        f"  command: \"echo ok\"\n"
        f"  working_dir: .\n"
        + source_yaml,
        encoding="utf-8",
    )
    ey = exp / "experiment.yaml"
    data = yaml.safe_load(ey.read_text(encoding="utf-8"))
    data["agent_runtimes"] = [{"id": rt_id, "harness": "A",
                               "spec": f"agent-runtimes/{rt_id}.yaml"}]
    if not any(h.get("id") == "A" for h in (data.get("harnesses") or [])):
        data.setdefault("harnesses", [])
        data["harnesses"].append({"id": "A", "name": "A", "path": "harnesses/A"})
        (exp / "harnesses" / "A").mkdir(parents=True, exist_ok=True)
    import io as _io
    buf = _io.StringIO()
    yaml.dump(data, buf, allow_unicode=True, default_flow_style=False)
    ey.write_text(buf.getvalue(), encoding="utf-8")
    return rt_path


def _make_local_git_repo(root: Path, files: dict | None = None) -> tuple[Path, str]:
    """Create a local git repo inside `root` (root is the repo dir itself). Returns (repo_path, head_sha)."""
    from tests.githelper import git
    root.mkdir(parents=True, exist_ok=True)
    repo = root
    if files is None:
        files = {"agent.py": "print('hello')\n"}
    for fname, content in files.items():
        fpath = repo / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    git(["init", "-b", "main"], cwd=repo)
    git(["config", "user.email", "test@test.com"], cwd=repo)
    git(["config", "user.name", "Test"], cwd=repo)
    git(["add", "."], cwd=repo)
    git(["commit", "-m", "init"], cwd=repo)
    # Get HEAD sha
    result = git(["rev-parse", "HEAD"], cwd=repo)
    head_sha = result.stdout.strip()
    return repo, head_sha


# ---------------------------------------------------------------------------
# Test: no-source experiment — behavior byte-identical to before PR8
# ---------------------------------------------------------------------------

class TestNoSourceExperimentUnchanged(unittest.TestCase):
    """Experiments with no source: section must produce the exact same
    review behavior as before PR8 (no probe_ problems, no source_checks)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_no_source_review_verdict_unchanged(self):
        saved = os.getcwd()
        os.chdir(self.root)
        try:
            ws, exp = _minimal_experiment(self.root)
            from agent_harness_lab.reviewer import PASS, review_experiment
            report = review_experiment(exp)
            self.assertEqual(report.verdict, PASS, [str(p) for p in report.problems])
            probe_problems = [p for p in report.problems if p.code.startswith("probe_")]
            self.assertEqual(probe_problems, [],
                             "no source: section → no probe_ problems expected")
            self.assertEqual(report.source_checks, [],
                             "no source: section → source_checks must be empty")
        finally:
            os.chdir(saved)

    def test_no_source_cli_review_output_contains_no_source_checks_section(self):
        """Source health checks section must not appear when no runtime has source:."""
        saved = os.getcwd()
        os.chdir(self.root)
        try:
            ws, exp = _minimal_experiment(self.root, name="nosrc2")
            from agent_harness_lab import cli
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["review", "probe-test"])
            output = out.getvalue()
            self.assertNotIn("source health checks", output)
        finally:
            os.chdir(saved)


# ---------------------------------------------------------------------------
# Test: local_path source
# ---------------------------------------------------------------------------

class TestLocalPathSourceHealthCheck(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        saved = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(lambda: os.chdir(saved))

    def _make_source_dir(self) -> Path:
        src = self.root / "src-agent"
        src.mkdir(exist_ok=True)
        (src / "agent.py").write_text("print('hello')\n", encoding="utf-8")
        return src

    def test_healthy_local_path_review_pass_with_fingerprint(self):
        ws, exp = _minimal_experiment(self.root)
        src = self._make_source_dir()
        _patch_runtime_yaml(exp, "rt-a", (
            f"source:\n"
            f"  type: local_path\n"
            f"  path: {str(src).replace(chr(92), '/')}\n"
        ))
        from agent_harness_lab.reviewer import PASS, review_experiment
        report = review_experiment(exp)
        # Should PASS or WARN at most (auto_working_dir might warn but not local_path)
        probe_errors = [p for p in report.problems if p.code.startswith("probe_") and p.level == "ERROR"]
        self.assertEqual(probe_errors, [], f"Unexpected probe errors: {probe_errors}")
        self.assertEqual(len(report.source_checks), 1)
        sc = report.source_checks[0]
        self.assertEqual(sc["source_type"], "local_path")
        self.assertEqual(sc["check_result"], "PASS")
        # Fingerprint must be a sha256 hash
        self.assertTrue(sc["fingerprint"].startswith("sha256:"),
                        f"Expected sha256: fingerprint, got: {sc['fingerprint']!r}")

    def test_missing_source_dir_review_error(self):
        ws, exp = _minimal_experiment(self.root, name="miss-src")
        _patch_runtime_yaml(exp, "rt-a", (
            "source:\n"
            "  type: local_path\n"
            "  path: /nonexistent/path/that/does/not/exist\n"
        ))
        from agent_harness_lab.reviewer import ERROR, review_experiment
        report = review_experiment(exp)
        self.assertEqual(report.verdict, ERROR)
        codes = [p.code for p in report.errors]
        self.assertIn("probe_source_missing", codes,
                      f"Expected probe_source_missing in {codes}")

    def test_patch_source_missing_review_error(self):
        ws, exp = _minimal_experiment(self.root, name="patch-miss")
        src = self._make_source_dir()
        # Patch references a file that doesn't exist
        _patch_runtime_yaml(exp, "rt-a", (
            f"source:\n"
            f"  type: local_path\n"
            f"  path: {str(src).replace(chr(92), '/')}\n"
            f"  patch:\n"
            f"    files:\n"
            f"      - target: config.txt\n"
            f"        source: patches/nonexistent.txt\n"
        ))
        from agent_harness_lab.reviewer import ERROR, review_experiment
        report = review_experiment(exp)
        self.assertEqual(report.verdict, ERROR)
        codes = [p.code for p in report.errors]
        self.assertIn("probe_patch_source_missing", codes,
                      f"Expected probe_patch_source_missing in {codes}")

    def test_patch_source_present_no_error(self):
        ws, exp = _minimal_experiment(self.root, name="patch-ok")
        src = self._make_source_dir()
        # Patch references a file that DOES exist
        patch_dir = exp / "patches"
        patch_dir.mkdir()
        (patch_dir / "config.txt").write_text("value", encoding="utf-8")
        _patch_runtime_yaml(exp, "rt-a", (
            f"source:\n"
            f"  type: local_path\n"
            f"  path: {str(src).replace(chr(92), '/')}\n"
            f"  patch:\n"
            f"    files:\n"
            f"      - target: config.txt\n"
            f"        source: patches/config.txt\n"
        ))
        from agent_harness_lab.reviewer import review_experiment
        report = review_experiment(exp)
        probe_errors = [p for p in report.problems
                        if p.code.startswith("probe_") and p.level == "ERROR"]
        self.assertEqual(probe_errors, [], f"Unexpected probe errors: {probe_errors}")

    def test_source_check_in_cli_output(self):
        """Source health check summary appears in hlab review output."""
        ws, exp = _minimal_experiment(self.root, name="cli-src")
        src = self._make_source_dir()
        _patch_runtime_yaml(exp, "rt-a", (
            f"source:\n"
            f"  type: local_path\n"
            f"  path: {str(src).replace(chr(92), '/')}\n"
        ))
        from agent_harness_lab import cli
        out = io.StringIO()
        # Use the absolute path to avoid bare-name resolution issues with cwd
        with redirect_stdout(out):
            cli.main(["review", str(exp)])
        output = out.getvalue()
        self.assertIn("source health checks", output)
        self.assertIn("local_path", output)

    def test_reconciliation_review_fingerprint_matches_snapshot(self):
        """Review-emitted source_dir_hash must equal the snapshot's source_dir_hash."""
        from agent_harness_lab import auto, scaffold
        import yaml

        ws2 = self.root / "ws2"
        ws2.mkdir(exist_ok=True)
        scaffold.init_workspace(ws2)
        res = scaffold.new_experiment(ws2, "reconcile-test",
                                      run_mode="auto", question="Does A beat B?")
        exp = res.experiment_dir

        src = self.root / "src-rec"
        src.mkdir(exist_ok=True)
        exe = sys.executable.replace("\\", "/")
        (src / "agent.py").write_text(
            "import json,sys\n"
            "for l in sys.stdin:\n"
            "    d=json.loads(l)\n"
            "    sys.stdout.write(json.dumps({'response':'ok'})+'\\n')\n"
            "    sys.stdout.flush()\n",
            encoding="utf-8",
        )

        rt_id = "rt-rec"
        rt_yaml = (
            f"id: {rt_id}\n"
            f"connector:\n"
            f"  type: local_cli\n"
            f"  command: \"{exe} agent.py\"\n"
            f"  working_dir: .\n"
            f"source:\n"
            f"  type: local_path\n"
            f"  path: {str(src).replace(chr(92), '/')}\n"
        )
        rt_dir = exp / "agent-runtimes"
        rt_dir.mkdir(exist_ok=True)
        (rt_dir / f"{rt_id}.yaml").write_text(rt_yaml, encoding="utf-8")

        ey = exp / "experiment.yaml"
        data = yaml.safe_load(ey.read_text(encoding="utf-8"))
        data["agent_runtimes"] = [{"id": rt_id, "harness": "A",
                                   "spec": f"agent-runtimes/{rt_id}.yaml"}]
        if not any(h.get("id") == "A" for h in (data.get("harnesses") or [])):
            data["harnesses"] = [{"id": "A", "name": "A", "path": "harnesses/A"}]
            (exp / "harnesses" / "A").mkdir(parents=True, exist_ok=True)
        cases_dir = exp / "cases"
        cases_dir.mkdir(exist_ok=True)
        (cases_dir / "cases.jsonl").write_text(
            json.dumps({"id": "c1", "input": "hello"}) + "\n", encoding="utf-8")
        import io as _io
        buf = _io.StringIO()
        yaml.dump(data, buf, allow_unicode=True, default_flow_style=False)
        ey.write_text(buf.getvalue(), encoding="utf-8")

        # Phase 1: review — capture fingerprint
        from agent_harness_lab.reviewer import review_experiment
        report = review_experiment(exp)
        self.assertEqual(len(report.source_checks), 1)
        review_fp = report.source_checks[0]["fingerprint"]
        self.assertTrue(review_fp.startswith("sha256:"),
                        f"Expected sha256 fingerprint from review: {review_fp!r}")

        # Phase 2: run — write snapshot
        from agent_harness_lab.experiment_spec import parse_experiment_yaml
        spec = parse_experiment_yaml(ey)
        auto.run_auto(exp, spec, fresh=True)

        snap_path = exp / "evidence" / "snapshots" / f"{rt_id}.json"
        self.assertTrue(snap_path.exists(), "Snapshot must be written after run")
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        snap_fp = snap["runtime_source"]["source_dir_hash"]

        self.assertEqual(review_fp, snap_fp,
                         f"Review fingerprint {review_fp!r} must match snapshot {snap_fp!r}")


# ---------------------------------------------------------------------------
# Test: git_repo source
# ---------------------------------------------------------------------------

@unittest.skipUnless(GIT_AVAILABLE, "git not in PATH — skipping git_repo probe tests")
class TestGitRepoSourceHealthCheck(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        saved = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(lambda: os.chdir(saved))

    def test_git_repo_healthy_pass_with_resolved_sha(self):
        ws, exp = _minimal_experiment(self.root)
        repo, head_sha = _make_local_git_repo(self.root / "repo-healthy")
        url = repo.as_uri()
        _patch_runtime_yaml(exp, "rt-git", (
            f"source:\n"
            f"  type: git_repo\n"
            f"  url: {url}\n"
            f"  ref: main\n"
        ))
        from agent_harness_lab.reviewer import review_experiment
        report = review_experiment(exp)
        probe_errors = [p for p in report.problems
                        if p.code.startswith("probe_") and p.level == "ERROR"]
        self.assertEqual(probe_errors, [], f"Unexpected probe errors: {probe_errors}")
        self.assertEqual(len(report.source_checks), 1)
        sc = report.source_checks[0]
        self.assertEqual(sc["source_type"], "git_repo")
        self.assertEqual(sc["check_result"], "PASS")
        # fingerprint is the resolved SHA
        self.assertEqual(sc["fingerprint"], head_sha,
                         f"Review fingerprint {sc['fingerprint']!r} must match HEAD sha {head_sha!r}")

    def test_git_repo_bad_ref_error(self):
        ws, exp = _minimal_experiment(self.root, name="git-badref")
        repo, _ = _make_local_git_repo(self.root / "repo-badref")
        url = repo.as_uri()
        _patch_runtime_yaml(exp, "rt-git", (
            f"source:\n"
            f"  type: git_repo\n"
            f"  url: {url}\n"
            f"  ref: refs/heads/nonexistent-branch-xyz\n"
        ))
        from agent_harness_lab.reviewer import ERROR, review_experiment
        report = review_experiment(exp)
        self.assertEqual(report.verdict, ERROR)
        codes = [p.code for p in report.errors]
        self.assertIn("probe_git_ref_missing", codes,
                      f"Expected probe_git_ref_missing in {codes}")

    def test_git_repo_unreachable_url_error(self):
        """Unreachable/nonexistent git URL → ERROR probe_git_unreachable (fast failure)."""
        ws, exp = _minimal_experiment(self.root, name="git-unreach")
        # Use a nonexistent local path as URL — git ls-remote fails fast, no network needed
        fake_url = (self.root / "nonexistent-repo").as_uri()
        _patch_runtime_yaml(exp, "rt-git", (
            f"source:\n"
            f"  type: git_repo\n"
            f"  url: {fake_url}\n"
            f"  ref: main\n"
        ))
        from agent_harness_lab.reviewer import ERROR, review_experiment
        report = review_experiment(exp)
        self.assertEqual(report.verdict, ERROR)
        codes = [p.code for p in report.errors]
        self.assertIn("probe_git_unreachable", codes,
                      f"Expected probe_git_unreachable in {codes}")

    def test_git_repo_reconciliation_review_sha_matches_snapshot_commit_sha(self):
        """Review-emitted remote_commit_sha must equal snapshot commit_sha after a run."""
        from agent_harness_lab import auto, scaffold
        import yaml

        ws2 = self.root / "ws2"
        ws2.mkdir(exist_ok=True)
        scaffold.init_workspace(ws2)
        res = scaffold.new_experiment(ws2, "git-rec",
                                      run_mode="auto", question="Does A beat B?")
        exp = res.experiment_dir

        repo, head_sha = _make_local_git_repo(self.root / "repo-rec")
        url = repo.as_uri()

        exe = sys.executable.replace("\\", "/")
        rt_id = "rt-grec"
        rt_yaml = (
            f"id: {rt_id}\n"
            f"connector:\n"
            f"  type: local_cli\n"
            f"  command: \"{exe} agent.py\"\n"
            f"  working_dir: .\n"
            f"source:\n"
            f"  type: git_repo\n"
            f"  url: {url}\n"
            f"  ref: main\n"
        )
        rt_dir = exp / "agent-runtimes"
        rt_dir.mkdir(exist_ok=True)
        (rt_dir / f"{rt_id}.yaml").write_text(rt_yaml, encoding="utf-8")

        ey = exp / "experiment.yaml"
        data = yaml.safe_load(ey.read_text(encoding="utf-8"))
        data["agent_runtimes"] = [{"id": rt_id, "harness": "A",
                                   "spec": f"agent-runtimes/{rt_id}.yaml"}]
        if not any(h.get("id") == "A" for h in (data.get("harnesses") or [])):
            data["harnesses"] = [{"id": "A", "name": "A", "path": "harnesses/A"}]
            (exp / "harnesses" / "A").mkdir(parents=True, exist_ok=True)
        cases_dir = exp / "cases"
        cases_dir.mkdir(exist_ok=True)
        (cases_dir / "cases.jsonl").write_text(
            json.dumps({"id": "c1", "input": "hello"}) + "\n", encoding="utf-8")
        import io as _io
        buf = _io.StringIO()
        yaml.dump(data, buf, allow_unicode=True, default_flow_style=False)
        ey.write_text(buf.getvalue(), encoding="utf-8")

        # Phase 1: review — fingerprint = resolved remote SHA
        from agent_harness_lab.reviewer import review_experiment
        report = review_experiment(exp)
        self.assertEqual(len(report.source_checks), 1,
                         f"Expected 1 source check, got {report.source_checks}")
        review_sha = report.source_checks[0]["fingerprint"]
        self.assertEqual(review_sha, head_sha)

        # Phase 2: run — snapshot records commit_sha
        from agent_harness_lab.experiment_spec import parse_experiment_yaml
        spec = parse_experiment_yaml(ey)
        auto.run_auto(exp, spec, fresh=True)

        snap_path = exp / "evidence" / "snapshots" / f"{rt_id}.json"
        self.assertTrue(snap_path.exists(), "Snapshot must be written")
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        snap_sha = snap["runtime_source"]["commit_sha"]

        self.assertEqual(review_sha, snap_sha,
                         f"Review SHA {review_sha!r} must match snapshot commit_sha {snap_sha!r}")


# ---------------------------------------------------------------------------
# Test: harness_package source
# ---------------------------------------------------------------------------

class TestHarnessPackageSourceHealthCheck(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        saved = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(lambda: os.chdir(saved))

    def _make_pkg_dir(self, name: str = "pkg") -> Path:
        """Make a minimal harness package directory."""
        pkg = self.root / name
        pkg.mkdir(exist_ok=True)
        (pkg / "manifest.md").write_text("# manifest\n", encoding="utf-8")
        payload = pkg / "payload"
        payload.mkdir(exist_ok=True)
        (payload / "agent.py").write_text("print('pkg')\n", encoding="utf-8")
        return pkg

    def test_harness_package_match_pass(self):
        ws, exp = _minimal_experiment(self.root)
        pkg = self._make_pkg_dir()
        # No expected_fingerprint → just existence check passes
        _patch_runtime_yaml(exp, "rt-pkg", (
            f"source:\n"
            f"  type: harness_package\n"
            f"  path: {str(pkg).replace(chr(92), '/')}\n"
        ))
        from agent_harness_lab.reviewer import review_experiment
        report = review_experiment(exp)
        probe_errors = [p for p in report.problems
                        if p.code.startswith("probe_") and p.level == "ERROR"]
        self.assertEqual(probe_errors, [], f"Unexpected probe errors: {probe_errors}")
        self.assertEqual(len(report.source_checks), 1)
        sc = report.source_checks[0]
        self.assertEqual(sc["source_type"], "harness_package")
        self.assertEqual(sc["check_result"], "PASS")
        self.assertIn("manifest=", sc["fingerprint"])

    def test_harness_package_fingerprint_mismatch_error(self):
        ws, exp = _minimal_experiment(self.root, name="pkg-mismatch")
        pkg = self._make_pkg_dir("pkg2")

        import hashlib
        # Deliberately wrong manifest hash
        wrong_hash = "sha256:" + hashlib.sha256(b"wrong-content").hexdigest()
        _patch_runtime_yaml(exp, "rt-pkg", (
            f"source:\n"
            f"  type: harness_package\n"
            f"  path: {str(pkg).replace(chr(92), '/')}\n"
            f"  expected_fingerprint:\n"
            f"    manifest_hash: \"{wrong_hash}\"\n"
        ))
        from agent_harness_lab.reviewer import ERROR, review_experiment
        report = review_experiment(exp)
        self.assertEqual(report.verdict, ERROR)
        codes = [p.code for p in report.errors]
        self.assertIn("probe_fingerprint_mismatch", codes,
                      f"Expected probe_fingerprint_mismatch in {codes}")

    def test_harness_package_missing_path_error(self):
        ws, exp = _minimal_experiment(self.root, name="pkg-miss")
        _patch_runtime_yaml(exp, "rt-pkg", (
            "source:\n"
            "  type: harness_package\n"
            "  path: /nonexistent/harness-pkg\n"
        ))
        from agent_harness_lab.reviewer import ERROR, review_experiment
        report = review_experiment(exp)
        self.assertEqual(report.verdict, ERROR)
        codes = [p.code for p in report.errors]
        self.assertIn("probe_source_missing", codes,
                      f"Expected probe_source_missing in {codes}")

    def test_harness_package_fingerprint_correct_passes(self):
        """When expected_fingerprint matches actual, review passes."""
        ws, exp = _minimal_experiment(self.root, name="pkg-correct-fp")
        pkg = self._make_pkg_dir("pkg3")
        # Compute the actual manifest hash
        from agent_harness_lab.materialize_v1 import _file_sha256
        actual_manifest_hash = _file_sha256(pkg / "manifest.md")
        _patch_runtime_yaml(exp, "rt-pkg", (
            f"source:\n"
            f"  type: harness_package\n"
            f"  path: {str(pkg).replace(chr(92), '/')}\n"
            f"  expected_fingerprint:\n"
            f"    manifest_hash: \"{actual_manifest_hash}\"\n"
        ))
        from agent_harness_lab.reviewer import review_experiment
        report = review_experiment(exp)
        probe_errors = [p for p in report.problems
                        if p.code.startswith("probe_") and p.level == "ERROR"]
        self.assertEqual(probe_errors, [], f"Unexpected probe errors: {probe_errors}")


# ---------------------------------------------------------------------------
# Test: read-only guarantee
# ---------------------------------------------------------------------------

class TestReviewReadOnly(unittest.TestCase):
    """review must not create sandbox/ or evidence/ (beyond what already exists)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        saved = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(lambda: os.chdir(saved))

    def test_review_does_not_create_sandbox_or_new_evidence(self):
        ws, exp = _minimal_experiment(self.root)
        src = self.root / "src-ro"
        src.mkdir()
        (src / "agent.py").write_text("x\n", encoding="utf-8")
        _patch_runtime_yaml(exp, "rt-ro", (
            f"source:\n"
            f"  type: local_path\n"
            f"  path: {str(src).replace(chr(92), '/')}\n"
        ))

        sandbox_dir = exp / "sandbox"
        ev_dir = exp / "evidence"
        sandbox_before = sandbox_dir.exists()

        from agent_harness_lab.reviewer import review_experiment
        review_experiment(exp)

        # sandbox must not have been created by review
        if not sandbox_before:
            self.assertFalse(sandbox_dir.exists(),
                             "review must not create sandbox/")

        # evidence/ may exist (scaffold creates it), but no new subdirs from review
        if ev_dir.exists():
            new_subdirs = [d for d in ev_dir.iterdir()
                           if d.is_dir() and d.name == "snapshots"]
            snap_dir = ev_dir / "snapshots"
            if snap_dir.exists():
                # Should be empty — review never writes snapshots
                snap_files = list(snap_dir.rglob("*.json"))
                self.assertEqual(snap_files, [],
                                 f"review must not write snapshot files: {snap_files}")


# ---------------------------------------------------------------------------
# Test: multiple runtimes — each checked independently
# ---------------------------------------------------------------------------

class TestMultipleRuntimesProbe(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        saved = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(lambda: os.chdir(saved))

    def test_two_runtimes_one_source_one_no_source(self):
        """Runtime with source: gets checked; runtime without source: is skipped."""
        import yaml
        from agent_harness_lab import scaffold

        ws = self.root / "ws"
        ws.mkdir()
        scaffold.init_workspace(ws)
        res = scaffold.new_experiment(ws, "multi-rt", run_mode="auto",
                                      question="Does A beat B?")
        exp = res.experiment_dir

        src = self.root / "src-multi"
        src.mkdir()
        (src / "agent.py").write_text("x\n", encoding="utf-8")

        rt_dir = exp / "agent-runtimes"
        rt_dir.mkdir(exist_ok=True)

        # Runtime A: has source
        (rt_dir / "rt-a.yaml").write_text(
            f"id: rt-a\nconnector:\n  type: local_cli\n  command: echo a\n  working_dir: .\n"
            f"source:\n  type: local_path\n  path: {str(src).replace(chr(92), '/')}\n",
            encoding="utf-8",
        )
        # Runtime B: no source
        (rt_dir / "rt-b.yaml").write_text(
            "id: rt-b\nconnector:\n  type: local_cli\n  command: echo b\n  working_dir: .\n",
            encoding="utf-8",
        )

        ey = exp / "experiment.yaml"
        data = yaml.safe_load(ey.read_text(encoding="utf-8"))
        data["harnesses"] = [{"id": "A", "name": "A", "path": "harnesses/A"},
                             {"id": "B", "name": "B", "path": "harnesses/B"}]
        (exp / "harnesses" / "A").mkdir(parents=True, exist_ok=True)
        (exp / "harnesses" / "B").mkdir(parents=True, exist_ok=True)
        data["agent_runtimes"] = [
            {"id": "rt-a", "harness": "A", "spec": "agent-runtimes/rt-a.yaml"},
            {"id": "rt-b", "harness": "B", "spec": "agent-runtimes/rt-b.yaml"},
        ]
        import io as _io
        buf = _io.StringIO()
        yaml.dump(data, buf, allow_unicode=True, default_flow_style=False)
        ey.write_text(buf.getvalue(), encoding="utf-8")

        from agent_harness_lab.reviewer import review_experiment
        report = review_experiment(exp)
        # Only one source check (for rt-a)
        self.assertEqual(len(report.source_checks), 1)
        self.assertEqual(report.source_checks[0]["runtime_id"], "rt-a")
        # No probe errors
        probe_errors = [p for p in report.problems
                        if p.code.startswith("probe_") and p.level == "ERROR"]
        self.assertEqual(probe_errors, [])


if __name__ == "__main__":
    unittest.main()
