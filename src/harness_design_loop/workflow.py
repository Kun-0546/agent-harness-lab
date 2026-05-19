"""run / score / compare 的编排层。

cli 只管解析参数和打印;「加载 → 校验 → 跑 → 存结果」这套活儿在这里。
跑不下去的情况(校验不过、前置缺失、打分出错)抛 WorkflowError,由 cli 接住打印。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from harness_design_loop import designer, report
from harness_design_loop.brief import parse_brief
from harness_design_loop.comparator import compare_scores
from harness_design_loop.connect import parse_connect
from harness_design_loop.grader import llm_grader, score_run, stub_grader
from harness_design_loop.program import Program, parse_program
from harness_design_loop.rubric import parse_rubric
from harness_design_loop.runner import run_experiment
from harness_design_loop.simulator import (
    make_llm_simulator,
    parse_simulator,
    stub_simulator,
)
from harness_design_loop.testset import TestCase, load_testset
from harness_design_loop.version import Version, load_versions


class WorkflowError(Exception):
    """编排跑不下去 —— 消息直接给用户看,cli 接住打到 stderr。"""


@dataclass
class RunResult:
    """一次 run 的产出。"""

    out_path: Path
    total: int
    ok: int
    failed: int
    turns: int
    errors: list[tuple[str, str, str]]   # [(version_id, case_id, error), ...]


@dataclass
class ScoreResult:
    """一次 score 的产出。"""

    out_path: Path
    run_file: str
    grader_name: str
    by_version: list[tuple[str, float, int]]   # [(version_id, 平均总分, case 数), ...]


@dataclass
class CompareResult:
    """一次 compare 的产出。"""

    report_text: str
    out_path: Path


def baseline_problems(versions: list[Version], compare_mode: str) -> list[str]:
    """按对比方式查基线版本的数量。返回问题清单;空清单 = 没问题。

    对基线:必须恰好一个标了「基线」的版本。线性迭代:不要求基线(链式比)。
    """
    baselines = [v.version_id for v in versions if v.is_baseline]
    if compare_mode == "对基线":
        if len(baselines) == 0:
            return ["对比方式=对基线,但 versions/ 里没有标基线的版本(要恰好 1 个)"]
        if len(baselines) > 1:
            return [f"对比方式=对基线,但有 {len(baselines)} 个版本标了基线"
                    f"(只能 1 个):{'、'.join(baselines)}"]
    return []


def run_preflight(program: Program, versions: list[Version],
                  cases: list[TestCase]) -> list[str]:
    """run 前的聚合校验。返回带来源标注的问题清单;空清单 = 可以跑。

    把 hdl show / versions / cases 各自能查到的问题,在跑之前一次性拦下。
    最典型的是 case 段名写错(「## 初始输入」而非「## 起始输入」),起始输入
    解析成空串,run 不报错、直接把空输入发给 agent。program 没填、版本缺
    「这是什么」、基线数量不对同理 —— show 里看得到的,run 不该绕过。
    """
    problems: list[str] = []
    problems += [f"program:{p}" for p in program.validate()]
    for v in versions:
        problems += [f"版本 {v.version_id}:{p}" for p in v.validate()]
    for c in cases:
        problems += [f"case {c.case_id}:{p}" for p in c.validate()]
    problems += baseline_problems(versions, program.compare_mode)
    return problems


def run(exp_dir: Path, use_llm: bool) -> RunResult:
    """跑实验:加载 → 校验 → 每个版本过测试集 → 存对话。

    program / 版本 / case / 基线数量 / 接入配置 任一不过,都抛 WorkflowError。
    """
    program_path = exp_dir / "program.md"
    if not program_path.exists():
        raise WorkflowError(f"实验里没有 program.md:{exp_dir}")
    program = parse_program(program_path)
    try:
        versions = load_versions(exp_dir)
        cases = load_testset(exp_dir)
    except (FileNotFoundError, NotImplementedError, ValueError) as e:
        raise WorkflowError(str(e)) from e
    if not versions or not cases:
        raise WorkflowError("versions/ 或 测试集/ 是空的,没法跑")

    problems = run_preflight(program, versions, cases)
    if problems:
        raise WorkflowError(
            "跑不了,先修下面的问题(hdl show / versions / cases 可单独查):\n  - "
            + "\n  - ".join(problems))

    # 接入:版本自带的优先;没有就回退工作区根的 connect.md。
    # connect.md 在 project root,从 exp_dir 反推(experiments/<编号>/ 的上两级),
    # 不靠当前 shell 在哪。
    connect_path = exp_dir.parents[1] / "connect.md"
    connect = parse_connect(connect_path) if connect_path.exists() else None
    needs_global = [v.version_id for v in versions if v.connect is None]
    if needs_global:
        if connect is None:
            raise WorkflowError(
                f"这些版本要用全局 connect.md:{'、'.join(needs_global)}\n"
                "  但工作区根没有 connect.md(hdl init 会生成),"
                "或给这些版本各自加「类型」「配置」段")
        connect_issues = connect.validate()
        if connect_issues:
            raise WorkflowError(
                f"这些版本要用全局 connect.md:{'、'.join(needs_global)}\n"
                "  但 connect.md 有问题:\n  - " + "\n  - ".join(connect_issues))

    if use_llm:
        sim_path = exp_dir / "模拟器.md"
        if not sim_path.exists():
            raise WorkflowError(f"--llm 要 模拟器.md,实验里没有:{exp_dir}")
        try:
            simulator = make_llm_simulator(parse_simulator(sim_path))
        except RuntimeError as e:
            raise WorkflowError(str(e)) from e
        sim_name = "LLM 模拟器"
    else:
        simulator = stub_simulator
        sim_name = "本地桩模拟器"

    # 这行得在 run_experiment 之前打 —— 它后面紧跟 runner 现打的逐条进度
    print(f"实验:{exp_dir.name}  {len(versions)} 版本 × {len(cases)} case,"
          f"多轮跑({sim_name})")
    runs = run_experiment(connect, versions, cases, simulator)

    results_dir = exp_dir / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(
        json.dumps([r.__dict__ for r in runs], ensure_ascii=False, indent=2),
        encoding="utf-8")

    ok = sum(1 for r in runs if not r.error)
    turns = sum(len(r.transcript) for r in runs if not r.error)
    errors = [(r.version_id, r.case_id, r.error) for r in runs if r.error]
    return RunResult(out_path=out_path, total=len(runs), ok=ok,
                     failed=len(runs) - ok, turns=turns, errors=errors)


def score(exp_dir: Path, use_llm: bool) -> ScoreResult:
    """给最近一次 run 的对话按 rubric 打分。

    没有 rubric、rubric 校验不过、没有 run 结果、打分出错,都抛 WorkflowError。
    """
    rubric_path = exp_dir / "rubric.md"
    if not rubric_path.exists():
        raise WorkflowError(f"实验里没有 rubric.md:{exp_dir}")
    results_dir = exp_dir / "results"
    run_files = sorted(results_dir.glob("run-*.json")) if results_dir.exists() else []
    if not run_files:
        raise WorkflowError("还没有 run 结果,先 hdl run")
    run_file = run_files[-1]

    rubric = parse_rubric(rubric_path)
    rubric_problems = rubric.validate()
    if rubric_problems:
        raise WorkflowError(
            "rubric 有问题,先修(hdl rubric 可单独查):\n  - "
            + "\n  - ".join(rubric_problems))
    runs = json.loads(run_file.read_text(encoding="utf-8"))

    if use_llm:
        missing = [v for v in ("HDL_JUDGE_BASE_URL", "HDL_JUDGE_MODEL", "HDL_JUDGE_API_KEY")
                   if not os.environ.get(v)]
        if missing:
            raise WorkflowError(f"--llm 要先设环境变量:{'、'.join(missing)}")
        grader = llm_grader
        grader_name = f"LLM Judge({os.environ.get('HDL_JUDGE_MODEL')})"
    else:
        grader = stub_grader
        grader_name = "本地桩(未接真模型)"

    try:
        scores = score_run(rubric, runs, grader)
    except Exception as e:  # noqa: BLE001
        raise WorkflowError(f"打分出错:{e}") from e
    if not scores:
        raise WorkflowError("没有可打分的对话(run 结果全是错误?)")

    out_path = results_dir / f"score-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps({
        "run": run_file.name,
        "rubric": "rubric.md",
        "grader": grader_name,
        "scores": [s.__dict__ for s in scores],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    by_version: dict[str, list[float]] = {}
    for s in scores:
        by_version.setdefault(s.version_id, []).append(s.total)
    summary = [(vid, sum(totals) / len(totals), len(totals))
               for vid, totals in by_version.items()]
    return ScoreResult(out_path=out_path, run_file=run_file.name,
                       grader_name=grader_name, by_version=summary)


def compare(exp_dir: Path) -> CompareResult:
    """把最近一次 score 的各版本分数放一起比,产出对比报告。

    没有 score 结果、分数为空、基线数量不对,都抛 WorkflowError。
    """
    results_dir = exp_dir / "results"
    score_files = sorted(results_dir.glob("score-*.json")) if results_dir.exists() else []
    if not score_files:
        raise WorkflowError("还没有 score 结果,先 hdl score")
    score_file = score_files[-1]
    data = json.loads(score_file.read_text(encoding="utf-8"))
    scores = data.get("scores", [])
    if not scores:
        raise WorkflowError("score 文件里没有分数")

    try:
        versions = load_versions(exp_dir)
    except FileNotFoundError:
        versions = []
    program_path = exp_dir / "program.md"
    mode = parse_program(program_path).compare_mode if program_path.exists() else "对基线"
    bproblems = baseline_problems(versions, mode)
    if bproblems:
        raise WorkflowError("compare 跑不了:\n  - " + "\n  - ".join(bproblems))
    baseline_id = next((v.version_id for v in versions if v.is_baseline), "")
    comparison = compare_scores(scores, baseline_id, mode)
    report_text = report.build_compare_report(
        exp_dir.name, score_file.name, data.get("grader", "?"), baseline_id, comparison)

    out_path = results_dir / f"compare-{time.strftime('%Y%m%d-%H%M%S')}.md"
    out_path.write_text(report_text + "\n", encoding="utf-8")
    return CompareResult(report_text=report_text, out_path=out_path)


@dataclass
class DraftResult:
    """一次 draft 的产出。"""

    review_path: Path
    files: list[str]   # 起草出的文件(相对实验目录)


def _build_review(exp_name, brief, program, versions, cases, rubric) -> str:
    """拼 review.md —— 人只看这一份就能审完 Designer 起草的实验。"""
    lines = [f"# review — {exp_name}", "",
             f"- 实验目标:{program.assumption or '(空)'}"]
    for v in versions:
        tag = "(基线)" if v.is_baseline else ""
        what = v.what.splitlines()[0] if v.what.strip() else "(空)"
        lines.append(f"- {v.version_id}{tag}:{what}")
    dims = "、".join(f"{d.name} {d.weight:g}" for d in rubric.dimensions
                     if d.weight is not None)
    lines.append(f"- rubric:{dims or '(空)'}")
    lines.append(f"- 红线(来自 brief):{brief.redlines}")
    lines.append(f"- 测试集:{len(cases)} 个 case")
    for c in cases:
        first = c.opening.splitlines()[0] if c.opening.strip() else "(空)"
        if len(first) > 50:
            first = first[:50] + "…"
        lines.append(f"  - {c.case_id}:{first}")
    lines.append("- 来源:program / versions / 测试集 / rubric / 模拟器 "
                 "都是 Designer 起草、待你确认。")
    lines += ["", "重点核 rubric 和红线 —— 它们是锚点;要改就直接改对应文件。"]
    return "\n".join(lines) + "\n"


def _clear_drafted(exp_dir: Path) -> None:
    """清掉上一轮 draft 起草的文件 —— 让 --force 重起草是干净的。

    program / rubric / 模拟器 / review 直接删;versions/ 测试集/ 里清掉所有
    .md(上一轮可能起草了 D-01..D-03,这轮只出 D-01,旧的留着会被 run 读进去)。
    brief.md(人写的)和 results/(跑出来的)不动。
    """
    for name in ("program.md", "rubric.md", "模拟器.md", "review.md"):
        (exp_dir / name).unlink(missing_ok=True)
    for sub in ("versions", "测试集"):
        sub_dir = exp_dir / sub
        if sub_dir.is_dir():
            for md in sub_dir.glob("*.md"):
                md.unlink()


def draft(exp_dir: Path, use_llm: bool) -> DraftResult:
    """据 brief.md 让 Designer 起草整套实验定义(V2 的 agent-drafted 入口)。

    读 brief + goal → Designer 起草 → 落盘 → 校验产物真能跑 → 出 review.md。
    brief 没填全、Designer 失败、起草的实验过不了校验,都抛 WorkflowError。
    """
    brief_path = exp_dir / "brief.md"
    if not brief_path.exists():
        raise WorkflowError(f"实验里没有 brief.md:{exp_dir}")
    brief = parse_brief(brief_path)
    brief_problems = brief.validate()
    if brief_problems:
        raise WorkflowError(
            "brief.md 没填全,Designer 起草不了:\n  - " + "\n  - ".join(brief_problems))

    goal_path = exp_dir.parents[1] / "goal.md"
    goal = goal_path.read_text(encoding="utf-8") if goal_path.exists() else ""

    try:
        pkg = designer.design(brief, goal, use_llm)
    except designer.DesignerError as e:
        raise WorkflowError(str(e)) from e

    # 落盘前清掉上一轮草案 —— 不然旧 case / 旧版本会残留、被 run 读进去。
    # 首次起草没什么可清;--force 重起草时把上一轮清干净。
    # 放在 design 成功之后:Designer 调模型失败时不动原有草案。
    _clear_drafted(exp_dir)

    # 落盘
    (exp_dir / "测试集").mkdir(exist_ok=True)
    (exp_dir / "versions").mkdir(exist_ok=True)
    (exp_dir / "program.md").write_text(pkg.program, encoding="utf-8")
    (exp_dir / "rubric.md").write_text(pkg.rubric, encoding="utf-8")
    (exp_dir / "模拟器.md").write_text(pkg.simulator, encoding="utf-8")
    written = ["program.md", "rubric.md", "模拟器.md"]
    for fname, content in pkg.versions.items():
        (exp_dir / "versions" / fname).write_text(content, encoding="utf-8")
        written.append(f"versions/{fname}")
    for fname, content in pkg.cases.items():
        (exp_dir / "测试集" / fname).write_text(content, encoding="utf-8")
        written.append(f"测试集/{fname}")

    # 校验:Designer 起草的实验得真能跑(program / 版本 / case / 基线 / rubric / 模拟器)
    try:
        program = parse_program(exp_dir / "program.md")
        versions = load_versions(exp_dir)
        cases = load_testset(exp_dir)
    except (FileNotFoundError, NotImplementedError, ValueError) as e:
        raise WorkflowError(f"Designer 起草的实验解析不了:{e}") from e
    rubric = parse_rubric(exp_dir / "rubric.md")
    problems = run_preflight(program, versions, cases)
    problems += [f"rubric:{p}" for p in rubric.validate()]
    problems += [f"模拟器:{p}" for p in parse_simulator(exp_dir / "模拟器.md").validate()]
    if problems:
        raise WorkflowError(
            "Designer 起草的实验没过校验,别用(改 brief 后 hdl draft --force 重来):\n  - "
            + "\n  - ".join(problems))

    review_path = exp_dir / "review.md"
    review_path.write_text(
        _build_review(exp_dir.name, brief, program, versions, cases, rubric),
        encoding="utf-8")
    return DraftResult(review_path=review_path, files=written)
