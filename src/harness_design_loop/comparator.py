"""比 —— 把一组版本的分数放一起比。

看:每个版本总分、跟基线差多少、哪个维度退化。
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
    case_count: int
    total: float                                        # 平均总分
    dimensions: dict[str, float]                         # 维度名 -> 平均分
    total_delta: float | None = None                    # 跟基线比的总分差
    dimension_delta: dict[str, float] = field(default_factory=dict)
    regressed: list[str] = field(default_factory=list)   # 比基线低的维度


def compare_scores(scores: list[dict], baseline_id: str) -> list[VersionSummary]:
    """把 score 结果按版本聚合,非基线版本跟基线比;基线排最前。"""
    by_version: dict[str, list[dict]] = {}
    for s in scores:
        by_version.setdefault(s.get("version_id", ""), []).append(s)

    summaries: dict[str, VersionSummary] = {}
    for vid, items in by_version.items():
        dim_names = list(items[0].get("dimensions", {}).keys())
        dims = {
            dn: round(mean(it.get("dimensions", {}).get(dn, 0.0) for it in items), 2)
            for dn in dim_names
        }
        summaries[vid] = VersionSummary(
            version_id=vid,
            is_baseline=(vid == baseline_id),
            case_count=len(items),
            total=round(mean(it.get("total", 0.0) for it in items), 2),
            dimensions=dims,
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
    return ordered
