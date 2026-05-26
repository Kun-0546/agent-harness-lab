# Product Reliability & Evidence Hardening · v0.8 Spec

> 这份 spec 定义 Agent Harness Lab 的 v0.8 **Product Reliability & Evidence
> Hardening** —— 在 v0.7 把"完整产品流可跑"完成的基础上,把两个最薄弱
> 的环节补厚:**evidence 链路的 user-facing 清晰度**(score/compare 出的
> "strong/medium/weak/unknown"用户能不能解读 + 自己写 evidence 文件能不能
> 验证)和**product acceptance 的回归保护**(README 命令 / 文档声明 /
> sample-workspace 实际行为 三者不再脱节)。
>
> Status: target v0.8.0,branch `v0.8.0-planning` (local-only, unpushed)。
> **spec 锁定阶段 —— 代码尚未实现**。
> Date: 2026-05-26。
> Direction (per Kun): "Product Reliability & Evidence Hardening" —
> 主要靠 docs + tests + 小幅 evidence UX polish,**不**加新核心抽象、
> **不**加大 CLI、**不**改 snapshot schema、**不**做 public launch。

---

## 1. Purpose

v0.7 Complete Product Flow MVP 把分散在 v0.3-v0.6 的 4 个 MVP 收敛成一条
可跑的产品流(sample workspace + E2E 验收测 + 9-concept README + 4 spec
back-link)。新用户能 30 分钟内拿到第一份 compare report。

但 v0.7 完成后,**两个问题暴露出来**:

1. **Evidence 链 user-facing 不清晰**。v0.4 evidence-aware result 把 evidence
   level(strong / medium / weak / unknown)写进 score/compare report,但
   *没有一份 user-facing 文档解释这四档**怎么算出来的、哪一档对应什么行动**。
   `materials/*-evidence.md`(runtime / harness / cloud)这三种文件的格式
   分散在 v0.6 probe.py 和 v0.4 evidence.py 里,**用户想手写一份 cloud
   evidence 都不知道字段长什么样**。Sample workspace 也没演示这条路径。

2. **Doc-sample drift 没有保护机制**。v0.7 review 阶段抓到一条
   `simulator.md` 把 stub_simulator 行为描述错了(声称单轮,实际 3 轮)。
   这种"docs 说 A,sample / code 实际是 B"的漂移**没有自动化测可以捕捉**——
   只能靠人在 review 时凑巧看到。v0.7 后还有同类风险:
   - README 列了 14 个 CLI 命令,谁保证 `ahl --help` 真有这 14 个?
   - README 8 节"simplest workflow"列了 4 条命令,谁保证它们今天都能 exit 0?
   - sample workspace README 列了 14 个文件,谁保证 repo 里这 14 个文件都还在?

v0.8 修这两个问题。**只动 docs + tests + 极小 evidence-reason 文案,不动
snapshot schema / 不动 evidence 推断规则 / 不动 scoring 数学**。

---

## 2. Product problem

具象 friction list:

- 用户跑完 `ahl compare` 看到 `## Evidence` 表格,某 variant level=medium、
  reason="materialized runtime but incomplete harness package fingerprint",
  **不知道这意味着什么、要做什么才能升 strong**。
- 用户想给一个 cloud-deployed agent 写 `materials/cloud-evidence.md`
  让 evidence 从 weak 升 medium,**没有 reference 格式**,只能去读
  `src/agent_harness_lab/evidence.py` 推断字段。
- 用户读到 score JSON 顶层有 `evidence` block、compare md 顶部有
  `## Evidence` section、snapshot JSON 有 `harness_package` 块、experiment
  目录下还有 `probe-results/`、`materials/*-evidence.md` —— **这五种"evidence
  相关的产物"之间什么关系,没文档解释**。新用户 mental model 散。
- 用户改完一行代码,跑了 465 个测全过,**README 上的 4 行命令演示是不是还跑得
  通,没有自动验证**。
- 用户问 "v0.7 究竟交付了什么?当前 product surface 是什么样?" 没有一份
  user-facing 的**产品 acceptance checklist** —— v0.7 spec §13 的 12 项
  checklist 是 internal review artifact,**没暴露给文档读者**。

---

## 3. Why v0.8 follows v0.7

v0.7 sample workspace 是产品流的**第一份 canonical reference**,但只是
*事实上*的 canonical —— 没有任何机制保证 README / docs / sample workspace /
代码这四者保持一致。**v0.8 把"canonical reference"从 sample workspace 这
*一个*工件扩展到一组互相校验的工件 + 测试 + user-facing guide**:

```
v0.7 工件:
  README → docs → sample workspace → CLI → snapshot/evidence/compare 产物
   ↑       ↑           ↑              ↑           ↑
   |       |           |              |           |
   人读    人读        人跑           人验        人解读
  (易漂移)(易漂移)   (有 1 个 E2E)  (无校验)   (无 user guide)

v0.8 工件:
  README → docs → sample workspace → CLI → snapshot/evidence/compare 产物
   ↑       ↑           ↑              ↑           ↑
   |       |           |              |           |
   人读 + 测:命令/概念引用一致     人跑:E2E 扩到 doc-drift / smoke
                                                  ↑
                                       新增 docs/evidence-guide.md 让人能 *解读*
                                       新增 docs/product-acceptance-checklist.md 让人能 *验收*
                                       sample 配 evidence 示例让人能 *仿写*
```

**v0.8 不是 v0.9 / v1.0 的前置**(那些需要 probe↔snapshot binding、package
inspect CLI、Auto mode 这种更大的动作);v0.8 是 v0.7 的"加固层",把
v0.7 当前已有的 product surface 变得**更可信、更易学**。

---

## 4. Non-goals

v0.8 explicitly **does not**:

- **NOT** flip repo visibility — repo stays **PRIVATE**
- **NOT** publish to PyPI
- **NOT** prepare public announcement / blog / social
- **NOT** add any new major CLI command (`ahl package inspect` / `ahl package
  validate` are deferred to v0.9 explicitly — see §15 Open Questions if a
  *micro* hint flag becomes necessary)
- **NOT** implement Auto / autonomous iteration / approval gates
- **NOT** implement registry / remote package distribution / package fetch
- **NOT** implement cloud attestation API
- **NOT** add new runtime source types (`docker_image` / `remote_api` /
  `dev_agent` — still M2+)
- **NOT** change snapshot schema (probe ↔ snapshot binding deferred to v0.9)
- **NOT** change v0.4 evidence inference rules (only re-document them and
  make reason strings clearer)
- **NOT** change scoring / comparator math
- **NOT** break v0.5 harness package contract or v0.6 probe contract
- **NOT** add external dependencies (stdlib-only philosophy continues)
- **NOT** add CODE_OF_CONDUCT.md or PR/Issue templates
- **NOT** delete v0.7 sample workspace, README, or E2E tests

---

## 5. Acceptance hardening scope

### 5.1 Candidate analysis (6 candidates from Kun's brief)

| # | Candidate | v0.8 verdict | Rationale |
|---|---|---|---|
| 1 | Explicit product acceptance checklist (command **or** doc) | **GO as doc** | Kun's bias: prefer docs over new surface. v0.7 spec §13 already has the checklist in internal form; promote to `docs/product-acceptance-checklist.md` so users can self-validate after their own changes. **No** `ahl acceptance` CLI — that's a v0.9+ question. |
| 2 | Strengthen sample-workspace E2E to catch docs/sample drift | **GO** | The v0.7 simulator.md mismatch is the canonical example of what we want to prevent. Add 1 test that compares simulator.md's behavioral claim to actual stub_simulator output count. |
| 3 | Regression assertions for README command flow | **GO** | Parse the README quick-start / sample-workspace recipe; assert every command listed runs against sample workspace and exits 0. Catches "README says `ahl X` but CLI no longer has X" *and* "README says `cd examples/sample-workspace && ahl probe 001` but it errors". |
| 4 | Generated-artifact cleanliness checks | **EXTEND existing** | v0.7 already has `TestRepoSampleWorkspaceClean::test_no_generated_artifacts_in_committed_sample`. Extend to cover any new evidence sample paths added under §6, *not* a from-scratch new test module. |
| 5 | Deterministic output comparison helpers | **DEFER to v0.9** | The v0.7 `TestSampleWorkspaceDeterminism` already covers the sample. A reusable helper is only valuable when there are multiple determinism-sensitive tests. v0.8's scope doesn't add new ones. |
| 6 | Product-flow smoke script under `scripts/` or docs only | **GO as docs only** | A `docs/product-flow-smoke.md` (or section within `docs/product-acceptance-checklist.md`) that documents the 4-command recipe with expected outputs. **No** `scripts/` directory — Kun's bias: no new product surface. The README and sample workspace README already have the recipe; this doc consolidates "what to expect at each step" for verification purposes. |

### 5.2 v0.8 acceptance hardening deliverables

Mapping the GO verdicts to concrete files:

- **`docs/product-acceptance-checklist.md`** (new, ~120 lines) — user-facing
  checklist for verifying their AHL install is healthy, covering: CLI commands
  available, sample workspace files present, sample-workspace flow exit codes,
  expected artifact paths, sample-workspace snapshot fingerprint fields,
  expected output formats. Combines candidates #1 + #6.
- **`tests/test_doc_consistency.py`** (new, ~150 lines) — adds 3-5 new test
  cases:
  - `test_cli_help_lists_exactly_14_commands` — parses `ahl --help` output,
    asserts the 14-command list matches what README / docs/README / spec lock in.
  - `test_readme_quickstart_commands_match_cli` — extracts commands from
    `README.md`'s quickstart / sample-workspace sections, asserts each
    `ahl <subcommand>` is a real subcommand.
  - `test_sample_workspace_file_count_matches_readme` — counts files under
    `examples/sample-workspace/`, asserts the count matches what
    `examples/sample-workspace/README.md` documents.
  - `test_simulator_md_claim_matches_stub_behavior` — runs stub_simulator on
    a fixture transcript, asserts the turn count claimed in sample-workspace
    `simulator.md` matches actual `_STUB_FOLLOWUPS` length.
  - `test_docs_no_dead_internal_links` — basic markdown link scan across
    `docs/**/*.md` + `README.md` + `README_CN.md`, asserts every relative
    `[text](path)` resolves to a real file. Catches deletion / rename drift.
- **`tests/test_readme_command_flow.py`** (new, ~120 lines) — parses
  `README.md` §8 "Simplest end-to-end workflow" code block and runs each line
  via subprocess against a tmp-copied sample workspace; asserts all exit 0.
  Bridges README claim to actual CLI behavior; if Kun changes the recipe and
  forgets to test it, this trips.
- **Existing `tests/test_sample_workspace_e2e.py`** — small extension to its
  cleanliness check to also assert no `materials/*-evidence.md` *example*
  files accidentally make it into the committed sample (if §6.2 evidence
  examples live under sample-workspace; otherwise unchanged).

**Total acceptance-hardening adds**: ~1 doc + ~2 test files + 1 extension.
Estimated +~10-15 tests → 465 → ~475-480.

### 5.3 What this hardening guarantees

After v0.8 ships:

- A future PR that breaks the README quickstart fails CI / local test (today
  it would silently merge).
- A future PR that adds a CLI command without updating README fails the
  14-command-list test.
- A future PR that renames a doc path without fixing inbound links fails the
  no-dead-links test.
- A future PR that changes `stub_simulator` behavior without updating
  `simulator.md` fails the claim-matches-behavior test.
- A new user can run `docs/product-acceptance-checklist.md` against their
  install and verify it independently of the test suite.

---

## 6. Evidence hardening scope

### 6.1 Candidate analysis (6 candidates from Kun's brief)

| # | Candidate | v0.8 verdict | Rationale |
|---|---|---|---|
| 1 | Improve `materials/*-evidence.md` file format guidance | **GO** | Today these formats live in `src/agent_harness_lab/evidence.py` + `probe.py` parsers + brief mentions in `docs/file-formats.md`. Promote to a dedicated section in `docs/evidence-guide.md`. |
| 2 | Add examples of `runtime-evidence.md` / `harness-evidence.md` / `cloud-evidence.md` | **GO** | Three example files under `examples/evidence-examples/` (new top-level dir), each with realistic field values + comments. Importantly **does not** go inside sample-workspace (would trip cleanliness test). |
| 3 | Add validation rules for evidence files (minimal) | **DEFER to v0.9** | Validation = code = risk. v0.4 evidence inference already gracefully handles malformed `materials/*-evidence.md` (downgrades level, logs reason). Adding a strict validator before docs catch up to current behavior creates rework. |
| 4 | Make score/compare evidence reason strings clearer | **GO (micro)** | Current reasons like "materialized runtime but incomplete harness package fingerprint" are accurate but terse. Append a "see: `docs/evidence-guide.md#<anchor>`" hint where the anchor exists. **Single-line touch** to evidence.py if necessary, otherwise pure docs. **Not** a rule change. |
| 5 | Docs explaining strong / medium / weak / unknown | **GO (centerpiece)** | This is the heart of `docs/evidence-guide.md`. One section per level: definition + when AHL infers it + what user can do to upgrade + worked example from sample workspace + worked counter-example. |
| 6 | Clarify the 5 evidence-related artifact types | **GO (framing)** | First section of `docs/evidence-guide.md`: side-by-side comparison of snapshot evidence / supplied materials evidence / probe artifact / score evidence / compare evidence (file path + producer command + consumer / use case). Resolves the mental-model collision flagged in §2. |

### 6.2 v0.8 evidence hardening deliverables

- **`docs/evidence-guide.md`** (new, ~250 lines) — the centerpiece. Sections:
  1. **The 5 evidence-related artifacts** (table mapping path → producer →
     consumer → purpose); explicitly clarifies that snapshot, score, and
     compare each carry a *different* evidence concept and they layer.
  2. **The 4 evidence levels** (strong / medium / weak / unknown): for each,
     definition, inference rule (cite `evidence.py`), how to upgrade, worked
     example from sample workspace (V1=strong / V2=strong), worked
     counter-example.
  3. **`materials/*-evidence.md` file formats** (runtime / harness / cloud) —
     full field reference, when to author each, link to examples.
  4. **`ahl probe --write-evidence`** as the auto-write path for legacy_connect
     variants — and why it doesn't apply to materialized variants.
  5. **Decision aid**: "I see X in compare report, what do I do?" — keep /
     discard / next mapping conditional on evidence level + dimension delta
     direction.

- **`examples/evidence-examples/`** (new top-level dir, 3 files ~30-50 lines
  each):
  - `runtime-evidence.md` — realistic legacy_connect runtime attestation;
    references the auto-write format from `ahl probe --write-evidence` but
    annotated for hand-authoring.
  - `harness-evidence.md` — for installed harness state on an already-running
    agent (covers the v0.3 §3 2×2 case ②).
  - `cloud-evidence.md` — cloud-deployed agent attestation; demonstrates
    fields needed to upgrade `weak → medium`.

- **Optional micro CLI polish** (touches `evidence.py` *only* if needed):
  evidence reason strings get a `(see: docs/evidence-guide.md#level-medium)`
  suffix where it adds clarity. Reason rules unchanged; only the string
  format changes. If the polish proves invasive (e.g. forces re-running
  ~30 evidence tests), **defer the polish, ship the doc only**.

- **Wire up cross-references** in existing docs:
  - `README.md` §7 (What is evidence?) — append link to evidence-guide.
  - `README_CN.md` §7 — same.
  - `docs/evidence-aware-result.md` — append link to user-facing guide.
  - `docs/file-formats.md` — replace brief materials/*-evidence.md mention
    with link to evidence-guide §3.

### 6.3 What this hardening guarantees

After v0.8 ships:

- A user reading a compare report with `level=medium` can click through to a
  page that says **exactly** what produced that label and what they can do
  about it.
- A user wanting to write a cloud-evidence.md can copy from
  `examples/evidence-examples/cloud-evidence.md`, modify, and have it work.
- A new user reads `docs/evidence-guide.md` §1 and stops confusing snapshot
  evidence with score evidence with compare evidence.
- v0.4 evidence inference rules are documented **outside** the v0.4 spec
  (which is implementation-facing), giving v0.9+ a stable target to extend.

---

## 7. What should stay unchanged

For absolute clarity, v0.8 does **not** modify:

| Surface | Stay-unchanged guarantee |
|---|---|
| `src/agent_harness_lab/snapshot.py` | Untouched. Snapshot schema is the same as v0.7. |
| `src/agent_harness_lab/grader.py` | Untouched. Scoring math unchanged. |
| `src/agent_harness_lab/comparator.py` | Untouched. Comparator math unchanged. |
| `src/agent_harness_lab/harness_package.py` | Untouched. Package install / hash semantics unchanged. |
| `src/agent_harness_lab/probe.py` | Untouched. Probe contract unchanged. |
| `src/agent_harness_lab/runtime_source.py` | Untouched. Still `local_path` + `git_repo` + `legacy_connect`. |
| `src/agent_harness_lab/materialize/*` | Untouched. Three adapters unchanged. |
| `src/agent_harness_lab/evidence.py` | **Possibly micro touch** (§6.2 reason-string hint suffix). Inference rules unchanged. If touched, ≤10 lines diff. |
| `src/agent_harness_lab/cli.py` | Untouched. Still 14 commands. |
| `pyproject.toml` | Version bump 0.7.0 → 0.8.0 in release-prep commit only. `dependencies = []`. `[project.scripts]` unchanged. |
| `examples/sample-workspace/` | Untouched. v0.7 sample remains canonical. |
| Repo visibility | Stays PRIVATE. |

---

## 8. User-facing behavior

What changes for a user upgrading from v0.7 to v0.8:

- New doc at `docs/evidence-guide.md` linked from README §7 — they can now
  click through from "What is evidence?" and read the full inference rules.
- New doc at `docs/product-acceptance-checklist.md` linked from `docs/README.md`
  — they can self-verify their install after `pip install -e .`.
- New examples under `examples/evidence-examples/` — they can copy a template
  to author their own `materials/*-evidence.md`.
- If micro CLI polish ships: compare report's `## Evidence` reason column may
  include `(see: docs/evidence-guide.md#...)` suffixes. Same level inference,
  more discoverable.
- `ahl --help` and all 14 commands behave **identically** to v0.7.
- Existing experiments / snapshots / packages from v0.7 work without changes.

---

## 9. Files / artifacts affected

### New

| Path | Est lines | Purpose |
|---|---|---|
| `docs/evidence-guide.md` | ~250 | Centerpiece evidence user guide |
| `docs/product-acceptance-checklist.md` | ~120 | User-facing acceptance checklist |
| `docs/product-reliability-evidence-hardening.md` | ~500 (this spec) | v0.8 spec (this file) |
| `examples/evidence-examples/runtime-evidence.md` | ~40 | Sample legacy-connect runtime attestation |
| `examples/evidence-examples/harness-evidence.md` | ~40 | Sample harness-installed-state attestation |
| `examples/evidence-examples/cloud-evidence.md` | ~50 | Sample cloud-deployed agent attestation |
| `examples/evidence-examples/README.md` | ~50 | Index + when to use each example |
| `tests/test_doc_consistency.py` | ~150 | CLI ↔ docs ↔ sample drift detectors (5 tests) |
| `tests/test_readme_command_flow.py` | ~120 | Asserts README quickstart commands actually run |

### Modified

| Path | Est ± | Change |
|---|---|---|
| `README.md` | +5 / -0 | §7 evidence concept paragraph appends link to `docs/evidence-guide.md` |
| `README_CN.md` | +5 / -0 | Same link |
| `docs/README.md` | +10 / -0 | Mainline list adds `evidence-guide.md` + `product-acceptance-checklist.md`; first-time-reader path mentions evidence-guide after sample workspace |
| `docs/evidence-aware-result.md` | +5 / -0 | Top section appends "user-facing companion: `docs/evidence-guide.md`" |
| `docs/file-formats.md` | +10 / -5 | Replaces brief `materials/*-evidence.md` mention with link to evidence-guide §3 |
| `src/agent_harness_lab/evidence.py` | +0~10 / -0 | Optional micro polish: append doc-anchor hint to reason strings. Skip if disruptive. |
| `tests/test_sample_workspace_e2e.py` | +5 / -0 | Cleanliness test extends to verify `examples/evidence-examples/` doesn't accidentally land inside `examples/sample-workspace/` |
| `CHANGELOG.md` | +20 / -0 | `[Unreleased] / Added + Changed` bullets for v0.8 |
| `docs/roadmap.md` | +10 / -5 | Mark v0.8 [shipped], update v0.9 entry to absorb deferred items (package inspect CLI + probe↔snapshot binding) |

### Estimated total diff

~500 new spec lines + ~400 new docs lines + ~270 new test lines + ~120 new
example lines + ~80 lines modified across 8 existing files = **~1370 lines
added / ~10 deleted**. Comparable to v0.7 in size; smaller in risk
(no new src module, near-zero src diff).

---

## 10. CLI impact, if any

**None**, with one possible micro exception:

- **No new CLI command added.** 14 commands stay.
- **No CLI flag changes** to existing commands.
- **No CLI argparse re-organization.**
- **Possible**: `ahl compare` output's `## Evidence` table `reasons` column may
  include `(see: docs/evidence-guide.md#level-medium)` suffix in v0.8. This
  is a string format change to a human-readable column only, **not** a
  protocol change. Existing scripts parsing the JSON `evidence` block in
  `score-*.json` are unaffected (JSON fields unchanged).

If even this micro polish proves invasive, ship v0.8 as **pure docs + tests**
with no src touch at all.

---

## 11. Test plan

| Test category | Coverage |
|---|---|
| **Existing 465 tests** | Must continue to pass — regression gate. |
| **`tests/test_doc_consistency.py`** | 5 new tests covering CLI command list / README command snippets / sample workspace file count / simulator.md behavioral claim / no-dead-internal-links. |
| **`tests/test_readme_command_flow.py`** | 3-5 new tests running the README §8 quickstart commands against a tmp sample-workspace copy; assert each exits 0. |
| **`tests/test_sample_workspace_e2e.py`** | Existing 3 tests unchanged. Plus 1 micro-extension to cleanliness test if §6.2 evidence examples need it. |
| **No new unit tests under `tests/test_evidence.py`** | Evidence inference rules unchanged → no new unit tests on `evidence.py`. If reason-string polish lands, update existing reason-assertion tests in place. |
| **`pytest -W error::ResourceWarning` strict mode** | Must pass with same 465 → ~478 count. |

**Target**: 465 → ~475-480. Within ±15 of v0.7. No drop in coverage.

---

## 12. Acceptance criteria

v0.8 is "done" when **all** of the following are true on a fresh clone:

| # | Check | How to verify |
|---|---|---|
| 1 | `pip install -e .` succeeds | manual |
| 2 | `pytest tests` → 475-480 passed (no regression) | local |
| 3 | `pytest tests -W error::ResourceWarning` → same count | local |
| 4 | `docs/evidence-guide.md` exists with 5 sections covering 5-artifact table + 4 evidence levels + materials file formats + probe write-evidence + decision aid | code review |
| 5 | `docs/product-acceptance-checklist.md` exists; a new user can self-run the listed checks | manual |
| 6 | README §7 + README_CN §7 link to `docs/evidence-guide.md` | grep |
| 7 | `examples/evidence-examples/` has 3 files + README + each is a valid markdown sample format | code review |
| 8 | `tests/test_doc_consistency.py` covers ≥5 drift detectors and all pass | local |
| 9 | `tests/test_readme_command_flow.py` parses README, runs at least the §8 quickstart, asserts exit 0 | local |
| 10 | Sample workspace E2E (v0.7's 3 tests) still passes unchanged | local |
| 11 | `ahl --help` still shows the same 14 commands; v0.7 redline holds | grep / test |
| 12 | snapshot.py / grader.py / comparator.py / harness_package.py / probe.py / materialize/ untouched | git diff |
| 13 | Repo still PRIVATE; no tag created during dev; no GitHub release | gh CLI |
| 14 | v0.7.0 release / tag / branches untouched | gh CLI |
| 15 | v0.8.0-planning branch still local-only until explicit user push | git branch -a |

---

## 13. Implementation plan

### 13.1 Spec lock-in (current step)

This document is the v0.8 spec. Lock it in Kun review **before** any
implementation. Implementation only starts after Kun says GO.

### 13.2 Commit split

**2 commits** (matching v0.4 / v0.5 / v0.6 / v0.7 pattern):

- **C1**: `feat(evidence-guide): add user-facing evidence documentation and examples`
  - `docs/evidence-guide.md`
  - `examples/evidence-examples/{runtime,harness,cloud}-evidence.md` + `README.md`
  - `README.md` + `README_CN.md` §7 link
  - `docs/README.md` mainline list refresh
  - `docs/evidence-aware-result.md` companion link
  - `docs/file-formats.md` materials section refresh
  - Optional `src/agent_harness_lab/evidence.py` micro polish
- **C2**: `test(reliability): add doc consistency and README command flow tests + product acceptance checklist`
  - `docs/product-acceptance-checklist.md`
  - `tests/test_doc_consistency.py`
  - `tests/test_readme_command_flow.py`
  - `tests/test_sample_workspace_e2e.py` micro extension (if needed)
  - `CHANGELOG.md` `[Unreleased]` bullets
  - `docs/roadmap.md` update

C1 is independently shippable (gives users the evidence guide + examples
even without test additions). C2 adds the regression protection.

### 13.3 Spec first?

**Yes**. This doc is locked before C1 code.

### 13.4 Review bundle

Each commit gets `temp/v0.8.0-{c1,c2}-review/` with the established
RELEASE_REVIEW_SUMMARY.md pattern + sample artifacts (evidence guide
preview, acceptance checklist preview, test outputs, redline checklist).

### 13.5 Release-prep (after both commits merged)

Following v0.7's pattern:

- `pyproject.toml` 0.7.0 → 0.8.0
- `CHANGELOG.md` `[Unreleased]` → `[0.8.0] - <date>`
- `docs/roadmap.md` v0.8 [exploring] → [shipped]
- Single release-prep commit `chore(release): prepare v0.8.0 metadata`
- Annotated tag `v0.8.0` after main merge
- GitHub Release `v0.8.0 — Product Reliability & Evidence Hardening`
  (PRIVATE repo, internal release)

Total cycle estimated: ~1.5-2 weeks calendar time (smaller than v0.7).

---

## 14. Redlines

| Redline | Enforced by |
|---|---|
| Repo stays PRIVATE | `gh repo edit --visibility public` never invoked |
| No PyPI publish | `python -m build` / `twine` never invoked |
| No public announcement / blog / social | No external service touched |
| No new CLI command | Existing test `test_cli_help_lists_exactly_14_commands` (new in C2) enforces; `pyproject.toml` `[project.scripts]` unchanged |
| No new src module | C1/C2 file lists explicitly omit `src/agent_harness_lab/<new>.py` |
| No external dependency | `pyproject.toml` `dependencies = []` unchanged |
| No snapshot schema change | `src/agent_harness_lab/snapshot.py` untouched |
| No v0.4 evidence rule change | `src/agent_harness_lab/evidence.py` inference functions untouched (only optional reason-string format polish) |
| No scoring / comparator change | `grader.py` / `comparator.py` untouched |
| No package install change | `harness_package.py` / `materialize/*` untouched |
| No probe contract change | `probe.py` untouched |
| No runtime source type added | Still `local_path` + `git_repo` + `legacy_connect` |
| No cloud attestation API | Only docs + sample evidence file; no programmatic attestation channel |
| No registry / remote distribution | `examples/evidence-examples/` is workspace-local, no fetch code |
| No force push to main | Standard push only |
| No tag / branch deletion | Including the v0.7.0-planning and v0.8.0-planning branches |
| No deletion of v0.7 sample workspace, README, or tests | C1/C2 file lists explicitly modify only stated files |
| No public-launch creep | No `docs/launch-*.md`, no PR/Issue templates, no CODE_OF_CONDUCT |

---

## 15. Open questions — locked (Kun, 2026-05-26)

All 7 questions were locked by Kun on 2026-05-26 before C1 started.

1. **`examples/evidence-examples/` location** — **LOCKED: new top-level
   `examples/evidence-examples/` dir.** Keeps sample-workspace cleanliness
   invariant intact; no special-case test logic; sample workspace stays
   single-purpose (canonical product-flow demo, not evidence demo).

2. **`evidence.py` micro polish** — **LOCKED: default DEFER.** v0.8 keeps
   *zero* src behavior change as the baseline. The reason-string hint
   suffix is allowed only if **all** of the following hold:
   (a) we find an obvious text bug or typo while writing the guide that
       the polish naturally fixes;
   (b) the diff is ≤10 LOC under `src/agent_harness_lab/evidence.py`;
   (c) it does not change any evidence inference rule (level mapping,
       reason production logic, JSON field semantics).
   If any of (a)–(c) fail, evidence.py stays untouched; the guide carries
   the explanatory burden alone.

3. **`tests/test_readme_command_flow.py` scope** — **LOCKED: README §8
   "Simplest end-to-end workflow" + `examples/sample-workspace/README.md`
   5-step recipe only.** Do *not* parse the entire README — avoids the
   test going brittle on prose / install / history sections that aren't
   command flows.

4. **`docs/product-acceptance-checklist.md` voice** — **LOCKED: user-facing
   rewrite from scratch.** Do not copy v0.7 spec §13's internal-review
   language verbatim. Target audience: a new user verifying their install
   works, not a maintainer auditing a release.

5. **`docs/roadmap.md` v0.9 entry** — **LOCKED: rewrite as named candidates,
   keep `[exploring]`.** List `ahl package inspect / validate` and
   probe↔snapshot binding as candidates v0.8 deferred, but do **not**
   commit v0.9 to shipping either. v0.9 scope decision is a separate
   future session.

6. **Doc-drift detector scope** — **LOCKED: skip `docs/archive/` and
   deprecated/historical docs.** Only check current docs surface
   (banner-tagged historical docs are out of scope). Concretely the
   detector ignores: `docs/archive/**`, `docs/handoffs/**`, and any
   `docs/*.md` whose first 30 lines contain a `> 已被...取代` or
   `> historical / deprecated` banner.

7. **v0.8 release notes voice** — **LOCKED: continue internal/private
   release voice.** Repo is PRIVATE; release notes describe the change
   for the maintainer-audience (Kun + future Kun), not for a public
   launch announcement. No "we are excited to announce" phrasing.

All open questions resolved. **Spec is locked. Ready for C1 implementation
on Kun's GO.**

---

## 16. Summary

v0.8 is a **two-track hardening release** with one consistent bias:
*docs and tests, not code*.

- **Track 1 — Acceptance hardening**: catch doc-sample-CLI drift via
  ~5 regression tests, plus a user-facing acceptance checklist doc.
- **Track 2 — Evidence hardening**: write the user-facing
  `docs/evidence-guide.md` that v0.4 evidence-aware-result deserved,
  give users 3 reference evidence-file examples, and (optionally) make
  compare report reason strings point at the guide.

**~1370 lines added, ~10 deleted, ~13 tests added (465 → ~478), zero
contract changes, zero new src modules, zero new CLI commands, repo
stays PRIVATE.**

If C1 lands clean and C2 stays small, v0.9 has a clean runway to take
on the deferred bigger swings (`ahl package inspect` CLI + probe↔snapshot
binding + Co-pilot ergonomics).
