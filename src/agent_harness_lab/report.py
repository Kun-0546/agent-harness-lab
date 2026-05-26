"""compare 报告 —— 把一次对比的结果拼成 markdown 文本。"""
from __future__ import annotations

from agent_harness_lab.comparator import Comparison


def build_compare_report(exp_name: str, score_file: str, grader: str,
                         baseline_id: str, comparison: Comparison,
                         evidence: dict | None = None) -> str:
    """把一次 compare 的结果拼成 markdown 报告文本。

    v0.4:`evidence` 是 evidence.summarize_evidence_for_* 的产出。None 时
    向后兼容老调用,不渲染 Evidence section。
    """
    summaries = comparison.versions
    lines = [
        f"实验:{exp_name}",
        f"对比:{score_file}  评分器:{grader}",
        f"对比方式:{comparison.mode}",
    ]
    if comparison.mode != "线性迭代":
        lines.append(f"基线:{baseline_id or '(无 —— harnesses/ 里没标基线,只列总分)'}")
    if not comparison.coverage_even:
        lines.append("")
        lines.append("⚠ 版本间题目覆盖不一致 —— 总分、差值只在共同题上算:"
                      + "、".join(comparison.basis_cases))
        for s in summaries:
            if s.missing:
                lines.append(f"   {s.version_id} 缺:" + "、".join(s.missing))

    # v0.4:Evidence section 在版本总分之前,让用户先看到证据强度再读分数。
    # 空 variants 时不渲染(避免空表格;旧 result 走 fallback 仍能给数据)。
    if evidence and evidence.get("variants"):
        lines += _build_evidence_section(evidence)

    ref_label = "起点" if comparison.mode == "线性迭代" else "基线"
    lines += ["", "版本总分:"]
    for s in summaries:
        if s.total_delta is None:
            lines.append(f"  {s.version_id}  {s.total}  ({ref_label})")
        else:
            sign = "+" if s.total_delta >= 0 else ""
            lines.append(
                f"  {s.version_id}  {s.total}  vs {s.compared_to} {sign}{s.total_delta}")

    graded = [s for s in summaries if s.dimension_delta]
    if graded:
        lines += ["", "维度变化:"]
        for s in graded:
            parts = []
            for dn, d in s.dimension_delta.items():
                sign = "+" if d >= 0 else ""
                mark = "↓" if d < 0 else ""
                parts.append(f"{dn}{sign}{d}{mark}")
            lines.append(f"  {s.version_id}(vs {s.compared_to})  " + "  ".join(parts))
        lines += ["", "退化维度:"]
        for s in graded:
            lines.append(
                f"  {s.version_id}:{'、'.join(s.regressed) if s.regressed else '无'}")

    lines += ["", "注:差异稳不稳(噪声)要多跑几次 trial 才知道,本期没算。"]
    return "\n".join(lines)


def _build_evidence_section(evidence: dict) -> list[str]:
    """渲染 ## Evidence section(spec §5)。

    三档信号(spec §5.1):
    - 全部同 level → 只表格,不打 warning/note
    - 无 weak/unknown 但 level 不一 → ℹ 提示
    - 任意 weak/unknown → ⚠ 警告
    """
    variants = evidence.get("variants") or {}
    summary = evidence.get("summary") or {}
    lines = ["", "## Evidence", ""]
    lines.append("| variant | level | source | snapshot | materials | reasons |")
    lines.append("|---|---|---|---|---|---|")
    for vid, e in variants.items():
        snap = "✓" if e.get("snapshot_available") else "—"
        mats = ", ".join(e.get("materials_evidence") or []) or "—"
        reasons = "; ".join(e.get("reasons") or []) or "—"
        rs_type = e.get("runtime_source_type") or "—"
        lines.append(
            f"| {vid} | {e.get('level', 'unknown')} | {rs_type} | "
            f"{snap} | {mats} | {reasons} |")
    warning = summary.get("warning")
    note = summary.get("note")
    if warning:
        lines += ["", f"⚠ {warning}"]
    elif note:
        lines += ["", f"ℹ {note}"]
    return lines
