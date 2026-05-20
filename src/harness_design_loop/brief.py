"""读一个实验的 brief.md —— 人写的自然语言实验意图(v2)。

brief 是 V2 的入口:人写它,外层 coding agent(Claude Code / Cursor / Codex 等)
据它起草 program 等执行文件。HDL 自己不调模型起草。格式见 docs/v2-minimal-spec.md §3。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness_design_loop import mdutil
from harness_design_loop.program import COMPARE_MODES


@dataclass
class Brief:
    """一份实验 brief —— V2 里人写的意图入口。"""

    path: Path
    optimize: str = ""        # 想优化什么
    change: str = ""          # 验证什么改动
    care: str = ""            # 最在意什么
    redlines: str = ""        # 不能牺牲什么(红线)
    compare: str = ""         # 怎么比(可空;空值/占位符/非法都落「对基线」)

    @property
    def compare_mode(self) -> str:
        """怎么比;空值、占位符、非法值一律落「对基线」。

        跟 program.Program.compare_mode 同构 —— 外层 agent 据此定 program
        的「对比方式」声明。非法值另由 validate() 报问题。
        """
        return (self.compare if mdutil.is_filled(self.compare)
                and self.compare in COMPARE_MODES else "对基线")

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。

        前四段是外层 agent 起草实验的依据,必须填;「怎么比」可空,
        填了就得是 对基线 / 线性迭代。
        """
        problems: list[str] = []
        checks = (("想优化什么", self.optimize), ("验证什么改动", self.change),
                  ("最在意什么", self.care), ("不能牺牲什么", self.redlines))
        for label, value in checks:
            if not mdutil.is_filled(value):
                problems.append(f"「{label}」没填")
        if mdutil.is_filled(self.compare) and self.compare not in COMPARE_MODES:
            problems.append(
                f"「怎么比」填了「{self.compare}」,识别不了"
                f"(应为 {' / '.join(COMPARE_MODES)},或留空)")
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
