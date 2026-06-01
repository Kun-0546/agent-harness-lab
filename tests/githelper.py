"""Bounded, non-interactive git for test fixtures that build local repos.

Raw `git commit` / `git tag` can HANG FOREVER in environments where commit
signing is enabled globally (`commit.gpgsign=true` → GPG/pinentry passphrase
prompt) or a global hook / credential helper blocks waiting on input. The
canonical `python -m unittest discover` run timed out in such a review
environment on `git commit -m init`.

Every call here is hardened so test git usage can never stall the suite:
  - test-safe `-c` flags: commit.gpgsign=false, tag.gpgsign=false,
    core.hooksPath=/dev/null (no signing, no hooks — the usual hang sources);
  - stdin=subprocess.DEVNULL (a prompt gets EOF, not a blocked read);
  - non-interactive env: GIT_TERMINAL_PROMPT=0, GCM_INTERACTIVE=never;
  - a timeout (AHL_TEST_GIT_TIMEOUT, default 10s) — a stuck git fails the test
    fast instead of hanging the whole run.

Tests must use `git(args, cwd=...)` rather than calling the `git` binary directly.
"""
from __future__ import annotations

import os
import subprocess

try:
    GIT_TIMEOUT = float(os.environ.get("AHL_TEST_GIT_TIMEOUT", "10"))
except ValueError:
    GIT_TIMEOUT = 10.0

_SAFE_FLAGS = (
    "-c", "commit.gpgsign=false",
    "-c", "tag.gpgsign=false",
    "-c", "core.hooksPath=/dev/null",
)
_NONINTERACTIVE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",   # never prompt for username/password on the terminal
    "GCM_INTERACTIVE": "never",   # Git Credential Manager: no popup
}


def git(args, cwd=None, check=True):
    """Run a bounded, non-interactive git command for test fixtures.

    `args` is the git argv after the program name, e.g. ["init", "-b", "main"].
    Returns the CompletedProcess (stdout/stderr captured, text mode). Raises
    CalledProcessError on non-zero exit (when check=True) or TimeoutExpired on a
    stuck call — both surface as a test failure, never as a hang.
    """
    return subprocess.run(
        ["git", *_SAFE_FLAGS, *args],
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=GIT_TIMEOUT,
        env={**os.environ, **_NONINTERACTIVE_ENV},
    )
