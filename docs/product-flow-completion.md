# Product Flow Completion · v0.7 Spec

> 这份 spec 定义 Agent Harness Lab 的 v0.7 **Complete Product Flow MVP** ——
> 把已经实装的 4 个 MVP(runtime materialization v0.3.0 / evidence v0.4 /
> harness package v0.5 / runtime probe v0.6)从"独立模块"收敛到"完整产品
> 流",让一个刚 clone 的新用户能在 30 分钟内 zero API keys / zero cloud /
> zero network 拿到第一份 compare report。
>
> Status: target v0.7.0,branch `v0.7.0-planning`。**spec lock-in only —
> 代码尚未实现**。
> Date: 2026-05-26。
> Direction (per Kun, rev 2): v0.7 是**内部产品完成**,**不是** public
> launch / PyPI / announcement / visibility flip。Repo 全程 PRIVATE。

---

## 1. Purpose

v0.3.0 加了 runtime materialization,v0.4 加了 evidence,v0.5 加了
harness package,v0.6 加了 runtime probe。**每一档都独立可用,但合在一起
不像一个完整的产品**:

- 没有一个端到端可跑的样例 workspace,新用户只能读 spec 推断怎么用
- README 还停在 v0.3.1 的语气,没反映出 v0.5/v0.6 已经成熟的现状
- docs/ 4 份 MVP spec 互相不引用产品入口,user 找不到"应该按什么顺序读"
- CLI 14 个命令的错误消息散落,有的指向被 deprecate 的文档,有的没有给
  "下一步"建议
- 没有一份自动化脚本能在每次改动后验证"整条产品流是不是仍然 work"

**v0.7 修这一档**:把"看上去像个完整产品"这件事完成,不加任何底层能力。

---

## 2. Product problem

具象的 friction list:

- 新用户 clone repo,看 README,**还是不知道**:harness 是什么?package
  是什么?probe 干嘛?evidence 怎么影响 keep/discard?
- 新用户想试一下,**没有现成的可跑实验**。要自己拼 goal.md / 找一个
  runnable agent / 写一个 harness package / 写 cases。门槛过高。
- 新用户读 `docs/product-walkthrough.md`,9 步流程对了,但 cross-link 到
  其他 spec 时,有的 spec 不指回 walkthrough,**心智模型断**。
- `ahl run` / `ahl probe` 等命令的 error message 偶有差异化(有的说 ahl
  init,有的说改 connect.md),**用户不知道哪个 first**。
- 改了一行代码,跑完测试 462 全过,**但不知道"产品流"是不是还 work** ——
  没有 e2e 验证。

v0.7 目标就是消掉这 5 类 friction。

---

## 3. What "complete product flow" means

四个判据(v0.7 完成的可验证标志):

1. **A brand-new user can clone-and-run the sample workspace** without
   reading source code, ending in a `compare-*.md` with `## Evidence`
   section in <30 minutes.
2. **`README.md` + `README_CN.md` answer the 9 concept questions**
   (§10) clearly, with one paragraph per concept and a worked example
   pointing at the sample workspace.
3. **`docs/README.md` mainline list is a coherent reading order** —
   start at `product-walkthrough.md`,depth-read individual specs as
   needed.
4. **One automated pytest acceptance script** runs the full sample
   workspace flow as a regression gate;the script's pass = v0.7 is
   intact.

---

## 4. Non-goals (redlines, consolidated)

v0.7 explicitly **does not**:

- **NOT** flip repo visibility — repo stays PRIVATE
- **NOT** publish to PyPI
- **NOT** prepare public announcement / blog post / social
- **NOT** add any new CLI command (the 14 already shipped are the cap)
- **NOT** implement Auto / autonomous iteration / approval gates
- **NOT** implement registry / remote package distribution / package
  fetch
- **NOT** implement cloud attestation
- **NOT** add new runtime source types (docker_image / remote_api /
  dev_agent — v0.5 deferred to M2+)
- **NOT** change snapshot schema
- **NOT** change v0.4 evidence rules
- **NOT** change scoring / comparator math
- **NOT** add external dependencies (stdlib-only philosophy continues)
- **NOT** add CODE_OF_CONDUCT.md or PR/Issue templates
- **NOT** break v0.5 harness package or v0.6 probe contracts

---

## 5. Target user

A senior-ish IC who:

- can read Python
- has Python 3.10+ on their machine (PATH-accessible as `python` or `py`)
- doesn't have an LLM API key handy (and shouldn't need one to feel the
  product)
- has 30 minutes of attention budget
- is evaluating whether AHL is the right tool for their agent-improvement
  workflow

Out-of-scope target users: non-technical PMs (would need an interactive
walkthrough — not v0.7), users without Python (would need pre-built
binaries — not v0.7).

---

## 6. End-to-end sample workspace design

`examples/sample-workspace/` — **fully local + deterministic + offline +
zero API keys**. Demonstrates the full v0.3-v0.6 product surface.

### Story

> An AI PM is evaluating an FAQ-bot. The bot's answers are verbose. They
> want to compare:
> - **V1 (baseline)**: bot uses default system prompt → verbose answers
> - **V2**: bot uses `concise-prompt` harness package → terse answers
>
> Both run against the same cases. Compare report shows the prompt-package
> changed agent behavior in a measurable way.

### Architecture

```
examples/sample-workspace/
├── README.md                                # how to run the sample (5-step recipe)
├── goal.md                                  # workspace-level goal (FAQ-bot conciseness)
├── runtime-sources.md                       # declares local-tiny → tiny-runtime/
├── tiny-runtime/                            # the runnable agent
│   ├── agent.py                              # deterministic CLI agent (stdin JSON → stdout JSON)
│   └── prompts/
│       └── system.md                         # DEFAULT prompt
├── harness-packages/
│   └── concise-prompt/
│       └── 0.1.0/
│           ├── manifest.md                   # references payload/system.md
│           └── payload/
│               └── system.md                 # STRICT/concise prompt
└── experiments/
    └── 001-faq-conciseness/
        ├── program.md                        # experiment spec (assumption + 声明)
        ├── rubric.md                         # 2 dimensions: correctness, conciseness
        ├── simulator.md                      # minimal persona (single-turn fixture)
        ├── harnesses/
        │   ├── V1.md                         # baseline, runtime_source=local-tiny, ## Patch with start_command
        │   └── V2.md                         # runtime_source=local-tiny, harness_package=concise-prompt@0.1.0
        └── cases/
            ├── C1.md                         # FAQ question 1
            └── C2.md                         # FAQ question 2
```

### Determinism guarantees

- `tiny-runtime/agent.py` is **pure stdlib** + reads `prompts/system.md`
  and prepends it to the response. No randomness, no model calls.
- V1 sandbox: source copied → has DEFAULT prompt → agent answers
  `"DEFAULT: <user input>"`
- V2 sandbox: source copied → package install overwrites `prompts/system.md`
  with STRICT prompt → agent answers `"STRICT: <user input>"`
- `ahl score` uses `stub_grader` (no `--llm`) → score is a deterministic
  sha1 of `(dimension, agent_text)`. Different agent_text → different
  scores → V1 vs V2 compare delta is non-trivial and stable.
- `stub_simulator` returns None after first turn → 1-turn conversations
  → no simulator-side variance.

### Reproducibility test

Two consecutive `ahl run → score → compare` should produce **identical
score numbers** (modulo timestamps in filenames). Acceptance script
verifies this.

---

## 7. Required sample workspace files (concrete list)

| Path | Contents |
|---|---|
| `examples/sample-workspace/README.md` | 5-step user recipe + expected outputs + troubleshooting |
| `examples/sample-workspace/goal.md` | Workspace goal: improve FAQ-bot conciseness; baseline = verbose; success criterion = shorter response without losing correctness |
| `examples/sample-workspace/runtime-sources.md` | One source declared: `local-tiny` → `examples/sample-workspace/tiny-runtime/` (absolute path requirement: user adjusts, OR doc says use absolute path of clone) |
| `examples/sample-workspace/tiny-runtime/agent.py` | ~30-line Python CLI agent: stdin JSON `{"input"}` → stdout JSON `{"response": "<prompt-prefix>: <input>"}`; reads `prompts/system.md` for prefix |
| `examples/sample-workspace/tiny-runtime/prompts/system.md` | Default prompt: `"DEFAULT"` (or similar one-word marker) |
| `examples/sample-workspace/harness-packages/concise-prompt/0.1.0/manifest.md` | id=concise-prompt; version=0.1.0; runtime_compat=[local_path]; ## Description; ## Payload installing `prompts/system.md`; start_command=`python agent.py` |
| `examples/sample-workspace/harness-packages/concise-prompt/0.1.0/payload/system.md` | Concise prompt: `"STRICT - answer in minimal form"` |
| `examples/sample-workspace/experiments/001-faq-conciseness/program.md` | Standard program template, filled |
| `examples/sample-workspace/experiments/001-faq-conciseness/rubric.md` | 2 dimensions: correctness (0.5), conciseness (0.5) |
| `examples/sample-workspace/experiments/001-faq-conciseness/simulator.md` | Single-turn fixture; stub simulator returns None after turn 0 (uses default behavior) |
| `examples/sample-workspace/experiments/001-faq-conciseness/harnesses/V1.md` | id=V1, 基线=是, runtime_source=local-tiny; ## Patch with `start_command: python agent.py` (no file overrides — uses runtime's default system.md) |
| `examples/sample-workspace/experiments/001-faq-conciseness/harnesses/V2.md` | id=V2, 基线=否, runtime_source=local-tiny, harness_package=concise-prompt@0.1.0 (no ## Patch — manifest supplies start_command) |
| `examples/sample-workspace/experiments/001-faq-conciseness/cases/C1.md` | id=C1, ## 起始输入 = "How do I reset my password?" |
| `examples/sample-workspace/experiments/001-faq-conciseness/cases/C2.md` | id=C2, ## 起始输入 = "What is your refund policy?" |

**Total**: ~12 new files; small (each <30 lines). No new src/ code, no
new dependencies.

---

## 8. Expected command flow (sample workspace)

User commands (in the sample workspace dir):

```bash
cd examples/sample-workspace

# 1. Optional sanity — runtime + package readiness
ahl probe 001
#   expected: V1 status=ok runtime=local_path:local-tiny package=—   start_command=patch
#             V2 status=ok runtime=local_path:local-tiny package=concise-prompt@0.1.0 start_command=manifest
#   exit 0; artifact at probe-results/probe-<ts>/V*.json

# 2. Run the experiment (2 variants × 2 cases = 4 conversations)
ahl run 001
#   exit 0; results/run-<ts>.json + results/snapshots/run-<ts>/V*.json

# 3. Score (uses stub_grader; no --llm; no API keys)
ahl score 001
#   exit 0; results/score-<ts>.json with `evidence` block

# 4. Compare
ahl compare 001
#   exit 0; results/compare-<ts>.md with `## Evidence` section showing both variants strong;
#   V1 and V2 totals differ (stub_grader hash of different agent_text)
```

(`ahl init` and `ahl new` are not needed because the workspace is
pre-initted. README explains why.)

---

## 9. Expected outputs

After the 4 commands above, the workspace contains:

| Path | Content |
|---|---|
| `probe-results/probe-<ts>/V1.json` | status=ok runtime_source state, no package |
| `probe-results/probe-<ts>/V2.json` | status=ok runtime_source state + package state |
| `experiments/001-faq-conciseness/results/run-<ts>.json` | 4 records (V1×C1, V1×C2, V2×C1, V2×C2); each has snapshot_id |
| `experiments/001-faq-conciseness/results/snapshots/run-<ts>/V1.json` | snapshot with runtime_source (local_path) + harness_patch + sandbox + **harness_package: null** |
| `experiments/001-faq-conciseness/results/snapshots/run-<ts>/V2.json` | snapshot with runtime_source + **harness_package block** (manifest_hash + payload_hash + effective_harness_hash + install_order) + harness_patch=null + sandbox |
| `experiments/001-faq-conciseness/results/score-<ts>.json` | scores + top-level `evidence` block (V1 strong local_path, V2 strong local_path + package fully fingerprinted) |
| `experiments/001-faq-conciseness/results/compare-<ts>.md` | `## Evidence` section showing both variants strong; version totals showing V1≠V2; reasons mentioning `concise-prompt@0.1.0 fully fingerprinted` on V2 |

User can inspect each at any layer to understand the product.

---

## 10. README / README_CN update plan

Both files should clearly answer **9 concept questions** in order:

| # | Question | Section location |
|---|---|---|
| 1 | **What is Agent Harness Lab?** | Top-of-file one-line value prop + one-paragraph elaboration |
| 2 | **What problem does it solve?** | "Why this exists" section |
| 3 | **What is runtime?** | First conceptual section — agent's execution environment |
| 4 | **What is harness?** | Second conceptual section — the external structure shaping agent behavior (prompts / tools / memory / workflow / config) |
| 5 | **What is harness package?** | Third conceptual section — reusable, versioned, installable harness component |
| 6 | **What is probe?** | Fourth conceptual section — pre-run readiness check, read-only |
| 7 | **What is evidence?** | Fifth conceptual section — strong / medium / weak / unknown levels; how they impact keep/discard decisions |
| 8 | **What is the simplest end-to-end workflow?** | Pointer to `examples/sample-workspace/` + 4-line command recipe |
| 9 | **What is NOT implemented yet?** | Honest "Status" section — explicit list (Auto / cloud / registry / etc.) with version targets |

Length budget: README ~150 lines (versus current ~107), README_CN
1:1 sync. **Voice**: direct, accurate-first, no marketing-speak. Explicit
about MVP status of each feature.

**Existing README content to preserve**: install instructions, 4-agent
examples reference, project history (HDL → Agent Harness Lab),
related-work section. Reorganize, don't rewrite from scratch.

---

## 11. Docs navigation update plan

`docs/README.md` current-mainline list — currently includes 5 docs. After
v0.7:

- **First-time reader path**:
  `product-walkthrough.md` (the 9-step entry)
  → `product-definition.md` (concept depth)
  → `examples/sample-workspace/README.md` (try it)
- **Depth specs (read on demand)**:
  - `runtime-materialization.md` + `runtime-materialization-m1-spec.md` (v0.3.0)
  - `evidence-aware-result.md` (v0.4)
  - `harness-package-mvp.md` (v0.5)
  - `runtime-probe-mvp.md` (v0.6)
- **File formats**: `file-formats.md`
- **Roadmap**: `roadmap.md`
- **Contributing / Security**: `../CONTRIBUTING.md` / `../SECURITY.md`

Walkthrough consolidation: each MVP spec gains a top-section pointer back
to `product-walkthrough.md` saying "this spec is the depth-detail for
Step X of the 9-step walkthrough; if you haven't read the walkthrough,
start there." Stop treating specs as islands.

---

## 12. CLI UX polish candidates (opportunistic, not a sweep)

While building the sample workspace, surface friction in CLI errors:

- Error messages that point at deprecated docs (e.g. `connect.md` legacy
  pointers) — verify they point at the current `product-walkthrough.md`
  Step 3
- Errors without "next step" suggestion — add a short "try: `ahl X`" or
  "see: `docs/Y.md` §Z" hint
- Inconsistent quoting / punctuation across cmd_* functions (mix of
  Chinese 「」, 「:」, plain ASCII) — light-touch unify where touched
- `ahl init` stdout's Step 1/2/3 guidance is already good (v0.3.1 work);
  verify it doesn't drift after v0.5/v0.6

**Scope discipline**: fix what's encountered building C1; do not do a
separate "scan all 14 commands" sweep. If something is broken but not on
the sample-workspace path, log it as v0.8 follow-up.

---

## 13. Product acceptance checklist (yes/no, checker-runnable on fresh clone)

| # | Check | How to verify |
|---|---|---|
| 1 | `git clone <repo>` + `pip install -e .` succeeds on Python 3.10+ | manual or CI |
| 2 | `cd examples/sample-workspace` then `ahl probe 001` exit 0 | acceptance script |
| 3 | `ahl run 001` exit 0; produces 4 run records | acceptance script |
| 4 | `ahl score 001` exit 0; score JSON has top-level `evidence` block | acceptance script |
| 5 | `ahl compare 001` exit 0; compare md has `## Evidence` section | acceptance script |
| 6 | Snapshot for V2 has `harness_package` block with all 3 hashes | acceptance script |
| 7 | V1 vs V2 score totals differ (package made a behavior delta) | acceptance script |
| 8 | Re-running probe → run → score → compare twice yields identical score numbers (modulo timestamps) | acceptance script |
| 9 | `ahl review 001` shows "Last probe" line after probe was run | manual or extended script |
| 10 | All README concept questions (§10) have clear paragraphs | code review |
| 11 | `docs/README.md` mainline list links to every current MVP spec | code review |
| 12 | No new CLI command added (still 14) | existing redline tests |

---

## 14. Test / smoke plan

| Test type | Coverage |
|---|---|
| **Existing 462 tests** | Must continue to pass — regression gate |
| **New acceptance script** `tests/test_sample_workspace_e2e.py` | Subprocess-invoke `ahl probe → run → score → compare` against `examples/sample-workspace/`; assert items #2-#8 from §13 |
| **No new unit tests** | Sample workspace is content + 1 acceptance test; no new src code to unit-test |

Target: 462 → ~465 (+3 acceptance-script tests; one main flow + one
reproducibility check + one regression check on V1≠V2 delta).

---

## 15. Implementation plan

### 15.1 Files

**New (~12 files in `examples/sample-workspace/`; ~1 test file)**:

| Path | Est lines | Purpose |
|---|---|---|
| `examples/sample-workspace/{README, goal, runtime-sources}.md` | ~80 | User-facing entry |
| `examples/sample-workspace/tiny-runtime/{agent.py, prompts/system.md}` | ~40 | Deterministic CLI agent + default prompt |
| `examples/sample-workspace/harness-packages/concise-prompt/0.1.0/{manifest, payload/system}.md` | ~25 | Package fixture |
| `examples/sample-workspace/experiments/001-faq-conciseness/{program, rubric, simulator}.md` | ~40 | Standard experiment scaffold |
| `examples/sample-workspace/experiments/001-faq-conciseness/harnesses/{V1, V2}.md` | ~20 | Baseline + packaged variant |
| `examples/sample-workspace/experiments/001-faq-conciseness/cases/{C1, C2}.md` | ~10 | FAQ cases |
| `docs/product-flow-completion.md` | ~500 (this spec) | Already drafted in this PR |
| `tests/test_sample_workspace_e2e.py` | ~250 | Acceptance script |

**Modified**:

| Path | Est ± | Change |
|---|---|---|
| `README.md` | +50 / -10 | 9-concept rewrite (preserve install + history + related-work) |
| `README_CN.md` | +50 / -10 | Sync EN |
| `docs/README.md` | +20 / -5 | Mainline list refresh + first-time-reader path |
| `docs/product-walkthrough.md` | +15 / -0 | Reciprocal cross-link to all MVP specs |
| `docs/runtime-materialization.md` | +5 / -0 | Top-section "this is depth-detail for Step 7" pointer |
| `docs/evidence-aware-result.md` | +5 / -0 | Same pattern for Step 8 |
| `docs/harness-package-mvp.md` | +5 / -0 | Same pattern for Step 5/7 |
| `docs/runtime-probe-mvp.md` | +5 / -0 | Same pattern for Step 6.5 |
| CLI UX touches (opportunistic) | ~10 / -10 | Fix-as-found during sample workspace build |
| `CHANGELOG.md` | +15 / -0 | `[Unreleased] / Added` bullets |

### 15.2 Estimated diff

~600 new lines + ~200 lines modified across ~25 files. Smaller than v0.5
or v0.6 (no new src module).

### 15.3 Commit split

**2 commits** (matching v0.4/v0.5/v0.6 pattern):

- **C1**: `feat(sample): add complete-product-flow sample workspace + acceptance test`
  - All `examples/sample-workspace/` files
  - `tests/test_sample_workspace_e2e.py`
  - `docs/product-flow-completion.md`(spec)
- **C2**: `docs: refresh README + docs nav + walkthrough cross-links + CLI UX polish`
  - `README.md` + `README_CN.md` 9-concept rewrite
  - `docs/README.md` mainline list update
  - 4 MVP specs add walkthrough back-links
  - CLI UX touches encountered while building C1
  - `CHANGELOG.md` bullets

C1 is independently shippable (gives users a runnable example even without
docs refresh). C2 is the polish round.

### 15.4 Spec first?

**Yes**(this doc). Lock spec before C1 code.

### 15.5 Review bundle

Each commit gets `temp/v0.7.0-product-flow-c{1,2}-review/` with the
established RELEASE_REVIEW_SUMMARY.md pattern + sample artifacts.

---

## 16. Redlines (consolidated)

| Redline | Enforced by |
|---|---|
| No new CLI command | Existing redline tests; meta-check of `ahl --help` listing 14 commands |
| No new src module under `src/agent_harness_lab/` | C1/C2 file lists explicitly omit `src/` additions |
| No external dependency | `pyproject.toml` `dependencies = []` unchanged |
| No snapshot schema change | snapshot.py untouched in v0.7 |
| No evidence rule change | evidence.py untouched in v0.7 |
| No scoring/comparator change | grader.py / comparator.py untouched in v0.7 |
| No v0.5 package install change | materialize/* + harness_package.py untouched in v0.7 |
| No v0.6 probe contract change | probe.py untouched in v0.7 |
| No repo visibility flip | `gh repo edit --visibility` never invoked |
| No PyPI publish | `python -m build` / `twine` never invoked |
| No announcement / public-facing language | README + spec voice is internal product completion |
| No tag/release deletion | only adds `v0.7.0` tag in release-prep phase |

---

## 17. Open questions (lock before C1 GO)

1. **Sample workspace agent's prompt-prepend mechanism**: spec assumes
   agent reads `prompts/system.md` and prepends content to response. Is
   this realistic enough or does Kun want a more sophisticated demo
   (e.g. agent uses prompt as system instruction)? **Default: simple
   prepend** — keeps agent ~30 lines + behavior delta is obvious in
   `agent_text`.

2. **`runtime-sources.md` absolute path**: sample workspace's runtime
   source path needs to be the actual filesystem location of
   `tiny-runtime/`. Options:
   - (a) hardcode user-edits path before running
   - (b) document `cd examples/sample-workspace && ahl probe 001`
     (relative path resolution from cwd)
   - **Default: (b)** with explicit "cd into the sample-workspace dir
     first" instruction in README.

3. **CI workflow (workstream 7)**: include in v0.7 or defer to v0.8?
   **Default: defer to v0.8** — keeps v0.7 scope tight on product-flow
   completion. CI is independently valuable but not required for
   "product feels complete".

4. **README length**: target ~150 lines OK? Risk too long → fatigue, too
   short → can't cover 9 concepts. **Default: ~150 lines** with concept
   sections at ~10 lines each + worked example.

5. **English vs Chinese parity**: do README and README_CN have to be
   identical, or is README_CN a free-er translation? Current state is
   nearly 1:1. **Default: keep 1:1 for v0.7** to reduce divergence risk.

C1 编码前 Kun lock 这 5 项。

---

## 18. What this spec does NOT change (snapshot)

For absolute clarity:

- `src/agent_harness_lab/` modules: **all untouched** in v0.7
- snapshot schema / evidence rules / scoring math / comparator math /
  package install / probe contract: **all unchanged**
- CLI command list: **still 14** (init / walkthrough / connect / new /
  show / cases / rubric / simulator / harnesses / run / score / compare
  / review / probe)
- External dependencies: **still zero**
- Repo visibility: **PRIVATE** throughout v0.7
- Tags / releases: only `v0.7.0` added in release-prep phase
