"""读一个实验的 cases。

cases = experiments/<编号>/cases/ 目录,一个 case 一个文件。
一个 case 里装什么,由实验 program 声明的「对话模式」定。本模块先做「模拟」。
格式见 docs/file-formats.md。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_harness_lab import mdutil
from agent_harness_lab.program import parse_program


@dataclass
class TestCase:
    """一个测试 case(模拟模式)。"""

    __test__ = False   # 业务数据类 —— 不参与 pytest 测试收集

    path: Path
    case_id: str = ""
    type: str = ""                  # 可选的分类标签
    max_turns: int | None = None    # 对话轮次上限,可选
    depends_on: str = ""            # 可选;初始上下文来自哪个 case
    opening: str = ""               # 起始输入
    criterion: str = ""             # 完成标准,可选

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        if not self.case_id:
            problems.append("缺 id")
        if not mdutil.is_filled(self.opening):
            problems.append("起始输入 没填")
        return problems


def parse_sim_case(path: str | Path) -> TestCase:
    """解析一个「模拟」模式的 case 文件。"""
    path = Path(path)
    fields, body = mdutil.parse_frontmatter(path.read_text(encoding="utf-8"))
    sections = mdutil.split_sections(body)

    case = TestCase(path=path)
    case.case_id = fields.get("id", "").strip() or path.stem
    case.type = fields.get("type", "").strip()
    case.depends_on = fields.get("depends_on", "").strip()
    turns = fields.get("max_turns", "").strip()
    if turns.isdigit():
        case.max_turns = int(turns)
    case.opening = sections.get("起始输入", "").strip()
    case.criterion = sections.get("完成标准", "").strip()
    return case


def load_testset(experiment_dir: str | Path) -> list[TestCase]:
    """读一个实验的整套 cases。读法按实验 program 声明的「对话模式」分发。

    本期只实现「模拟」;回放 / 固定 抛 NotImplementedError。
    """
    experiment_dir = Path(experiment_dir)
    cases_dir = experiment_dir / "cases"
    if not cases_dir.exists():
        if (experiment_dir / "测试集").exists():
            raise FileNotFoundError(
                f"发现旧目录 测试集/,请改名为 cases/(Phase 2 命名同步):{experiment_dir}")
        raise FileNotFoundError(f"实验没有 cases/ 目录:{experiment_dir}")

    program_path = experiment_dir / "program.md"
    mode = ""
    if program_path.exists():
        mode = parse_program(program_path).declarations.get("对话模式", "").strip()

    if not mdutil.is_filled(mode) or mode == "模拟":
        return [parse_sim_case(p) for p in sorted(cases_dir.glob("*.md"))]
    if mode in ("回放", "固定"):
        raise NotImplementedError(f"对话模式「{mode}」的 cases 读取还没写,本期先做模拟")
    raise ValueError(f"program 里对话模式「{mode}」识别不了(应为 模拟 / 回放 / 固定)")
