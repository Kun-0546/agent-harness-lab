"""打分 —— 拿评分器按 rubric 给对话打分。

两种评分器实现:
- stub_grader —— 本地桩,不调模型,给伪分,只为验代码。
- llm_grader  —— LLM Judge,调一个 OpenAI 兼容模型按 rubric 打分。
                 模型 / 端点 / key 从环境变量读:HDL_JUDGE_BASE_URL /
                 HDL_JUDGE_MODEL / HDL_JUDGE_API_KEY。

跑和打分分开:打分便宜、能重打(换 rubric / 换模型再打一遍)。
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass

from harness_design_loop import llm
from harness_design_loop.rubric import Rubric

# 评分器:给 (rubric, 版本, case, 对话 transcript) -> {维度名: 分(1-10)}。
Grader = Callable[[Rubric, str, str, list], dict]


@dataclass
class CaseScore:
    """一个版本、一个 case 的打分。"""

    version_id: str
    case_id: str
    dimensions: dict[str, float]   # 维度名 -> 分(1-10)
    total: float = 0.0             # 按权重加权后的总分


def stub_grader(rubric: Rubric, version_id: str, case_id: str,
                transcript: list) -> dict[str, float]:
    """本地桩评分器 —— 不调模型,给稳定的伪分,只为验代码。"""
    agent_text = "".join(t.get("agent", "") for t in transcript)
    out: dict[str, float] = {}
    for d in rubric.dimensions:
        key = f"{version_id}|{case_id}|{d.name}|{len(transcript)}|{len(agent_text)}".encode("utf-8")
        h = int(hashlib.sha1(key).hexdigest(), 16)
        out[d.name] = round(4.0 + (h % 61) / 10.0, 1)
    return out


def _transcript_text(transcript: list) -> str:
    lines = []
    for t in transcript:
        lines.append(f"[第 {t.get('turn', '?')} 轮] 用户:{t.get('user', '')}")
        lines.append(f"           agent:{t.get('agent', '')}")
    return "\n".join(lines)


def build_judge_prompt(rubric: Rubric, transcript: list) -> str:
    """拼 LLM Judge 的打分 prompt。"""
    dims = "\n".join(f"- {d.name}:{d.description}" for d in rubric.dimensions)
    names = "、".join(d.name for d in rubric.dimensions)
    return (
        "你是严格的评分员。下面是被测 agent 与用户的一段对话。\n"
        "请按给定维度,各打 1-10 分(1 最差、10 最好)。\n\n"
        f"【对话】\n{_transcript_text(transcript)}\n\n"
        f"【维度】\n{dims}\n\n"
        f"只输出一个 JSON 对象,键是维度名({names}),值是 1-10 的数。别写别的。"
    )


def parse_judge_response(text: str, rubric: Rubric) -> dict[str, float]:
    """从 LLM 回答里抠出 {维度名: 分}。"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"评分模型没返回 JSON:{text.strip()[:120]}")
    data = json.loads(text[start:end + 1])
    out: dict[str, float] = {}
    for d in rubric.dimensions:
        if d.name in data:
            try:
                out[d.name] = float(data[d.name])
            except (TypeError, ValueError):
                pass
    missing = [d.name for d in rubric.dimensions if d.name not in out]
    if missing:
        raise ValueError(f"评分模型漏了维度:{'、'.join(missing)}")
    return out


def _call_llm(prompt: str) -> str:
    """调评分模型。端点 / 模型 / key 从 HDL_JUDGE_* 环境变量读。"""
    base = os.environ.get("HDL_JUDGE_BASE_URL", "")
    model = os.environ.get("HDL_JUDGE_MODEL", "")
    key = os.environ.get("HDL_JUDGE_API_KEY", "")
    if not (base and model and key):
        raise RuntimeError(
            "没配评分模型 —— 设环境变量 "
            "HDL_JUDGE_BASE_URL / HDL_JUDGE_MODEL / HDL_JUDGE_API_KEY")
    return llm.chat(base, model, key, prompt)


def llm_grader(rubric: Rubric, version_id: str, case_id: str,
               transcript: list) -> dict[str, float]:
    """LLM Judge 评分器 —— 调真模型按 rubric 打分。"""
    return parse_judge_response(_call_llm(build_judge_prompt(rubric, transcript)), rubric)


def score_run(rubric: Rubric, runs: list[dict], grader: Grader = stub_grader) -> list[CaseScore]:
    """给一次 run 的所有对话打分(跳过 run 出错的)。"""
    raw = {d.name: (d.weight if d.weight is not None else 0.0) for d in rubric.dimensions}
    total_w = sum(raw.values())
    if total_w > 0:
        weight = {k: v / total_w for k, v in raw.items()}
    elif raw:
        weight = {k: 1.0 / len(raw) for k in raw}
    else:
        weight = {}

    scores: list[CaseScore] = []
    for r in runs:
        if r.get("error"):
            continue
        vid = r.get("version_id", "")
        cid = r.get("case_id", "")
        dims = grader(rubric, vid, cid, r.get("transcript", []))
        total = round(sum(dims.get(name, 0.0) * w for name, w in weight.items()), 2)
        scores.append(CaseScore(vid, cid, dims, total))
    return scores
