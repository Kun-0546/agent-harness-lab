"""读 harnesses/V*.md 的 ## Patch 段 —— harness variant 的 patch 配置(M1)。

格式见 docs/runtime-materialization-m1-spec.md §1.2,YAML-like:

  files:
    - target: prompts/system.md
      source: patches/V2/system.md
    - target: config/tools.yaml
      source: patches/V2/tools.yaml
  env:
    HARNESS_MAX_DEPTH: "5"
  start_command: python -m openmanus.agent

不引入 PyYAML 依赖(项目 dependencies=[])。手写 mini-parser 应对这种受控结构。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PatchFile:
    """一个 patch 文件:source_path 的内容会覆盖 target_path。"""

    target_path: str
    source_path: Path
    hash: str = ""

    def compute_hash(self) -> str:
        """读 source_path 内容算 sha256:...;文件不存在返回空串。"""
        if not self.source_path or not self.source_path.exists():
            return ""
        h = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        return f"sha256:{h}"


@dataclass
class HarnessPatch:
    """一个 variant 的 patch:files + env + start_command 三段。"""

    files: list[PatchFile] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    start_command: str | None = None

    def validate(self) -> list[str]:
        """返回问题清单。M1 要求 start_command 必填(不假设默认命令)。"""
        problems: list[str] = []
        if not self.start_command:
            problems.append("缺 start_command(M1 不假设默认命令)")
        for i, f in enumerate(self.files):
            if not f.target_path:
                problems.append(f"files[{i}] 缺 target")
            if not f.source_path or str(f.source_path) == ".":
                problems.append(f"files[{i}]「{f.target_path}」缺 source")
            elif not f.source_path.exists():
                problems.append(
                    f"files[{i}]「{f.target_path}」source 文件不存在:{f.source_path}")
        return problems


def parse_patch(text: str, experiment_dir: Path) -> HarnessPatch:
    """解析 ## Patch 段内容(YAML-like)。

    text 是 ## Patch 段的 body 文本(不含 `## Patch` 标题本身)。
    experiment_dir 是 variant 所在的 experiment 根目录;source: 字段
    相对此目录解析(通常 `patches/<variant_id>/<filename>`)。
    """
    patch = HarnessPatch()
    state = "top"  # top | files | env
    current_file: dict[str, str] = {}

    def _flush_file() -> None:
        if not current_file:
            return
        target = current_file.get("target", "")
        source_rel = current_file.get("source", "")
        source_abs = (experiment_dir / source_rel) if source_rel else Path()
        pf = PatchFile(target_path=target, source_path=source_abs)
        pf.hash = pf.compute_hash()
        patch.files.append(pf)
        current_file.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if indent == 0:
            # top-level key
            _flush_file()
            m = re.match(r"^(\w+)\s*:\s*(.*)$", stripped)
            if not m:
                state = "top"
                continue
            key, val = m.group(1), m.group(2).strip()
            if key == "files":
                state = "files"
            elif key == "env":
                state = "env"
            elif key == "start_command":
                patch.start_command = val
                state = "top"
            else:
                state = "top"
        else:
            # nested(缩进行)
            if state == "files":
                if stripped.startswith("- "):
                    # 新 file item:flush 上一个再开启
                    _flush_file()
                    m = re.match(r"^-\s+(\w+)\s*:\s*(.*)$", stripped)
                    if m:
                        current_file[m.group(1)] = m.group(2).strip()
                else:
                    m = re.match(r"^(\w+)\s*:\s*(.*)$", stripped)
                    if m:
                        current_file[m.group(1)] = m.group(2).strip()
            elif state == "env":
                m = re.match(r"^(\w+)\s*:\s*(.*)$", stripped)
                if m:
                    # 去掉引号(YAML "value" / 'value')
                    patch.env[m.group(1)] = m.group(2).strip().strip("\"'")
    _flush_file()
    return patch
