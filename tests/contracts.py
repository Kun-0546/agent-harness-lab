"""契约测试 —— 任意一个接口实现都必须过的通用用例。

用法：给你的适配器写一个测试类，多继承「契约基类 ＋ unittest.TestCase」，
实现 make_xxx() 工厂方法即可：

    import unittest
    from contracts import ConnectionContract
    from harness_design_loop.adapters.my_connection import MyConnection

    class TestMyConnection(ConnectionContract, unittest.TestCase):
        def make_connection(self):
            return MyConnection(...)

契约基类自己不继承 TestCase，所以不会被直接收集 —— 只有跟 TestCase 一起被
子类化时才跑。这样「过契约测试」就成了一个适配器明确的验收标准。

骨架阶段先做 Connection 和 Scorer 两个契约；ConversationDriver / Simulator /
Snapshotter 的契约按同样的模式补（TODO）。
"""
from __future__ import annotations

from pathlib import Path

from harness_design_loop.interfaces.connection import Connection, Session
from harness_design_loop.interfaces.scorer import Scorer
from harness_design_loop.models import Conversation, Response, ScoreCard, Turn
from harness_design_loop.rubric import Dimension, Rubric


class ConnectionContract:
    """任意 Connection 实现都必须满足的契约。"""

    def make_connection(self) -> Connection:
        raise NotImplementedError("子类提供一个待测的 Connection")

    def test_open_session_returns_session(self) -> None:
        session = self.make_connection().open_session()
        self.assertIsInstance(session, Session)

    def test_open_session_gives_fresh_sessions(self) -> None:
        conn = self.make_connection()
        self.assertIsNot(conn.open_session(), conn.open_session())

    def test_send_returns_response_with_str_content(self) -> None:
        session = self.make_connection().open_session()
        resp = session.send("hello")
        self.assertIsInstance(resp, Response)
        self.assertIsInstance(resp.content, str)

    def test_close_does_not_raise(self) -> None:
        session = self.make_connection().open_session()
        session.send("hello")
        session.close()


class ScorerContract:
    """任意 Scorer 实现都必须满足的契约。"""

    def make_scorer(self) -> Scorer:
        raise NotImplementedError("子类提供一个待测的 Scorer")

    def _sample_rubric(self) -> Rubric:
        rubric = Rubric(path=Path("sample-rubric"))
        rubric.dimensions = [
            Dimension(name="维度A", weight=0.5, description="测试用"),
            Dimension(name="维度B", weight=0.5, description="测试用"),
        ]
        return rubric

    def _sample_conversation(self) -> Conversation:
        return Conversation(
            version_id="V1",
            case_id="c1",
            turns=[
                Turn(role="user", content="你好"),
                Turn(role="agent", content="你好，有什么可以帮你"),
            ],
            run_id="r1",
        )

    def test_score_returns_scorecard(self) -> None:
        card = self.make_scorer().score(
            self._sample_conversation(), self._sample_rubric())
        self.assertIsInstance(card, ScoreCard)

    def test_scorecard_covers_rubric_dimensions(self) -> None:
        rubric = self._sample_rubric()
        card = self.make_scorer().score(self._sample_conversation(), rubric)
        scored = {s.dimension for s in card.scores}
        for dim in rubric.dimensions:
            self.assertIn(dim.name, scored, f"维度「{dim.name}」没被打分")

    def test_scorecard_carries_provenance(self) -> None:
        # design §4：每份分数要能追溯到哪个评分器。
        card = self.make_scorer().score(
            self._sample_conversation(), self._sample_rubric())
        self.assertTrue(card.scorer_id, "ScoreCard.scorer_id 没填 —— 分数追不到评分器")
