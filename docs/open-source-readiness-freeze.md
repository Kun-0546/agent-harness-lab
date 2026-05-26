# Open-Source Readiness Freeze · v0.10 Spec

> 这份 spec 定义 Agent Harness Lab 的 v0.10 **Open-Source Readiness
> Freeze / Release Candidate / Final Acceptance** —— v0.3.0 →
> v0.9.0 累计 9 个 cycle 之后,先停下做一次系统性 OSS-ready 审计 +
> 出 release candidate + 立 final acceptance 标尺,而**不是**继续做
> 功能 cycle,**不是** Auto mode cycle,**不是**真正翻 visibility
> 把 repo 公开。**docs + audits + tests + 极小幅 wording polish,
> zero src behavior change, no new CLI command, no contract change,
> NO public visibility flip。**
>
> Status: target v0.10.0,branch `v0.10.0-planning`
> (local-only, unpushed)。**spec lock-in only —— 代码尚未实现**。
> Date: 2026-05-26 (immediately after v0.9.0 ship)。
> Direction (per Kun): "Open-Source Readiness Freeze /
> Release Candidate / Final Acceptance" —— **不是** Auto mode、
> **不是** public launch、**不是** PyPI publish、**不是** registry、
> **不是** package inspect/validate、**不是** probe-snapshot binding、
> **不是** 新 CLI feature cycle。Auto 推到 **v1.x / post-open-source**。

---

## 1. Purpose

v0.3.0 到 v0.9.0,**9 个 release cycle 已经把 AHL 的产品 surface 立
稳**:14 CLI commands、stdlib-only Python 3.10+ package、canonical
runnable sample workspace、evidence reference templates、co-pilot
setup productization、479 → 512 tests passing。但**每一档都是
feature cycle**,没有一档是"停下来,以公开发布候选(RC)的标准
**整体**审计一次"。

v0.10 是这一档:**冻结产品 surface,做一次端到端 OSS-readiness
audit + 建立可重复的 GO/NO-GO 决策标尺**,让 *post-v0.10* 的
"visibility flip + PyPI + 公开宣布"决策有依据。

**v0.10 本身不翻 visibility**。v0.10 完成后会留下:

- 11 份 audit reports(README / README_CN / docs nav / walkthrough /
  install / LICENSE+CONTRIBUTING+SECURITY / .gitignore+artifacts /
  pyproject metadata / CHANGELOG / sample-workspace smoke / private-
  info scan + public-facing wording cleanup)
- 1 份新 doc `docs/public-launch-checklist.md` —— *post-v0.10*
  visibility flip 的 GO/NO-GO 清单
- 1 份新 test module `tests/test_release_candidate.py` —— RC-level
  invariants
- README / docs / 个别 src wording 的小幅调整(每条都源自具体 audit
  finding)

post-v0.10 才是一档**独立** "visibility flip + PyPI + announcement"
cycle —— 走自己的 spec / 自己的 GO 决策。

---

## 2. Why v0.10 follows v0.9

v0.9 把"co-pilot setup mode 用得起来"这件事最后一块短板补完。9 个
cycle 走完,product surface 自然进入"够了,该 audit 了"的状态:

- v0.3 / v0.5 / v0.6 把核心机制(runtime materialization / harness
  package / probe)立起来
- v0.4 / v0.8 把 evidence 闭环 + 用户解读做厚
- v0.7 把 sample-workspace 拉成端到端 runnable canonical reference
- v0.9 把 co-pilot setup mode 从脚手架升成 actionable workflow

**v0.10 该做的是停下来**:
1. 把每一档累计的产物以 "公开读者看会怎么想" 的标准过一遍
2. 留下一份后续 visibility flip 的 GO/NO-GO 决策清单
3. 确保 release history、license、安全披露、metadata、install 流程
   都不留尾巴
4. 留一份 RC-level test module 让未来 PR 不会默默打破 OSS-readiness

**为什么不能再 defer 一档功能**:多做一档功能 = 多一档没 audit 的
surface,visibility flip 的决策就更难做,而且 Auto / package
inspect / probe-snapshot binding 这些 *后续候选* 都对 contract 有
非平凡影响,在没有 RC freeze 的状态下做这些会增加之后回滚成本。

---

## 3. What "open-source readiness" means

"OSS-ready" **不等于** "已经公开发布"。**等于**:
**如果**未来某天 visibility flip 被 GO,**当下的 repo 状态能直接撑
住公开**,不需要紧急修补 / 删 commit / 改 README。

具体可验证标志(每条会展开为 audit 子项 §7-§14):

1. **第一印象**:任何打开 GitHub repo 页面的人,30 秒内能搞懂
   - AHL 是什么(README 第 1 段)
   - 当前实现了什么、没实现什么(README §9 honest status)
   - 怎么试一下(README §8 simplest workflow + sample-workspace
     README)
2. **安装可重复**:`git clone && pip install -e .` 在干净环境跑得通
3. **文档闭环**:首次接触路径(walkthrough → copilot-setup →
   sample-workspace recipe)的每一步都能往下走,不撞死链 / 不撞
   "未实现" 红墙
4. **承诺与现状一致**:README + docs 不声称 AHL "已 Auto mode" /
   "已 cloud attestation" / "已 registry" 这些尚未实现的能力;
   roadmap [exploring] / [shipped] 跟代码 + tag 状态精确对齐
5. **法律 + 安全**:LICENSE 当前(MIT)、CONTRIBUTING 描述当前 PR 流
   程、SECURITY 给当前联系方式、不含未脱敏的私密信息
6. **包元数据**:`pyproject.toml` 项目名 / 描述 / requires-python /
   作者 / project URLs 对公开 reader 不别扭(即使我们不发 PyPI)
7. **Release history 自洽**:CHANGELOG dates / version numbers /
   theme statements 跟 git tags + GitHub Releases 完全一致
8. **测试覆盖**:512 tests + RC test module 双 mode passing,
   包括 doc-consistency drift detectors

---

## 4. What v0.10 will freeze

v0.10 freeze **不动 contract**,只 freeze **公开面**:

- **CLI 命令名 + 参数 surface**:14 个命令(`init / walkthrough /
  connect / new / show / cases / rubric / simulator / harnesses /
  run / score / compare / review / probe`)+ 它们的 `--flag`。任
  何 audit 发现的 ambiguous flag 在 v0.10 期间**不重命名**(改 flag
  名是 contract change),只在 audit findings 里留 v1.0 / v1.x 待办
- **文件格式锚点**:snapshot JSON / evidence JSON / compare md /
  score JSON / probe JSON / harness package manifest / brief 12
  sections / materials 8 sections —— 每份都已经有 drift tests 守住
- **Reference workspace**:`examples/sample-workspace/`(runnable
  end-state)+ `examples/copilot-setup-example/`(setup-state)+
  `examples/evidence-examples/`(evidence templates)—— 三份都进
  RC 测试守住
- **Roadmap 表述**:v0.X 是 [shipped] / v0.10 是 [exploring] /
  Auto + 一组 named candidates 是 v1.x / 未来 future
- **README EN/CN 1:1 parity**:section anchor 级别对齐

v0.10 **不 freeze** 任何 src 内部 API 或文件 layout —— 那是 v1.0
的工作。

---

## 5. Public launch is separate from v0.10

**Hard rule**:public launch(visibility flip + PyPI publish +
announcement)是 *post-v0.10* 独立 cycle,**不在 v0.10 范围内**:

| 行动 | 在 v0.10? | 由谁触发? |
|---|---|---|
| Audit + 发现问题 + 出 finding 报告 | ✅ | v0.10 工作 |
| 据 finding 改 README / docs / wording | ✅ | v0.10 工作 |
| 写 `docs/public-launch-checklist.md`(后续清单) | ✅ | v0.10 工作 |
| 跑 RC tests / sample-workspace smoke | ✅ | v0.10 工作 |
| 标 v0.10 tag + GitHub Release | ✅ | v0.10 release-prep |
| **`gh repo edit --visibility public`** | ❌ | Post-v0.10 独立 GO |
| **`twine upload` / PyPI publish** | ❌ | Post-v0.10 独立 GO |
| **Blog / 社媒 / announcement** | ❌ | Post-v0.10 独立 GO |
| **添加 `.github/` CI / 模板** | ❌ | Post-v0.10(visibility flip cycle) |

`docs/public-launch-checklist.md`(v0.10 新增)是**未来**那一次 GO
决策的清单,**不是** v0.10 工作内容。把 checklist 写好但不去做。

---

## 6. Non-goals (redlines, consolidated)

v0.10 explicitly **does not**:

- **NOT** flip repo visibility — repo stays **PRIVATE**.
- **NOT** publish to PyPI / Test PyPI / anywhere.
- **NOT** prepare public announcement / blog post / social.
- **NOT** add any new CLI command (the 14 already shipped are the
  cap).
- **NOT** implement Auto mode / autonomous iteration / approval
  gates / calibration sub-system.
- **NOT** invoke coding agents automatically.
- **NOT** integrate MCP / Claude Desktop / Cursor Composer / etc.
- **NOT** add a registry / package distribution / `ahl package
  publish` / `ahl package inspect` / `ahl package validate`.
- **NOT** add cloud attestation API.
- **NOT** add probe ↔ snapshot binding.
- **NOT** add new runtime source types (no docker_image, no
  remote_api, no dev_agent).
- **NOT** change runtime materialization contract.
- **NOT** change harness package install contract.
- **NOT** change runtime probe contract.
- **NOT** change v0.4 evidence inference rules.
- **NOT** change snapshot schema.
- **NOT** change scoring / comparator math.
- **NOT** change `ahl run` / `ahl score` / `ahl compare` behavior.
- **NOT** rename any CLI command or flag.
- **NOT** delete release history (tags / GitHub Releases / CHANGELOG
  sections).
- **NOT** delete audit-trail planning branches
  (`v0.7.0-planning` / `v0.8.0-planning` / `v0.9.0-planning`).
- **NOT** delete `examples/sample-workspace/` /
  `examples/copilot-setup-example/` / `examples/evidence-examples/`.
- **NOT** delete historical docs (`agent-authoring-guide.md` /
  `product-modes.md` / `v2-minimal-spec.md` / `design-v0.3.md` /
  `design-v0.4.1.md` — banners stay).
- **NOT** add `.github/` workflows / issue templates / PR template
  / CODEOWNERS / ISSUE_TEMPLATE / FUNDING (these belong to the
  post-v0.10 visibility-flip cycle).
- **NOT** mark "public launch" as completed anywhere.
- **NOT** make any visibility-flip-implying claim ("ready for
  public", "open source soon") in README / docs.

---

## 7. Repository audit

**Goal**: end-to-end repo file inventory + spot any artifacts that
should not survive a hypothetical future visibility flip.

**Inputs**:
- `git ls-files` snapshot
- `find . -size +1M` (large file scan)
- `.gitignore` cross-check
- Per-directory README presence audit (`src/` / `tests/` / `docs/`
  / `examples/`)

**Findings format**: `temp/v0.10.0-audit-bundle/01-repo-audit.md`:
- File-count summary by top-level directory
- Any files > 1MB (should be 0 for stdlib-only Python)
- Any files outside `.gitignore` coverage that look generated
- Any directories without a README / explainer where one would help
  a public reader

**Expected outcome**: list of `keep / remove / add README` decisions
for Kun to lock in. No file moves / deletes in v0.10 unless Kun
explicitly OKs.

---

## 8. Documentation audit

**Goal**: read every doc in `docs/` end-to-end as a public reader
would. Verify consistency, link health, and absence of stale
references.

**Inputs**:
- All current-surface docs (everything in `docs/` not
  banner-tagged HISTORICAL)
- All banner-tagged historical docs (verify banners still correct)
- All cross-doc links resolve

**Findings format**: `temp/v0.10.0-audit-bundle/02-docs-audit.md`:
- Per-doc summary (purpose / public-readability score 1-5 /
  blockers / nice-to-haves)
- Cross-doc link sanity (build on top of existing
  `tests/test_doc_consistency.py` mainline-link detector)
- Historical-banner spot-check (banners still describe the actual
  conflict + still point to current path)
- Any "TODO" / "XXX" / "FIXME" comments in current-surface docs
  (none allowed in RC)
- Any references to internal-only tools / paths / Kun's machine

**Expected outcome**: per-doc actionable edit list. Edits land in
the same cycle (in `docs/` directly), not deferred. Each edit small
enough to fit the freeze posture.

---

## 9. README / README_CN audit

**Goal**: README (EN) and README_CN must read clean for a first-
time public visitor. EN/CN parity at the section-anchor level.

**Inputs**:
- README.md
- README_CN.md
- Existing `tests/test_readme_command_flow.py` (v0.8) for CLI
  anchor health

**Findings format**: `temp/v0.10.0-audit-bundle/03-readme-audit.md`:
- Section-by-section review (EN / CN parallel comparison)
- 9-concept order still correct? Install instructions unambiguous?
  "Three product modes" callout reads cleanly?
- Author bio + related-work section appropriate for public eyes?
- Any embedded jargon that needs glossing?
- Section-anchor parity: every `## N. <name>` in README must have
  a matching `## N. <name>` in README_CN (drift gate to add to RC
  tests)

**Expected outcome**: synchronized small edits to README /
README_CN. **New** drift-detector in `tests/test_release_candidate.py`
asserting section-anchor parity. No structural rewrites.

---

## 10. Security / safety / privacy audit

**Goal**: zero private / sensitive information leaks through repo
files or commit history. Public-launch-blocking risk if missed.

**Inputs**:
- `git grep` for common secret patterns: `api_key` / `apikey` /
  `token` / `password` / `secret` / `BEGIN PRIVATE KEY` /
  `-----BEGIN` / `Authorization:` / `Bearer` / `AWS_` / `GCP_`
- Email-address scan (anything other than Kun's documented contact)
- Hostnames / IP addresses scan
- Internal Slack handles / customer names / coworker names
- `git log -p` quick spot-check for accidentally-committed +
  rolled-back secrets
- SECURITY.md content (disclosure contact still valid?)

**Findings format**: `temp/v0.10.0-audit-bundle/04-security-audit.md`:
- Per-pattern match counts + per-match human-review verdict
  (false positive / acceptable / FINDING)
- Any FINDING is a NO-GO blocker for the *post-v0.10* visibility
  flip — must be remediated in v0.10
- SECURITY.md content review

**Expected outcome**: clean — or list of must-remediate items
*before* v0.10 release. Remediation lands in v0.10 (per Kun's
direction: v0.10 is the freeze cycle, fix-it-now is part of the
freeze).

---

## 11. License / contribution / issue-template audit

**Goal**: governance files are accurate, current, and minimally
suitable for a hypothetical public reader.

**Inputs**:
- `LICENSE` (MIT, per v0.3.1)
- `CONTRIBUTING.md` (v0.3.1 baseline)
- `SECURITY.md` (v0.3.1 baseline)
- Absence of `.github/` (no ISSUE_TEMPLATE / PR template /
  CODEOWNERS / FUNDING)

**Findings format**: `temp/v0.10.0-audit-bundle/05-license-audit.md`:
- LICENSE: copyright year + holder name correct?
- CONTRIBUTING: describes current cycle workflow (spec → C1 →
  review → release)? Doesn't promise external-PR review SLA that
  Kun-as-solo-maintainer cannot meet? Notes repo is PRIVATE and PRs
  are not currently accepted from outside?
- SECURITY: disclosure contact still Kun's documented address?
  Mentions current scope of supported versions?
- `.github/` decision: confirmed deferred to post-v0.10 (NOT v0.10
  scope)

**Expected outcome**: small edits to CONTRIBUTING + SECURITY to
honestly reflect "currently single-maintainer, PRIVATE, no
external PR pipeline yet". LICENSE year update (if needed).
No `.github/` work this cycle.

---

## 12. Packaging / install audit

**Goal**: `pip install -e .` works on a fresh clone + clean venv +
all 3 platforms (Windows / Linux / macOS) as far as can be
verified from Kun's machine + manual testing.

**Inputs**:
- `pyproject.toml`
- README "Install" section
- Fresh-clone manual test (Kun's Windows machine — only platform
  available without CI)

**Findings format**: `temp/v0.10.0-audit-bundle/06-install-audit.md`:
- pyproject metadata review:
  - `name`: `agent-harness-lab` — public-discoverable, no conflict
    on PyPI namespace (even though we are not publishing)
  - `version`: matches latest tag
  - `description`: clean for public readers
  - `requires-python`: `>=3.10` — verified against actual stdlib
    usage
  - `dependencies`: `[]` — stdlib-only philosophy maintained
  - `[project.scripts]`: `ahl` + `hdl` (legacy redirect) still
    appropriate
  - **Add (if missing)**: `classifiers` (Development Status,
    Intended Audience, License, Programming Language, Topic),
    `keywords`, `authors`, `urls.Homepage` / `urls.Issues` /
    `urls.Changelog`
- README Install section accuracy: `pip install -e .` works on
  fresh clone; `ahl --help` prints 14 commands; `python -m
  agent_harness_lab` fallback works
- Platform notes: Windows path handling tested; macOS / Linux
  documented as "not CI-tested in v0.10" with explicit caveat

**Expected outcome**: small pyproject.toml metadata fill-in (no
behavior change) + 1-2 README install-section edits.

---

## 13. Sample workspace audit

**Goal**: `examples/sample-workspace/` (v0.7), `examples/copilot-
setup-example/` (v0.9), `examples/evidence-examples/` (v0.8) all
still work, all still match their advertised contracts.

**Inputs**:
- Existing `tests/test_sample_workspace_e2e.py` (v0.7)
- Existing `tests/test_copilot_setup_example.py` (v0.9)
- Existing `tests/test_doc_consistency.py` evidence-examples checks
  (v0.8)
- Manual fresh smoke run

**Findings format**: `temp/v0.10.0-audit-bundle/07-sample-audit.md`:
- All 3 example trees pass their respective acceptance tests?
- `ahl probe / run / score / compare` on `sample-workspace/001`
  exits 0, produces compare report with `## Evidence` section
  showing `strong`?
- `copilot-setup-example/` directory shape unchanged?
- `evidence-examples/` 3 template files still valid?
- No generated artifacts in any example tree
- READMEs in each example tree read clean for public visitors

**Expected outcome**: confirm green; if any example tree drifted
since its release cycle, fix-forward in v0.10 (these are public-
facing reference artifacts).

---

## 14. Evidence / release history audit

**Goal**: CHANGELOG + GitHub Releases + tags + roadmap all tell the
same story, with consistent dates / versions / theme statements.

**Inputs**:
- `CHANGELOG.md`
- `git tag --list`
- `gh release list --repo Kun-0546/agent-harness-lab`
- `docs/roadmap.md`
- Each release-notes file in `temp/v0.X.0-release-notes.md`

**Findings format**: `temp/v0.10.0-audit-bundle/08-history-audit.md`:
- Per-tag row: `tag / CHANGELOG section / GitHub Release title /
  roadmap entry status` — all consistent?
- Date alignment: each release tag's commit date matches its
  CHANGELOG `[X.Y.Z] - YYYY-MM-DD` line
- Theme statement alignment: CHANGELOG header line ↔ GitHub Release
  title ↔ roadmap entry title
- No "v0.X is shipped" claims in roadmap that don't have an actual
  tag
- No `[Unreleased]` content that's already shipped

**Expected outcome**: typically clean (we've been disciplined); any
findings get tiny edits in v0.10.

---

## 15. Final acceptance checklist

Output artifact: **`docs/public-launch-checklist.md`** —— v0.10 ships
this as the *post-v0.10* visibility-flip GO/NO-GO clipboard.

Structure mirrors v0.8 `docs/product-acceptance-checklist.md`
(12-group A-L format):

- **Group A — Repo hygiene**: no large files, no generated
  artifacts, .gitignore covers temp/sandbox/results
- **Group B — Docs first impression**: README + README_CN read
  clean, walkthrough Step 1 → Step 9 navigates cleanly
- **Group C — Install + smoke**: fresh-clone install works,
  `ahl --help` shows 14 commands, sample-workspace recipe completes
- **Group D — Sample workspaces**: 3 example trees pass tests + smoke
- **Group E — Evidence reading**: compare report `## Evidence`
  section legible without out-of-band explanation
- **Group F — Co-pilot workflow**: brief.md 12-section + materials/
  8-section + copilot-setup.md + copilot-setup-example all coherent
- **Group G — Honest status**: README §9 "What is NOT implemented
  yet" matches actual state; no Auto-mode-imminent implication
- **Group H — Governance**: LICENSE / CONTRIBUTING / SECURITY all
  current
- **Group I — Release history**: CHANGELOG + tags + GitHub Releases
  + roadmap all consistent
- **Group J — Security**: no secret / PII leaks (per §10 scan)
- **Group K — Packaging**: pyproject metadata accurate
- **Group L — RC tests**: 512+ pass default + strict, RC test
  module pass

Each group has 3-6 explicit yes/no items. v0.10 release condition:
**all groups green** (Kun signs off line-by-line).

---

## 16. GO / NO-GO criteria for public visibility flip

> **Important**: these are criteria for the *post-v0.10*
> visibility-flip decision, not for shipping v0.10 itself. v0.10
> ships when §15 checklist is green. The visibility flip is its own
> later GO event.

**GO only if all of**:
- Repo clean of secrets / private info (§10 audit green)
- README explains product clearly to a public reader (§9 audit
  green)
- Fresh-clone install works (§12 audit green)
- Sample workspaces work (§13 audit green)
- Tests pass in default + strict modes (§Quality gates green)
- Docs links pass (drift detectors green)
- Release history coherent (§14 audit green)
- LICENSE / CONTRIBUTING / SECURITY all accurate (§11 audit green)
- Public-facing terms not misleading (§9 + audit findings cleared)
- No Auto-mode-implemented claims anywhere
- No unsupported cloud / registry / PyPI claims
- No broken v0.1-v0.9 compatibility claims
- `docs/public-launch-checklist.md` exists and is green
- A separate, explicit Kun decision (no automatic flip on v0.10
  ship)

**NO-GO if any of**:
- Private material leak found (commit history or current files)
- Any sample workspace fails
- Install instructions fail on fresh clone
- Docs overclaim (Auto / cloud / scale / production-readiness)
- Auto is implied as implemented / next-release
- Public-launch-checklist has unresolved blockers
- Repo visibility cannot be safely flipped (e.g., PR review SLA
  cannot be honored as solo maintainer)
- Kun is not personally ready to maintain a public project

v0.10 ship itself does **not** require GO on the visibility flip
question. v0.10 ship requires only §15 checklist green.

---

## 17. Implementation plan

Standard v0.X cycle pattern. Because every audit sub-component is
independent + small, **C1 + C2 split is optional**. Kun's direction
said "If the implementation is small enough to complete cleanly in
one pass, still report it as a single implementation bundle with
tests." Default: **single implementation bundle**.

### Single-bundle (default) flow

Allowed files:
- `temp/v0.10.0-audit-bundle/` (11 audit reports, NOT committed)
- `docs/public-launch-checklist.md` (NEW)
- `docs/open-source-readiness-freeze.md` (this spec — already
  in this commit)
- `tests/test_release_candidate.py` (NEW)
- `tests/test_doc_consistency.py` (extend with README EN/CN parity)
- `tests/test_readme_command_flow.py` (extend if needed for §9
  findings)
- `README.md` / `README_CN.md` (small edits per §9 findings)
- `docs/README.md` (small edits per §8 findings)
- `docs/product-walkthrough.md` (small edits per §8 findings)
- `docs/file-formats.md` (small edits per §8 findings)
- `docs/copilot-setup.md` (small edits per §8 findings)
- `docs/evidence-guide.md` (small edits per §8 findings)
- `docs/roadmap.md` (mark v0.10 [shipped] at release-prep stage)
- `pyproject.toml` (small metadata fill-in per §12 + version bump
  at release-prep)
- `CONTRIBUTING.md` / `SECURITY.md` / `LICENSE` (small edits per §11)
- `CHANGELOG.md` (new `[0.10.0]` section at release-prep)
- `.gitignore` (only if §7 audit surfaces a gap)
- `temp/v0.10.0-release-notes.md` (at release-prep)

Forbidden files this cycle:
- Anything in `src/` (zero src behavior change)
- Any new `examples/` tree
- `.github/` (deferred to post-v0.10)
- `tests/test_*.py` other than the two listed above (no regression
  to existing behavior-tests)

Acceptance: §15 final acceptance checklist all green.

### Split C1 + C2 (fallback if findings are large)

If §7-§14 audits surface ≥10 unrelated edits across ≥5 docs, split:
- **C1 = audit + findings + spec edits** (all 11 audit reports
  written, all spec edits identified but **not** applied)
- **C2 = remediation + RC tests + checklist** (apply edits, write
  RC test module + public-launch-checklist, run quality gates)

Default is single-bundle. Spec lock-in stage will pick after audits
run.

### Release-prep stage (after acceptance)

- Bump `pyproject.toml` to `0.10.0`
- Add `CHANGELOG.md` `[0.10.0] - YYYY-MM-DD` section
- `docs/roadmap.md` v0.10 entry → `[shipped]`; v1.x bucket stays
  [future]
- Annotated tag `v0.10.0` on release-prep commit (peeled commit =
  release-prep, NOT last audit commit)
- GitHub Release notes from `temp/v0.10.0-release-notes.md`
- **STOP**. Do NOT flip visibility. Do NOT publish PyPI. Do NOT
  announce.

---

## 18. Redlines

Reproduced for cycle-lock convenience (full list in §6):

- Repo PRIVATE throughout v0.10 — visibility flip is *post-v0.10*
- No PyPI publish / announcement / social
- No new CLI command (14-cap)
- No Auto mode / approval gates / calibration
- No MCP / registry / cloud attestation API
- No `ahl package inspect / validate` (deferred to v1.x)
- No probe ↔ snapshot binding (deferred to v1.x)
- No new runtime source types
- No snapshot / evidence / scoring / package / probe contract
  changes
- No `ahl run / score / compare` behavior changes
- No CLI command or flag rename
- No deletion of release history (tags / GitHub Releases /
  CHANGELOG)
- No deletion of audit-trail planning branches
- No deletion of v0.7 / v0.8 / v0.9 artifacts
- No deletion of historical docs (banners stay)
- No `.github/` workflows / templates this cycle
- No marking "public launch" as completed anywhere
- No "open source soon" / "ready for public" claims in docs
- No `--no-verify` / hook bypass
- No push without Kun explicit OK (per
  [[feedback-no-implicit-push]])

---

## 19. Open questions (for Kun to lock before audits start)

### Q1 · Audit bundle commit policy?

Spec assumes `temp/v0.10.0-audit-bundle/` is **NOT committed** (per
v0.7 / v0.8 / v0.9 review-bundle pattern). Audit *findings* drive
in-cycle edits; the raw bundle stays local.

- (a) Default — bundle stays local (in `temp/`, gitignored)
- (b) Bundle committed for transparency / public-launch
  decision-record value

**Recommendation**: **(a)**. Findings drive edits; raw bundle is
working material.

### Q2 · Audit-trail planning branches — keep all on origin pre-launch?

Currently on origin: `v0.7.0-planning`, `v0.8.0-planning`,
`v0.9.0-planning`. If repo flips public, these are visible to
public readers.

- (a) Keep all three (audit trail > cosmetic) — default
- (b) Delete from origin pre-launch, keep local

**Recommendation**: **(a)** for v0.10. The visibility-flip cycle
(post-v0.10) can revisit this — but it should NOT happen in v0.10
itself (no deletion of release history is a v0.10 redline).

### Q3 · README §9 "What is NOT implemented yet" — auto-Auto vs honest deferral?

v0.9 README §9 currently lists "Auto mode" as not-implemented with
"Needs calibration + approval gates first (M2+)". Now that Q5 lock
moves Auto to post-OSS / v1.x, the §9 wording may understate the
deferral.

- (a) Tighten §9 Auto bullet to read "deferred to v1.x /
  post-open-source; NOT planned for v0.10"
- (b) Leave §9 as-is (the M2+ language is technically still
  correct)

**Recommendation**: **(a)** — public readers must not infer Auto is
"coming soon."

### Q4 · `pyproject.toml` classifiers — add even though no PyPI publish?

- (a) Add `classifiers` / `keywords` / `urls` per §12 — makes the
  metadata complete even pre-PyPI; trivially useful for any future
  PyPI cycle
- (b) Leave minimal; add only when actually publishing

**Recommendation**: **(a)**. Cost is trivial; benefit is "pyproject
is complete on day-1 of future PyPI cycle, no last-minute scramble".

### Q5 · `docs/public-launch-checklist.md` — wording strength?

Public-launch checklist is the *post-v0.10* GO clipboard. Should it
be:

- (a) Specific, with line-by-line yes/no items (~80-120 line doc)
- (b) High-level intent, with audit cross-references (~30-40 line
  doc)

**Recommendation**: **(a)** — mirrors v0.8
`product-acceptance-checklist.md` (12 groups A-L). Concrete >
gestural for a GO decision.

### Q6 · RC test module — how strict?

`tests/test_release_candidate.py` proposed to cover: top-level files
exist, README EN/CN section-anchor parity, no TODO/XXX/FIXME in
current-surface docs, CHANGELOG section ordering = tag order, no
broken internal links.

- (a) All 5 invariants — strict RC tests
- (b) Just the "files exist" + "no TODO" — light-touch tests

**Recommendation**: **(a)**. Drift detectors are the codebase's
contract-enforcement style; RC deserves the same.

### Q7 · Install audit — Kun's machine only, or fail-soft attempt at Linux/macOS?

No CI infrastructure in v0.10 (`.github/workflows/ci.yml` deferred
to post-v0.10). Install audit can only really run on Kun's Windows
machine.

- (a) Document Windows-only verification + add explicit
  "Linux / macOS not CI-tested in v0.10" caveat in install audit
- (b) Defer install audit entirely until post-v0.10 CI cycle

**Recommendation**: **(a)**. Some verification > none. The caveat
ensures the post-v0.10 visibility-flip cycle catches the gap.

### Q8 · `temp/v0.10.0-release-notes.md` content emphasis?

v0.10 ships an audit + freeze + RC clipboard, not a feature. Release
notes should emphasize:

- (a) "Open-source readiness audit + RC + GO/NO-GO checklist"
  (process-focused, accurate)
- (b) "What's new in v0.10" feature-list framing (mismatched —
  v0.10 has no features)

**Recommendation**: **(a)**. Be honest about cycle character.
