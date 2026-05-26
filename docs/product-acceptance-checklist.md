# Product Acceptance Checklist

> Self-verification checklist for Agent Harness Lab. Two audiences:
>
> - **You just installed AHL** — work through groups A–G to confirm your
>   install reproduces the canonical sample-workspace flow.
> - **You're a maintainer about to merge / tag / release** — work
>   through groups H–L to confirm the release doesn't break any redline.
>
> Tone: pragmatic, command-driven. Each item is "what to check / how to
> check / what good looks like." Skip what doesn't apply.

---

## A. Sample workspace flow

The canonical end-to-end demo. If this fails, nothing downstream matters.

- [ ] **A1** — `cd examples/sample-workspace` resolves to a real
  directory containing `goal.md`, `runtime-sources.md`,
  `tiny-runtime/agent.py`, `harness-packages/concise-prompt/0.1.0/`, and
  `experiments/001-faq-conciseness/`.
- [ ] **A2** — `python -m agent_harness_lab probe 001` exits 0 (or
  `ahl probe 001` if the `ahl` script is on PATH). Stdout shows two
  variants both at `status=ok`.
- [ ] **A3** — `python -m agent_harness_lab run 001` exits 0. Writes 4
  run records to `experiments/001-faq-conciseness/results/run-*.json`.
- [ ] **A4** — `python -m agent_harness_lab score 001` exits 0. Writes
  `results/score-*.json` containing a top-level `evidence` block.
- [ ] **A5** — `python -m agent_harness_lab compare 001` exits 0. Writes
  `results/compare-*.md` with a `## Evidence` section + version-totals
  section.
- [ ] **A6** — Re-running A2–A5 a second time produces **identical**
  per-(variant, case) score totals (the `stub_grader` is deterministic).

How to verify quickly: `tests/test_sample_workspace_e2e.py` automates
A2–A5 + A6 against a temp copy.

---

## B. Probe behavior

- [ ] **B1** — Probe artifact lands at
  `experiments/001-faq-conciseness/probe-results/probe-<timestamp>/V*.json`,
  one file per variant.
- [ ] **B2** — V1's probe shows `runtime_source.type=local_path`,
  `harness_package=null`, `start_command.source=patch`.
- [ ] **B3** — V2's probe shows `runtime_source.type=local_path`,
  `harness_package.ref=concise-prompt@0.1.0`,
  `start_command.source=manifest`.
- [ ] **B4** — `probe` is read-only: no `sandbox/` directory created
  before `ahl run`, no source files modified.

---

## C. Run behavior

- [ ] **C1** — 4 run records (V1×C1, V1×C2, V2×C1, V2×C2), each with
  `transcript` length > 0 and `error == ""`.
- [ ] **C2** — Sandboxes created at
  `experiments/001-faq-conciseness/sandbox/run-<timestamp>/V*/` (kept
  by default for inspection; cleaned only with `--cleanup-sandboxes`).
- [ ] **C3** — Snapshots at
  `experiments/001-faq-conciseness/results/snapshots/run-<timestamp>/V*.json`.
- [ ] **C4** — V1 vs V2 transcripts differ — V1 agent text starts with
  `[DEFAULT verbose prompt: ...]`, V2 starts with `[STRICT concise
  prompt: ...]`. The harness package changed agent behavior.

---

## D. Score behavior

- [ ] **D1** — `score-*.json` has top-level keys
  `run / rubric / grader / scores / evidence`.
- [ ] **D2** — Each entry in `scores` has
  `version_id / case_id / dimensions / total`.
- [ ] **D3** — V1 average total ≠ V2 average total (delta is non-zero
  because the package changed agent text → different `stub_grader`
  hashes).
- [ ] **D4** — Default grader is `stub_grader` ("本地桩(未接真模型)"
  in the JSON). No API key required for the sample workspace.

---

## E. Compare behavior

- [ ] **E1** — `compare-*.md` has `## Evidence` section *before* the
  version-totals section.
- [ ] **E2** — Evidence table shows both V1 and V2 at `strong`.
- [ ] **E3** — V2's reason column mentions
  `concise-prompt@0.1.0 fully fingerprinted`.
- [ ] **E4** — Version totals show V1 (basline) and V2 with a numeric
  delta vs V1.
- [ ] **E5** — Comparator math, winner selection, and per-dimension
  delta unchanged from v0.7 / v0.6 / v0.4 contracts (no regressions).

---

## F. Snapshot package fingerprint

- [ ] **F1** — V1 snapshot has `harness_package: null` (no package
  declared).
- [ ] **F2** — V2 snapshot has `harness_package` block with **all three
  hashes** present and non-empty:
  - `manifest_hash` (sha256 of manifest.md raw bytes)
  - `payload_hash` (sha256 over sorted payload files + env + start_command)
  - `effective_harness_hash` (sha256 over sandbox files after both
    install layers applied)
- [ ] **F3** — V2 snapshot `install_order` = `["package", "patch"]`
  (variant patch wins, runs *after* the package install).
- [ ] **F4** — V2 snapshot `manifest_path` is
  `harness-packages/concise-prompt/0.1.0/manifest.md` (forward slashes
  for cross-OS reproducibility).

---

## G. Evidence presence and interpretation

- [ ] **G1** — Compare report's Evidence table renders both V1 and V2 at
  `strong` for the sample workspace (no `weak` / `unknown` warnings).
- [ ] **G2** — Score JSON's `evidence.summary.levels` shows
  `{strong: 2, medium: 0, weak: 0, unknown: 0}`; `warning` and `note`
  are both `null` (uniform-strong path).
- [ ] **G3** — Reading [`evidence-guide.md`](evidence-guide.md) answers
  these without ambiguity:
  - What does each of `strong / medium / weak / unknown` mean?
  - How do I upgrade a legacy `connect.md` variant from `weak` to
    `medium`?
  - Why is supplied evidence **not** cloud attestation?
  - How does a `harness_package` affect the evidence label?
- [ ] **G4** — [`examples/evidence-examples/`](../examples/evidence-examples/)
  has 3 templates (runtime / harness / cloud) and a README explaining
  when to use each.

---

## H. Generated artifact cleanliness

The committed `examples/sample-workspace/` is a *source* of truth — it
must not carry generated outputs from previous runs.

- [ ] **H1** — `examples/sample-workspace/experiments/001-faq-conciseness/`
  does **not** contain `results/`, `probe-results/`, `sandbox/`, or
  `materials/runtime-evidence.md` in the committed tree.
- [ ] **H2** — `.gitignore` patterns at repo root cover those four
  paths. Verify: `git check-ignore -v examples/sample-workspace/experiments/001-faq-conciseness/results/`
  reports a match.
- [ ] **H3** — `examples/sample-workspace/` is otherwise complete: 14
  committed source files (run `find examples/sample-workspace -type f`).

How to verify quickly: `tests/test_sample_workspace_e2e.py::TestRepoSampleWorkspaceClean`
and `tests/test_doc_consistency.py::TestSampleWorkspaceCleanliness`
automate H1.

---

## I. README command accuracy

Both English and Chinese README must reflect the real CLI surface.

- [ ] **I1** — README §8 "Simplest end-to-end workflow" mentions
  `ahl probe`, `ahl run`, `ahl score`, `ahl compare` (in that order).
- [ ] **I2** — README_CN §8 mirrors the same four command anchors.
- [ ] **I3** — `examples/sample-workspace/README.md` 5-step recipe
  includes the experiment-id-qualified commands: `ahl probe 001`,
  `ahl run 001`, `ahl score 001`, `ahl compare 001`.
- [ ] **I4** — Each command listed in those sections is invokable via
  `python -m agent_harness_lab <subcommand>` (the test verifies this
  by subprocess against a temp sample-workspace copy).

How to verify quickly: `tests/test_readme_command_flow.py` covers
I1–I4.

---

## J. Docs navigation sanity

- [ ] **J1** — `docs/README.md` "首次接触的推荐顺序" path resolves
  start-to-finish: walkthrough → product-definition → sample-workspace
  README.
- [ ] **J2** — `docs/README.md` mainline list links each currently
  shipped MVP spec: `evidence-aware-result.md`,
  `harness-package-mvp.md`, `runtime-probe-mvp.md`,
  `product-flow-completion.md`, and the user-facing
  `evidence-guide.md`.
- [ ] **J3** — Each `[text](path)` reference in current docs (excluding
  `docs/archive/`, `docs/handoffs/`, and banner-tagged historical docs)
  resolves to a real file or directory.
- [ ] **J4** — `examples/evidence-examples/README.md` is discoverable
  from `docs/README.md` and `docs/evidence-guide.md`.

How to verify quickly: `tests/test_doc_consistency.py` covers J1–J4.

---

## K. Redlines before merge to main

Before fast-forwarding any feature branch into main:

- [ ] **K1** — Both pytest modes pass:
  `PYTHONPATH=src py -m pytest tests` and
  `PYTHONPATH=src py -W error::ResourceWarning -m pytest tests`.
- [ ] **K2** — `py -m compileall -q src tests` exits 0.
- [ ] **K3** — `git diff --check` exits 0 (no whitespace issues).
- [ ] **K4** — No new CLI command. `ahl --help` shows the same 14
  commands as the prior release.
- [ ] **K5** — No new src module unless the cycle's spec authorized
  it.
- [ ] **K6** — No new dependency. `pyproject.toml` `dependencies = []`.
- [ ] **K7** — Repo visibility is still PRIVATE.
- [ ] **K8** — Merge command is `git merge --ff-only <branch>` — no
  three-way merge that loses history.
- [ ] **K9** — Push is `git push origin main` — no `--force`,
  no `+` ref-spec.

---

## L. Redlines before release / tag / GitHub Release

If the cycle ships an internal (PRIVATE) release:

- [ ] **L1** — `pyproject.toml` version bumped (e.g. `0.7.0 → 0.8.0`)
  in a dedicated `chore(release): prepare vX.Y.Z metadata` commit.
- [ ] **L2** — `CHANGELOG.md` `[Unreleased]` promoted to `[X.Y.Z] -
  <date>` with full bullets. `[Unreleased]` reset to empty placeholder.
  Compare-link footer extended.
- [ ] **L3** — `docs/roadmap.md` updated: this cycle marked `[shipped]`;
  next cycle not over-committed.
- [ ] **L4** — Annotated tag created with `git tag -a vX.Y.Z -m "..."`
  *after* the release-prep commit is on main. Verify `git rev-parse
  vX.Y.Z^{}` equals the release-prep commit, not a feature commit.
- [ ] **L5** — `git push origin vX.Y.Z` (annotated tag push) — no
  `--force`.
- [ ] **L6** — GitHub Release created via `gh release create vX.Y.Z
  --notes-file <path>`. `gh release view vX.Y.Z` shows `draft: false`,
  `prerelease: false`. `gh release list --limit 1` shows it as Latest.
- [ ] **L7** — Repo visibility **still PRIVATE** after the release.
- [ ] **L8** — Feature branch preserved (not deleted) for audit trail.
- [ ] **L9** — No PyPI publish. No public announcement / blog / social.

---

## When this checklist itself drifts

If you find an item in this checklist that the codebase no longer
matches (e.g., a command renamed, a path moved), **fix the checklist**
before merging the change that broke it. The checklist is the
user-facing acceptance contract; treating it as authoritative keeps
the docs ↔ code chain honest.

For automated equivalents that catch drift on every PR / commit:

- `tests/test_doc_consistency.py` — links, file presence, banner
  detection, simulator-claim ↔ code consistency.
- `tests/test_readme_command_flow.py` — README §8 + sample-workspace
  recipe ↔ real CLI invocation.
- `tests/test_sample_workspace_e2e.py` — full product flow + score
  determinism + committed-tree cleanliness.

If a check here lacks a test, that's a candidate addition for the
next reliability cycle.
