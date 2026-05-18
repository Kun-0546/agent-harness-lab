# adapters/ —— 给实现方

这个目录放五个接口的**具体实现**。`harness_design_loop/core/` 和
`harness_design_loop/interfaces/` 由架构侧维护；这里由实现方填。

## 三条规矩

1. **只 import `interfaces` 和 `models`，不改它们。** 接口是契约。要改契约，
   走架构侧，不在 adapter 里绕。
2. **一个适配器「写完了」＝ 过契约测试。** 见 `tests/contracts.py`。给你的适配器
   写一个 `tests/test_<名字>.py`，让测试类继承对应的契约基类。CI 绿才算完成。
3. **不耦合进 core。** core 不会 import 你的适配器；它通过接口拿到你的实例。
   配置怎么变成适配器实例（接线层），是另说的一件事，不在 core 里写死。

## 要实现什么

| 接口 | design 出处 | 内置实现（待写） |
|---|---|---|
| `Connection` / `Session` | §3.2 接入 | 进程内库 · 外部命令行 · HTTP 无状态 · HTTP 有状态 |
| `ConversationDriver` | §3.3 对话模式 | 模拟 · 回放 · 固定 |
| `Simulator` | §3.3 模拟器 | 至少一个 LLM 模拟器 |
| `Scorer` | §3.3 评分器 | 规则脚本 · LLM Judge · 组合 |
| `Snapshotter` | §3.1 环境快照 | 按被测 agent 而定 |

## 怎么验收自己的适配器

```python
# tests/test_my_connection.py
import unittest
from contracts import ConnectionContract
from harness_design_loop.adapters.my_connection import MyConnection


class TestMyConnection(ConnectionContract, unittest.TestCase):
    def make_connection(self):
        return MyConnection(...)
```

契约基类里的每个 `test_*` 都会在你的适配器上跑一遍。全绿 ＝ 这个适配器满足契约。
