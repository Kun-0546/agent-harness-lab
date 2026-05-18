"""假适配器 —— in-memory 的接口实现，只为测 core 和验契约脚手架用。

它们不连任何真实 agent。core 能对着这些假适配器端到端跑通，就证明 core
没耦合任何具体项目。这些是测试设施，不是 adapters/ 里的产品实现。
"""
from __future__ import annotations

from harness_design_loop.interfaces.connection import Connection, Session
from harness_design_loop.interfaces.conversation import ConversationDriver
from harness_design_loop.interfaces.scorer import Scorer
from harness_design_loop.interfaces.simulator import Simulator
from harness_design_loop.models import (
    Conversation,
    DimensionScore,
    Response,
    ScoreCard,
    Turn,
)
from harness_design_loop.rubric import Rubric
from harness_design_loop.testset import TestCase


class FakeSession(Session):
    """假会话：把输入原样回声成回应，记下发过哪几轮。"""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    def send(self, message: str) -> Response:
        self.sent.append(message)
        return Response(content=f"echo: {message}")

    def close(self) -> None:
        self.closed = True


class FakeConnection(Connection):
    """假接入：每次 open_session 给一个新的 FakeSession。"""

    def __init__(self) -> None:
        self.sessions: list[FakeSession] = []

    def open_session(self) -> FakeSession:
        session = FakeSession()
        self.sessions.append(session)
        return session


class FakeSimulator(Simulator):
    """假模拟器：固定追问 turns 轮后收口。"""

    def __init__(self, turns: int = 2) -> None:
        self.turns = turns

    def next_turn(self, history: Conversation) -> str | None:
        user_turns = sum(1 for t in history.turns if t.role == "user")
        if user_turns >= self.turns:
            return None
        return f"追问 {user_turns + 1}"


class FakeDriver(ConversationDriver):
    """假对话模式：开一个会话，发一轮起始输入，收一轮回应，就结束。"""

    def run(self, case: TestCase, connection: Connection) -> Conversation:
        session = connection.open_session()
        convo = Conversation(version_id="", case_id=case.case_id)
        opening = case.opening or "(空起始输入)"
        convo.turns.append(Turn(role="user", content=opening))
        response = session.send(opening)
        convo.turns.append(Turn(role="agent", content=response.content))
        session.close()
        return convo


class FakeScorer(Scorer):
    """假评分器：给 rubric 每个维度打固定分。确定性，无噪声。"""

    def __init__(self, fixed: float = 1.0, scorer_id: str = "fake") -> None:
        self.fixed = fixed
        self.scorer_id = scorer_id

    def score(self, conversation: Conversation, rubric: Rubric) -> ScoreCard:
        return ScoreCard(
            version_id=conversation.version_id,
            case_id=conversation.case_id,
            scores=[
                DimensionScore(dim.name, self.fixed, rationale="(假评分)")
                for dim in rubric.dimensions
            ],
            rubric_id="fake-rubric",
            scorer_id=self.scorer_id,
            run_id=conversation.run_id,
        )
