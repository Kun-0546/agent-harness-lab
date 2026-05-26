# Public Launch Checklist

> **Future GO / NO-GO review tool**. This checklist is consulted
> *post-v0.10*, before a separate, explicit decision to flip the
> repository from PRIVATE to public. **v0.10 itself does NOT flip
> visibility.** v0.10 ships this checklist as a durable artifact;
> running through it is a *post-v0.10* event, not v0.10 work.
>
> Format mirrors [`product-acceptance-checklist.md`](product-acceptance-checklist.md)
> (12 groups A–L). Each item is "what to check / how to check /
> what good looks like." Skip what doesn't apply.
>
> **Not an automatic process.** All groups green is **necessary
> but not sufficient** for visibility flip. A separate Kun decision
> is always required. See [`open-source-readiness-freeze.md`](open-source-readiness-freeze.md)
> §16 for the GO / NO-GO criteria.

---

## A. Repo hygiene

The repo's file shape should not embarrass on first public read.

- [ ] **A1** — `git ls-files | wc -l` shows a reasonable count
  (~130 ± expected new files); no surprise binaries or generated
  artifacts in tracked files.
- [ ] **A2** — `git ls-files | xargs -I {} ls -la {} 2>/dev/null
  | awk '$5 > 1048576 {print}'` returns empty (no >1MB files —
  stdlib-only Python should have none).
- [ ] **A3** — `.gitignore` covers `__pycache__/`, `.venv/`,
  `venv/`, `temp/`, sample-workspace generated artifacts
  (`experiments/*/results/`, `probe-results/`, `sandbox/`,
  `materials/runtime-evidence.md`).
- [ ] **A4** — No `*.egg-info/` / `dist/` / `build/` directories
  tracked.
- [ ] **A5** — Top-level governance files all present: `README.md`,
  `README_CN.md`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CHANGELOG.md`, `pyproject.toml`.

---

## B. Docs first impression

The first 5 minutes of a public visitor's read.

- [ ] **B1** — `README.md` opens with a one-paragraph "what AHL
  is" pitch (current §0 blurb).
- [ ] **B2** — README §1-§7 answer the 7 concept questions
  cleanly (what is AHL / problem / runtime / harness / harness
  package / probe / evidence).
- [ ] **B3** — README §8 "Simplest end-to-end workflow" points
  at `examples/sample-workspace/` with copy-pasteable commands.
- [ ] **B4** — README §9 "What is NOT implemented yet" is honest:
  Auto mode listed as **deferred to v1.x / post-open-source**
  (NOT "M2+ coming soon"); Cloud attestation NOT implemented;
  harness package registry / PyPI NOT implemented; runtime source
  M2+ types NOT implemented.
- [ ] **B5** — `docs/README.md` mainline reading order resolves
  every link (use the v0.8
  `tests/test_doc_consistency.py::TestDocsReadmeMainlineLinks`).
- [ ] **B6** — `docs/product-walkthrough.md` Step 1 → Step 9
  navigates cleanly; Step 6.5 references probe correctly.
- [ ] **B7** — `docs/copilot-setup.md` (v0.9) reads as a complete
  guide for both human operators and coding agents.

---

## C. Install + smoke (Linux/macOS caveat applies)

`pip install -e .` works on a fresh clone + clean venv.

> **Caveat**: in v0.10, install audit was performed **Windows-
> only** (Kun's machine). Linux and macOS were **not independently
> tested in v0.10**. Re-test on at least one Linux / macOS host
> before visibility flip if possible.

- [ ] **C1** — Fresh `git clone https://github.com/Kun-0546/
  agent-harness-lab.git` succeeds.
- [ ] **C2** — Fresh virtualenv: `python -m venv .venv &&
  source .venv/bin/activate` (or Windows `py -m venv .venv;
  .\.venv\Scripts\Activate.ps1`).
- [ ] **C3** — `pip install -e .` (or `py -m pip install -e .`)
  exits 0; no `pip` errors; no missing dependencies (should
  install zero — stdlib-only).
- [ ] **C4** — `ahl --help` prints exactly 14 subcommands:
  `init walkthrough connect new show cases rubric simulator
  harnesses run score compare review probe`.
- [ ] **C5** — `python -m agent_harness_lab --help` works as a
  fallback if `ahl` isn't on PATH.
- [ ] **C6** — `ahl init` in a fresh empty directory creates
  `goal.md` and `experiments/`.
- [ ] **C7** — `ahl new rc-check --mode copilot` creates
  `experiments/01-rc-check/brief.md` + `materials/README.md` +
  `cases/` + `harnesses/`; no errors.

---

## D. Sample workspaces

Three example trees ship with the repo; each must still work.

- [ ] **D1** — `cd examples/sample-workspace && ahl probe 001
  && ahl run 001 && ahl score 001 && ahl compare 001` succeeds
  end-to-end; compare report contains `## Evidence` section with
  evidence level `strong`.
- [ ] **D2** — `tests/test_sample_workspace_e2e.py` passes.
- [ ] **D3** — `examples/copilot-setup-example/` exists with the
  9 expected files; `tests/test_copilot_setup_example.py`
  passes (17 tests including setup-state-only invariants).
- [ ] **D4** — `examples/evidence-examples/` exists with
  `README.md` + 3 attestation templates
  (`runtime-evidence.md`, `harness-evidence.md`,
  `cloud-evidence.md`).
- [ ] **D5** — No generated artifacts in any example tree
  (verified by `tests/test_doc_consistency.py` cleanliness
  checks).

---

## E. Evidence reading

A public visitor running `ahl compare` should understand the
output without out-of-band help.

- [ ] **E1** — Compare report `## Evidence` section is
  self-explanatory: each variant has an `evidence_level`
  (strong / medium / weak / unknown) and a `reason` string.
- [ ] **E2** — `docs/evidence-guide.md` (v0.8) explains all
  four levels + how to upgrade weak → medium → strong.
- [ ] **E3** — `examples/evidence-examples/` templates are
  copy-able into a user's `materials/` directory; the
  "**not** cloud attestation" honest disclosure in
  `cloud-evidence.md` is prominent.

---

## F. Co-pilot workflow

The default `ahl new` mode produces an actionable workflow.

- [ ] **F1** — `ahl new <name>` (default `--mode copilot`)
  generates the 12-section brief.md and 8-section
  materials/README.md.
- [ ] **F2** — `docs/copilot-setup.md` covers the workflow
  end-to-end (9 sections, ≤400 lines).
- [ ] **F3** — `examples/copilot-setup-example/` demonstrates a
  filled brief + materials + `expected-coding-agent-plan.md`
  (3-anchor schema).
- [ ] **F4** — `tests/test_copilot_templates.py` +
  `tests/test_copilot_setup_example.py` cover drift.

---

## G. Honest status (no overclaim)

README and docs must not claim capabilities AHL does not have.

- [ ] **G1** — Search `README.md` + `README_CN.md` for words
  "scientific" / "rigorous" / "production-ready" — should be 0
  occurrences (or contextual / hedged).
- [ ] **G2** — Search docs for "open source soon" / "ready for
  public" / "公开发布" — should be 0 occurrences.
- [ ] **G3** — Auto mode is consistently described as **deferred
  to v1.x / post-open-source**, NOT as imminent or as v0.10
  scope.
- [ ] **G4** — No claims that AHL has cloud attestation,
  package registry, package publish, MCP integration, CI
  workflow, or any unimplemented capability listed in
  README §9.
- [ ] **G5** — `--mode auto` still exits 2 with not-implemented
  message; the message recommends `--mode copilot` +
  `docs/copilot-setup.md`.

---

## H. Governance

- [ ] **H1** — `LICENSE` is MIT, with current year and Kun's
  name as copyright holder.
- [ ] **H2** — `CONTRIBUTING.md` accurately describes the
  current cycle workflow + notes that the repo is currently
  single-maintainer and external PRs are not yet accepted
  (until / unless visibility flips and the maintenance posture
  changes).
- [ ] **H3** — `SECURITY.md` lists Kun's documented disclosure
  contact + notes the env-var-key policy (`AHL_JUDGE_API_KEY`
  / `AHL_SIM_API_KEY` are never written to disk).
- [ ] **H4** — No `.github/` directory expected in v0.10 (issue
  templates / PR template / CODEOWNERS / CI workflow are
  deferred to the visibility-flip cycle). If `.github/` exists,
  verify it does not advertise external contribution channels
  that are not yet honored.

---

## I. Release history coherence

- [ ] **I1** — `git tag --list` matches `gh release list` matches
  CHANGELOG section ordering.
- [ ] **I2** — Every CHANGELOG `[X.Y.Z] - YYYY-MM-DD` entry has
  a corresponding tag of the same version.
- [ ] **I3** — `[Unreleased]` section exists (empty placeholder
  is OK between releases).
- [ ] **I4** — `docs/roadmap.md` v0.X status matches reality:
  shipped versions = [shipped], current/next = [exploring] /
  [in progress], future = [future].
- [ ] **I5** — No release-history claims that contradict tags
  (e.g., do NOT claim v0.10 shipped before the v0.10.0 tag
  exists).
- [ ] **I6** — v0.1.0 / v0.2.0 absence from CHANGELOG is
  documented (those predate the Keep-a-Changelog adoption in
  v0.3.1).

---

## J. Security / private-information scan

Pre-flip irreversibility risk. **Run twice**, weeks apart, before
any flip.

- [ ] **J1** — `git grep -iIE
  '(api[_-]?key|apikey|password\s*=|secret\s*=|BEGIN.*KEY|
  authorization:\s*bearer|aws_access_key|gcp_credentials)'`
  returns only env-var NAMES (no actual values).
- [ ] **J2** — `git log -p --all | grep -iIE
  '(BEGIN.*KEY|password\s*=)'` — even commit history is clean.
- [ ] **J3** — `git grep -iIE
  '[a-z0-9._%+-]+@[a-z0-9.-]+\.(com|net|org|io)'` returns only
  Kun's documented contact + noreply addresses.
- [ ] **J4** — No internal hostnames / IPs / customer names /
  coworker names / Slack handles in any file.
- [ ] **J5** — No accidentally-committed-then-rolled-back
  secrets in `git log`.

---

## K. Packaging

- [ ] **K1** — `pyproject.toml` `version` matches the latest
  tag.
- [ ] **K2** — `name = "agent-harness-lab"` — no PyPI namespace
  collision check needed unless we are about to publish.
- [ ] **K3** — `requires-python = ">=3.10"` — verified against
  actual stdlib usage.
- [ ] **K4** — `dependencies = []` — stdlib-only philosophy
  maintained.
- [ ] **K5** — `classifiers` / `keywords` / `authors` / `urls`
  metadata is complete and accurate.
- [ ] **K6** — `[project.scripts]` exposes `ahl` (+ legacy
  `hdl` redirect) — verified by `ahl --help`.

---

## L. RC tests + planning-branch hygiene

- [ ] **L1** — `pytest tests` passes in default mode
  (~520 tests for v0.10).
- [ ] **L2** — `pytest -W error::ResourceWarning tests` passes
  in strict mode.
- [ ] **L3** — `py -m compileall -q src tests` is clean.
- [ ] **L4** — `git diff --check` is clean.
- [ ] **L5** — `tests/test_release_candidate.py` passes all 5
  RC invariants (required files / EN-CN parity / no
  unresolved TODO/XXX/FIXME / CHANGELOG ↔ tag order / no
  broken internal links).
- [ ] **L6** — Audit-trail planning branches review: decide
  whether to keep `v0.7.0-planning`, `v0.8.0-planning`,
  `v0.9.0-planning`, `v0.10.0-planning` visible on origin
  post-flip. **v0.10 default = keep** (audit trail > cosmetic);
  the visibility-flip cycle revisits this.

---

## Final GO / NO-GO

After all 12 groups green, the post-v0.10 visibility-flip
decision still requires a **separate, explicit Kun yes**.

**GO** ⇒ run a separate visibility-flip-cycle spec (NOT this
one). That cycle will cover: `.github/` workflow / templates,
PyPI publish posture, public announcement plan, support /
issue triage plan, maintenance posture.

**NO-GO** ⇒ list specific blocker findings; treat them as input
to a follow-on PRIVATE-cycle (e.g., security remediation,
docs cleanup, sample-workspace fix). Do NOT flip until they
are resolved and the checklist runs green again.

**Public launch is irreversible** in practice (you can re-make
the repo PRIVATE, but the public footprint stays in
search indexes / forks / archive sites). Treat the GO as a
one-way door; run the checklist twice if uncertain.
