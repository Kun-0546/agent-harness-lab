"""评分器 —— 把一段对话按 rubric 打成分。

design §3.3 三种评分器，都是 Scorer 的实现：
- 规则脚本：确定性代码（正则、精确匹配、查工具调用）。没噪声、不花钱。
- LLM Judge：一个 LLM 照 rubric 打分。有噪声、花钱。
- 组合：客观维度走规则脚本，主观维度走 LLM Judge。

接缝：打分只读对话，不碰 Connection。所以「跑」和「打分」彻底分开 ——
打分便宜、能换 rubric / 换模型重打。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from harness_design_loop.models import Conversation, ScoreCard
from harness_design_loop.rubric import Rubric


class Scorer(ABC):
    """把对话打成分。"""

    @abstractmethod
    def score(self, conversation: Conversation, rubric: Rubric) -> ScoreCard:
        """按 rubric 给一段对话打分。

        产出的 ScoreCard 必须填全出处 —— rubric_id、scorer_id、run_id。
        design §4 要求每份分数可追溯到「哪版 rubric、哪个评分器、哪次跑」。
        """
        raise NotImplementedError
