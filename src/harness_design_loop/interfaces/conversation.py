"""对话模式 —— 怎么把一个测试 case 变成一段完整对话。

design §3.3 三种对话模式，都是 ConversationDriver 的实现：
- 模拟：一个 Simulator 扮用户，从起始输入起一轮轮现生对话。
- 回放：把录好的真实对话喂进去。
- 固定：按写死的脚本跑。

模拟那种实现还要再持有一个 Simulator。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from harness_design_loop.interfaces.connection import Connection
from harness_design_loop.models import Conversation
from harness_design_loop.testset import TestCase


class ConversationDriver(ABC):
    """把一个测试 case 在一个 Connection 上跑成一段对话。"""

    @abstractmethod
    def run(self, case: TestCase, connection: Connection) -> Conversation:
        """开一个会话，按本模式生成对话，跑到结束，返回整段。

        core 只调这一个方法，不关心背后是模拟、回放还是固定。
        """
        raise NotImplementedError
