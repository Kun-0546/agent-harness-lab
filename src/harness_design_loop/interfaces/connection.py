"""接入 —— 工具够到被测 agent 的通道。

design §3.2：四种接入（进程内库 / 外部命令行 / HTTP 无状态 / HTTP 服务端有状态），
是 Connection 的四个实现。具体实现放 adapters/，由实现方写；core 只认这个接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from harness_design_loop.models import Response


class Session(ABC):
    """一段对话期间，跟被测 agent 的一条连接。

    对话状态住在 Session 里：HTTP 服务端有状态的实现握一个服务端 session id；
    HTTP 无状态的实现自己在内存里攒历史、每轮重发完整对话。core 不关心是哪种。
    """

    @abstractmethod
    def send(self, message: str) -> Response:
        """发一轮用户输入，拿被测 agent 的一轮回应。"""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """收尾，释放资源（子进程、连接、临时文件等）。"""
        raise NotImplementedError


class Connection(ABC):
    """配好的接入通道。一个版本一个 Connection。

    它知道怎么连到这个版本的被测 agent；每要跑一段对话，就 open_session()
    开一个新 Session。
    """

    @abstractmethod
    def open_session(self) -> Session:
        """开一个新会话，用来跑一段对话。"""
        raise NotImplementedError
