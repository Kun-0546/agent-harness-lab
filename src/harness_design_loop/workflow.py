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

from harness_design_loop import report
from harness_design_loop.comparator import compare_scores
from harness_design_loop.connect import CONNECT_TYPES, parse_connect
from harness_design_loop.grader import llm_grader, score_run, stub_grader
from harness_design_loop.program import parse_program
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


def run_preflight(versions: list[Version], cases: list[TestCase]) -> list[str]:
    """run 前的聚合校验。返回带来源标注的问题清单;空清单 = 可以跑。

    专门拦那些会被静默跑过去的坏数据 —— 最典型的是 case 段名写错
    (写成「## 初始输入」而不是「## 起始输入」),起始输入解析成空串,
    run 不报错、直接把空输入发给 agent。
    """
    problems: list[str] = []
    for v in versions:
        problems += [f"版本 {v.version_id}:{p}" for p in v.validate()]
    for c in cases:
        problems += [f"case {c.case_id}:{p}" for p in c.validate()]
    return problems


def run(exp_dir: Path, use_llm: bool) -> RunResult:
    """跑实验:加载 → 校验 → 每个版本过测试集 → 存对话。

    校验不过、没有可用接入、模拟器配置缺失,都抛 WorkflowError。
    """
    try:
        versions = load_versions(exp_dir)
        cases = load_testset(exp_dir)
    except (FileNotFoundError, NotImplementedError, ValueError) as e:
        raise WorkflowError(str(e)) from e
    if not versions or not cases:
        raise WorkflowError("versions/ 或 测试集/ 是空的,没法跑")

    problems = run_preflight(versions, cases)
    if problems:
        raise WorkflowError(
            "跑不了,先修下面的问题(hdl versions / hdl cases 可单独查):\n  - "
            + "\n  - ".join(problems))

    # 全局 connect 是各版本的回退;版本自带接入的可以不靠它
    connect_path = Path.cwd() / "connect.md"
    connect = parse_connect(connect_path) if connect_path.exists() else None
    global_ok = connect is not None and connect.conn_type in CONNECT_TYPES
    no_conn = [v.version_id for v in versions if v.connect is None and not global_ok]
    if no_conn:
        raise WorkflowError(
            f"这些版本没接入配置、全局 connect.md 也用不了:{'、'.join(no_conn)}\n"
            "  给版本加「类型」「配置」段,或在 connect.md 配好全局接入")

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

    没有 score 结果、分数为空,都抛 WorkflowError。
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
    baseline_id = next((v.version_id for v in versions if v.is_baseline), "")
    program_path = exp_dir / "program.md"
    mode = parse_program(program_path).compare_mode if program_path.exists() else "对基线"
    comparison = compare_scores(scores, baseline_id, mode)
    report_text = report.build_compare_report(
        exp_dir.name, score_file.name, data.get("grader", "?"), baseline_id, comparison)

    out_path = results_dir / f"compare-{time.strftime('%Y%m%d-%H%M%S')}.md"
    out_path.write_text(report_text + "\n", encoding="utf-8")
    return CompareResult(report_text=report_text, out_path=out_path)
