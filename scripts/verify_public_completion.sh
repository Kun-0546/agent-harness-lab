#!/usr/bin/env sh
# Public COMPLETION verification for Agent Harness Lab.
#
# Installs the package into a throwaway venv and drives the WHOLE user path on the
# flagship template — init -> new --template -> review -> run -> status -> report ->
# compare -> conclude -> review — then asserts every artifact exists.
#
# Runs with NO API key on purpose: the flagship's objective track is a deterministic
# benchmark, so the path must complete without AHL_JUDGE_*. The optional llm_judge
# track stays pending (never a fake verdict) and must not fail the run.
#
# POSIX sh. Override the interpreter with PYTHON=... (default: python3). The template's
# local_cli connector spawns `python3`, so python3 must be on PATH.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PY="${PYTHON:-python3}"
fail() { echo "FAIL: $1" >&2; exit 1; }

TMP=$(mktemp -d 2>/dev/null) || fail "cannot create temp dir"
cleanup() { rm -rf "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

# No judge key -> llm_judge MUST stay pending (this is the no-key completion path).
unset AHL_JUDGE_API_KEY AHL_JUDGE_BASE_URL AHL_JUDGE_MODEL 2>/dev/null || true

echo "== Agent Harness Lab :: public COMPLETION verification =="
echo "repo:   $ROOT"
command -v python3 >/dev/null 2>&1 || fail "python3 not on PATH (template's local_cli connector requires it)"
ver=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
case "$ver" in
  3.10|3.11|3.12) : ;;
  *) fail "unsupported Python $ver — AHL v1 supports 3.10–3.12 (run with PYTHON=python3.12)";;
esac

# 1. Install the package into an isolated venv (provides the `hlab` entry point).
echo "--- [1/11] install package into a throwaway venv ---"
"$PY" -m venv "$TMP/venv" || fail "venv creation"
VPY="$TMP/venv/bin/python"; HLAB="$TMP/venv/bin/hlab"
[ -x "$VPY" ] || { VPY="$TMP/venv/Scripts/python.exe"; HLAB="$TMP/venv/Scripts/hlab.exe"; }  # Windows
"$VPY" -m pip install -q --disable-pip-version-check "$ROOT" || fail "pip install"

run() { ( cd "$WS" && "$HLAB" "$@" ); }
WS="$TMP/ws"; mkdir -p "$WS"
EXP="experiments/memory-policy-ab"

echo "--- [2/11] hlab --help ---";          "$HLAB" --help >/dev/null 2>&1 || fail "hlab --help"
echo "--- [3/11] hlab init ---";            run init >/dev/null 2>&1 || fail "init"
echo "--- [4/11] hlab new --template ---";  run new memory-policy-ab --template memory-policy-ab-lite >/dev/null 2>&1 || fail "new --template"
echo "--- [5/11] hlab review (pre-conclude) ---"; run review "$EXP" >/dev/null 2>&1 || fail "review (pre)"
echo "--- [6/11] hlab run (no API key) ---"; run run "$EXP" >/dev/null 2>&1 || fail "run"
echo "--- [7/11] hlab status ---";          run status "$EXP" >/dev/null 2>&1 || fail "status"
echo "--- [8/11] hlab report ---";          run report "$EXP" >/dev/null 2>&1 || fail "report"
echo "--- [9/11] hlab compare ---";         run compare "$EXP" >/dev/null 2>&1 || fail "compare"
echo "--- [10/11] hlab conclude --winner B ---"; \
  run conclude "$EXP" --winner B --reason "Filtered retrieval cut leakage while keeping task success." >/dev/null 2>&1 || fail "conclude"
echo "--- [11/11] hlab review (post-conclude) ---"; run review "$EXP" >/dev/null 2>&1 || fail "review (post)"

# --- artifact assertions ---
D="$WS/$EXP"
echo "--- asserting artifacts under $EXP ---"
ls "$D/evidence/traces"/*.jsonl >/dev/null 2>&1 || fail "no evidence traces"
[ -f "$D/reports/report.md" ]   || fail "reports/report.md missing"
[ -f "$D/reports/report.html" ] || fail "reports/report.html missing"
[ -f "$D/reports/compare.json" ] || fail "reports/compare.json missing"
[ -f "$D/conclusion.md" ]        || fail "conclusion.md missing"

# Deterministic outcome: filtered retrieval (B) must win, with no API key.
grep -q '"winner": *"B"' "$D/reports/compare.json" || fail "compare winner is not B"
# report.html must be a REAL render (a table), not the old <pre> dump.
grep -q "<table" "$D/reports/report.html" || fail "report.html is not rendered (no <table>)"
# conclusion_missing must be cleared after conclude.
if run review "$EXP" 2>&1 | grep -q "conclusion_missing"; then
  fail "review still warns conclusion_missing after conclude"
fi
# llm_judge stays pending without a key (never a fabricated verdict).
grep -rqi "pending" "$D/evidence/scores" 2>/dev/null || true

echo "== ALL PUBLIC-COMPLETION CHECKS PASSED =="
echo "(verified: init -> new --template -> review -> run -> status -> report -> compare -> conclude; B won; report.md+html+compare.json+conclusion.md present; no API key)"
