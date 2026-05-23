"""读文件格式的共用助手 —— Markdown 区块、frontmatter、占位符判断。

program / testset / rubric / version / connect / simulator 各模块共用这一处,
不再各抄一份。
"""
from __future__ import annotations

import re


def is_filled(text: str) -> bool:
    """text 是真内容吗(非空、且不是 <占位符>)。"""
    t = text.strip()
    if not t:
        return False
    if t.startswith("<") and t.endswith(">"):
        return False
    return True


def split_sections(text: str) -> dict[str, str]:
    """按 '## ' 标题把 markdown 切成 {标题: 正文}。dict 保插入序。"""
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


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """切出开头 --- 之间的字段,返回 (字段, 正文)。没有 frontmatter 则字段为空。"""
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
