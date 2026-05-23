"""模拟器 —— 模拟模式下扮用户的那个 agent。

模拟器 = experiment 里的 simulator.md(人设 + 背景知识 + 追问策略)。
多轮 run 里,模拟器看着对话生成下一句用户话。
- stub_simulator     —— 本地桩,固定追问,验代码用。
- make_llm_simulator —— 真模拟器,调模型按 simulator.md 生成追问。
                        模型 / 端点 / key 从 AHL_SIM_* 环境变量读。
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_harness_lab import llm, mdutil

_STUB_FOLLOWUPS = [
    "这个能再具体点吗?给个数。",
    "那如果情况变了,你会怎么调整?",
]


def stub_simulator(transcript: list[dict]) -> str | None:
    """桩模拟器:不调模型,出几句固定追问,只为验多轮 run 的代码。"""
    asked = max(0, len(transcript) - 1)
    if asked < len(_STUB_FOLLOWUPS):
        return _STUB_FOLLOWUPS[asked]
    return None


@dataclass
class Simulator:
    """一个实验的模拟器配置。"""

    path: Path
    persona: str = ""        # 人设
    background: str = ""     # 背景知识
    strategy: str = ""       # 追问策略

    def validate(self) -> list[str]:
        problems: list[str] = []
        for name, val in (("人设", self.persona), ("追问策略", self.strategy)):
            if not mdutil.is_filled(val):
                problems.append(f"没写{name}")
        return problems


def parse_simulator(path: str | Path) -> Simulator:
    """读 simulator.md,解析成 Simulator。"""
    path = Path(path)
    sec = mdutil.split_sections(path.read_text(encoding="utf-8"))
    return Simulator(
        path=path,
        persona=sec.get("人设", "").strip(),
        background=sec.get("背景知识", "").strip(),
        strategy=sec.get("追问策略", "").strip(),
    )


def _transcript_text(transcript: list) -> str:
    lines = []
    for t in transcript:
        lines.append(f"[第 {t.get('turn', '?')} 轮] 用户:{t.get('user', '')}")
        lines.append(f"           agent:{t.get('agent', '')}")
    return "\n".join(lines)


def build_simulator_prompt(sim: Simulator, transcript: list) -> str:
    """拼真模拟器的 prompt —— 让模型扮用户、出下一句话。"""
    return (
        "你在一段对话里扮演用户。按下面的人设和追问策略,生成你的下一句话。\n\n"
        f"【人设】\n{sim.persona}\n\n"
        f"【背景知识】\n{sim.background or '(无)'}\n\n"
        f"【追问策略】\n{sim.strategy}\n\n"
        f"【到目前的对话】\n{_transcript_text(transcript)}\n\n"
        "只输出你(用户)的下一句话。如果对话已经聊透、该收尾了,只输出两个字:结束"
    )


def make_llm_simulator(sim: Simulator) -> Callable[[list], "str | None"]:
    """从模拟器配置造一个真模拟器函数(调模型生成追问)。"""
    base = os.environ.get("AHL_SIM_BASE_URL", "")
    model = os.environ.get("AHL_SIM_MODEL", "")
    key = os.environ.get("AHL_SIM_API_KEY", "")
    if not (base and model and key):
        raise RuntimeError(
            "没配模拟器模型 —— 设环境变量 "
            "AHL_SIM_BASE_URL / AHL_SIM_MODEL / AHL_SIM_API_KEY")

    def _sim(transcript: list) -> str | None:
        reply = llm.chat(base, model, key, build_simulator_prompt(sim, transcript)).strip()
        if reply.startswith("结束"):
            return None
        return reply

    return _sim
