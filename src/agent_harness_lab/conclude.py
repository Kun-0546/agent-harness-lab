"""hlab conclude — record the human's final decision as conclusion.md.

This does NOT compute or judge anything. It fixes the human's conclusion (decision,
winner, reason) into conclusion.md, with references to the report, the comparison,
and the evidence tree. After it runs, `hlab review` no longer warns
`conclusion_missing` (the check is just whether conclusion.md exists).
"""
from __future__ import annotations

from pathlib import Path

from agent_harness_lab.experiment_spec import ExperimentSpec

_TEMPLATE = """# Conclusion — {id}

> Recorded with `hlab conclude`. This is the human's decision, not a generated
> verdict — AHL fixes what you concluded; it does not conclude for you.

## Decision
{decision}

## Winner
{winner}

## Reason
{reason}

## Evidence relied on
- Report: [{report_path}]({report_path})
- Comparison: [{compare_path}]({compare_path})
- Evidence tree: `evidence/` (traces, raw output, artifacts, scores, issues)

## Next step
{next_step}
"""


def write_conclusion(exp_dir: Path, spec: ExperimentSpec, *, winner: str | None = None,
                     reason: str | None = None, decision: str | None = None,
                     next_step: str | None = None) -> Path:
    """Write conclusion.md from the human's decision. Returns the path."""
    decision = decision or (f"Adopt harness {winner}." if winner
                            else "See the reason below.")
    next_step = next_step or ("Apply the winning harness, or iterate the experiment "
                              "design and run again.")
    content = _TEMPLATE.format(
        id=spec.id or "experiment",
        decision=decision,
        winner=(winner if winner else "(none recorded)"),
        reason=(reason if reason else "(no reason recorded)"),
        report_path="reports/report.md",
        compare_path="reports/compare.json",
        next_step=next_step,
    )
    out = Path(exp_dir) / "conclusion.md"
    out.write_text(content, encoding="utf-8")
    return out
