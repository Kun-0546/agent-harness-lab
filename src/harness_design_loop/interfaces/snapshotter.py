"""快照器 —— 抓被测 agent 的环境快照。

design §3.1：一个版本是一份环境快照，环境按「能不能快照」分五层。
抓环境是个过程，一层层来；能抓多少抓多少，抓不到的明写「这层没抓全」。
到底能取多全，完全看那个 agent —— 所以 Snapshotter 是个接口，一种 agent 一个实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from harness_design_loop.models import Snapshot


class Snapshotter(ABC):
    """抓某一种被测 agent 的环境快照。

    实现方在构造时拿到要抓的目标（路径、配置等）；capture() 真正去抓。
    """

    @abstractmethod
    def capture(self, version_id: str) -> Snapshot:
        """抓一份当前环境快照，标上是哪个版本。"""
        raise NotImplementedError
