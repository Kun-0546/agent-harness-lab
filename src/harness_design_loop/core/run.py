"""跑 —— 让每个版本过一遍测试集，产出对话。design §4「跑」。

core 不知道被测 agent 是谁：它只通过 open_connection 拿到 Connection 接口、
通过 driver 拿到 ConversationDriver 接口。换任何 agent，这里一行都不动。
"""
from __future__ import annotations

from collections.abc import Callable

from harness_design_loop.interfaces.connection import Connection
from harness_design_loop.interfaces.conversation import ConversationDriver
from harness_design_loop.models import Conversation
from harness_design_loop.testset import TestCase
from harness_design_loop.version import Version


def run_experiment(
    versions: list[Version],
    testset: list[TestCase],
    open_connection: Callable[[Version], Connection],
    driver: ConversationDriver,
    run_id: str = "",
) -> list[Conversation]:
    """每个版本 × 每个 case 跑一段对话。

    参数全是接口或纯数据 —— core 靠依赖注入拿到 Connection 和 driver，自己不
    解析 config、不 import 任何 adapter。这就是「通用 by construction」：
    config 怎么变成 Connection，是 core 之外的接线层的事（见 adapters/）。

    一个版本开一次 Connection；每个 case 由 driver 内部各开一个 Session。
    """
    conversations: list[Conversation] = []
    for version in versions:
        connection = open_connection(version)
        for case in testset:
            convo = driver.run(case, connection)
            # 出处由 core 统一盖章 —— driver 不一定知道版本和 run。
            convo.version_id = version.version_id
            convo.case_id = case.case_id
            convo.run_id = run_id
            conversations.append(convo)
    return conversations
