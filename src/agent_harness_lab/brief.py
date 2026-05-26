"""读一个实验的 brief.md —— Co-pilot setup 工作单 (v0.3.1 Step 2 重定义)。

brief.md 由 coding agent (Claude Code / Cursor / Codex) 通过对话与用户协作
维护,并据它生成或补全 program / rubric / cases / harnesses 等实验文件。
用户不必一次填完——只 §1「想优化什么」是 blocking。AHL 自己不调模型起草。
完整 setup mode flow 见 docs/product-walkthrough.md (Step 2 + Step 4)。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_harness_lab import mdutil
from agent_harness_lab.program import COMPARE_MODES


@dataclass
class Brief:
    """一份 Co-pilot setup brief —— coding agent 维护的实验工作单。"""

    path: Path
    optimize: str = ""        # 想优化什么
    change: str = ""          # 验证什么改动
    care: str = ""            # 最在意什么
    redlines: str = ""        # 不能牺牲什么(红线)
    compare: str = ""         # 怎么比(可空;空值/占位符/非法都落「对基线」)

    @property
    def compare_mode(self) -> str:
        """怎么比;空值、占位符、非法值一律落「对基线」。

        跟 program.Program.compare_mode 同构 —— 外层 agent 据此定 program
        的「对比方式」声明。非法值另由 validate() 报问题。
        """
        return (self.compare if mdutil.is_filled(self.compare)
                and self.compare in COMPARE_MODES else "对基线")

    def validate(self) -> list[str]:
        """返回 blocking problems;空清单表示没问题。

        v0.3.1 Step 2 放宽:brief.md 是 coding agent 工作单,不是用户必须
        一次填完的表单。只 §1「想优化什么」是 blocking(它决定 coding
        agent 起草方向);其他段缺失不报,coding agent 据 goal.md 推。
        「怎么比」填了但非法仍报。
        """
        problems: list[str] = []
        if not mdutil.is_filled(self.optimize):
            problems.append(
                "「想优化什么」没填 (必填:它决定 coding agent 起草方向)")
        if mdutil.is_filled(self.compare) and self.compare not in COMPARE_MODES:
            problems.append(
                f"「怎么比」填了「{self.compare}」,识别不了"
                f"(应为 {' / '.join(COMPARE_MODES)},或留空)")
        return problems


def parse_brief(path: str | Path) -> Brief:
    """读 brief.md,解析成 Brief。

    v0.9 把 BRIEF_TEMPLATE 重写为 12 section co-pilot 工作单
    (`docs/copilot-setup.md` §4.1)。`parse_brief` 同时支持 v0.9 新
    section 名 + v0.3.1 历史 section 名 —— 两版模板都能干净解析。

    映射(优先 v0.9 → 回落 v0.3.1):
    - optimize ← 「想优化什么」(两版同名)
    - change   ← 「Harness 假设」(v0.9 §5) → 回落 「验证什么改动」(v0.3.1)
    - care     ← 「Rubric 应该如何判断」(v0.9 §7) → 回落 「最在意什么」
    - redlines ← 「Files the coding agent should not change」(v0.9 §10)
                 → 回落 「不能牺牲什么」
    - compare  ← 「怎么比」(v0.3.1 only;v0.9 未保留同义段)
    """
    path = Path(path)
    sections = mdutil.split_sections(path.read_text(encoding="utf-8"))

    def _pick(*keys: str) -> str:
        for k in keys:
            if k in sections:
                return sections[k].strip()
        return ""

    return Brief(
        path=path,
        optimize=_pick("想优化什么"),
        change=_pick("Harness 假设", "验证什么改动"),
        care=_pick("Rubric 应该如何判断", "最在意什么"),
        redlines=_pick("Files the coding agent should not change",
                       "不能牺牲什么"),
        compare=_pick("怎么比"),
    )
