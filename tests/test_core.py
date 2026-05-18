"""core 对着假适配器端到端 —— 零真实 agent 跑通 run / score / compare。

这套测试绿了，就证明 core 没耦合任何具体被测 agent —— 它「通用」。
"""
import unittest
from pathlib import Path

from fakes import FakeConnection, FakeDriver, FakeScorer

from harness_design_loop.core import compare, run_experiment, score_conversations
from harness_design_loop.models import ComparisonReport, Conversation, ScoreCard
from harness_design_loop.rubric import Dimension, Rubric
from harness_design_loop.testset import TestCase
from harness_design_loop.version import Version


def _versions() -> list[Version]:
    return [
        Version(path=Path("V1"), version_id="V1", is_baseline=True,
                what="基线", setup="假接入"),
        Version(path=Path("V2"), version_id="V2", is_baseline=False,
                what="改了 memory 规则", setup="假接入"),
    ]


def _testset() -> list[TestCase]:
    return [
        TestCase(path=Path("c1"), case_id="c1", opening="任务一"),
        TestCase(path=Path("c2"), case_id="c2", opening="任务二"),
    ]


def _rubric() -> Rubric:
    rubric = Rubric(path=Path("rubric"))
    rubric.dimensions = [
        Dimension(name="正确性", weight=0.6, description="测试用"),
        Dimension(name="简洁度", weight=0.4, description="测试用"),
    ]
    return rubric


class TestRun(unittest.TestCase):
    def test_one_conversation_per_version_case(self) -> None:
        convos = run_experiment(
            _versions(), _testset(),
            open_connection=lambda v: FakeConnection(),
            driver=FakeDriver(),
            run_id="r1",
        )
        self.assertEqual(len(convos), 4)   # 2 版本 × 2 case
        for c in convos:
            self.assertIsInstance(c, Conversation)
            self.assertEqual(c.run_id, "r1")
            self.assertTrue(c.version_id)
            self.assertTrue(c.case_id)

    def test_core_needs_no_real_agent(self) -> None:
        # 整个 run 只见到 FakeConnection —— core 里没有任何 import adapter。
        convos = run_experiment(
            _versions(), _testset(),
            open_connection=lambda v: FakeConnection(),
            driver=FakeDriver(),
        )
        self.assertTrue(all(c.turns for c in convos))


class TestScore(unittest.TestCase):
    def test_one_scorecard_per_conversation(self) -> None:
        convos = run_experiment(
            _versions(), _testset(),
            open_connection=lambda v: FakeConnection(),
            driver=FakeDriver(), run_id="r1",
        )
        cards = score_conversations(convos, _rubric(), FakeScorer(fixed=0.8))
        self.assertEqual(len(cards), 4)
        for card in cards:
            self.assertIsInstance(card, ScoreCard)
            self.assertEqual(card.run_id, "r1")
            self.assertEqual(len(card.scores), 2)


class TestCompare(unittest.TestCase):
    def test_report_has_one_result_per_version(self) -> None:
        convos = run_experiment(
            _versions(), _testset(),
            open_connection=lambda v: FakeConnection(),
            driver=FakeDriver(),
        )
        cards = score_conversations(convos, _rubric(), FakeScorer(fixed=0.8))
        report = compare(cards, _rubric(), baseline_version="V1")
        self.assertIsInstance(report, ComparisonReport)
        self.assertEqual(len(report.results), 2)
        baseline = [r for r in report.results if r.is_baseline]
        self.assertEqual(len(baseline), 1)
        self.assertEqual(baseline[0].version_id, "V1")
        self.assertIs(report.results[0].is_baseline, True)   # 基线排最前

    def test_weighted_total_uses_rubric_weights(self) -> None:
        # FakeScorer 固定 0.8；加权和 = 0.8×0.6 + 0.8×0.4 = 0.8
        convos = run_experiment(
            _versions(), _testset(),
            open_connection=lambda v: FakeConnection(),
            driver=FakeDriver(),
        )
        cards = score_conversations(convos, _rubric(), FakeScorer(fixed=0.8))
        report = compare(cards, _rubric(), baseline_version="V1")
        for r in report.results:
            self.assertAlmostEqual(r.weighted_total, 0.8, places=6)


if __name__ == "__main__":
    unittest.main()
