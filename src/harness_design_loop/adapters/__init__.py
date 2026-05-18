"""具体适配器 —— 五个接口的实现，由实现方填。

这个包是「项目相关」的边缘：每个被测 agent 的接入方式、评分器、模拟器等
具体实现住这里。core 永不 import 这里 —— 反过来，这里 import interfaces
并实现它们。

一个适配器「写完了」的定义：过 tests/contracts.py 里对应的契约测试。
详见 adapters/README.md。
"""
