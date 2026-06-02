#!/usr/bin/env sh
# Public MVP verification for Agent Harness Lab.
#
# Resolves the repo root from this script's location, so it works from anywhere.
# POSIX sh. No network, no external APIs, no hidden dependencies.
#
# Override the interpreter with PYTHON=... (default: python3). The examples'
# local_cli connector spawns `python3` directly, so python3 must be on PATH.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT" || { echo "FAIL: cannot cd to repo root" >&2; exit 1; }
PY="${PYTHON:-python3}"

fail() { echo "FAIL: $1" >&2; exit 1; }

echo "== Agent Harness Lab :: public MVP verification =="
echo "repo:   $ROOT"
echo "python: $("$PY" --version 2>&1)"
command -v python3 >/dev/null 2>&1 || fail "python3 not on PATH (examples' local_cli connector requires it)"

# Supported interpreter range is 3.10–3.12. Python 3.13 is pinned out (an unresolved
# test-suite hang); fail fast with a clear message instead of hanging there.
ver=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
case "$ver" in
  3.10|3.11|3.12) : ;;
  *) fail "unsupported Python $ver — AHL v1 supports 3.10–3.12 (run with PYTHON=python3.12)";;
esac

# 1. Full unit-test suite (committed tests; no network).
echo "--- [1/5] unit tests: python -m unittest discover -s tests -t . ---"
PYTHONPATH=src "$PY" -m unittest discover -s tests -t . >/tmp/ahl_verify_tests.log 2>&1 \
  || { tail -n 20 /tmp/ahl_verify_tests.log >&2; fail "unit tests"; }
tail -n 3 /tmp/ahl_verify_tests.log

# 2. CLI import / help.
echo "--- [2/5] CLI: python -m agent_harness_lab --help ---"
PYTHONPATH=src "$PY" -m agent_harness_lab --help >/dev/null 2>&1 || fail "CLI --help"
echo "ok: CLI help works"

# 3 + 4. Examples: review -> run -> report, then assert reports/report.md exists.
verify_example() {
  step="$1"; name="$2"
  exp="examples/$name/experiments/demo"
  echo "--- [$step/5] example: $name (review -> run -> report) ---"
  rm -rf "$exp/evidence" "$exp/reports" "$exp/optimization" \
         "$exp/harnesses/incumbent" "$exp/harnesses/candidates" \
         "$exp/harnesses/base/produced" 2>/dev/null || true
  for cmd in review run report; do
    ( cd "examples/$name" && PYTHONPATH=../../src "$PY" -m agent_harness_lab "$cmd" experiments/demo ) \
      >/dev/null 2>&1 || fail "$name: $cmd"
  done
  [ -f "$exp/reports/report.md" ] || fail "$name: reports/report.md missing"
  echo "ok: $name review/run/report -> reports/report.md"
}
verify_example 3 "auto-run-local-cli-lite"
verify_example 4 "auto-optimize-copy-lite"

# 5. No leftover connector / script / git child processes.
echo "--- [5/5] no leftover agent.py / runner.py / git ---"
leftover=$(ps -eo args 2>/dev/null | grep -v grep | grep -E '(agent|runner)\.py|(^| |/)git( |$)' || true)
[ -z "$leftover" ] || { echo "$leftover" >&2; fail "leftover process detected"; }
echo "ok: no leftover agent.py / runner.py / git"

echo "== ALL PUBLIC-MVP CHECKS PASSED =="
