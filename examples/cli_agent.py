#!/usr/bin/env python3
"""外部命令行 接入 —— 最小样例 agent。

协议:
  - 工具起这个进程,一直留着,直到一段对话结束。
  - 每一轮:工具往 stdin 写一行 JSON {"input": "用户这句话"};
            你往 stdout 写一行 JSON {"response": "agent 的回答"}。

connect.md 里这样配:
    ## 类型
    外部命令行
    ## 配置
    命令:python examples/cli_agent.py

把 reply() 换成你自己的 agent 逻辑就行。
"""
import json
import sys

for _stream in (sys.stdin, sys.stdout):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def reply(user_input: str, turn: int) -> str:
    """样例逻辑:把收到的话回显一遍。换成你的真 agent。"""
    return f"(第 {turn} 轮)我收到了:{user_input}"


def main() -> None:
    turn = 1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        out = {"response": reply(msg.get("input", ""), turn)}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        turn += 1


if __name__ == "__main__":
    main()
