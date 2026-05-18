"""打分 —— 拿评分器给对话打分。design §4「打分」。

跟「跑」分开：打分只读对话、不碰被测 agent，所以便宜、能重打
（换 rubric、换评分模型再打一遍）。
"""
from __future__ import annotations

from harness_design_loop.interfaces.scorer import Scorer
from harness_design_loop.models import Conversation, ScoreCard
from harness_design_loop.rubric import Rubric


def score_conversations(
    conversations: list[Conversation],
    rubric: Rubric,
    scorer: Scorer,
) -> list[ScoreCard]:
    """给一批对话逐个打分。

    每张 ScoreCard 的出处（rubric_id / scorer_id / run_id）由 scorer 填；
    这里只兜底补 run_id —— 它来自对话，scorer 不一定知道。
    """
    cards: list[ScoreCard] = []
    for convo in conversations:
        card = scorer.score(convo, rubric)
        if not card.run_id:
            card.run_id = convo.run_id
        cards.append(card)
    return cards
