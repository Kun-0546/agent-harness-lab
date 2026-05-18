"""harness-design-loop 的扩展点 —— 五个接口。

工具的通用 core 只依赖这五个接口；所有跟「具体被测 agent」相关的东西，
都关在接口后面，由实现方在 adapters/ 里写成具体实现。

- Connection / Session —— 接入（design §3.2）
- ConversationDriver   —— 对话模式（design §3.3）
- Simulator            —— 模拟器（design §3.3）
- Scorer               —— 评分器（design §3.3）
- Snapshotter          —— 环境快照（design §3.1）
"""
from harness_design_loop.interfaces.connection import Connection, Session
from harness_design_loop.interfaces.conversation import ConversationDriver
from harness_design_loop.interfaces.scorer import Scorer
from harness_design_loop.interfaces.simulator import Simulator
from harness_design_loop.interfaces.snapshotter import Snapshotter

__all__ = [
    "Connection",
    "Session",
    "ConversationDriver",
    "Simulator",
    "Scorer",
    "Snapshotter",
]
