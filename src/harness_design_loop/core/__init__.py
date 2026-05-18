"""harness-design-loop 的通用 core —— 三个动作的编排。

design §4 的三个动作：
- run     —— 每个版本过一遍测试集，产出对话。
- score   —— 拿评分器给对话打分。
- compare —— 把一组版本的分数放一起比。

core 只依赖 interfaces 和 models，不 import 任何 adapter —— 所以它在零真实
agent 的情况下也能跑通（对着 tests/fakes.py 的假适配器），这就是它「通用」的证明。
"""
from harness_design_loop.core.compare import compare
from harness_design_loop.core.run import run_experiment
from harness_design_loop.core.score import score_conversations

__all__ = ["run_experiment", "score_conversations", "compare"]
