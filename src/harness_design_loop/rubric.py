"""读一个实验的 rubric —— 评分器的维度 + 权重。

rubric = experiments/<编号>/rubric.md。维度从实验 goal 推导。
格式见 docs/file-formats.md。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from harness_design_loop import mdutil


@dataclass
class Dimension:
    """rubric 里的一个维度。"""

    name: str
    weight: float | None = None
    description: str = ""


@dataclass
class Rubric:
    """一个实验的 rubric。"""

    path: Path
    dimensions: list[Dimension] = field(default_factory=list)

    def weight_total(self) -> float:
        return sum(d.weight for d in self.dimensions if d.weight is not None)

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        if not self.dimensions:
            problems.append("没有维度")
            return problems
        for d in self.dimensions:
            if d.weight is None:
                problems.append(f"维度「{d.name}」没写权重")
            if not mdutil.is_filled(d.description):
                problems.append(f"维度「{d.name}」没写说明")
        weights = [d.weight for d in self.dimensions if d.weight is not None]
        if weights:
            total = sum(weights)
            if not (abs(total - 1.0) < 0.01 or abs(total - 100.0) < 0.5):
                problems.append(f"权重之和 {total:g},应为 1.0 或 100")
        return problems


def parse_rubric(path: str | Path) -> Rubric:
    """读 rubric.md,解析成 Rubric。"""
    path = Path(path)
    rubric = Rubric(path=path)
    for name, body in mdutil.split_sections(path.read_text(encoding="utf-8")).items():
        dim = Dimension(name=name)
        desc: list[str] = []
        for line in body.splitlines():
            m = re.match(r"\s*权重\s*[:：]\s*(\S+)", line)
            if m and dim.weight is None:
                try:
                    dim.weight = float(m.group(1).strip().rstrip("%％"))
                except ValueError:
                    pass
            else:
                desc.append(line)
        dim.description = "\n".join(desc).strip()
        rubric.dimensions.append(dim)
    return rubric
