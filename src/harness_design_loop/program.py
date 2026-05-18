"""解析一个实验的 program.md。

program 是 PM 交给 coding agent 的实验指令。格式见 docs/file-formats.md。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from harness_design_loop import mdutil

# 声明 里已知的几项,按规范顺序。
KNOWN_DECLARATIONS = ["环境", "对话模式", "状态", "评分", "运行模式"]

# 对比方式:多版本 compare 怎么算 delta。program 里可选声明,默认「对基线」。
COMPARE_MODES = ["对基线", "线性迭代"]

# 每项声明目前在工具里的状态 —— hdl show 如实标出来,不让「检查:通过」给假安心。
DECLARATION_STATUS = {
    "环境": "暂未接线",
    "对话模式": "生效",
    "状态": "暂未接线",
    "评分": "描述用,实际评分器由 score --llm 定",
    "运行模式": "暂未接线",
    "对比方式": "生效",
}


@dataclass
class Program:
    """一个实验的 program。"""

    path: Path
    title: str = ""
    assumption: str = ""                                        # 假设
    declarations: dict[str, str] = field(default_factory=dict)  # 声明
    keep_discard: str = ""                                      # 留/丢规则
    call_human: str = ""                                        # 喊人规则

    @property
    def run_mode(self) -> str:
        return self.declarations.get("运行模式", "").strip()

    @property
    def compare_mode(self) -> str:
        """对比方式;空值、占位符、非法值一律落「对基线」。

        非法声明由 validate() 单独报问题;这个属性只保证 compare 拿到合法值,
        不让模板占位符这类脏值进对比报告。
        """
        raw = self.declarations.get("对比方式", "").strip()
        return raw if raw in COMPARE_MODES else "对基线"

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        if not mdutil.is_filled(self.assumption):
            problems.append("假设 没填")
        for key in KNOWN_DECLARATIONS:
            if key not in self.declarations:
                problems.append(f"声明 缺「{key}」")
            elif not mdutil.is_filled(self.declarations[key]):
                problems.append(f"声明「{key}」没填")
        mode = self.run_mode
        if mdutil.is_filled(mode) and mode not in ("人评", "自迭代"):
            problems.append(f"运行模式「{mode}」未知(应为 人评 或 自迭代)")
        if mode == "自迭代":
            if not mdutil.is_filled(self.keep_discard):
                problems.append("运行模式=自迭代,但 留/丢规则 没填")
            if not mdutil.is_filled(self.call_human):
                problems.append("运行模式=自迭代,但 喊人规则 没填")
        cmp_raw = self.declarations.get("对比方式", "").strip()
        if cmp_raw and not mdutil.is_filled(cmp_raw):
            problems.append(
                f"对比方式 还是模板占位符没填(可不写;要填就填 {' 或 '.join(COMPARE_MODES)})")
        elif mdutil.is_filled(cmp_raw) and cmp_raw not in COMPARE_MODES:
            problems.append(f"对比方式「{cmp_raw}」未知(应为 {' / '.join(COMPARE_MODES)})")
        return problems


def _parse_declarations(body: str) -> dict[str, str]:
    """从 声明 段里解析 '- 键:值' 行(中英文冒号都认)。"""
    decls: dict[str, str] = {}
    for raw in body.splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        item = line[1:].strip()
        m = re.match(r"([^:：]+)[:：](.*)", item)
        if m:
            decls[m.group(1).strip()] = m.group(2).strip()
    return decls


def parse_program(path: str | Path) -> Program:
    """读 program.md,解析成 Program。"""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    prog = Program(path=path)
    for line in text.splitlines():
        if line.startswith("# "):
            prog.title = line[2:].strip()
            break
    sections = mdutil.split_sections(text)
    prog.assumption = sections.get("假设", "").strip()
    prog.keep_discard = sections.get("留/丢规则", "").strip()
    prog.call_human = sections.get("喊人规则", "").strip()
    prog.declarations = _parse_declarations(sections.get("声明", ""))
    return prog
