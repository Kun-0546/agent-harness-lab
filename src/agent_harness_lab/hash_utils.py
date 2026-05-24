"""Source 目录 hash 工具 —— 给 LocalPathAdapter (C5+) 算 source_dir_hash。

source_dir_hash 是 local_path source 的可复现指纹:同样目录内容 → 同样 hash。
忽略 VCS / venv / cache / IDE 目录,避免环境噪音(.git ref 变了不算 source 变)。

算法(deterministic): sorted relative path + 内容 sha256 综合。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# 硬编码 ignore (M1);M2+ 考虑 .ahlignore 文件支持
_IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__",
    "node_modules", ".idea", ".vscode", ".pytest_cache",
}
_IGNORE_SUFFIXES = {".pyc", ".pyo"}
_IGNORE_FILES = {".DS_Store", "Thumbs.db"}


def _should_ignore(path: Path, root: Path) -> bool:
    """检查 path 是否在 ignore 范围内。看祖先 dir 名 + 文件名/后缀。"""
    if path.name in _IGNORE_FILES:
        return True
    if path.suffix in _IGNORE_SUFFIXES:
        return True
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    for part in rel.parts:
        if part in _IGNORE_DIRS:
            return True
    return False


def compute_dir_hash(dir_path: Path) -> str:
    """对 dir 内所有文件按 sorted relative path + 内容 sha256 综合。

    reproducible:同样目录内容 → 同样 hash。空 dir → sha256() empty 哈希。
    忽略 _IGNORE_DIRS / _IGNORE_SUFFIXES / _IGNORE_FILES。
    dir 不存在 → FileNotFoundError(由调用方翻成 WorkflowError)。
    """
    if not dir_path.exists():
        raise FileNotFoundError(f"source dir not found: {dir_path}")
    h = hashlib.sha256()
    for p in sorted(dir_path.rglob("*")):
        if not p.is_file():
            continue
        if _should_ignore(p, dir_path):
            continue
        rel = p.relative_to(dir_path).as_posix()
        h.update(rel.encode("utf-8") + b"\0")
        h.update(p.read_bytes() + b"\0")
    return f"sha256:{h.hexdigest()}"
