"""读 workspace 根的 runtime-sources.md —— harness variant 可绑定的 runtime 来源。

M1 范围:local_path / git_repo 两种 source 类型(spec §0.1)。
格式见 docs/runtime-materialization-m1-spec.md §1.1。

向后兼容:文件不存在 → 返回空 list,所有 variant 走 legacy connect 路径。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from agent_harness_lab import mdutil

RUNTIME_SOURCE_TYPES = ["local_path", "git_repo"]

# M1 严格白名单:每个 type 只允许声明的字段,unknown field 抛 ValueError。
# 避免 silently 把 typo / 未来字段塞进 config dict。
_ALLOWED_FIELDS = {
    "local_path": frozenset({"path"}),
    "git_repo": frozenset({"url", "ref"}),
}

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class RuntimeSource:
    """workspace 里声明的一个 runtime source。"""

    name: str
    type: str
    config: dict[str, str] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        if not self.name:
            problems.append("缺 name")
        if not self.type:
            problems.append("缺 type")
        elif self.type not in RUNTIME_SOURCE_TYPES:
            problems.append(
                f"type「{self.type}」识别不了"
                f"(M1 范围:{' / '.join(RUNTIME_SOURCE_TYPES)})")
        elif self.type == "local_path":
            if not self.config.get("path"):
                problems.append("local_path 缺 path")
        elif self.type == "git_repo":
            if not self.config.get("url"):
                problems.append("git_repo 缺 url")
            if not self.config.get("ref"):
                problems.append("git_repo 缺 ref")
        return problems


def parse_runtime_sources(path: str | Path) -> list[RuntimeSource]:
    """读 runtime-sources.md,解析成 RuntimeSource 列表。

    - 文件不存在 → 返回空 list(不抛错;legacy 路径全用)
    - 文件存在但 0 个 source 段 → 抛 ValueError
    - source name 重复(同名 `##` heading) → 抛 ValueError(M1 强制 unique)
    - 不识别的 type → 抛 ValueError(M1 边界硬控)
    - 不在白名单的 field → 抛 ValueError(避免 silently 收 typo / 未来字段)
    """
    path = Path(path)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")

    # 1. duplicate name detection(mdutil.split_sections 会 silent dedup,
    #    在它前面 raw 扫一遍 heading,显式抓重复)
    raw_names = [m.strip() for m in _HEADING_RE.findall(text)]
    if len(raw_names) != len(set(raw_names)):
        dups = [n for n, c in Counter(raw_names).items() if c > 1]
        raise ValueError(
            f"runtime source name 重复:{', '.join(dups)}"
            f"(每个 ## name 必 unique):{path}")

    sections = mdutil.split_sections(text)
    if not sections:
        raise ValueError(
            f"runtime-sources.md 存在但没有 source 段(## <name>):{path}")
    sources: list[RuntimeSource] = []
    for name, body in sections.items():
        fields: dict[str, str] = {}
        for line in body.splitlines():
            m = re.match(r"([^:：]+)[:：](.*)", line)
            if m:
                fields[m.group(1).strip()] = m.group(2).strip()
        type_ = fields.pop("type", "")
        if type_ and type_ not in RUNTIME_SOURCE_TYPES:
            raise ValueError(
                f"runtime source 「{name}」 type「{type_}」识别不了"
                f"(M1 范围:{' / '.join(RUNTIME_SOURCE_TYPES)})")
        # 白名单校验:只允许这个 type 声明过的 field,unknown 一律抛错。
        if type_ in _ALLOWED_FIELDS:
            allowed = _ALLOWED_FIELDS[type_]
            unknown = sorted(set(fields.keys()) - allowed)
            if unknown:
                raise ValueError(
                    f"runtime source 「{name}」 ({type_}) 含未知字段:"
                    f"{', '.join(unknown)}"
                    f"(只允许:{' / '.join(sorted(allowed))})")
        sources.append(RuntimeSource(name=name, type=type_, config=fields))
    return sources


def validate_variant_source_refs(
    variant_refs: list[tuple[str, str | None]],
    sources: list[RuntimeSource],
) -> list[str]:
    """检查 variants 引用的 runtime_source 名是否都在 sources 列表里。

    variant_refs 是 (variant_id, runtime_source_ref) 对的列表。
    ref 为 None 时跳过(legacy);ref 非 None 但不在 sources → 报问题。

    返回问题清单;空清单 = 没问题。workflow.run 在 preflight 阶段调用此函数
    cross-validate。
    """
    available = {s.name for s in sources}
    problems: list[str] = []
    for vid, ref in variant_refs:
        if ref and ref not in available:
            problems.append(
                f"variant 「{vid}」 的 runtime_source「{ref}」"
                f"不在 runtime-sources.md"
                f"(可用:{', '.join(sorted(available)) if available else '(空)'})")
    return problems
