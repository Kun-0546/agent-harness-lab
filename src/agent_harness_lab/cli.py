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
    for name, content in (("connect.md", templates.CONNECT_TEMPLATE),
                          ("goal.md", templates.GOAL_TEMPLATE)):
        p = root / name
        if p.exists():
            print(f"已存在,跳过:{name}")
        else:
            p.write_text(content, encoding="utf-8")
            created.append(name)
    if not _experiments_dir().exists():
        _experiments_dir().mkdir()
        created.append("experiments/")
    golden = root / "calibration" / "golden"
    if not golden.exists():
        golden.mkdir(parents=True)
        created.append("calibration/golden/")
    print(f"初始化:{root}")
    for c in created:
        print(f"  + {c}")
    print("  下一步:")
    print("    1. 填 connect.md、goal.md")
    print("    2. 开实验:ahl new <名字>(v1 人手写)或 ahl draft <名字>(v2,外层 agent 起草)")
    print("    3. calibration/golden/ 放 golden case(对话 + 人判定;本期是约定,v2.5 用它校 judge)")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    path = Path.cwd() / "connect.md"
    if not path.exists():
        print("当前目录没有 connect.md(先 ahl init)", file=sys.stderr)
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
    exp_name = f"{_next_number()}-{args.name}"
    exp_dir = _experiments_dir() / exp_name
    if exp_dir.exists():
        print(f"实验目录已存在:{exp_dir}", file=sys.stderr)
        return 1
    exp_dir.mkdir(parents=True)
    (exp_dir / "program.md").write_text(
        templates.PROGRAM_TEMPLATE.replace("{name}", exp_name), encoding="utf-8")
    (exp_dir / "rubric.md").write_text(templates.RUBRIC_TEMPLATE, encoding="utf-8")
    (exp_dir / "simulator.md").write_text(templates.SIMULATOR_TEMPLATE, encoding="utf-8")
    (exp_dir / "cases").mkdir()
    (exp_dir / "harnesses").mkdir()
    print(f"建好实验:{exp_name}")
    print(f"  {exp_dir}")
    print("    program.md     —— 实验指令(假设 + 声明)")
    print("    rubric.md      —— 评分维度 + 权重")
    print("    simulator.md   —— 模拟模式下扮用户的 agent")
    print("    cases/         —— 放 case 文件")
    print("    harnesses/     —— 放被测的 harness variant 文件")
    print("  下一步:填 program.md、rubric.md、simulator.md;往 cases/、harnesses/ 加文件。")
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
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    """V2 入口:为外层 coding agent 开一个 authoring workspace。

    AHL 不调模型起草实验 —— 那是外层 coding agent(Claude Code / Cursor /
    Codex)的活,据 brief.md 起草 program / harnesses / cases / rubric /
    simulator,完了走 ahl run / score / compare。AHL 这里只 scaffold:建实验
    目录、brief.md 模板、空的 harnesses/ 和 cases/。幂等可重跑。
    """
    exp_dir = _find_experiment(args.name)
    if exp_dir is None:
        exp_name = f"{_next_number()}-{args.name}"
        exp_dir = _experiments_dir() / exp_name
        exp_dir.mkdir(parents=True)
    else:
        exp_name = exp_dir.name
    brief_path = exp_dir / "brief.md"
    new_brief = not brief_path.exists()
    if new_brief:
        brief_path.write_text(
            templates.BRIEF_TEMPLATE.replace("{name}", exp_name), encoding="utf-8")
    (exp_dir / "cases").mkdir(exist_ok=True)
    (exp_dir / "harnesses").mkdir(exist_ok=True)

    print(f"实验:{exp_name}")
    print(f"  {exp_dir}")
    print(f"    brief.md       —— 人写的实验意图({'已建模板,去填' if new_brief else '已在'})")
    print(f"    harnesses/     —— 外层 agent 在此放 harness variant 文件")
    print(f"    cases/         —— 外层 agent 在此放 case 文件")
    print()
    if (exp_dir / "program.md").exists():
        print(f"  program.md 已起草 —— 下一步:ahl review {args.name}")
    else:
        print("  下一步:")
        print(f"    1. 填好 brief.md(human-owned,外层 agent 不要改它)")
        print(f"    2. 让外层 coding agent(Claude Code / Cursor / Codex)据 brief.md 起草:")
        print(f"       program.md、harnesses/V*.md、cases/D*.md、rubric.md、simulator.md")
        print(f"       agent 读 docs/agent-authoring-guide.md;格式以 docs/file-formats.md 为准")
        print(f"    3. 跑 ahl review {args.name}  —— 出 review.md(可多次跑,缺什么标未起草)")
        print(f"    4. 通过后:ahl run {args.name}")
    return 0


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
    if not (result.missing or result.broken or result.skipped or result.warnings):
        print(f"  齐了 —— 没问题就 ahl run {args.experiment}")
    else:
        print(f"  让外层 coding agent 据 brief.md + docs/agent-authoring-guide.md "
              f"起草 / 修正,再跑 ahl review {args.experiment}")
    return 0


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

    p_init = sub.add_parser("init", help="初始化工作目录(connect.md + goal.md + experiments/)")
    p_init.set_defaults(func=cmd_init)

    p_connect = sub.add_parser("connect", help="读接入配置 connect.md 并检查")
    p_connect.set_defaults(func=cmd_connect)

    p_new = sub.add_parser("new", help="新建实验,生成 program.md / rubric.md 模板 + cases/ harnesses/")
    p_new.add_argument("name", help="实验名,会建成 experiments/<编号-名字>/")
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

    p_draft = sub.add_parser("draft",
                              help="为外层 coding agent 开一个 authoring workspace(V2):建实验目录 + brief.md")
    p_draft.add_argument("name", help="实验名;建成 experiments/<编号-名字>/")
    p_draft.set_defaults(func=cmd_draft)

    p_review = sub.add_parser("review",
                               help="读实验里现有文件出 review.md(宽松,缺什么标未起草;V2)")
    p_review.add_argument("experiment", help="实验编号或名字")
    p_review.set_defaults(func=cmd_review)

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
