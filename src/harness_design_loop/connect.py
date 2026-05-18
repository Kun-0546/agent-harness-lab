"""读「接入」配置 —— 工具怎么接到被测 agent。

connect.md 放在工作目录根,一次配好(design-v0.3 §3.2 的四种接入方式)。
格式见 docs/file-formats.md。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness_design_loop import mdutil

CONNECT_TYPES = ["进程内库", "外部命令行", "HTTP无状态", "HTTP有状态"]


@dataclass
class Connect:
    """接入配置。"""

    path: Path
    conn_type: str = ""      # 四种接入方式之一
    config: str = ""         # 类型相关的配置(命令 / URL / 模块路径)

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        if not mdutil.is_filled(self.conn_type):
            problems.append("没写接入类型")
        elif self.conn_type not in CONNECT_TYPES:
            problems.append(
                f"接入类型「{self.conn_type}」识别不了(应为:{' / '.join(CONNECT_TYPES)})")
        if not mdutil.is_filled(self.config):
            problems.append("没写配置")
        return problems


def parse_connect(path: str | Path) -> Connect:
    """读 connect.md,解析成 Connect。"""
    path = Path(path)
    sections = mdutil.split_sections(path.read_text(encoding="utf-8"))
    return Connect(
        path=path,
        conn_type=sections.get("类型", "").strip(),
        config=sections.get("配置", "").strip(),
    )
