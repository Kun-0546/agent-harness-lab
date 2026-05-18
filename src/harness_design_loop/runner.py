"""跑 —— 让被测 agent 过一遍测试集,产出多轮对话。

外部命令行接入:起一个 agent 子进程,多轮交换 JSON。
turn 0 发起始输入,之后模拟器现生用户话,到 max_turns 或模拟器收尾。
真 agent 的逐轮超时、按版本起不同环境,随后做。
"""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

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


def command_of(connect: Connect) -> str:
    """从外部命令行接入配置里取要跑的命令。"""
    for line in connect.config.splitlines():
        s = line.strip()
        for sep in ("：", ":"):
            if s.startswith("命令") and sep in s:
                return s.split(sep, 1)[1].strip()
    for line in connect.config.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _child_env() -> dict[str, str]:
    """子进程环境:强制 UTF-8,免得中文在 Windows 上炸。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_agent_session(command: str, opening: str, simulator: Simulator,
                      max_turns: int) -> list:
    """起一个 agent 子进程,多轮跑,返回 transcript。"""
    proc = subprocess.Popen(
        command,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_child_env(),
    )
    transcript: list = []
    try:
        user_turn: str | None = opening
        for i in range(max(1, max_turns)):
            assert proc.stdin and proc.stdout
            proc.stdin.write(json.dumps({"input": user_turn}, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                err = proc.stderr.read().strip()[:200] if proc.stderr else ""
                raise RuntimeError(f"agent 没回话:{err}")
            agent_resp = str(json.loads(line).get("response", ""))
            transcript.append({"turn": i, "user": user_turn, "agent": agent_resp})
            user_turn = simulator(transcript)
            if user_turn is None:
                break
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            proc.kill()
    return transcript


def run_experiment(connect: Connect, versions: list[Version],
                   cases: list[TestCase], simulator: Simulator) -> list[CaseRun]:
    """每个版本过一遍测试集(多轮)。"""
    command = command_of(connect)
    runs: list[CaseRun] = []
    for v in versions:
        for c in cases:
            max_turns = c.max_turns or 8
            try:
                tr = run_agent_session(command, c.opening, simulator, max_turns)
                runs.append(CaseRun(v.version_id, c.case_id, transcript=tr))
            except Exception as exc:  # noqa: BLE001
                runs.append(CaseRun(v.version_id, c.case_id, error=str(exc)))
    return runs
