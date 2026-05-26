"""Agent Harness Lab 命令行入口。

这层只管:解析参数、把结果打印给用户、把活儿交给 workflow。
run / score / compare 的编排逻辑在 workflow.py。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_harness_lab import templates, workflow
from agent_harness_lab.connect import parse_connect
from agent_harness_lab.program import (
    DECLARATION_STATUS,
    KNOWN_DECLARATIONS,
    parse_program,
)
from agent_harness_lab.rubric import parse_rubric
from agent_harness_lab.simulator import parse_simulator
from agent_harness_lab.testset import load_testset
from agent_harness_lab.version import load_versions


def _experiments_dir() -> Path:
    return Path.cwd() / "experiments"


def _next_number() -> str:
    d = _experiments_dir()
    nums = []
    if d.exists():
        for p in d.iterdir():
            head = p.name.split("-", 1)[0]
            if p.is_dir() and head.isdigit():
                nums.append(int(head))
    return f"{(max(nums) + 1) if nums else 1:03d}"


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    created = []
    goal = root / "goal.md"
    if goal.exists():
        print("已存在,跳过:goal.md")
    else:
        goal.write_text(templates.GOAL_TEMPLATE, encoding="utf-8")
        created.append("goal.md")
    if not _experiments_dir().exists():
        _experiments_dir().mkdir()
        created.append("experiments/")
    print(f"初始化:{root}")
    for c in created:
        print(f"  + {c}")
    print()
    print("Agent Harness Lab 帮你通过实验改进 agent 的 runtime harness。")
    print()
    print("下一步:")
    print("  Step 1  编辑 goal.md")
    print("          先说清楚:你想改善这个 agent 的什么行为?")
    print()
    print("  Step 2  选择 setup mode (只影响 ahl new 建什么结构)")
    print("          copilot (默认):coding agent 引导式配置实验,")
    print("                         维护 brief.md / materials/")
    print("          manual:你手动编辑完整骨架")
    print("          auto:未来模式,当前 not implemented")
    print()
    print("  Step 3  声明 runtime boundary (agent 在哪 + harness 在哪)")
    print("          本地源码 / Git repo → runtime-sources.md "
          "(通常 strong evidence)")
    print("          已运行的 agent → connect.md")
    print("                          可能需要补 materials/*-evidence.md "
          "(尤其 cloud agent)")
    print()
    print("查看完整流程:")
    print("  ahl walkthrough")
    print("  docs/product-walkthrough.md")
    return 0


def cmd_walkthrough(args: argparse.Namespace) -> int:
    """打印 AHL 9 步标准产品流程概览。"""
    print(templates.WALKTHROUGH_TEXT, end="")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    path = Path.cwd() / "connect.md"
    if not path.exists():
        print("当前目录没有 connect.md。", file=sys.stderr)
        print("connect.md 是 Step 3 的 legacy running-agent 接入配置,"
              "不再由 ahl init 默认创建。", file=sys.stderr)
        print("- 要连一个已经在跑的 agent:手动创建 connect.md"
              "(格式见 docs/file-formats.md)", file=sys.stderr)
        print("- 要从本地源码或 Git repo 跑实验:创建 runtime-sources.md",
              file=sys.stderr)
        print("", file=sys.stderr)
        print("用 connect.md 时 AHL 看不到 agent 内部状态,可能需要补 evidence;",
              file=sys.stderr)
        print("详见 docs/product-walkthrough.md Step 3 "
              "(2×2 矩阵 + evidence level)。", file=sys.stderr)
        return 1
    c = parse_connect(path)
    print(f"接入配置:{path}")
    print()
    print(f"类型:{c.conn_type or '(空)'}")
    print(f"配置:{c.config or '(空)'}")
    print()
    problems = c.validate()
    if problems:
        print(f"检查:{len(problems)} 个问题")
        for item in problems:
            print(f"  - {item}")
    else:
        print("检查:通过")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    """新建实验。

    --mode 是 experiment setup mode:只决定 ahl new 建什么结构,
    不影响 run / score / compare;不写元数据到实验目录。
    """
    setup_mode = args.mode  # copilot / manual / auto

    if setup_mode == "auto":
        print("Auto mode 暂未实现执行能力 (M2+),还在产品设计阶段。",
              file=sys.stderr)
        print("当前可用 setup mode:", file=sys.stderr)
        print("  - copilot (默认) —— AI 引导式实验配置", file=sys.stderr)
        print("  - manual         —— 你手动编辑完整骨架", file=sys.stderr)
        print("", file=sys.stderr)
        print("推荐路径:--mode copilot (默认) —— 见 docs/copilot-setup.md",
              file=sys.stderr)
        print("Auto 完整设计:docs/product-walkthrough.md Step 2 + Step 9",
              file=sys.stderr)
        return 2

    exp_name = f"{_next_number()}-{args.name}"
    exp_dir = _experiments_dir() / exp_name
    if exp_dir.exists():
        print(f"实验目录已存在:{exp_dir}", file=sys.stderr)
        return 1
    exp_dir.mkdir(parents=True)

    if setup_mode == "manual":
        (exp_dir / "program.md").write_text(
            templates.PROGRAM_TEMPLATE.replace("{name}", exp_name),
            encoding="utf-8")
        (exp_dir / "rubric.md").write_text(templates.RUBRIC_TEMPLATE,
                                            encoding="utf-8")
        (exp_dir / "simulator.md").write_text(templates.SIMULATOR_TEMPLATE,
                                               encoding="utf-8")
        (exp_dir / "cases").mkdir()
        (exp_dir / "harnesses").mkdir()
        print(f"建好实验:{exp_name}  (setup mode=manual)")
        print(f"  {exp_dir}")
        print("    program.md     —— 实验指令(假设 + 声明)")
        print("    rubric.md      —— 评分维度 + 权重")
        print("    simulator.md   —— 模拟模式下扮用户的 agent")
        print("    cases/         —— 放 case 文件")
        print("    harnesses/     —— 放被测的 harness variant 文件")
        print("  下一步:填 program.md、rubric.md、simulator.md;"
              "往 cases/、harnesses/ 加文件。")
        return 0

    # copilot (default)
    (exp_dir / "brief.md").write_text(templates.BRIEF_TEMPLATE,
                                       encoding="utf-8")
    materials_dir = exp_dir / "materials"
    materials_dir.mkdir()
    (materials_dir / "README.md").write_text(
        templates.MATERIALS_README_TEMPLATE, encoding="utf-8")
    (exp_dir / "cases").mkdir()
    (exp_dir / "harnesses").mkdir()
    print(f"建好实验:{exp_name}  (setup mode=copilot)")
    print(f"  {exp_dir}")
    print("    brief.md             —— 工作单 (跟 coding agent 一起维护)")
    print("    materials/README.md  —— 协作目录说明")
    print("    cases/               —— coding agent 起草")
    print("    harnesses/           —— coding agent 起草")
    print()
    print("下一步:")
    print('  1. (可选) 编辑 brief.md §1 写清"这次想验证什么"')
    print("  2. 让 coding agent (Claude Code / Cursor / Codex) 协作:")
    print("     - 据 goal.md + brief.md + materials/ 起草 "
          "program/rubric/cases/harnesses")
    print("     - 通过对话帮你完善 brief.md / 整理 materials/")
    print("     - 锁定不让 AI 改的文件:在 materials/locked.md 里列 (可选)")
    print(f"  3. 文件准备好后:ahl review {args.name}  → ahl run {args.name}")
    return 0


def _find_experiment(ident: str) -> Path | None:
    d = _experiments_dir()
    if not d.exists():
        return None
    if (d / ident).is_dir():
        return d / ident
    for p in sorted(d.iterdir()):
        if not p.is_dir():
            continue
        head, _, tail = p.name.partition("-")
        if ident in (p.name, head, tail):
            return p
    return None


def cmd_show(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    program_path = exp_dir / "program.md"
    if not program_path.exists():
        print(f"实验里没有 program.md:{exp_dir}", file=sys.stderr)
        return 1

    prog = parse_program(program_path)
    print(f"实验:{exp_dir.name}")
    print(f"program:{program_path}")
    print()
    print(f"假设:{prog.assumption or '(空)'}")
    print("声明:")
    for key in KNOWN_DECLARATIONS:
        val = prog.declarations.get(key, "(缺)")
        status = DECLARATION_STATUS.get(key, "")
        print(f"  {key}:{val}" + (f"  [{status}]" if status else ""))
    cmp_status = DECLARATION_STATUS.get("对比方式", "")
    print(f"  对比方式:{prog.compare_mode}" + (f"  [{cmp_status}]" if cmp_status else ""))
    for key, val in prog.declarations.items():
        if key not in KNOWN_DECLARATIONS and key != "对比方式":
            print(f"  {key}:{val}  (额外)")
    print(f"留/丢规则:{prog.keep_discard or '(空)'}")
    print(f"喊人规则:{prog.call_human or '(空)'}")
    print()

    problems = prog.validate()
    if problems:
        print(f"检查:{len(problems)} 个问题")
        for item in problems:
            print(f"  - {item}")
    else:
        print("检查:通过")
    return 0


def cmd_cases(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    try:
        cases = load_testset(exp_dir)
    except (FileNotFoundError, NotImplementedError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"实验:{exp_dir.name}  cases:{len(cases)} 个")
    if not cases:
        print("(cases/ 是空的——往 cases/ 加 case 文件;格式见 docs/file-formats.md)")
        return 0
    print()
    total_problems = 0
    for c in cases:
        bits = [c.case_id]
        if c.type:
            bits.append(f"type={c.type}")
        if c.max_turns is not None:
            bits.append(f"max_turns={c.max_turns}")
        if c.depends_on:
            bits.append(f"前置={c.depends_on}(暂未接入 run)")
        print("  " + "  ".join(bits))
        first = c.opening.splitlines()[0] if c.opening.strip() else "(空)"
        if len(first) > 42:
            first = first[:42] + "…"
        print(f"    起始输入:{first}")
        print(f"    完成标准:{'有' if c.criterion.strip() else '无'}")
        for p in c.validate():
            total_problems += 1
            print(f"    ! {p}")
    print()
    print(f"检查:{total_problems} 个问题" if total_problems else "检查:通过")
    return 0


def cmd_rubric(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    rubric_path = exp_dir / "rubric.md"
    if not rubric_path.exists():
        print(f"实验里没有 rubric.md:{exp_dir}", file=sys.stderr)
        return 1

    rubric = parse_rubric(rubric_path)
    print(f"实验:{exp_dir.name}")
    print(f"rubric:{rubric_path}")
    print()
    if not rubric.dimensions:
        print("(没有维度)")
    for d in rubric.dimensions:
        weight = f"{d.weight:g}" if d.weight is not None else "(缺)"
        print(f"  {d.name}  权重 {weight}")
        desc = d.description.splitlines()[0] if d.description.strip() else "(空)"
        if len(desc) > 46:
            desc = desc[:46] + "…"
        print(f"    {desc}")
    if rubric.dimensions:
        print(f"  —— 权重之和 {rubric.weight_total():g}")
    print()

    problems = rubric.validate()
    if problems:
        print(f"检查:{len(problems)} 个问题")
        for item in problems:
            print(f"  - {item}")
    else:
        print("检查:通过")
    return 0


def cmd_versions(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    try:
        versions = load_versions(exp_dir)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"实验:{exp_dir.name}  harnesses:{len(versions)} 个")
    if not versions:
        print("(harnesses/ 是空的——一个 harness variant 一个文件;格式见 docs/file-formats.md)")
        return 0
    print()
    total_problems = 0
    baseline_count = 0
    for v in versions:
        if v.is_baseline:
            baseline_count += 1
        tag = "  [基线]" if v.is_baseline else ""
        print(f"  {v.version_id}{tag}")
        what = v.what.splitlines()[0] if v.what.strip() else "(空)"
        if len(what) > 44:
            what = what[:44] + "…"
        print(f"    这是什么:{what}")
        if v.connect is not None:
            print(f"    接入:{v.connect.conn_type}(版本自带)")
        else:
            print("    接入:用全局 connect.md")
        for p in v.validate():
            total_problems += 1
            print(f"    ! {p}")
    print()
    if baseline_count == 0:
        total_problems += 1
        print("! 没有标基线的版本(应有一个不动的当参照)")
    elif baseline_count > 1:
        total_problems += 1
        print(f"! 有 {baseline_count} 个版本标了基线(应只有一个)")
    print(f"检查:{total_problems} 个问题" if total_problems else "检查:通过")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    try:
        result = workflow.run(exp_dir, args.llm,
                              cleanup_sandboxes=args.cleanup_sandboxes)
    except workflow.WorkflowError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"  跑完 {result.total} 条:成功 {result.ok},"
          f"失败 {result.failed},共 {result.turns} 轮对话")
    for version_id, case_id, error in result.errors:
        print(f"  ! {version_id}/{case_id}:{error}")
    print(f"  对话存到:{result.out_path}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    try:
        result = workflow.score(exp_dir, args.llm)
    except workflow.WorkflowError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"实验:{exp_dir.name}  打分:{result.run_file}  评分器:{result.grader_name}")
    print()
    for version_id, avg, case_count in result.by_version:
        print(f"  {version_id}  平均总分 {avg:.2f}  ({case_count} case)")
    print()
    print(f"  分数存到:{result.out_path}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    try:
        result = workflow.compare(exp_dir)
    except workflow.WorkflowError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(result.report_text)
    print(f"\n对比报告存到:{result.out_path}")
    # v0.4:evidence 有 warning/note 时多打一行指向 report 顶部 Evidence 段。
    # 退出码不变;不 block。spec docs/evidence-aware-result.md §5.2。
    from agent_harness_lab.evidence import evidence_warning
    signals = evidence_warning(result.evidence)
    if signals["warning"]:
        print(f"⚠ {signals['warning']} —— 见 report 顶部 Evidence 段")
    elif signals["note"]:
        print(f"ℹ {signals['note']} —— 见 report 顶部 Evidence 段")
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    """ahl draft 已合并到 ahl new --mode copilot。打印迁移提示后退出。

    v0.3.1 Step 2 处理:跟 cmd_versions_legacy_redirect 套路一致——
    不做转发(避免双入口语义),不创建任何实验目录或文件,旧调用拿明确指引。
    """
    print("ahl draft 已合并到 ahl new --mode copilot。", file=sys.stderr)
    print("请改用:", file=sys.stderr)
    name = getattr(args, "name", None) or "<name>"
    print(f"  ahl new {name} --mode copilot", file=sys.stderr)
    print("或省略 --mode (copilot 是默认):", file=sys.stderr)
    print(f"  ahl new {name}", file=sys.stderr)
    print("", file=sys.stderr)
    print("完整 setup mode 说明:ahl walkthrough (Step 2) "
          "或 docs/product-walkthrough.md", file=sys.stderr)
    return 1


def cmd_review(args: argparse.Namespace) -> int:
    """读实验里现有文件,出 review.md。

    宽松 —— 不抛错。CLI summary 把四类信号都拉出来:
    未起草 / 解析失败 / 未检查(依赖文件坏)/ 校验提醒(validate 问题)。
    任一非空就不说「齐了」。
    """
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    try:
        result = workflow.review(exp_dir)
    except workflow.WorkflowError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"review:{result.out_path}")
    if result.missing:
        print(f"  未起草:{'、'.join(result.missing)}")
    if result.broken:
        print(f"  解析失败:{'、'.join(result.broken)}")
    if result.skipped:
        print(f"  未检查(依赖文件有问题):{'、'.join(result.skipped)}")
    if result.warnings:
        print(f"  校验提醒:{len(result.warnings)} 处(详见 review.md);"
              f"建议修完再跑 ahl run")
    # v0.6: probe summary 显示 (review 是 read-only, 不触发 probe;
    # spec docs/runtime-probe-mvp.md §5)。
    if result.probe_summary:
        s = result.probe_summary
        c = s.get("counts") or {}
        total = s.get("total", 0)
        print(f"  Last probe: {s['probe_id']} · "
              f"{c.get('ok', 0)}/{total} ok / "
              f"{c.get('warn', 0)} warn / "
              f"{c.get('fail', 0)} fail")
    else:
        print(f"  No probe artifact yet — run `ahl probe {args.experiment}` "
              f"to verify runtime ready (read-only check)")
    if not (result.missing or result.broken or result.skipped or result.warnings):
        print(f"  齐了 —— 没问题就 ahl run {args.experiment}")
    else:
        print(f"  让外层 coding agent 据 goal.md + brief.md + materials/ + "
              f"docs/product-walkthrough.md + docs/file-formats.md "
              f"起草 / 修正,再跑 ahl review {args.experiment}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """v0.6 Runtime Probe — pre-run inspection (read-only)。

    spec: docs/runtime-probe-mvp.md。退出码:任一 variant fail → 1;否则 0
    (不阻塞 future ahl run; advisory only)。
    """
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    try:
        result = workflow.probe(
            exp_dir,
            smoke_command=args.smoke_command,
            write_evidence=args.write_evidence,
            timeout=args.timeout,
        )
    except workflow.WorkflowError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"Probe: {exp_dir.name}  (probe_id: {result.probe_id})")
    for vid, art in result.variants.items():
        st = art.get("status", "?")
        rs = art.get("runtime_source") or {}
        pkg = art.get("harness_package")
        sc = art.get("start_command") or {}
        rs_type = rs.get("type", "?")
        rs_name = rs.get("name") or "—"
        pkg_str = pkg.get("ref", "—") if pkg else "—"
        sc_src = sc.get("source", "?")
        smoke = ""
        if sc.get("smoke_executed"):
            smoke = (f" smoke={sc.get('smoke_status', '?')}"
                     f"(exit {sc.get('exit_code', '?')})")
        print(f"  {vid}  status={st}  runtime={rs_type}:{rs_name}  "
              f"package={pkg_str}  start_command={sc_src}{smoke}")
        if st != "ok":
            for sub_name, sub in (("runtime_source", rs),
                                   ("harness_package", pkg),
                                   ("start_command", sc)):
                if not sub or not isinstance(sub, dict):
                    continue
                if sub.get("status") in ("warn", "fail"):
                    for r in sub.get("reasons", []):
                        print(f"      {sub_name}: {r}")

    counts = result.counts
    total = sum(counts.values())
    print(f"\nartifact: {result.probe_dir}")
    print(f"summary: {counts.get('ok', 0)}/{total} ok, "
          f"{counts.get('warn', 0)} warn, "
          f"{counts.get('fail', 0)} fail, "
          f"{counts.get('skip', 0)} skip")

    if result.evidence_writes:
        for ev_path in result.evidence_writes:
            print(f"materials evidence written: {ev_path}")
    elif args.write_evidence:
        if result.materialized_write_skipped:
            print(f"⚠ --write-evidence: skipped materialized variants "
                  f"({', '.join(result.materialized_write_skipped)}); "
                  f"materialized variants 已有 strong evidence path "
                  f"(spec docs/runtime-probe-mvp.md §7.4)")
        else:
            print("⚠ --write-evidence: no legacy_connect variants with "
                  "ok/warn status; nothing written")

    # spec §16 locked decision 4: any fail → exit 1; otherwise 0
    return 1 if counts.get("fail", 0) > 0 else 0


def cmd_simulator(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    path = exp_dir / "simulator.md"
    if not path.exists():
        if (exp_dir / "模拟器.md").exists():
            print(f"发现旧文件 模拟器.md,请改名为 simulator.md(Phase 2 命名同步):{exp_dir}",
                  file=sys.stderr)
            return 1
        print(f"实验里没有 simulator.md:{exp_dir}", file=sys.stderr)
        return 1
    sim = parse_simulator(path)
    print(f"实验:{exp_dir.name}")
    print(f"simulator:{path}")
    print()
    for label, val in (("人设", sim.persona), ("背景知识", sim.background),
                        ("追问策略", sim.strategy)):
        first = val.splitlines()[0] if val.strip() else "(空)"
        if len(first) > 46:
            first = first[:46] + "…"
        print(f"{label}:{first}")
    print()
    problems = sim.validate()
    if problems:
        print(f"检查:{len(problems)} 个问题")
        for item in problems:
            print(f"  - {item}")
    else:
        print("检查:通过")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ahl",
        description="Agent Harness Lab：设计、测试和改进 agent runtime harness 的实验工作流。",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_init = sub.add_parser("init", help="初始化工作目录(goal.md + experiments/)")
    p_init.set_defaults(func=cmd_init)

    p_walkthrough = sub.add_parser("walkthrough",
                                    help="打印 9 步产品流程概览(Step 1 Define goal → Step 9 Decide)")
    p_walkthrough.set_defaults(func=cmd_walkthrough)

    p_connect = sub.add_parser("connect",
                                help="检查 legacy running-agent 接入配置 connect.md")
    p_connect.set_defaults(func=cmd_connect)

    p_new = sub.add_parser("new",
                            help="新建实验 (setup mode=copilot 默认 / manual / auto)")
    p_new.add_argument("name", help="实验名,会建成 experiments/<编号-名字>/")
    p_new.add_argument("--mode",
                        choices=["copilot", "manual", "auto"],
                        default="copilot",
                        help="experiment setup mode (只决定建什么结构,"
                             "不影响 run/score/compare);默认 copilot:"
                             "AI 引导式配置 (brief.md 工作单 + materials/);"
                             "manual:手动完整骨架 (program/rubric/simulator);"
                             "auto:暂未实现 M2+")
    p_new.set_defaults(func=cmd_new)

    p_show = sub.add_parser("show", help="读实验的 program.md 并检查")
    p_show.add_argument("experiment", help="实验编号或名字")
    p_show.set_defaults(func=cmd_show)

    p_cases = sub.add_parser("cases", help="读实验的 cases 并检查")
    p_cases.add_argument("experiment", help="实验编号或名字")
    p_cases.set_defaults(func=cmd_cases)

    p_rubric = sub.add_parser("rubric", help="读实验的 rubric 并检查")
    p_rubric.add_argument("experiment", help="实验编号或名字")
    p_rubric.set_defaults(func=cmd_rubric)

    p_simulator = sub.add_parser("simulator", help="读实验的模拟器配置并检查")
    p_simulator.add_argument("experiment", help="实验编号或名字")
    p_simulator.set_defaults(func=cmd_simulator)

    p_harnesses = sub.add_parser("harnesses", help="读实验的 harnesses 并检查")
    p_harnesses.add_argument("experiment", help="实验编号或名字")
    p_harnesses.set_defaults(func=cmd_versions)

    p_versions = sub.add_parser("versions", help=argparse.SUPPRESS)
    p_versions.add_argument("experiment", nargs="?", help=argparse.SUPPRESS)
    p_versions.set_defaults(func=cmd_versions_legacy_redirect)
    # argparse 的 help=SUPPRESS 对 subparser 不彻底 —— 仍出现在 choice list 和描述里。
    # 手动从 _choices_actions 移除,让 ahl --help 完全不显示 versions。
    sub._choices_actions = [
        a for a in sub._choices_actions if getattr(a, "dest", None) != "versions"
    ]
    if "versions" in sub.choices:
        # 仍保留 sub.choices['versions'] 让 parse_args(['versions', ...]) 走 redirect
        pass

    p_run = sub.add_parser("run", help="跑实验:每个 harness variant 过 cases,产出对话")
    p_run.add_argument("experiment", help="实验编号或名字")
    p_run.add_argument("--llm", action="store_true",
                       help="用 LLM 模拟器现生追问(先设 AHL_SIM_* 环境变量);默认用本地桩")
    p_run.add_argument("--cleanup-sandboxes", action="store_true",
                       help="跑完删 sandbox dir (默认 keep,sandbox 是证据链);"
                            "legacy variant 无 sandbox path,该 flag 对它们无效")
    p_run.set_defaults(func=cmd_run)

    p_score = sub.add_parser("score", help="给最近一次 run 的对话按 rubric 打分")
    p_score.add_argument("experiment", help="实验编号或名字")
    p_score.add_argument("--llm", action="store_true",
                         help="用 LLM Judge 真打分(先设 AHL_JUDGE_* 环境变量);默认用本地桩")
    p_score.set_defaults(func=cmd_score)

    p_compare = sub.add_parser("compare", help="把 harness variants 的分数放一起比")
    p_compare.add_argument("experiment", help="实验编号或名字")
    p_compare.set_defaults(func=cmd_compare)

    p_draft = sub.add_parser("draft", help=argparse.SUPPRESS)
    p_draft.add_argument("name", nargs="?", help=argparse.SUPPRESS)
    p_draft.set_defaults(func=cmd_draft)
    # argparse 的 help=SUPPRESS 对 subparser 不彻底 —— 仍出现在 choice list。
    # 手动从 _choices_actions 移除,让 ahl --help 完全不显示 draft
    # (跟 cmd_versions_legacy_redirect 一致处理)。
    sub._choices_actions = [
        a for a in sub._choices_actions if getattr(a, "dest", None) != "draft"
    ]

    p_review = sub.add_parser("review",
                               help="读实验里现有文件出 review.md(宽松,缺什么标未起草)")
    p_review.add_argument("experiment", help="实验编号或名字")
    p_review.set_defaults(func=cmd_review)

    # v0.6: Runtime Probe MVP (spec docs/runtime-probe-mvp.md)
    p_probe = sub.add_parser(
        "probe",
        help="对实验做 pre-run inspection (read-only;不创建 sandbox / 不修改 source)")
    p_probe.add_argument("experiment", help="实验编号或名字")
    p_probe.add_argument(
        "--command", default=None, dest="smoke_command",
        help="legacy_connect variant 的 smoke command (用户责任;"
             "捕获 stdout/stderr 各 ≤1KB)。注:dest=smoke_command 避开 "
             "subparsers dest='command' 命名冲突")
    p_probe.add_argument(
        "--write-evidence", action="store_true",
        help="对 ok/warn legacy_connect variant 写 "
             "materials/runtime-evidence.md;fail 不写")
    p_probe.add_argument(
        "--timeout", type=int, default=30,
        help="smoke command 超时秒数 (default 30,仅作用于 --command)")
    p_probe.set_defaults(func=cmd_probe)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # Windows: 强制 UTF-8
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


def cmd_versions_legacy_redirect(args: argparse.Namespace) -> int:
    """versions 子命令已改名为 harnesses。打印迁移提示后退出。

    不做转发(避免双名长期共存),按 Phase 3 兼容策略直接退出。
    """
    exp = getattr(args, "experiment", None) or "<experiment>"
    print("versions 子命令已改名为 harnesses,请用:", file=sys.stderr)
    print(f"  ahl harnesses {exp}", file=sys.stderr)
    return 1


def hdl_legacy_redirect() -> int:
    """旧 hdl 命令的迁移提示 —— Phase 3 已改名为 ahl(Agent Harness Lab)。

    保留 entry point 是为了让旧脚本/文档调用 hdl 时拿到明确指引,而非
    'command not found'。不做转发(避免双主命令长期共存),直接退出。
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args_str = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "<子命令>"
    print("hdl 命令已改名为 ahl(Agent Harness Lab)。请用:", file=sys.stderr)
    print(f"  ahl {args_str}", file=sys.stderr)
    return 1
