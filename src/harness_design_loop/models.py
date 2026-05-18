"""核心数据类型 —— 整个工具流转的纯数据，不含行为。

这些类型把 interfaces 和 core 连起来：接口产出/消费它们，core 编排它们。
谁都能 import，它们不 import 任何别的本包模块 —— 处在依赖链的最底层。
"""
from __future__ import annotations

from dataclasses import dataclass, field


# —— 对话 ——————————————————————————————————————————————————

@dataclass
class Turn:
    """对话里的一轮。"""

    role: str       # "user" | "agent"
    content: str


@dataclass
class Response:
    """被测 agent 对一轮输入的回应。Session.send 的产出。"""

    content: str
    raw: dict | None = None    # 适配器可塞原始返回；core 不依赖它


@dataclass
class Conversation:
    """一个版本在一个测试 case 上跑出来的整段对话。"""

    version_id: str
    case_id: str
    turns: list[Turn] = field(default_factory=list)
    run_id: str = ""           # 对应哪次跑
    note: str = ""             # 可选：怎么生出来的（模式、是否截断等）


# —— 分数 ——————————————————————————————————————————————————

@dataclass
class DimensionScore:
    """一个 rubric 维度上的得分。"""

    dimension: str
    score: float
    rationale: str = ""


@dataclass
class ScoreCard:
    """一段对话的打分结果。

    带全套出处 —— design §4 要求每份分数都标清楚是哪版 rubric、哪个评分器、
    对应哪次跑，这样换 rubric / 换模型重打时分得清。
    """

    version_id: str
    case_id: str
    scores: list[DimensionScore] = field(default_factory=list)
    rubric_id: str = ""        # 哪版 rubric
    scorer_id: str = ""        # 哪个评分器（含模型）
    run_id: str = ""           # 对应哪次跑

    def get(self, dimension: str) -> float | None:
        """取某个维度的分；没有则返回 None。"""
        for s in self.scores:
            if s.dimension == dimension:
                return s.score
        return None


# —— 环境快照 ————————————————————————————————————————————————

@dataclass
class Snapshot:
    """一个版本的环境快照 —— design §3.1 的五层模型。

    按「能不能快照」分五层。能抓多少抓多少；抓不全的层，把说明写进 uncaptured。
    """

    version_id: str
    versioned_files: list[str] = field(default_factory=list)   # 1 可版本化文件：memory/skill/prompt/config/harness 代码
    identifiers: dict[str, str] = field(default_factory=dict)  # 2 标识符：model、平台
    bulk_state: list[str] = field(default_factory=list)        # 3 大块状态：state.db、runtime 镜像
    dependencies: list[str] = field(default_factory=list)      # 4 依赖：venv、lockfile
    external: dict[str, str] = field(default_factory=dict)     # 5 外部会漂的：快照不了，只记录
    captured_at: str = ""                                      # 时间戳
    uncaptured: list[str] = field(default_factory=list)        # 明写哪层没抓全


# —— 对比 ——————————————————————————————————————————————————

@dataclass
class VersionResult:
    """对比报告里，一个版本的汇总。"""

    version_id: str
    is_baseline: bool = False
    weighted_total: float = 0.0
    per_dimension: dict[str, float] = field(default_factory=dict)


@dataclass
class ComparisonReport:
    """一次「比」的结果 —— design §4「比」。

    design 说「比」要看四样：差异多大、差异有没有过噪声、哪个维度退化、
    该归因到 feature 还是评测设置。噪声和归因要 trial 数据与算法支持，
    骨架阶段先把「差异」算出来，其余进 notes 标 TODO。
    """

    baseline_version: str
    results: list[VersionResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
