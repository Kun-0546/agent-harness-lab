"""模拟器 —— 模拟模式下扮用户的那个 agent。

模拟器 = experiment 里的 模拟器.md(人设 + 背景知识 + 追问策略)。
多轮 run 里,真模拟器读这份配置 + 调模型生成追问。
本期多轮 run 先用一个本地桩模拟器验代码;真模拟器随后接。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 桩模拟器出的固定追问 —— 不调模型,只为验多轮 run 的代码。
_STUB_FOLLOWUPS = [
    "这个能再具体点吗?给个数。",
    "那如果情况变了,你会怎么调整?",
]


def stub_simulator(transcript: list[dict]) -> str | None:
    """桩模拟器:看着到目前的对话,出下一句用户话;返回 None 表示对话结束。

    transcript: [{turn, user, agent}, ...]。turn 0 是起始输入,之后才算追问。
    """
    asked = max(0, len(transcript) - 1)
    if asked < len(_STUB_FOLLOWUPS):
        return _STUB_FOLLOWUPS[asked]
    return None


def _split_sections(text: str) -> dict[str, str]:
    """按 '## ' 标题把 markdown 切成 {标题: 正文}。"""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


@dataclass
class Simulator:
    """一个实验的模拟器配置。"""

    path: Path
    persona: str = ""        # 人设
    background: str = ""     # 背景知识
    strategy: str = ""       # 追问策略

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        for name, val in (("人设", self.persona), ("追问策略", self.strategy)):
            t = val.strip()
            if not t or (t.startswith("<") and t.endswith(">")):
                problems.append(f"没写{name}")
        return problems


def parse_simulator(path: str | Path) -> Simulator:
    """读 模拟器.md,解析成 Simulator。"""
    path = Path(path)
    sec = _split_sections(path.read_text(encoding="utf-8"))
    return Simulator(
        path=path,
        persona=sec.get("人设", "").strip(),
        background=sec.get("背景知识", "").strip(),
        strategy=sec.get("追问策略", "").strip(),
    )
