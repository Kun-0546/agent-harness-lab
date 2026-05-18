"""模拟器 —— 模拟对话模式下，扮演用户的那一方。

design §3.3：模拟器 = 人设 + 背景知识 + 追问策略。它看着对话历史，
生成下一句用户输入。可以是一个 LLM。具体实现放 adapters/。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from harness_design_loop.models import Conversation


class Simulator(ABC):
    """模拟模式下的「用户」。"""

    @abstractmethod
    def next_turn(self, history: Conversation) -> str | None:
        """看着到目前为止的对话，给出下一句用户输入。

        返回 None 表示「用户没有更多要说的」，对话到此结束。
        """
        raise NotImplementedError
