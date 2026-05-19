"""Designer Agent —— V2 里据 brief 起草整套实验定义。

输入:一份 brief(人写的意图)+ goal.md 原文。
输出:一个 DraftPackage —— program / versions / 测试集 / rubric / 模拟器 的内容。

- stub_designer —— 本地桩,出一套写死但合法的实验,验 draft 流程用。
- llm_designer  —— 真 Designer,两次调用:brief+goal → program,program+brief → 其余。
                   模型 / 端点 / key 从 HDL_DESIGNER_* 环境变量读。

设计依据:docs/v2-minimal-spec.md §4。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from harness_design_loop import llm
from harness_design_loop.brief import Brief


class DesignerError(Exception):
    """Designer 起草失败 —— 消息给用户看;workflow 接住转成 WorkflowError。"""


@dataclass
class DraftPackage:
    """Designer 起草出的一套实验定义(还没落盘)。"""

    program: str                   # program.md 内容
    versions: dict[str, str]       # {"V1.md": 内容, "V2.md": 内容}
    cases: dict[str, str]          # {"D-01.md": 内容, ...}
    rubric: str                    # rubric.md 内容
    simulator: str                 # 模拟器.md 内容


# ---- 本地桩 ----

def _sentence(text: str) -> str:
    """收尾成一句:去首尾空白,没有句末标点才补一个句号(避免拼出「。。」)。"""
    text = text.strip()
    return text if text[-1:] in "。.!?！？" else text + "。"


def stub_designer(brief: Brief, goal: str) -> DraftPackage:
    """桩 Designer:出一套写死但合法的实验,不调模型,验 draft 流程用。

    内容会带上 brief 的字段(改动 / 红线等),不至于完全脱节。
    """
    program = (
        "# 实验 · program\n\n"
        f"## 假设\n{brief.change or '验证一个改动'} —— 看它让 agent 变好还是变差。\n\n"
        "## 声明\n"
        "- 环境:无\n"
        "- 对话模式:模拟\n"
        "- 状态:重置\n"
        "- 评分:本地桩\n"
        "- 运行模式:人评\n"
        "- 对比方式:对基线\n\n"
        "## 留/丢规则\n人评模式,留空。\n\n"
        "## 喊人规则\n人评模式,留空。\n"
    )
    versions = {
        "V1.md": ("---\nid: V1\n基线: 是\n---\n"
                  "## 这是什么\n基线版:改动前的 agent。\n"),
        "V2.md": ("---\nid: V2\n基线: 否\n---\n"
                  f"## 这是什么\n改动版:{_sentence(brief.change or '待填')}\n"),
    }
    cases = {
        "D-01.md": ("---\nid: D-01\nmax_turns: 4\n---\n"
                    f"## 起始输入\n{_sentence(brief.optimize or '帮我处理一个典型任务')}\n\n"
                    "## 完成标准\nagent 给出可用、扣题的回应。\n"),
    }
    rubric = (
        "# rubric\n\n"
        f"## 表现\n权重: 0.5\n{_sentence(brief.care or '回答好不好')}\n\n"
        f"## 红线\n权重: 0.5\n{brief.redlines or '不该出现的退化'} —— 退化即扣分。\n"
    )
    simulator = (
        "# 模拟器\n\n"
        "## 人设\n一个普通用户,沟通直接、会追问。\n\n"
        "## 背景知识\n(无)\n\n"
        "## 追问策略\n盯没答透的点追问,两三轮后收尾。\n"
    )
    return DraftPackage(program=program, versions=versions, cases=cases,
                        rubric=rubric, simulator=simulator)


# ---- 真 Designer(调模型)----

_FILE_MARKER = re.compile(r"^===\s*(.+?)\s*===\s*$", re.MULTILINE)


def _split_files(text: str) -> dict[str, str]:
    """把 '=== 文件名 ===' 分隔的多文件输出切成 {文件名: 内容}。"""
    parts = _FILE_MARKER.split(text)   # [前言, 名1, 内容1, 名2, 内容2, ...]
    files: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        files[parts[i].strip()] = parts[i + 1].strip() + "\n"
    return files


def _designer_env() -> tuple[str, str, str]:
    base = os.environ.get("HDL_DESIGNER_BASE_URL", "")
    model = os.environ.get("HDL_DESIGNER_MODEL", "")
    key = os.environ.get("HDL_DESIGNER_API_KEY", "")
    if not (base and model and key):
        raise DesignerError(
            "没配 Designer 模型 —— 设环境变量 "
            "HDL_DESIGNER_BASE_URL / HDL_DESIGNER_MODEL / HDL_DESIGNER_API_KEY")
    return base, model, key


def _call1_prompt(brief: Brief, goal: str) -> str:
    return (
        "你是 AI 产品实验的设计助手。据下面的 brief 和总目标,写出实验的 program.md。\n\n"
        f"【总目标 goal】\n{goal or '(空)'}\n\n"
        f"【brief】\n想优化:{brief.optimize}\n要验证的改动:{brief.change}\n"
        f"最在意:{brief.care}\n不能牺牲(红线):{brief.redlines}\n"
        f"怎么比:{brief.compare or '(没指定,你定:对基线 或 线性迭代)'}\n\n"
        "program.md 严格照这个格式:\n"
        "# 实验 · program\n\n## 假设\n<这次想验证什么>\n\n"
        "## 声明\n- 环境:无\n- 对话模式:模拟\n- 状态:重置\n"
        "- 评分:LLM Judge\n- 运行模式:人评\n- 对比方式:对基线\n\n"
        "## 留/丢规则\n人评模式,留空。\n\n## 喊人规则\n人评模式,留空。\n\n"
        "只输出 program.md 的内容。"
    )


def _call2_prompt(program: str, brief: Brief) -> str:
    return (
        "下面是一份实验的 program.md。据它写出配套的版本、测试集、rubric、模拟器。\n\n"
        f"【program.md】\n{program}\n\n"
        f"【brief 红线】\n{brief.redlines}\n\n"
        "输出下列文件,每个文件前用一行 `=== 文件名 ===` 标注,严格照格式:\n\n"
        "=== versions/V1.md ===\n---\nid: V1\n基线: 是\n---\n## 这是什么\n<基线版说明>\n\n"
        "=== versions/V2.md ===\n---\nid: V2\n基线: 否\n---\n## 这是什么\n<改动版说明>\n\n"
        "=== 测试集/D-01.md ===\n---\nid: D-01\nmax_turns: 6\n---\n"
        "## 起始输入\n<开场用户消息>\n\n## 完成标准\n<可选>\n\n"
        "(2-4 个 case,文件名 D-01、D-02……)\n\n"
        "=== rubric.md ===\n# rubric\n\n## <维度名>\n权重: <0-1,各维度之和为 1>\n"
        "<这个维度判什么>\n(其中一个维度对应 brief 的红线)\n\n"
        "=== 模拟器.md ===\n# 模拟器\n\n## 人设\n<扮谁>\n\n"
        "## 背景知识\n<可空>\n\n## 追问策略\n<怎么追问>\n"
    )


def llm_designer(brief: Brief, goal: str) -> DraftPackage:
    """真 Designer:两次调用模型,起草整套实验。"""
    base, model, key = _designer_env()
    try:
        program = llm.chat(base, model, key, _call1_prompt(brief, goal)).strip() + "\n"
        raw = llm.chat(base, model, key, _call2_prompt(program, brief))
    except RuntimeError as e:
        raise DesignerError(f"Designer 调模型失败:{e}") from e

    files = _split_files(raw)
    versions = {k.split("/")[-1]: v for k, v in files.items() if "versions/" in k}
    cases = {k.split("/")[-1]: v for k, v in files.items() if "测试集/" in k}
    rubric = next((v for k, v in files.items() if k.endswith("rubric.md")), "")
    simulator = next((v for k, v in files.items() if "模拟器" in k), "")
    if not (versions and cases and rubric and simulator):
        raise DesignerError(
            "Designer 输出解析不全 —— 缺 versions / 测试集 / rubric / 模拟器 之一")
    return DraftPackage(program=program, versions=versions, cases=cases,
                        rubric=rubric, simulator=simulator)


def design(brief: Brief, goal: str, use_llm: bool) -> DraftPackage:
    """起草一套实验定义。use_llm 决定走真 Designer 还是本地桩。"""
    return llm_designer(brief, goal) if use_llm else stub_designer(brief, goal)
