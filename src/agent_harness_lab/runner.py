"""跑 —— 让被测 agent 过一遍测试集,产出多轮对话。

C3 改造:接入方式不再直接读 connect,改为 adapter dispatch。
- 每个 (variant, case):adapter.materialize → start → run session loop → teardown
- LegacyAdapter (v0.2.0 兼容路径) 内部仍调 agentconn.open_session,行为等价
- materialized adapter (local_path / git_repo) 留 C4-C5

turn 0 发起始输入,之后模拟器现生用户话,到 max_turns 或模拟器收尾。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agent_harness_lab.agentconn import AgentSession
from agent_harness_lab.materialize import (
    MaterializeContext,
    adapter_for,
)
from agent_harness_lab.testset import TestCase
from agent_harness_lab.version import Version

# 模拟器:看着 transcript,出下一句用户话,或 None 收尾。
Simulator = Callable[[list], "str | None"]


@dataclass
class CaseRun:
    """一个版本跑一个 case 的结果(多轮对话)。"""

    version_id: str
    case_id: str
    transcript: list = field(default_factory=list)   # [{turn, user, agent}, ...]
    error: str = ""


def run_agent_session(session: AgentSession, opening: str, simulator: Simulator,
                      max_turns: int) -> list:
    """跑 session loop:session 必须已经 open;close 在本函数 finally 调。

    C3 签名变化:不再接 Connect,改接已建好的 AgentSession (来自 adapter.start)。
    """
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


def run_experiment(versions: list[Version], cases: list[TestCase],
                   simulator: Simulator,
                   ctx: MaterializeContext) -> list[CaseRun]:
    """每个 (variant, case) 起 sandbox 跑;adapter 处理 connect / materialize 细节。

    C3:adapter_for(v) 只返回 LegacyAdapter (workflow.preflight 已 hard fail
    runtime_source 写了但 adapter 没实现的 variant)。

    一个 case 的 exception (materialize 失败、start 失败、session 内 exception)
    都 catch 翻为 CaseRun.error,继续下一个 case —— 保 v0.2.0 行为等价。
    spec §B.5 Q6 "hard fail" 留给 materialized adapter (C4-C5);在那时,
    materialized adapter 在 preflight 抛 WorkflowError 早 fail,不到 runner。
    """
    runs: list[CaseRun] = []
    total = len(versions) * len(cases)
    done = 0
    for v in versions:
        adapter = adapter_for(v)
        for c in cases:
            done += 1
            print(f"  [{done}/{total}] {v.version_id} / {c.case_id} …", flush=True)
            try:
                sandbox = adapter.materialize(v, ctx)
                try:
                    session = adapter.start(sandbox)
                    tr = run_agent_session(session, c.opening, simulator,
                                            c.max_turns or 8)
                finally:
                    adapter.teardown(sandbox)
                runs.append(CaseRun(v.version_id, c.case_id, transcript=tr))
                print(f"  [{done}/{total}] {v.version_id} / {c.case_id} ✓ {len(tr)} 轮",
                      flush=True)
            except Exception as exc:  # noqa: BLE001
                runs.append(CaseRun(v.version_id, c.case_id, error=str(exc)))
                print(f"  [{done}/{total}] {v.version_id} / {c.case_id} ✗ {exc}",
                      flush=True)
    return runs
