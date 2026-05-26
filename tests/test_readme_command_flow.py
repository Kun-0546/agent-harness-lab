"""README command-flow tests — README claims must match actual CLI behavior.

Spec: docs/product-reliability-evidence-hardening.md §5.2 + Kun lock #3.

Scope:
- README.md §8 "Simplest end-to-end workflow"
- README_CN.md §8 (mirror)
- examples/sample-workspace/README.md 5-step recipe

NOT in scope (lock #3): the rest of README (install / history / related work)
— avoids brittle parsing of prose / install / hyperlink-heavy sections.

Subprocess invocation (per lock #3 + existing test_sample_workspace_e2e.py
pattern):
- Copy examples/sample-workspace into tmp_path before running anything.
- Use `python -m agent_harness_lab` via sys.executable (no `ahl` alias
  dependency).
- Patch `python agent.py` → `<sys.executable> agent.py` in the harness +
  manifest so the test runs on systems where `python` is not on PATH.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
SAMPLE_WORKSPACE = REPO_ROOT / "examples" / "sample-workspace"

EXPECTED_BASE_COMMANDS = ("ahl probe", "ahl run", "ahl score", "ahl compare")
EXPECTED_RECIPE_COMMANDS = (
    "ahl probe 001", "ahl run 001", "ahl score 001", "ahl compare 001")


# ---------------------------------------------------------------------------
# Subprocess helpers — duplicated from test_sample_workspace_e2e.py so each
# test module is self-contained (matches existing project convention).
# ---------------------------------------------------------------------------


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
        f"`{sys.executable} -m agent_harness_lab {' '.join(args)}` "
        f"expected exit {expect_exit}, got {r.returncode}\n"
        f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
    return r


def _patch_python_executable(workspace: Path) -> None:
    """Replace `python agent.py` with `"<sys.executable>" agent.py`."""
    quoted_exe = f'"{sys.executable}"'
    targets = (
        workspace / "experiments" / "001-faq-conciseness" / "harnesses" / "V1.md",
        workspace / "harness-packages" / "concise-prompt" / "0.1.0" / "manifest.md",
    )
    for path in targets:
        text = path.read_text(encoding="utf-8")
        text = text.replace("python agent.py", f"{quoted_exe} agent.py")
        path.write_text(text, encoding="utf-8")


def _copy_sample(tmp: Path) -> Path:
    ws = tmp / "sample-workspace"
    shutil.copytree(SAMPLE_WORKSPACE, ws)
    _patch_python_executable(ws)
    return ws


# ===========================================================================
# Check 1 + 2 + 3: README files contain the expected command anchors
# ===========================================================================


class TestREADMEMentionsCommands(unittest.TestCase):

    def _read(self, rel: str) -> str:
        p = REPO_ROOT / rel
        self.assertTrue(p.exists(), f"{rel} not found")
        return p.read_text(encoding="utf-8")

    def test_readme_simplest_workflow_has_command_anchors(self):
        """README.md §8 'Simplest end-to-end workflow' must contain all four
        base command anchors (substring match — tolerates code-fence / arg
        wrapping)."""
        text = self._read("README.md")
        # Locate §8 section as starting point to give clearer failure msgs;
        # fall back to whole-file search if section header drifts.
        section_anchor = "Simplest end-to-end workflow"
        idx = text.find(section_anchor)
        scope = text[idx:] if idx >= 0 else text
        missing = [cmd for cmd in EXPECTED_BASE_COMMANDS if cmd not in scope]
        self.assertFalse(
            missing,
            f"README.md §8 missing command anchors: {missing}. "
            f"§8 head:\n{scope[:600]!r}")

    def test_readme_cn_simplest_workflow_mirrors_command_anchors(self):
        """README_CN.md §8 must contain the same four anchors (EN/CN 1:1
        invariant in v0.7)."""
        text = self._read("README_CN.md")
        section_anchor = "最简端到端流程"
        idx = text.find(section_anchor)
        scope = text[idx:] if idx >= 0 else text
        missing = [cmd for cmd in EXPECTED_BASE_COMMANDS if cmd not in scope]
        self.assertFalse(
            missing,
            f"README_CN.md §8 missing command anchors: {missing}. "
            f"§8 head:\n{scope[:600]!r}")

    def test_sample_workspace_readme_has_5step_recipe(self):
        """examples/sample-workspace/README.md must contain the four
        experiment-id-qualified commands in its 5-step recipe."""
        text = self._read("examples/sample-workspace/README.md")
        missing = [cmd for cmd in EXPECTED_RECIPE_COMMANDS if cmd not in text]
        self.assertFalse(
            missing,
            f"examples/sample-workspace/README.md missing recipe commands: "
            f"{missing}.")


# ===========================================================================
# Check 4: the sample-workspace commands actually execute
# ===========================================================================


class TestREADMECommandsExecuteSuccessfully(unittest.TestCase):

    def test_sample_workspace_recipe_commands_execute(self):
        """Each `ahl <subcommand> 001` from the recipe must succeed via
        `python -m agent_harness_lab` against a fresh tmp sample workspace.

        Sequential execution (probe → run → score → compare) because the
        order is the documented user flow and downstream commands consume
        upstream artifacts.
        """
        with TemporaryDirectory() as t:
            ws = _copy_sample(Path(t))
            for subcommand in ("probe", "run", "score", "compare"):
                with self.subTest(subcommand=subcommand):
                    result = _run_cli(ws, subcommand, "001")
                    # Spot-check stdout has the experiment id; protects
                    # against silent no-op where exit is 0 but nothing ran.
                    self.assertIn(
                        "001-faq-conciseness",
                        result.stdout + result.stderr,
                        f"`ahl {subcommand} 001` exited 0 but stdout/stderr "
                        f"never mentioned the experiment id — looks like a "
                        f"silent no-op.\nstdout: {result.stdout!r}\n"
                        f"stderr: {result.stderr!r}")


if __name__ == "__main__":
    unittest.main()
