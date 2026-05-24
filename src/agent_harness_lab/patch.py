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
import json
import re
import shutil
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
        if source_rel:
            source_abs = _safe_source_path(experiment_dir, source_rel)
        else:
            source_abs = Path()
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


def _safe_target_path(sandbox_dir: Path, target_path: str) -> Path:
    """防 path traversal:target_path 越出 sandbox 抛 RuntimeError。

    用 Path.resolve() + relative_to() 检测(不仅字符串 startswith,避免符号链接 /
    `..` segment / 绝对路径 等多种 traversal 路径绕过)。返回 resolve 后的
    target 绝对路径。

    apply_patch 运行时使用 → RuntimeError;parse_patch 解析时使用
    _safe_source_path → ValueError(让 _safe_call 自然 catch)。
    """
    sandbox_root = sandbox_dir.resolve()
    target_abs = (sandbox_root / target_path).resolve()
    try:
        target_abs.relative_to(sandbox_root)
    except ValueError as exc:
        raise RuntimeError(
            f"patch target_path 越出 sandbox: {target_path}") from exc
    return target_abs


def _safe_source_path(experiment_dir: Path, source_rel: str) -> Path:
    """防 path traversal:patch source 必须在 experiment root 内。

    用 Path.resolve() + relative_to() 检测,覆盖 `..` 段 / 绝对路径等 traversal。
    parse 时使用 → ValueError(让 _safe_call 自然翻成 WorkflowError)。
    """
    exp_root = experiment_dir.resolve()
    source_abs = (exp_root / source_rel).resolve()
    try:
        source_abs.relative_to(exp_root)
    except ValueError as exc:
        raise ValueError(
            f"patch source 越出 experiment: {source_rel}") from exc
    return source_abs


def apply_patch(patch: HarnessPatch, sandbox_dir: Path) -> list[PatchFile]:
    """对 sandbox_dir 应用 patch.files —— 每个 PatchFile 覆盖对应 target。

    target 父目录自动 mkdir。覆盖原 source dir 内的同名文件(整文件替换)。
    target_path 越出 sandbox 抛 RuntimeError (path traversal 防御)。
    任一 source 文件不存在 → FileNotFoundError(由 LocalPathAdapter 翻成
    WorkflowError 显示给用户)。返回 applied 的 PatchFile 列表。
    """
    applied: list[PatchFile] = []
    for pf in patch.files:
        if not pf.source_path.exists():
            raise FileNotFoundError(
                f"patch source 不存在: {pf.source_path} (target: {pf.target_path})")
        target_abs = _safe_target_path(sandbox_dir, pf.target_path)
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(pf.source_path, target_abs)
        applied.append(pf)
    return applied


def compute_patch_hash(patch: HarnessPatch) -> str:
    """对 patch 算 deterministic hash —— spec §2.1 harness_patch.patch_hash。

    输入: sorted [target_path + file_hash] + env JSON(sort_keys) + start_command
    输出: sha256:<64 hex>。

    reproducible:同样 patch 内容 → 同样 hash。env/start_command 任一变化都触发。
    """
    h = hashlib.sha256()
    for pf in sorted(patch.files, key=lambda x: x.target_path):
        h.update(pf.target_path.encode("utf-8") + b"\0")
        h.update(pf.hash.encode("utf-8") + b"\0")
    h.update(
        json.dumps(patch.env, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\0")
    h.update((patch.start_command or "").encode("utf-8") + b"\0")
    return f"sha256:{h.hexdigest()}"
