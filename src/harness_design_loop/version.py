"""读一个实验的版本 —— 被测系统里摆出来对比的那几个 agent。

版本 = experiments/<编号>/versions/ 目录,一个版本一个文件。
其中一个标为基线(不动,当参照)。格式见 docs/file-formats.md。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_YES = {"是", "yes", "true", "y", "1", "基线"}


def _filled(text: str) -> bool:
    """text 是真内容吗(非空、且不是 <占位符>)。"""
    t = text.strip()
    if not t:
        return False
    if t.startswith("<") and t.endswith(">"):
        return False
    return True


@dataclass
class Version:
    """被测系统里的一个版本。"""

    path: Path
    version_id: str = ""
    is_baseline: bool = False
    what: str = ""       # 这是什么(基线 / 改了什么)
    setup: str = ""      # 接入配置

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        if not self.version_id:
            problems.append("缺 id")
        if not _filled(self.what):
            problems.append("没写「这是什么」")
        if not _filled(self.setup):
            problems.append("没写接入配置")
        return problems


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """切出开头 --- 之间的字段,返回 (字段, 正文)。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fields: dict[str, str] = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([^:：]+)[:：](.*)", line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return fields, text[end + 4:]


def _split_sections(text: str) -> dict[str, str]:
    """按 '## ' 标题把 markdown 切成 {标题: 正文}。"""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def parse_version(path: str | Path) -> Version:
    """解析一个版本文件。"""
    path = Path(path)
    fields, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    sections = _split_sections(body)
    v = Version(path=path)
    v.version_id = fields.get("id", "").strip() or path.stem
    v.is_baseline = fields.get("基线", "").strip().lower() in _YES
    v.what = sections.get("这是什么", "").strip()
    v.setup = sections.get("接入配置", "").strip()
    return v


def load_versions(experiment_dir: str | Path) -> list[Version]:
    """读一个实验的所有版本文件。"""
    experiment_dir = Path(experiment_dir)
    versions_dir = experiment_dir / "versions"
    if not versions_dir.exists():
        raise FileNotFoundError(f"实验没有 versions/ 目录:{experiment_dir}")
    return [parse_version(p) for p in sorted(versions_dir.glob("*.md"))]
