"""读一个实验的 harness variants —— 被测系统里摆出来对比的几个 harness 设计。

variants = experiments/<编号>/harnesses/ 目录,一个 variant 一个文件。
其中一个标为基线(不动,当参照)。
Variant 可以在「类型」「配置」段里写自己的接入方式;不写就用全局 connect.md。
格式见 docs/file-formats.md。

(注:本模块仍叫 version.py,Phase 3 跟包名一起整理。dataclass 名 Version 同。)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_harness_lab import mdutil
from agent_harness_lab.connect import Connect
from agent_harness_lab.patch import HarnessPatch, parse_patch

_YES = {"是", "yes", "true", "y", "1", "基线"}


@dataclass
class Version:
    """被测系统里的一个版本。"""

    path: Path
    version_id: str = ""
    is_baseline: bool = False
    what: str = ""                          # 这是什么(基线 / 改了什么)
    connect: Connect | None = None          # 版本自带的接入;None = 用全局 connect.md
    # M1 新增:Runtime Materialization 字段;None = legacy 路径,走 connect.md
    runtime_source: str | None = None       # frontmatter 字段,引用 runtime-sources.md 的 name
    patch: HarnessPatch | None = None       # ## Patch 段;runtime_source 未写时为 None
    # v0.5 新增:Harness Package MVP frontmatter 字段
    harness_package: str | None = None      # "<id>@<version>" 引用 harness-packages/

    def validate(self) -> list[str]:
        """返回问题清单;空清单表示没问题。"""
        problems: list[str] = []
        if not self.version_id:
            problems.append("缺 id")
        if not mdutil.is_filled(self.what):
            problems.append("没写「这是什么」")
        if self.connect is not None:
            problems += [f"接入配置:{p}" for p in self.connect.validate()]
        if self.runtime_source and self.patch is not None:
            patch_problems = self.patch.validate()
            # v0.5:variant 引用 harness_package 时,patch 可省略 start_command
            # (package manifest 可供给)。其它 patch 问题仍 surface。最终
            # 双方都缺 start_command 由 workflow.run preflight 抓(此时 Manifest
            # 已加载,可看 manifest.payload_start_command)。
            if self.harness_package:
                patch_problems = [p for p in patch_problems
                                  if "缺 start_command" not in p]
            problems += [f"patch:{p}" for p in patch_problems]
        return problems


def parse_version(path: str | Path) -> Version:
    """解析一个版本文件。"""
    path = Path(path)
    fields, body = mdutil.parse_frontmatter(path.read_text(encoding="utf-8"))
    sections = mdutil.split_sections(body)
    v = Version(path=path)
    v.version_id = fields.get("id", "").strip() or path.stem
    v.is_baseline = fields.get("基线", "").strip().lower() in _YES
    v.what = sections.get("这是什么", "").strip()
    conn_type = sections.get("类型", "").strip()
    if mdutil.is_filled(conn_type):
        v.connect = Connect(
            path=path,
            conn_type=conn_type,
            config=sections.get("配置", "").strip(),
        )
    # M1:runtime_source frontmatter 字段 + ## Patch 段。
    # 不写 runtime_source 时 patch 段忽略(legacy 路径)。
    rs = fields.get("runtime_source", "").strip()
    if rs:
        v.runtime_source = rs
        patch_text = sections.get("Patch", "").strip()
        # variant 在 experiments/<id>/harnesses/V*.md;experiment_dir = path.parent.parent
        experiment_dir = path.parent.parent
        v.patch = parse_patch(patch_text, experiment_dir)
    # v0.5:harness_package frontmatter 字段;格式 <id>@<version>。
    # 这里只 carry 原 string;格式校验 + resolution 由 workflow.run preflight 做
    # (此时 packages index 已加载,可 cross-validate)。
    pkg = fields.get("harness_package", "").strip()
    if pkg:
        v.harness_package = pkg
    return v


def load_versions(experiment_dir: str | Path) -> list[Version]:
    """读一个实验的所有 harness variant 文件。"""
    experiment_dir = Path(experiment_dir)
    harnesses_dir = experiment_dir / "harnesses"
    if not harnesses_dir.exists():
        if (experiment_dir / "versions").exists():
            raise FileNotFoundError(
                f"发现旧目录 versions/,请改名为 harnesses/(Phase 2 命名同步):{experiment_dir}")
        raise FileNotFoundError(f"实验没有 harnesses/ 目录:{experiment_dir}")
    return [parse_version(p) for p in sorted(harnesses_dir.glob("*.md"))]
