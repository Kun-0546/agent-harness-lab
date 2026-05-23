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

from agent_harness_lab import report
from agent_harness_lab.brief import parse_brief
from agent_harness_lab.comparator import compare_scores
from agent_harness_lab.connect import parse_connect
from agent_harness_lab.grader import llm_grader, score_run, stub_grader
from agent_harness_lab.materialize import MaterializeContext
from agent_harness_lab.program import Program, parse_program
from agent_harness_lab.rubric import parse_rubric
from agent_harness_lab.runner import run_experiment
from agent_harness_lab.runtime_source import (
    parse_runtime_sources,
    validate_variant_source_refs,
)
from agent_harness_lab.simulator import (
    make_llm_simulator,
    parse_simulator,
    stub_simulator,
)
from agent_harness_lab.testset import TestCase, load_testset
from agent_harness_lab.version import Version, load_versions


class WorkflowError(Exception):
    """编排跑不下去 —— 消息直接给用户看,cli 接住打到 stderr。"""


def _load_json(path: Path):
    """读 + 解 JSON —— IO / 编码 / JSON 异常由 _safe_call 翻译。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_call(label: str, fn, *args):
    """把 parse / load 函数的 IO / 编码 / 解析异常统一翻成 WorkflowError。

    解决 dogfood 暴露的 P0:run / score / compare 遇到 corrupt 文件直接吐
    Python traceback —— cli.cmd_* 只 catch WorkflowError,parse_* 抛的
    UnicodeDecodeError / JSONDecodeError 不被它们接住,会冒到 main 变 traceback。
    在 workflow 层统一翻译,给用户看友好消息(如「program.md 读取失败:不是合法 UTF-8」)。
    """
    try:
        return fn(*args)
    except UnicodeDecodeError as e:
        raise WorkflowError(
            f"{label} 读取失败:不是合法 UTF-8(位置 {e.start})") from e
    except FileNotFoundError as e:
        # legacy detection(load_versions / load_testset 发现旧目录时抛的)带详细消息
        # —— 这种要原样透传给用户,不能被吞成 "<label> 找不到"
        msg = str(e)
        if "请改名为" in msg:
            raise WorkflowError(msg) from None
        raise WorkflowError(f"{label} 找不到") from None
    except json.JSONDecodeError as e:
        raise WorkflowError(
            f"{label} JSON 解析失败:{e.msg}(行 {e.lineno} 列 {e.colno})") from e
    except (ValueError, NotImplementedError) as e:
        raise WorkflowError(f"{label} 解析失败:{e}") from e


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


@dataclass
class ReviewResult:
    """一次 review 的产出。"""

    out_path: Path
    missing: list[str]   # 未起草的产物 —— 文件不存在
    broken: list[str]    # parse 失败的产物 —— 文件存在但读不出来,格式 "name(解析失败:msg)"
    skipped: list[str]   # 未检查的产物 —— 自己没坏,但依赖的文件坏了(如 cases 依赖 program 读对话模式)
    warnings: list[str]  # validate() 校验提醒 —— brief 未填全、rubric 权重错、case 缺起始输入 等


def baseline_problems(versions: list[Version], compare_mode: str) -> list[str]:
    """按对比方式查基线版本的数量。返回问题清单;空清单 = 没问题。

    对基线:必须恰好一个标了「基线」的版本。线性迭代:不要求基线(链式比)。
    """
    baselines = [v.version_id for v in versions if v.is_baseline]
    if compare_mode == "对基线":
        if len(baselines) == 0:
            return ["对比方式=对基线,但 harnesses/ 里没有标基线的 harness variant(要恰好 1 个)"]
        if len(baselines) > 1:
            return [f"对比方式=对基线,但有 {len(baselines)} 个版本标了基线"
                    f"(只能 1 个):{'、'.join(baselines)}"]
    return []


def run_preflight(program: Program, versions: list[Version],
                  cases: list[TestCase]) -> list[str]:
    """run 前的聚合校验。返回带来源标注的问题清单;空清单 = 可以跑。

    把 ahl show / harnesses / cases 各自能查到的问题,在跑之前一次性拦下。
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
    """跑实验:加载 → 校验 → 每个 harness variant 过 cases → 存对话。

    program / 版本 / case / 基线数量 / 接入配置 任一不过,都抛 WorkflowError。

    C3 加 Runtime Materialization preflight:
    - parse workspace 根的 runtime-sources.md (不存在返回空 list)
    - cross-validate variant.runtime_source 引用是否都在 sources 里
    - C3 只支持 legacy (无 runtime_source);写了 runtime_source 的 variant
      hard fail("adapter 还没实现",留 C4-C5)
    - 构造 MaterializeContext 传给 runner;runner 通过 adapter dispatch
    """
    program_path = exp_dir / "program.md"
    if not program_path.exists():
        raise WorkflowError(f"实验里没有 program.md:{exp_dir}")
    program = _safe_call("program.md", parse_program, program_path)
    versions = _safe_call("harnesses/", load_versions, exp_dir)
    cases = _safe_call("cases/", load_testset, exp_dir)
    if not versions or not cases:
        raise WorkflowError("harnesses/ 或 cases/ 是空的,没法跑")

    problems = run_preflight(program, versions, cases)
    if problems:
        raise WorkflowError(
            "跑不了,先修下面的问题(ahl show / harnesses / cases 可单独查):\n  - "
            + "\n  - ".join(problems))

    # 接入:版本自带的优先;没有就回退工作区根的 connect.md。
    # connect.md 在 project root,从 exp_dir 反推(experiments/<编号>/ 的上两级),
    # 不靠当前 shell 在哪。
    workspace_root = exp_dir.parents[1]
    connect_path = workspace_root / "connect.md"
    connect = parse_connect(connect_path) if connect_path.exists() else None

    # === C3:Runtime Materialization preflight ===
    # parse 错误(unknown type / duplicate / unknown field)由 _safe_call 翻成
    # WorkflowError "runtime-sources.md 解析失败:..."
    sources_path = workspace_root / "runtime-sources.md"
    runtime_sources = _safe_call(
        "runtime-sources.md", parse_runtime_sources, sources_path)

    # variant.runtime_source 引用必须在 sources 里(legacy None 跳过)
    ref_problems = validate_variant_source_refs(
        [(v.version_id, v.runtime_source) for v in versions],
        runtime_sources,
    )
    if ref_problems:
        raise WorkflowError(
            "runtime_source 引用有问题:\n  - " + "\n  - ".join(ref_problems))

    # C3 只支持 legacy(无 runtime_source);写了的 → hard fail
    unsupported = [
        f"版本 {v.version_id}:写了 runtime_source={v.runtime_source!r},"
        f"但 materialize adapter 还没实现 (留 C4-C5;当前 C3 只支持 legacy)"
        for v in versions if v.runtime_source is not None
    ]
    if unsupported:
        raise WorkflowError(
            "runtime_source path not implemented yet:\n  - "
            + "\n  - ".join(unsupported))

    # Legacy connect fallback 校验:无 runtime_source + 无 variant.connect → 要全局 connect.md
    needs_global = [v.version_id for v in versions
                    if v.connect is None and v.runtime_source is None]
    if needs_global:
        if connect is None:
            raise WorkflowError(
                f"这些版本要用全局 connect.md:{'、'.join(needs_global)}\n"
                "  但工作区根没有 connect.md(ahl init 会生成),"
                "或给这些版本各自加「类型」「配置」段")
        connect_issues = connect.validate()
        if connect_issues:
            raise WorkflowError(
                f"这些版本要用全局 connect.md:{'、'.join(needs_global)}\n"
                "  但 connect.md 有问题:\n  - " + "\n  - ".join(connect_issues))

    if use_llm:
        sim_path = exp_dir / "simulator.md"
        if not sim_path.exists():
            if (exp_dir / "模拟器.md").exists():
                raise WorkflowError(
                    f"--llm 要 simulator.md,发现旧文件 模拟器.md,"
                    f"请改名为 simulator.md(Phase 2 命名同步):{exp_dir}")
            raise WorkflowError(f"--llm 要 simulator.md,实验里没有:{exp_dir}")
        parsed_sim = _safe_call("simulator.md", parse_simulator, sim_path)
        try:
            simulator = make_llm_simulator(parsed_sim)
        except RuntimeError as e:
            raise WorkflowError(str(e)) from e
        sim_name = "LLM 模拟器"
    else:
        simulator = stub_simulator
        sim_name = "本地桩模拟器"

    # 这行得在 run_experiment 之前打 —— 它后面紧跟 runner 现打的逐条进度
    print(f"实验:{exp_dir.name}  {len(versions)} 版本 × {len(cases)} case,"
          f"多轮跑({sim_name})")

    # C3:构造 ctx 传给 runner;adapter dispatch 在 runner 里。
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    ctx = MaterializeContext(
        run_id=run_id,
        experiment_dir=exp_dir,
        fallback_connect=connect,
        runtime_sources=runtime_sources,
    )
    runs = run_experiment(versions, cases, simulator, ctx)

    results_dir = exp_dir / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / f"{run_id}.json"
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
        raise WorkflowError("还没有 run 结果,先 ahl run")
    run_file = run_files[-1]

    rubric = _safe_call("rubric.md", parse_rubric, rubric_path)
    rubric_problems = rubric.validate()
    if rubric_problems:
        raise WorkflowError(
            "rubric 有问题,先修(ahl rubric 可单独查):\n  - "
            + "\n  - ".join(rubric_problems))
    runs = _safe_call(f"results/{run_file.name}", _load_json, run_file)

    if use_llm:
        missing = [v for v in ("AHL_JUDGE_BASE_URL", "AHL_JUDGE_MODEL", "AHL_JUDGE_API_KEY")
                   if not os.environ.get(v)]
        if missing:
            raise WorkflowError(f"--llm 要先设环境变量:{'、'.join(missing)}")
        grader = llm_grader
        grader_name = f"LLM Judge({os.environ.get('AHL_JUDGE_MODEL')})"
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
        raise WorkflowError("还没有 score 结果,先 ahl score")
    score_file = score_files[-1]
    data = _safe_call(f"results/{score_file.name}", _load_json, score_file)
    scores = data.get("scores", [])
    if not scores:
        raise WorkflowError("score 文件里没有分数")

    if (exp_dir / "harnesses").is_dir():
        versions = _safe_call("harnesses/", load_versions, exp_dir)
    else:
        versions = []
    program_path = exp_dir / "program.md"
    if program_path.exists():
        mode = _safe_call("program.md", parse_program, program_path).compare_mode
    else:
        mode = "对基线"
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


def review(exp_dir: Path) -> ReviewResult:
    """读实验里现有文件,出 review.md。

    宽松 —— 三态:文件不存在 = 未起草、parse 失败 = 解析失败:<msg>、
    parse 通过 = ok(ok 后再跑 validate(),问题作为「校验提醒」内联展示)。
    不抛错。review 是 authoring loop 里的状态快照,外层 agent 边 author
    边跑 review 看进度。硬关卡是 ahl run 的 preflight,不在这里。
    """
    if not exp_dir.exists():
        raise WorkflowError(f"找不到实验:{exp_dir}")

    def _piece(parse, path: Path) -> tuple:
        """返回 (object_or_None, status):ok / 未起草 / 解析失败:<msg>。"""
        if not path.exists():
            return None, "未起草"
        try:
            return parse(path), "ok"
        except Exception as e:  # noqa: BLE001
            return None, f"解析失败:{e!s}"

    def _dir_piece(loader) -> tuple:
        """harnesses/ 和 cases/ —— 目录粒度,整体一个 status。"""
        try:
            items = loader(exp_dir)
            return items, ("ok" if items else "未起草")
        except FileNotFoundError:
            return [], "未起草"
        except (NotImplementedError, ValueError) as e:
            return [], f"解析失败:{e!s}"

    brief = _piece(parse_brief, exp_dir / "brief.md")
    program = _piece(parse_program, exp_dir / "program.md")
    rubric = _piece(parse_rubric, exp_dir / "rubric.md")
    simulator = _piece(parse_simulator, exp_dir / "simulator.md")
    versions = _dir_piece(load_versions)
    # P1.a:cases 依赖 program 的「对话模式」—— program 解析失败时不要 cascade
    # 调 load_testset(那会让 cases 也被误标「解析失败」),改成「未检查」单独 surface。
    if program[1].startswith("解析失败"):
        cases = ([], f"未检查:program.md {program[1]}")
    else:
        cases = _dir_piece(load_testset)

    missing: list[str] = []
    broken: list[str] = []
    skipped: list[str] = []
    for name, (_obj, state) in (
        ("brief.md", brief), ("program.md", program),
        ("harnesses/", versions), ("cases/", cases),
        ("rubric.md", rubric), ("simulator.md", simulator),
    ):
        if state == "未起草":
            missing.append(name)
        elif state.startswith("未检查"):
            skipped.append(f"{name}({state})")
        elif state != "ok":
            broken.append(f"{name}({state})")

    # P1.b:收集 validate() 校验提醒 —— cli summary 用它判要不要说「齐了」。
    # parse 成功才跑 validate;未起草 / 解析失败 / 未检查 的产物不再调 validate。
    warnings: list[str] = []
    for name, (obj, state) in (
        ("brief.md", brief), ("program.md", program),
        ("rubric.md", rubric), ("simulator.md", simulator),
    ):
        if obj is not None and state == "ok":
            warnings += [f"{name}:{p}" for p in obj.validate()]
    if versions[1] == "ok":
        for v in versions[0]:
            warnings += [f"版本 {v.version_id}:{p}" for p in v.validate()]
    if cases[1] == "ok":
        for c in cases[0]:
            warnings += [f"case {c.case_id}:{p}" for p in c.validate()]

    text = _build_review(exp_dir.name, brief, program, versions, cases,
                          rubric, simulator)
    out_path = exp_dir / "review.md"
    out_path.write_text(text, encoding="utf-8")
    return ReviewResult(out_path=out_path, missing=missing, broken=broken,
                        skipped=skipped, warnings=warnings)


def _build_review(exp_name, brief, program, versions, cases, rubric, simulator) -> str:
    """拼 review.md —— 人审入口,外层 agent 起草的实验一页看完。

    每条产物三态:ok / 未起草 / 解析失败:<msg>。ok 时再跑 validate(),
    校验问题作为「⚠ 校验」内联展示。参数都是 (obj, state) 元组。
    """
    lines = [f"# review — {exp_name}", ""]

    # 实验目标(来自 program 假设)
    p_obj, p_state = program
    if p_state == "未起草":
        lines.append("- 实验目标:**program.md 未起草**")
    elif p_state != "ok":
        lines.append(f"- 实验目标:**program.md {p_state}**")
    else:
        problems = p_obj.validate()
        warn = f"  ⚠ 校验:{'、'.join(problems)}" if problems else ""
        if p_obj.assumption:
            lines.append(f"- 实验目标:{p_obj.assumption}{warn}")
        else:
            lines.append(f"- 实验目标:(program.md 的「假设」段为空){warn}")

    # harness variants
    v_list, v_state = versions
    if v_state == "未起草":
        lines.append("- harnesses:**harnesses/ 未起草**")
    elif v_state != "ok":
        lines.append(f"- harnesses:**harnesses/ {v_state}**")
    else:
        for v in v_list:
            tag = "(基线)" if v.is_baseline else ""
            what = v.what.splitlines()[0] if v.what.strip() else "(空)"
            problems = v.validate()
            warn = f"  ⚠ {'、'.join(problems)}" if problems else ""
            lines.append(f"- {v.version_id}{tag}:{what}{warn}")

    # rubric
    r_obj, r_state = rubric
    if r_state == "未起草":
        lines.append("- rubric:**rubric.md 未起草**")
    elif r_state != "ok":
        lines.append(f"- rubric:**rubric.md {r_state}**")
    else:
        dims = "、".join(f"{d.name} {d.weight:g}" for d in r_obj.dimensions
                         if d.weight is not None)
        problems = r_obj.validate()
        warn = f"  ⚠ 校验:{'、'.join(problems)}" if problems else ""
        lines.append(f"- rubric:{dims or '(无有效维度)'}{warn}")

    # 红线(brief)—— brief.validate() 会识别占位符 / 必填段没填
    b_obj, b_state = brief
    if b_state == "未起草":
        lines.append("- 红线(brief):**brief.md 未起草**")
    elif b_state != "ok":
        lines.append(f"- 红线(brief):**brief.md {b_state}**")
    else:
        problems = b_obj.validate()
        if problems:
            # 必填段没填、或仍是模板占位符 —— 不能把它当真红线 echo 出来
            lines.append(
                f"- 红线(brief):**brief.md 未填写完整:{'、'.join(problems)}**")
        elif b_obj.redlines:
            lines.append(f"- 红线(brief):{b_obj.redlines}")
        else:
            lines.append("- 红线(brief):(空)")

    # cases
    c_list, c_state = cases
    if c_state == "未起草":
        lines.append("- cases:**cases/ 未起草**")
    elif c_state != "ok":
        lines.append(f"- cases:**cases/ {c_state}**")
    else:
        lines.append(f"- cases:{len(c_list)} 个 case")
        for c in c_list:
            first = c.opening.splitlines()[0] if c.opening.strip() else "(空)"
            if len(first) > 50:
                first = first[:50] + "…"
            problems = c.validate()
            warn = f"  ⚠ {'、'.join(problems)}" if problems else ""
            lines.append(f"  - {c.case_id}:{first}{warn}")

    # simulator
    s_obj, s_state = simulator
    if s_state == "未起草":
        lines.append("- simulator:**simulator.md 未起草**")
    elif s_state != "ok":
        lines.append(f"- simulator:**simulator.md {s_state}**")
    else:
        persona = s_obj.persona.splitlines()[0] if s_obj.persona.strip() else "(空)"
        if len(persona) > 50:
            persona = persona[:50] + "…"
        problems = s_obj.validate()
        warn = f"  ⚠ 校验:{'、'.join(problems)}" if problems else ""
        lines.append(f"- simulator 人设:{persona}{warn}")

    # 来源 —— v2-minimal 用集中式 provenance(per-file frontmatter 留 v2.5)
    def _src(state: str, human_owned: bool = False) -> str:
        if state == "ok":
            return "human" if human_owned else "external_agent_drafted"
        return state  # 未起草 / 解析失败:<msg>

    lines += ["", "## 来源",
              f"- brief.md:{_src(brief[1], human_owned=True)}",
              f"- program.md:{_src(program[1])}",
              f"- harnesses/:{_src(versions[1])}",
              f"- cases/:{_src(cases[1])}",
              f"- rubric.md:{_src(rubric[1])}",
              f"- simulator.md:{_src(simulator[1])}"]

    lines += ["",
              "重点核 rubric 和红线 —— 它们是锚点;要改就直接改对应文件,"
              "再跑 ahl review。"]
    return "\n".join(lines) + "\n"
