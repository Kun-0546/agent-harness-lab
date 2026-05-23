"""比 —— 把一组版本的分数放一起比。

三种对比方式(由 program 的「对比方式」声明定):
- 对基线:非基线版本都跟基线比。
- 线性迭代:V1→V2→V3 一条链,每个版本跟前一个比。
- 单版本:只有一个版本时,两种模式都退化成「只列那一个分」。

版本之间题目覆盖不一致时(某版本某题没跑成),只在「共同题」上比。
差异稳不稳(噪声)要多跑几次 trial 才知道,本期先不做。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass
class VersionSummary:
    """一个版本在一次对比里的汇总。"""

    version_id: str
    is_baseline: bool                                      # 是否基线
    case_count: int                                        # 参与对比的题数
    total: float                                           # 平均总分
    dimensions: dict[str, float]                            # 维度名 -> 平均分
    total_delta: float | None = None                       # 总分差;参照点为 None
    dimension_delta: dict[str, float] = field(default_factory=dict)
    regressed: list[str] = field(default_factory=list)      # 退化的维度
    missing: list[str] = field(default_factory=list)        # 这个版本没跑成的题
    compared_to: str = ""                                   # delta 是相对谁算的


@dataclass
class Comparison:
    """一次对比的结果。"""

    versions: list[VersionSummary]
    mode: str                   # 对基线 / 线性迭代
    basis_cases: list[str]      # 实际用来比的题(各版本都有的)
    coverage_even: bool         # 各版本题目覆盖是否一致


def _aggregate(by_version: dict[str, list[dict]], baseline_id: str,
               all_cases: set, basis: set) -> dict[str, VersionSummary]:
    """把每个版本的若干 case 分聚成一个 VersionSummary(只用 basis 里的题)。"""
    summaries: dict[str, VersionSummary] = {}
    for vid, items in by_version.items():
        used = [it for it in items if it.get("case_id", "") in basis]
        dim_names = list(used[0].get("dimensions", {}).keys()) if used else []
        dims = {
            dn: round(mean(it.get("dimensions", {}).get(dn, 0.0) for it in used), 2)
            for dn in dim_names
        }
        cases_of_vid = {it.get("case_id", "") for it in items}
        summaries[vid] = VersionSummary(
            version_id=vid,
            is_baseline=(vid == baseline_id),
            case_count=len(used),
            total=round(mean(it.get("total", 0.0) for it in used), 2) if used else 0.0,
            dimensions=dims,
            missing=sorted(all_cases - cases_of_vid),
        )
    return summaries


def _delta(s: VersionSummary, ref: VersionSummary) -> None:
    """算 s 相对 ref 的总分差、各维度差、退化维度;就地写进 s。"""
    s.total_delta = round(s.total - ref.total, 2)
    s.compared_to = ref.version_id
    for dn, val in s.dimensions.items():
        d = round(val - ref.dimensions.get(dn, 0.0), 2)
        s.dimension_delta[dn] = d
        if d < 0:
            s.regressed.append(dn)


def compare_scores(scores: list[dict], baseline_id: str,
                   mode: str = "对基线") -> Comparison:
    """把 score 结果按版本聚合,按对比方式算 delta。

    对基线:非基线版本都跟基线比,基线排最前。
    线性迭代:版本按出场顺序(= 版本文件名顺序)排,每个跟前一个比。
    覆盖不一致时只在「共同题」上算。
    """
    by_version: dict[str, list[dict]] = {}
    for s in scores:
        by_version.setdefault(s.get("version_id", ""), []).append(s)

    cases_of = {vid: {it.get("case_id", "") for it in items}
                for vid, items in by_version.items()}
    all_cases = set().union(*cases_of.values()) if cases_of else set()
    common = set.intersection(*cases_of.values()) if cases_of else set()
    coverage_even = (common == all_cases)
    basis = all_cases if coverage_even else common

    summaries = _aggregate(by_version, baseline_id, all_cases, basis)

    if mode == "线性迭代":
        prev: VersionSummary | None = None
        for s in summaries.values():        # 出场顺序 = 版本文件名顺序 = 迭代链顺序
            if prev is not None:
                _delta(s, prev)
            prev = s
        ordered = list(summaries.values())
    else:                                    # 对基线
        base = summaries.get(baseline_id)
        if base is not None:
            for vid, s in summaries.items():
                if vid != baseline_id:
                    _delta(s, base)
        ordered = ([base] if base is not None else []) \
            + [s for vid, s in summaries.items() if vid != baseline_id]

    return Comparison(
        versions=ordered,
        mode=mode,
        basis_cases=sorted(basis),
        coverage_even=coverage_even,
    )
