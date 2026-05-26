# Agent Harness Lab

English | [中文](README_CN.md)

> A workbench for humans and coding agents to design, test, and improve the **runtime harnesses** that shape agent behavior.

Change a harness — a prompt, a tool config, a memory rule, a workflow — then measure whether the change made the agent better, worse, or no different. `ahl` runs experiments: you describe a goal, a set of harness variants, a set of test cases, and a rubric; the tool drives each variant through the cases, scores the conversations, and lays the variants side by side so you can see what the change did.

## 1. What is Agent Harness Lab?

A CLI-driven workbench for **comparing harness variants of an agent on the same cases, with reproducible evidence**. You point AHL at an agent runtime, hand it 2–3 variants of the harness you want to test, hand it a small set of cases and a scoring rubric, and it produces a side-by-side compare report with snapshots that capture exactly what ran.

It is Python 3.10+, stdlib-only (zero external dependencies), and runs locally. The full [`docs/product-definition.md`](docs/product-definition.md) frames the three layers (Harness / Experiment / Loop) and the core objects.

## 2. What problem does it solve?

I'm an AI Product Manager. My day job is designing memory, skill, and harness features for AI agents — features where you can't write a PRD on Monday and ship it Friday, because the design surface is in flight and the right answer is unknown when you start.

For months I ran the same loop on my own work: define a goal, build a change, run experiments, look at the data, refine the goal, repeat. The pattern was consistent enough to treat as an architecture, not a workflow. `ahl` is that loop, extracted into a tool — but with a sharper claim than "evaluate agents": the first-class object is the **harness** that wraps the agent, not the agent itself.

## 3. What is a runtime?

The agent's execution environment — the source code, prompts, tools, configs, and start command that, when run, produce agent behavior. In AHL, you declare runtime sources in `runtime-sources.md` (workspace root). Two source types are supported in v0.3.0:

- **`local_path`** — a directory on your machine. AHL copies it into a per-variant sandbox and applies the variant's patch.
- **`git_repo`** — clone + checkout a specific ref + apply patch.

The materialization pipeline is `materialize → snapshot → start`, and every run persists a `RuntimeSnapshot` (source dir hash, patch hash, commit SHA) so a run is reproducible months later. Depth detail: [`docs/runtime-materialization.md`](docs/runtime-materialization.md).

## 4. What is a harness?

The **external structure that shapes agent behavior without changing the model weights** — prompts, tool configs, memory rules, workflow steps, start command, env. A harness variant is one specific configuration of that structure. AHL's first-class object.

You write one variant per file at `experiments/<id>/harnesses/V*.md`. By convention `V1` is the baseline; `V2+` are the changes you want to test. A variant declares `runtime_source:` (which runtime it patches) and an optional `## Patch` section (files / env / start_command overrides). Format: [`docs/file-formats.md`](docs/file-formats.md) §Harness Variant.

## 5. What is a harness package?

A **reusable, versioned, installable harness component** at workspace root: `harness-packages/<id>/<version>/{manifest.md, payload/...}`. A variant opts in with frontmatter `harness_package: <id>@<version>`, and AHL installs the package's payload into the variant's sandbox before applying the variant's patch.

Install order is fixed: **runtime materialize → package install → variant `## Patch` → snapshot**. Variant patch wins on file/env/start_command conflicts. The snapshot records the package's `manifest_hash`, `payload_hash`, and `effective_harness_hash` — three fingerprints that together prove which package version actually ran. Depth detail: [`docs/harness-package-mvp.md`](docs/harness-package-mvp.md).

## 6. What is probe?

A **read-only pre-run inspection** of every variant: `ahl probe <experiment>`. Checks `runtime_source` is accessible, the harness package (if any) is complete, the start command is supplied, and optionally runs a user-supplied smoke command (`--command "<cmd>"`, default 30s timeout). It never creates a sandbox, never installs anything, and never mutates source.

Probe-results land at `experiments/<id>/probe-results/<probe_id>/<variant_id>.json`. Probe failure is **advisory** (any variant `fail` → exit 1) — it does not block `ahl run`. Depth detail: [`docs/runtime-probe-mvp.md`](docs/runtime-probe-mvp.md).

## 7. What is evidence?

A four-level label on every variant's score (`strong` / `medium` / `weak` / `unknown`) inferred from the runtime snapshot plus optional `materials/*-evidence.md` files. `strong` means AHL materialized the runtime itself and (if the variant uses a package) fingerprinted it completely. `weak` / `unknown` means AHL couldn't prove what actually ran — typically a legacy `connect.md` adapter or a cloud agent without supplied attestation.

Evidence shows up at the **top of the compare report** as a `## Evidence` section. The point is not to block decisions — it's to let you make `keep / discard / next` calls with eyes open on how much you can trust the numbers. User guide: [`docs/evidence-guide.md`](docs/evidence-guide.md) (when to trust each level, how to upgrade weak → medium, why supplied evidence is not cloud attestation). Implementation contract: [`docs/evidence-aware-result.md`](docs/evidence-aware-result.md).

## 8. Simplest end-to-end workflow

The sample workspace at [`examples/sample-workspace/`](examples/sample-workspace/) is pre-initted, fully local, fully offline, zero API keys, and uses a deterministic 30-line tiny agent. From the repo root:

```bash
cd examples/sample-workspace
ahl probe 001            # readiness check (read-only)
ahl run 001              # 2 variants × 2 cases = 4 conversations
ahl score 001            # stub_grader → score-*.json with evidence block
ahl compare 001          # compare-*.md with ## Evidence + version totals
```

V2 uses the `concise-prompt@0.1.0` package; V1 does not. The compare report shows the package made a measurable, reproducible behavior delta. See [`examples/sample-workspace/README.md`](examples/sample-workspace/README.md) for the full recipe and what to expect.

For your own work: `ahl init` → fill `goal.md` → `ahl walkthrough` (prints the 9-step product flow) → declare runtime in `runtime-sources.md` (recommended) or `connect.md` (legacy) → `ahl new <name>` → run / score / compare. The 9 steps are documented in [`docs/product-walkthrough.md`](docs/product-walkthrough.md).

## Install

Requires Python 3.10+.

```
git clone https://github.com/Kun-0546/agent-harness-lab.git
cd agent-harness-lab
pip install -e .
```

This installs the `ahl` command. If your shell reports `ahl: command not found`, the script directory isn't on your PATH — add it, or run the tool as `python -m agent_harness_lab` (on Windows, `py -m agent_harness_lab`).

## Three product modes

`ahl` exposes three setup modes (full flow in [`docs/product-walkthrough.md`](docs/product-walkthrough.md) Step 2):

- **Manual** — you design harness variants and the experiment; `ahl` validates, runs, scores, compares. **Shipped.**
- **Co-pilot** *(default)* — an external coding agent (Claude Code / Cursor / Codex) collaborates with you through conversation to maintain `brief.md` and `materials/`, and to generate or complete the experiment files. **Shipped.** Driving guide: [`docs/copilot-setup.md`](docs/copilot-setup.md); setup-state reference: [`examples/copilot-setup-example/`](examples/copilot-setup-example/).
- **Auto** — agents iterate harnesses inside rules, budgets, and approval gates; escalate to you on anomalies. **Future mode** (depends on calibration + approval gates, M2+).

## Commands

14 commands: `init` · `walkthrough` · `connect` · `new` · `show` · `cases` · `rubric` · `simulator` · `harnesses` · `run` · `score` · `compare` · `review` · `probe`. Run `ahl --help` or `ahl <command> --help` for details.

`run` and `score` default to built-in stubs (a canned simulator and a hash-based grader) — enough to smoke-test the pipeline, not to produce real results. For real runs, pass `--llm` and set the model env vars (`AHL_SIM_*` for the simulator, `AHL_JUDGE_*` for the grader). `examples/` ships a minimal agent for each of the four connection types (in-process library, external CLI, HTTP stateless, HTTP stateful), each with its protocol documented.

## 9. What is NOT implemented yet

Honest status — each item names the version that would carry it:

- **Auto mode** — agent-iterated harnesses with approval gates and budget rules. Needs calibration + approval gates first (M2+).
- **Cloud attestation** — proving what actually loaded inside a remote agent runtime. Currently cloud variants land at `weak` evidence unless you hand-write `materials/*-evidence.md`.
- **Harness package registry / remote distribution** — packages are workspace-local only (v0.5). No `ahl package publish`, no fetch, no version resolver.
- **Additional runtime source types** — `docker_image`, `remote_api`, `dev_agent` are spec'd but deferred to runtime-materialization M2+.
- **`depends_on`** — seeding a case from a prior case's transcript is parsed and displayed but not consumed by `run` yet.
- **Replay / scripted conversation modes** — only the simulated mode is implemented.
- **Noise / trial / multi-run statistics** — every run is a single trial today.
- **Polished public case study** — no published worked example yet; treat AHL as an architecture being proposed.

## History

This project began as **HDL / Harness Design Loop**. It is now renamed to **Agent Harness Lab** to make explicit what the first-class object actually is. HDL remains as a historical codename in commit history, old branches, and the v1 design docs (`docs/design-v0.3.md` / `docs/design-v0.4.1.md`).

## Related Work

**Heuristic Learning** — Jiayi Weng, *Learning Beyond Gradients* (2026): a coding agent improves a software system by editing code — rules, state, tests, memory — rather than training neural-network parameters. `ahl` is a tool for running that kind of loop.

**Karpathy's AutoResearch** (2026) demonstrated an automated research loop on ML training against a fixed objective. `ahl` addresses an adjacent problem — AI *product* research, where the goal itself is under revision. A reference, not a template.

## Author

Built by Kun, an AI Product Manager.
