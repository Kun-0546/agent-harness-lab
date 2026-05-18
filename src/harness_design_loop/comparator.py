"""比 —— 把一组版本的分数放一起比。

看:每个版本总分、跟基线差多少、哪个维度退化。
版本之间题目覆盖不一致时(某版本某题没跑成),只在「共同题」上比,
并记下每个版本缺哪些题 —— 不拿不同题集瞎比。
差异稳不稳(噪声)要多跑几次 trial 才知道,本期先不做。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass
class VersionSummary:
    """一个版本在一次对比里的汇总。"""

    version_id: str
    is_baseline: bool
    case_count: int                                      # 参与对比的题数
    total: float                                         # 平均总分
    dimensions: dict[str, float]                          # 维度名 -> 平均分
    total_delta: float | None = None                     # 跟基线比的总分差
    dimension_delta: dict[str, float] = field(default_factory=dict)
    regressed: list[str] = field(default_factory=list)    # 比基线低的维度
    missing: list[str] = field(default_factory=list)      # 这个版本没跑成的题


@dataclass
class Comparison:
    """一次对比的结果。"""

    versions: list[VersionSummary]
    basis_cases: list[str]      # 实际用来比的题(各版本都有的)
    coverage_even: bool         # 各版本题目覆盖是否一致


def compare_scores(scores: list[dict], baseline_id: str) -> Comparison:
    """把 score 结果按版本聚合,非基线版本跟基线比;基线排最前。

    各版本覆盖的题不一致时,只在「共同题」上算总分和差值。
    """
    by_version: dict[str, list[dict]] = {}
    for s in scores:
        by_version.setdefault(s.get("version_id", ""), []).append(s)

    # 各版本覆盖了哪些题
    cases_of = {vid: {it.get("case_id", "") for it in items}
                for vid, items in by_version.items()}
    all_cases = set().union(*cases_of.values()) if cases_of else set()
    common = set.intersection(*cases_of.values()) if cases_of else set()
    coverage_even = (common == all_cases)
    basis = all_cases if coverage_even else common   # 不一致就只用共同题

    summaries: dict[str, VersionSummary] = {}
    for vid, items in by_version.items():
        used = [it for it in items if it.get("case_id", "") in basis]
        dim_names = list(used[0].get("dimensions", {}).keys()) if used else []
        dims = {
            dn: round(mean(it.get("dimensions", {}).get(dn, 0.0) for it in used), 2)
            for dn in dim_names
        }
        summaries[vid] = VersionSummary(
            version_id=vid,
            is_baseline=(vid == baseline_id),
            case_count=len(used),
            total=round(mean(it.get("total", 0.0) for it in used), 2) if used else 0.0,
            dimensions=dims,
            missing=sorted(all_cases - cases_of[vid]),
        )

    base = summaries.get(baseline_id)
    if base is not None:
        for vid, s in summaries.items():
            if vid == baseline_id:
                continue
            s.total_delta = round(s.total - base.total, 2)
            for dn, val in s.dimensions.items():
                delta = round(val - base.dimensions.get(dn, 0.0), 2)
                s.dimension_delta[dn] = delta
                if delta < 0:
                    s.regressed.append(dn)

    ordered: list[VersionSummary] = []
    if base is not None:
        ordered.append(base)
    ordered += [s for vid, s in summaries.items() if vid != baseline_id]
    return Comparison(
        versions=ordered,
        basis_cases=sorted(basis),
        coverage_even=coverage_even,
    )
