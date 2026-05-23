# Agent Harness Lab v0.2.0 Release 总结(Phase 1-4:HDL → Agent Harness Lab 重命名线收口)

> 日期:2026-05-21 启动 → 2026-05-22 v0.2.0 release 完成(Checkpoint A/A2/B/C/C2 + Phase 4 release/rename)
> 项目根:`<workspace>/projects/agent-harness-lab/`(已从 `harness-design-loop/` rename)
> 分支:`main`(已 merge v2-agent-drafted-lab);origin 仓库:`Kun-0546/agent-harness-lab` (PRIVATE)
> Distribution:`agent-harness-lab` v0.1.0(package version,与 release tag v0.2.0 分开)
> Status:**v0.2.0 release 完成,重命名线收口**;暂不进入 materialization / Auto / approval gates 实现
> 本文档原名 `phase-1-to-3-summary.md`,Phase 4 收口后改名 `release-v0.2.0-summary.md`,完整覆盖 Phase 1-4。

---

## 0. 背景与升级范围

项目最初叫 **HDL / Harness Design Loop**(historical codename)。此次重命名线把工具名、CLI、Python 包、环境变量、实验目录命名全部对齐到 **Agent Harness Lab**,让"一等对象是 harness 而非 agent"这件事在产品名上明示出来。

Kun 在 2026-05-21 Q3 选项 **C: 破坏性改名**(不双名长期共存,旧名只做迁移提示,不 fallback)。

升级范围(以下都是本轮做了):
- 顶层文档主线(三层架构 + 三模式)
- 实验目录/文件命名(`versions/` / `测试集/` / `模拟器.md` → `harnesses/` / `cases/` / `simulator.md`)
- Python 包(`harness_design_loop` → `agent_harness_lab`)
- Distribution name(`harness-design-loop` → `agent-harness-lab`)
- CLI 主命令(`hdl` → `ahl`)
- CLI 子命令(`versions` → `harnesses`)
- 环境变量(`HDL_*` → `AHL_*`)
- 兼容策略:旧名全做 legacy redirect,报错指向新名,不 fallback

---

## 1. Phase 1:产品定义 + 三层架构 + 三模式(2026-05-21)

### 1.1 产出物

| 文档 | 作用 |
|------|------|
| `docs/product-definition.md` | **顶层主线**:产品定位、三层架构、三模式、核心对象、文件目录、命名过渡。13 章。第一次读读这份。 |
| `docs/product-modes.md` | Manual / Co-pilot / Auto 三模式的用户心智、流程、当前状态 |
| `docs/runtime-materialization.md` | Harness Runtime Materialization & Snapshotting 的下一阶段 spec(设计阶段,**未实现**) |

### 1.2 关键决策

- **Lab 是 protocol,不是 designer**:Agent Harness Lab 不内置 Designer LLM。起草由外层 coding agent(Claude Code / Cursor / Codex)做;Lab 是协议、验证器、运行器、证据库。
- **三层架构**:Harness Layer(被设计的对象) / Experiment Layer(测量装置) / Loop Layer(改进闭环)
- **三模式**:Manual(v1 已完成) / Co-pilot(v2-minimal 当前) / Auto(未来,依赖 materialization 成熟)
- **核心对象**:Harness Variant + Agent Runtime + Runtime Sandbox = Runnable Subject

### 1.3 Checkpoint A 通过

---

## 2. Phase 1.5:六项细化 + Checkpoint A2(2026-05-21)

- product-definition 的概念跟 v2-minimal-spec 的实现对齐
- file-formats.md 跟新命名对齐
- agent-authoring-guide.md 跟新主线对齐
- 命名映射表(§11)
- 旧文档状态标注(`design-v0.3.md` v1 架构仍有效、`design-v0.4.1.md` 部分有效)
- 关键设计文档全部 freeze(spec 阶段不实现,5 source/M1-M3 分阶段交付)

Checkpoint A2 通过。

---

## 3. Phase 2:实验目录/文件命名同步 + Legacy Detection(2026-05-22 凌晨)

### 3.1 改名

| 旧 | 新 |
|----|----|
| `versions/` 目录 | `harnesses/` |
| `测试集/` 目录 | `cases/` |
| `模拟器.md` 文件 | `simulator.md` |

### 3.2 Legacy Detection 设计

按 Kun 明确要求"破坏性改名,不 fallback,不 migrate"原则:

- 代码只识别新名(`harnesses/` / `cases/` / `simulator.md`)
- 检测到旧名时抛**友好错误**,指引用户改名
- 不做自动迁移、不 fallback 到旧名

落点:
- `src/agent_harness_lab/testset.py` 检测 `测试集/`
- `src/agent_harness_lab/version.py` 检测 `versions/`
- `src/agent_harness_lab/cli.py` cmd_simulator 检测 `模拟器.md`
- `src/agent_harness_lab/workflow.py` --llm 模式检测 `模拟器.md`

### 3.3 测试

加 3 个 legacy detection 测试到 `tests/test_workflow.py` 的 TestLegacyDetection class:
- `test_legacy_versions_dir_triggers_friendly_error`
- `test_legacy_testset_dir_triggers_friendly_error`
- `test_legacy_simulator_md_triggers_friendly_error_via_cli`

pytest:55/55 OK。

### 3.4 Checkpoint B 通过

---

## 4. Phase 2 Cleanup:14 处文案(2026-05-22 早间)

Kun review Phase 2 主体通过,但指出 4 处用户可见文案 + docstring 仍残留旧目录心智。

### 4.1 14 处改动(A+B+C+E 四组)

| 组 | 类型 | 处数 | 文件 |
|----|------|------|------|
| A | 用户可见文案(空状态、错误消息、报告输出) | 4 | cli.py(2) / workflow.py(1) / report.py(1) |
| B | docstring / 内部注释 | 4 | cli.py(1) / workflow.py(3) |
| C | CLI subparser help | 3 | cli.py(3) |
| E | simulator.py 文件名 docstring(grep 阶段额外发现) | 3 | simulator.py(3) |

### 4.2 边界

- 改:出现在用户可见文案 / docstring / CLI help 中的路径名提及(`versions/` / `测试集/` / `模拟器.md`)
- 不改:legacy detection 报错指引旧名(必须保留)、概念词"模拟器"/"测试集"/"版本"、CLI 子命令 versions、Python 模块名 testset.py / version.py(留 Phase 3)

### 4.3 Checkpoint B(经 cleanup 后)通过 → 进 Phase 3

---

## 5. Phase 3:包名 + CLI + 环境变量改名(2026-05-22 下午)

### 5.1 子任务序列(P3-0 → P3-6)

| 子任务 | 改动 | 关键验证 |
|--------|------|----------|
| **P3-0** install 清理 | `<local-repo>` archive 为 `.archived_2026-05-22`,pip install -e 重定向到 <workspace> | `import harness_design_loop` 不再可用(已从环境清除) |
| **P3-1** Python 包名 | `src/harness_design_loop/` → `src/agent_harness_lab/`,19 个 .py + tests + pyproject entry path 同步 | `import agent_harness_lab` OK |
| **P3-2** 环境变量 | `HDL_SIM_*` / `HDL_JUDGE_*` / `HDL_AGENT_TIMEOUT` → `AHL_*`(5 个 .py) | grep `HDL_` 在 src/ 0 命中 |
| **P3-3** CLI 主命令 + dist name | pyproject `[project].name` 改 + entry point `hdl` → `ahl`,src + tests 中 hdl/HDL → ahl/AHL(8 文件 word-boundary) | `ahl --help` 显示 `usage: ahl ...` |
| **P3-4** hdl 兼容策略 | 加 `cli:hdl_legacy_redirect()` + pyproject `hdl = ...:hdl_legacy_redirect` | `hdl run xxx` → 迁移提示 exit 1 |
| **P3-5** README / docs 转正 | 类 B 9 处重写(过渡条幅删 + Quickstart 合一 + 状态描述更新)+ 类 A 7 个 .md 批量替换 + 类 C 4 处历史代号还原(HDL/Harness Design Loop 在 History 段保留) | grep 残留命中全部在合法位置 |
| **P3-6** Bundle | 打 phase3-bundle.zip 含全部代码 + 文档 + pytest log | unzip -l 看 49 文件 |

### 5.2 关键设计判断

- **legacy redirect 风格**:Kun 选"报错指向新名"(选项 A),保留 entry point 但不做转发,exit 1
- **Install 冲突方案**:Kun 选 A(删 ~/code/),发现 ~/code/ 是 broken 旧 checkout(无 src/),archive 后零信息损失
- **类 A 排除**:批量替换排除 `docs/design-v0.3.md` / `docs/design-v0.4.1.md` / `docs/archive/*`(历史设计文档保留旧名)
- **类 C 还原**:README/README_CN 的 "## History/历史" 段、`product-definition.md` §11 命名过渡表中"HDL / Harness Design Loop"作历史代号保留

### 5.3 Checkpoint C 通过(主体)

---

## 6. Phase 3 Cleanup:harnesses 子命令 + 5 项(2026-05-22 晚间,Checkpoint C2)

Kun review Phase 3 主体通过,但 1 个 blocker:README / product-definition 已宣告 `ahl harnesses` 子命令,但实际 `ahl --help` 仍只有 `versions` —— `ahl harnesses` 会 invalid choice。

### 6.1 7 项改动

1. 新增 `ahl harnesses` 子命令,复用 `cmd_versions` 逻辑
2. `ahl versions` 改 legacy redirect,exit 1
3. `ahl --help` 完全不显示 versions(SUPPRESS + `_choices_actions` mutate + `metavar="<command>"` 三重 hide)
4. docstring(`__init__.py` / `cli.py` 头 / `tests/__init__.py`)→ Agent Harness Lab
5. pyproject description → "A workflow tool for designing, testing, and improving agent runtime harnesses."
6. cmd_versions 状态行 `版本:N 个` → `harnesses:N 个`(跟 `cases:N 个` 风格一致)
7. 加 2 个测试到 TestLegacyDetection class(harnesses 子命令工作、versions 子命令 legacy)

### 6.2 argparse 隐藏 versions 的 3 层 hack

- `help=argparse.SUPPRESS`:描述行变 `versions    ==SUPPRESS==`(sentinel 字面化)
- 手动 `_choices_actions = [a for a in ... if a.dest != "versions"]`:消除描述行
- `metavar="<command>"`:让 usage 顶部 choice list 不 enumerate(否则 `{init,...,versions,...}` 仍含)
- 三者合一:`--help` 完全不显示 versions,但 `parse_args(["versions",...])` 仍走 redirect

### 6.3 Checkpoint C2 通过 → Phase 3 收口

---

## 7. 兼容策略汇总(所有 legacy redirect)

| 旧名 | 新名 | 触发时输出 | 行为 |
|------|------|-----------|------|
| `hdl` 命令 | `ahl` | "hdl 命令已改名为 ahl(Agent Harness Lab)。请用: ahl <args>" | exit 1 |
| `ahl versions` 子命令 | `ahl harnesses` | "versions 子命令已改名为 harnesses,请用: ahl harnesses <experiment>" | exit 1 |
| `versions/` 目录 | `harnesses/` | "发现旧目录 versions/,请改名为 harnesses/(Phase 2 命名同步): <exp>" | run / cli 抛 WorkflowError |
| `测试集/` 目录 | `cases/` | "发现旧目录 测试集/,请改名为 cases/(Phase 2 命名同步): <exp>" | 同上 |
| `模拟器.md` | `simulator.md` | "发现旧文件 模拟器.md,请改名为 simulator.md(Phase 2 命名同步): <exp>" | cli simulator / workflow --llm 报错 |

**统一原则**:全部报错指向新名,不 fallback、不 migrate。

---

## 8. 验收数据(Kun 本地 verify)

- `python -m compileall -q src tests`:OK
- `PYTHONPATH=src python -m unittest -v`:**57 tests OK**(原 55 + Phase 3 cleanup 加 2)
- `pip install -e .`:成功 (dist=agent-harness-lab v0.1.0)
- `pip show agent-harness-lab`:Summary 是新文案
- `ahl --help`:显示 harnesses,不显示 versions,13 个正常子命令
- `ahl harnesses 001`:正常执行(读 harnesses/ 下的 variants)
- `ahl versions 001`:迁移提示 exit 1
- `hdl run 001`:迁移提示 exit 1
- `AHL_*` 环境变量已替代 `HDL_*`
- README / README_CN:命名升级 banner 已删,正式转为 ahl

---

## 9. 留作后续(不在 Phase 3 范围)

### 9.1 Kun 列的 2 个非阻塞 wording fix

- `ahl --help` 顶部描述 "AI 产品研究的实验循环" → "Agent Harness Lab:设计、测试和改进 agent runtime harness 的实验工作流。"
- `ahl compare --help` 中 "把版本的分数放一起比" → "把 harness variants 的分数放一起比"

### 9.2 Phase 2 / 3 边界声明里的"未改"清单(等后续重构)

- Python 模块文件 `version.py` / `testset.py`(仍叫原名;包名已是 `agent_harness_lab`,所以路径是 `src/agent_harness_lab/version.py`)
- 概念词"模拟器"/"测试集"/"版本"在 runner.py / simulator.py 等内部表达中
- 历史设计文档(`design-v0.3.md` / `design-v0.4.1.md` / `archive/`)保留 HDL 命名
- "## History/历史/§11 命名过渡"段中"HDL / Harness Design Loop"作历史代号保留

### 9.3 Kun 明确约束(本次收口后)

> **暂时不要进入 materialization / Auto / approval gates 实现** —— 只收口不顺手加新功能。

下一阶段 spec(`docs/runtime-materialization.md`)只是设计阶段,等未来另行启动。

---

## 10. Checkpoint 时间线

| Checkpoint | 时间 | 状态 | 关卡 |
|------------|------|------|------|
| A | 2026-05-21 | ✅ 通过 | Phase 1 产品定义 + 三层架构 + 三模式 |
| A2 | 2026-05-21 | ✅ 通过 | Phase 1.5 六项细化 |
| B(初) | 2026-05-22 | ✅ 通过 | Phase 2 实验目录改名 + legacy detection |
| B(cleanup) | 2026-05-22 | ✅ 通过 | Phase 2 cleanup 14 处文案 |
| C | 2026-05-22 | ✅ 通过(有 blocker) | Phase 3 包名 / CLI / 环境变量 主体 |
| C2 | 2026-05-22 | ✅ 通过(收口) | Phase 3 cleanup harnesses 子命令 + 5 项 |

---

## 11. 收口

Phase 1-3 全部通过,Agent Harness Lab 重命名线收口。

下一动作待 Kun 决定:
- commit 全部改动到 v2-agent-drafted-lab 分支 + 推 origin
- 顺手收 2 个 wording fix(可选)
- 进入下一阶段(materialization spec 推进或别的方向)

按 Kun 明确约束,本轮收口不再顺手加新功能。

---

## 12. Phase 4:Release v0.2.0 + 三层 Rename(2026-05-22 收尾)

Phase 3 cleanup 通过(Checkpoint C2)后,本阶段做完命名升级线的全部 release 收口工作。

### 12.1 2 个 wording fix(从 §9.1 移入,已收)

Phase 3 收口时记为"留作后续"的 2 个非阻塞 wording fix,本阶段顺手收完:

- `ahl --help` 顶部:`"AI 产品研究的实验循环。"` → `"Agent Harness Lab:设计、测试和改进 agent runtime harness 的实验工作流。"`
- `compare` help:`"把版本的分数放一起比"` → `"把 harness variants 的分数放一起比"`

### 12.2 分主题 4-commit 切分 → push v2-agent-drafted-lab

按主题分 4 个 commit,by-file 粒度切分(cli.py / workflow.py 等核心文件横跨多 phase,git add -p 不可用,文件按主要 phase 归属):

- `02eef5e` docs: define Agent Harness Lab product model (Phase 1/1.5 docs)
- `8faee5c` rename experiment artifacts to harnesses and cases (Phase 2 docs/examples)
- `bab62f9` rename package and CLI to Agent Harness Lab (Phase 3 src/tests/README;含 staged rename 19 个 src 文件)
- `ad54bd2` docs: finalize Agent Harness Lab handoff (本文档进 repo)

`git push -u origin v2-agent-drafted-lab` 成功(新建 origin 分支)。

### 12.3 Merge v2 → main + Release tags

- `git merge --no-ff origin/v2-agent-drafted-lab` 无 conflict,生成 merge commit `886a7cc`
- 全套验证(compileall + pytest 57/57 + 4 smoke 全过):`ahl --help` 显示新文案、`ahl harnesses` smoke、`ahl versions` legacy redirect、`hdl` legacy redirect
- `git push origin main` 推 34 commits(首次公开 v0.1.0 + v0.2.0 完整历史到 origin/main;之前 origin/main HEAD 仅 `56b2891` 远古状态)
- `git tag -a v0.2.0 -m "v0.2.0: rename to Agent Harness Lab"` annotated tag sha `5c6eb70`,指向 merge commit `886a7cc`
- `git push origin v0.1.0 v0.2.0` 双 tag 同步上去(v0.1.0 也是首次到 origin)

### 12.4 三层 Rename(GitHub repo + remote URL + local dir)

发现 Phase 3 改动只覆盖 Python 包名/CLI/distribution name,但 GitHub 仓库名、git remote URL、local 项目目录仍是旧名。本阶段把这三层也对齐到新名:

1. `gh repo rename agent-harness-lab` → GitHub repo 改为 `Kun-0546/agent-harness-lab`(仓库仍 PRIVATE)
2. `git remote set-url origin https://github.com/Kun-0546/agent-harness-lab.git` → local remote 指新 URL
3. `mv <workspace>/projects/harness-design-loop <workspace>/projects/agent-harness-lab` + `pip install -e .` 重装 → local 目录 + pip editable link 同步

GitHub 自动 redirect 旧 URL,所以已存的 PR/issue/commit 链接仍可访问。Fork 仓库(如有)不会自动改名,所有者需要自行 rename。

### 12.5 Windows mv lock 诊断(小插曲,留作经验)

第一次 mv 失败"Access denied"。下载 Sysinternals `handle64.exe` 诊断:发现 `explorer.exe` 进程(PID 20740)持有 `harness-design-loop\temp\` 目录两个 file handle(用户在 File Explorer 看了 bundle 文件未关窗口)。关 Explorer 窗口后 mv 一次成功。

经验:**Windows directory rename 对 OS-level handle lock 极敏感**(file/dir handle,不只是 process cwd),`PowerShell Rename-Item` 也会被 lock 挡下。排查工具 `Sysinternals handle.exe`(下载 `https://download.sysinternals.com/files/Handle.zip`,跑 `handle.exe -accepteula <path-substring>`)。

### 12.6 收尾 cleanup

- 清理 `src/harness_design_loop.egg-info/`(Phase 3 之前的旧 pip metadata 残留,pip 不再引用)
- 本文档从 `phase-1-to-3-summary.md` 改名 `release-v0.2.0-summary.md`,加 Phase 4 章节,把 release 完整覆盖

---

## 13. v0.2.0 Release 收口

至此 Agent Harness Lab 重命名线 v0.2.0 release 全线收口:

- **代码**:Python 包 `agent_harness_lab` / CLI `ahl` / 环境变量 `AHL_*` / 实验目录 `harnesses` `cases` / 实验文件 `simulator.md`
- **打包**:distribution name `agent-harness-lab`,editable install 指向新 local path
- **仓库**:GitHub `Kun-0546/agent-harness-lab` (PRIVATE),local `<workspace>/projects/agent-harness-lab/`
- **历史**:main 分支 `886a7cc` 含完整 Phase 1-4 工作 + 5 个 Checkpoint,v0.1.0/v0.2.0 tags 同步 push origin
- **兼容**:所有旧名都做 legacy redirect 报错指向新名(不 fallback、不 migrate)

**Repo 仍 PRIVATE**(未来 Kun 决定要不要 public:`gh repo edit --visibility public`)。

按 Kun 明确约束,**不进入 materialization / Auto / approval gates 实现** — 那是下一阶段单独启动的工作。
