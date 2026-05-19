"""读一个实验的 brief.md —— 人写的自然语言实验意图(v2)。

brief 是 V2 的入口:人写它,Designer Agent 据此起草 program 等执行文件。
格式见 docs/v2-minimal-spec.md §3。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness_design_loop import mdutil


@dataclass
class Brief:
    """一份实验 brief —— V2 里人写的意图入口。"""

    path: Path
    optimize: str = ""        # 想优化什么
    change: str = ""          # 验证什么改动
    care: str = ""            # 最在意什么
    redlines: str = ""        # 不能牺牲什么(红线)
    compare: str = ""         # 怎么比(可空,留给 Designer 定)

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。

        前四段是 Designer 起草实验的依据,必须填;「怎么比」可空。
        """
        problems: list[str] = []
        checks = (("想优化什么", self.optimize), ("验证什么改动", self.change),
                  ("最在意什么", self.care), ("不能牺牲什么", self.redlines))
        for label, value in checks:
            if not mdutil.is_filled(value):
                problems.append(f"「{label}」没填")
        return problems


def parse_brief(path: str | Path) -> Brief:
    """读 brief.md,解析成 Brief。"""
    path = Path(path)
    sections = mdutil.split_sections(path.read_text(encoding="utf-8"))
    return Brief(
        path=path,
        optimize=sections.get("想优化什么", "").strip(),
        change=sections.get("验证什么改动", "").strip(),
        care=sections.get("最在意什么", "").strip(),
        redlines=sections.get("不能牺牲什么", "").strip(),
        compare=sections.get("怎么比", "").strip(),
    )
