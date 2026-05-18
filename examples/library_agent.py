#!/usr/bin/env python3
"""进程内库 接入 —— 最小样例 agent。

协议:
  - 暴露一个函数 respond(history) -> str。
  - history 是到目前为止的完整对话:
    [{"role": "user"/"assistant", "content": "..."}, ...]
  - 工具每轮把完整 history 传进来,你返回 agent 这一轮的回答。

connect.md 里这样配:
    ## 类型
    进程内库
    ## 配置
    模块:library_agent:respond
  (确保这个模块在 Python 的 import 路径上 —— 设 PYTHONPATH,
   或直接把这个文件放进你的项目里。)

把 respond() 换成你自己的 agent 逻辑。
"""
from __future__ import annotations


def respond(history: list[dict]) -> str:
    """样例逻辑:回显最后一句用户话。换成你的真 agent。"""
    last_user = ""
    for turn in history:
        if turn.get("role") == "user":
            last_user = turn.get("content", "")
    user_turns = sum(1 for t in history if t.get("role") == "user")
    return f"(第 {user_turns} 轮)我收到了:{last_user}"
