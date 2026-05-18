"""把契约测试套在假适配器上 —— 证明契约脚手架本身能跑通、是绿的。

实现方写真适配器时，照这个样子加自己的测试类即可。
"""
import unittest

from contracts import ConnectionContract, ScorerContract
from fakes import FakeConnection, FakeScorer


class TestFakeConnectionContract(ConnectionContract, unittest.TestCase):
    def make_connection(self) -> FakeConnection:
        return FakeConnection()


class TestFakeScorerContract(ScorerContract, unittest.TestCase):
    def make_scorer(self) -> FakeScorer:
        return FakeScorer()


if __name__ == "__main__":
    unittest.main()
