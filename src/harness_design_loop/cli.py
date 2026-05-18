"""harness-design-loop 命令行入口。

这层只管:解析参数、把结果打印给用户、把活儿交给 workflow。
run / score / compare 的编排逻辑在 workflow.py。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness_design_loop import templates, workflow
from harness_design_loop.connect import parse_connect
from harness_design_loop.program import (
    DECLARATION_STATUS,
    KNOWN_DECLARATIONS,
    parse_program,
)
from harness_design_loop.rubric import parse_rubric
from harness_design_loop.simulator import parse_simulator
from harness_design_loop.testset import load_testset
from harness_design_loop.version import load_versions


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
    print(f"初始化:{root}")
    for c in created:
        print(f"  + {c}")
    print("  下一步:填 connect.md、goal.md;hdl new <实验名> 开第一个实验。")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    path = Path.cwd() / "connect.md"
    if not path.exists():
        print("当前目录没有 connect.md(先 hdl init)", file=sys.stderr)
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
    (exp_dir / "模拟器.md").write_text(templates.SIMULATOR_TEMPLATE, encoding="utf-8")
    (exp_dir / "测试集").mkdir()
    (exp_dir / "versions").mkdir()
    print(f"建好实验:{exp_name}")
    print(f"  {exp_dir}")
    print("    program.md   —— 实验指令(假设 + 声明)")
    print("    rubric.md    —— 评分维度 + 权重")
    print("    模拟器.md    —— 模拟模式下扮用户的 agent")
    print("    测试集/      —— 放 case 文件")
    print("    versions/    —— 放被测的版本文件")
    print("  下一步:填 program.md、rubric.md、模拟器.md;往 测试集/、versions/ 加文件。")
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

    print(f"实验:{exp_dir.name}  测试集:{len(cases)} 个 case")
    if not cases:
        print("(测试集是空的——往 测试集/ 加 case 文件;格式见 docs/file-formats.md)")
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

    print(f"实验:{exp_dir.name}  版本:{len(versions)} 个")
    if not versions:
        print("(versions/ 是空的——一个版本一个文件;格式见 docs/file-formats.md)")
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
        result = workflow.run(exp_dir, args.llm)
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


def cmd_simulator(args: argparse.Namespace) -> int:
    exp_dir = _find_experiment(args.experiment)
    if exp_dir is None:
        print(f"找不到实验:{args.experiment}", file=sys.stderr)
        return 1
    path = exp_dir / "模拟器.md"
    if not path.exists():
        print(f"实验里没有 模拟器.md:{exp_dir}", file=sys.stderr)
        return 1
    sim = parse_simulator(path)
    print(f"实验:{exp_dir.name}")
    print(f"模拟器:{path}")
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
        prog="hdl",
        description="AI 产品研究的实验循环。",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="初始化工作目录(connect.md + goal.md + experiments/)")
    p_init.set_defaults(func=cmd_init)

    p_connect = sub.add_parser("connect", help="读接入配置 connect.md 并检查")
    p_connect.set_defaults(func=cmd_connect)

    p_new = sub.add_parser("new", help="新建实验,生成 program.md / rubric.md 模板 + 测试集/ versions/")
    p_new.add_argument("name", help="实验名,会建成 experiments/<编号-名字>/")
    p_new.set_defaults(func=cmd_new)

    p_show = sub.add_parser("show", help="读实验的 program.md 并检查")
    p_show.add_argument("experiment", help="实验编号或名字")
    p_show.set_defaults(func=cmd_show)

    p_cases = sub.add_parser("cases", help="读实验的测试集并检查")
    p_cases.add_argument("experiment", help="实验编号或名字")
    p_cases.set_defaults(func=cmd_cases)

    p_rubric = sub.add_parser("rubric", help="读实验的 rubric 并检查")
    p_rubric.add_argument("experiment", help="实验编号或名字")
    p_rubric.set_defaults(func=cmd_rubric)

    p_simulator = sub.add_parser("simulator", help="读实验的模拟器配置并检查")
    p_simulator.add_argument("experiment", help="实验编号或名字")
    p_simulator.set_defaults(func=cmd_simulator)

    p_versions = sub.add_parser("versions", help="读实验的版本并检查")
    p_versions.add_argument("experiment", help="实验编号或名字")
    p_versions.set_defaults(func=cmd_versions)

    p_run = sub.add_parser("run", help="跑实验:每个版本过测试集,产出对话")
    p_run.add_argument("experiment", help="实验编号或名字")
    p_run.add_argument("--llm", action="store_true",
                       help="用 LLM 模拟器现生追问(先设 HDL_SIM_* 环境变量);默认用本地桩")
    p_run.set_defaults(func=cmd_run)

    p_score = sub.add_parser("score", help="给最近一次 run 的对话按 rubric 打分")
    p_score.add_argument("experiment", help="实验编号或名字")
    p_score.add_argument("--llm", action="store_true",
                         help="用 LLM Judge 真打分(先设 HDL_JUDGE_* 环境变量);默认用本地桩")
    p_score.set_defaults(func=cmd_score)

    p_compare = sub.add_parser("compare", help="把版本的分数放一起比")
    p_compare.add_argument("experiment", help="实验编号或名字")
    p_compare.set_defaults(func=cmd_compare)

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
