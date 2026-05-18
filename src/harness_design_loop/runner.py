"""跑 —— 让被测 agent 过一遍测试集,产出多轮对话。

接入方式(怎么连 agent)由 connect 配置定,见 agentconn.py。
turn 0 发起始输入,之后模拟器现生用户话,到 max_turns 或模拟器收尾。
真 agent 的逐轮超时、按版本起不同环境,随后做。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from harness_design_loop.agentconn import open_session
from harness_design_loop.connect import Connect
from harness_design_loop.testset import TestCase
from harness_design_loop.version import Version

# 模拟器:看着 transcript,出下一句用户话,或 None 收尾。
Simulator = Callable[[list], "str | None"]


@dataclass
class CaseRun:
    """一个版本跑一个 case 的结果(多轮对话)。"""

    version_id: str
    case_id: str
    transcript: list = field(default_factory=list)   # [{turn, user, agent}, ...]
    error: str = ""


def run_agent_session(connect: Connect, opening: str, simulator: Simulator,
                      max_turns: int) -> list:
    """开一个 agent 会话,多轮跑,返回 transcript。"""
    session = open_session(connect)
    transcript: list = []
    try:
        user_turn: str | None = opening
        for i in range(max(1, max_turns)):
            agent_resp = session.send(user_turn)
            transcript.append({"turn": i, "user": user_turn, "agent": agent_resp})
            user_turn = simulator(transcript)
            if user_turn is None:
                break
    finally:
        session.close()
    return transcript


def run_experiment(connect: Connect, versions: list[Version],
                   cases: list[TestCase], simulator: Simulator) -> list[CaseRun]:
    """每个版本过一遍测试集(多轮)。每跑完一个 case 打一行进度。"""
    runs: list[CaseRun] = []
    total = len(versions) * len(cases)
    done = 0
    for v in versions:
        for c in cases:
            done += 1
            print(f"  [{done}/{total}] {v.version_id} / {c.case_id} …", flush=True)
            try:
                tr = run_agent_session(connect, c.opening, simulator, c.max_turns or 8)
                runs.append(CaseRun(v.version_id, c.case_id, transcript=tr))
                print(f"  [{done}/{total}] {v.version_id} / {c.case_id} ✓ {len(tr)} 轮",
                      flush=True)
            except Exception as exc:  # noqa: BLE001
                runs.append(CaseRun(v.version_id, c.case_id, error=str(exc)))
                print(f"  [{done}/{total}] {v.version_id} / {c.case_id} ✗ {exc}",
                      flush=True)
    return runs
