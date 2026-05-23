"""comparator 的单测 —— 三种对比方式、题目覆盖不一致。"""
import unittest

from agent_harness_lab.comparator import compare_scores


def _mk(vid: str, cid: str, total: float) -> dict:
    return {"version_id": vid, "case_id": cid, "total": total,
            "dimensions": {"d": total}}


class TestCompareModes(unittest.TestCase):
    def setUp(self) -> None:
        self.three = [_mk("V1", "C1", 6.0), _mk("V2", "C1", 7.0), _mk("V3", "C1", 6.5)]

    def test_baseline_mode(self):
        by = {v.version_id: v for v in compare_scores(self.three, "V1", "对基线").versions}
        self.assertIsNone(by["V1"].total_delta)
        self.assertEqual(by["V2"].total_delta, 1.0)        # 7.0 - 6.0
        self.assertEqual(by["V3"].total_delta, 0.5)        # 6.5 - 6.0
        self.assertEqual(by["V3"].compared_to, "V1")

    def test_linear_mode(self):
        by = {v.version_id: v for v in compare_scores(self.three, "V1", "线性迭代").versions}
        self.assertIsNone(by["V1"].total_delta)
        self.assertEqual(by["V2"].total_delta, 1.0)        # 7.0 - 6.0
        self.assertEqual(by["V3"].total_delta, -0.5)       # 6.5 - 7.0
        self.assertEqual(by["V3"].compared_to, "V2")

    def test_single_version(self):
        c = compare_scores([_mk("V1", "C1", 8.0)], "V1", "对基线")
        self.assertEqual(len(c.versions), 1)
        self.assertIsNone(c.versions[0].total_delta)

    def test_coverage_mismatch(self):
        scores = [_mk("V1", "C1", 6.0), _mk("V2", "C1", 7.0), _mk("V2", "C2", 9.0)]
        c = compare_scores(scores, "V1", "对基线")
        self.assertFalse(c.coverage_even)
        self.assertEqual(c.basis_cases, ["C1"])            # 只在共同题上比


if __name__ == "__main__":
    unittest.main()
