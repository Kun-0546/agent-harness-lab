"""Legacy (Stack A) — retained pending v1.1 PR9 retirement; the live v1 path is
user_sim.py + auto.py.

跑 —— 让被测 agent 过一遍测试集,产出多轮对话。

Lifecycle 由 workflow.run 编排(C5):
- per variant materialize / teardown 在 workflow 层做(sandbox 是 per variant,
  跨 case 复用 —— spec §2.1 sandbox.path = "sandbox/<run_id>/<variant_id>/")
- runner 只负责 per (variant, case) start session + run_agent_session + close
- LegacyAdapter materialize/teardown 是 no-op,行为等价 v0.2.0
- LocalPathAdapter (C5):materialize 一次 copy_dir + apply patch, start 起子进程
  (shell=False), teardown M1 默认 keep (C7 加 --cleanup-sandboxes flag 后才删)

turn 0 发起始输入,之后模拟器现生用户话,到 max_turns 或模拟器收尾。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agent_harness_lab.agentconn import AgentSession
from agent_harness_lab.materialize import RuntimeAdapter, Sandbox
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
    snapshot_id: str = ""                            # 对应 RuntimeSnapshot 的 id;
                                                     # legacy = "legacy",materialized = "snap-<run_id>-<variant_id>"


def run_agent_session(session: AgentSession, opening: str, simulator: Simulator,
                      max_turns: int) -> list:
    """跑 session loop:session 必须已经 open;close 在本函数 finally 调。

    签名:接已建好的 AgentSession (来自 adapter.start),不直接读 connect。
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
                   adapters_map: dict[str, RuntimeAdapter],
                   sandboxes_map: dict[str, Sandbox],
                   snapshots_map: dict[str, str]) -> list[CaseRun]:
    """跑每个 (variant, case):workflow 已 per variant materialize 完,
    runner 只 per case start session + run_agent_session + close。

    workflow.run 在调用本函数前已 per variant:
    - adapter_for(v, ctx) 选 adapter
    - adapter.materialize(v, ctx) 一次,sandbox 存 sandboxes_map (跨 case 复用)
    - build_snapshot + write_snapshot,snapshot_id 存 snapshots_map
    - finally 块在 runner 跑完后调 adapter.teardown(sandbox) per variant

    一个 case 的 exception (start 失败 / session 内 exception) catch 翻为
    CaseRun.error,继续下一个 case —— 保 v0.2.0 行为等价。
    spec §B.5 Q6 "hard fail materialize" 由 workflow 在 materialize 时抛
    WorkflowError 实现(早 fail,不到 runner)。
    """
    runs: list[CaseRun] = []
    total = len(versions) * len(cases)
    done = 0
    for v in versions:
        adapter = adapters_map[v.version_id]
        sandbox = sandboxes_map[v.version_id]
        snapshot_id = snapshots_map[v.version_id]
        for c in cases:
            done += 1
            print(f"  [{done}/{total}] {v.version_id} / {c.case_id} …", flush=True)
            try:
                session = adapter.start(sandbox)
                tr = run_agent_session(session, c.opening, simulator,
                                        c.max_turns or 8)
                runs.append(CaseRun(v.version_id, c.case_id, transcript=tr,
                                    snapshot_id=snapshot_id))
                print(f"  [{done}/{total}] {v.version_id} / {c.case_id} ✓ {len(tr)} 轮",
                      flush=True)
            except Exception as exc:  # noqa: BLE001
                runs.append(CaseRun(v.version_id, c.case_id, error=str(exc),
                                    snapshot_id=snapshot_id))
                print(f"  [{done}/{total}] {v.version_id} / {c.case_id} ✗ {exc}",
                      flush=True)
    return runs
