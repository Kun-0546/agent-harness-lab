"""比 —— 把一组版本的分数放一起比。design §4「比」。

design 说「比」要看四样：差异多大、差异有没有过噪声、哪个维度退化、该归因到
feature 还是评测设置的干扰。噪声和归因要 trial 数据和算法支持，骨架阶段先把
「差异」算出来，噪声/归因/退化标 TODO。
"""
from __future__ import annotations

from harness_design_loop.models import (
    ComparisonReport,
    DimensionScore,
    ScoreCard,
    VersionResult,
)
from harness_design_loop.rubric import Rubric


def _weighted_total(card: ScoreCard, rubric: Rubric) -> float:
    """按 rubric 权重，把一张 ScoreCard 的维度分加权求和。"""
    total = 0.0
    for dim in rubric.dimensions:
        if dim.weight is None:
            continue
        raw = card.get(dim.name)
        if raw is not None:
            total += raw * dim.weight
    return total


def compare(
    scorecards: list[ScoreCard],
    rubric: Rubric,
    baseline_version: str,
) -> ComparisonReport:
    """把按版本分组的分数汇总成一份对比报告。

    一个版本可能有多张 ScoreCard（多个 case、将来还有多次 trial），这里对每个
    维度取平均、再加权。骨架阶段一个版本汇总成一个值；trial 级的噪声留 TODO。
    """
    by_version: dict[str, list[ScoreCard]] = {}
    for card in scorecards:
        by_version.setdefault(card.version_id, []).append(card)

    results: list[VersionResult] = []
    for version_id, cards in by_version.items():
        per_dim: dict[str, float] = {}
        for dim in rubric.dimensions:
            vals = [card.get(dim.name) for card in cards]
            vals = [v for v in vals if v is not None]
            if vals:
                per_dim[dim.name] = sum(vals) / len(vals)
        # 用维度均值组一张合成卡，算这个版本的加权总分。
        synthetic = ScoreCard(
            version_id=version_id,
            case_id="(汇总)",
            scores=[DimensionScore(name, s) for name, s in per_dim.items()],
        )
        results.append(VersionResult(
            version_id=version_id,
            is_baseline=(version_id == baseline_version),
            weighted_total=_weighted_total(synthetic, rubric),
            per_dimension=per_dim,
        ))

    # 基线排最前，其余按 id。
    results.sort(key=lambda r: (not r.is_baseline, r.version_id))

    notes = [
        "TODO: 噪声 —— 多 trial 时算版本内方差，判差异有没有过噪声线。",
        "TODO: 归因 —— 区分差异来自 feature 本身还是评测设置的干扰。",
        "TODO: 维度退化 —— 标出相对基线掉分的维度。",
    ]
    return ComparisonReport(
        baseline_version=baseline_version,
        results=results,
        notes=notes,
    )
