#!/usr/bin/env python3
"""HTTP有状态 接入 —— 最小样例 agent。

协议:
  - 监听 HTTP,接受 POST。
  - 请求体 {"input": "用户这句话", "session_id": "会话 id"}
    ——只发新一轮的话 + 会话 id;"有状态"指服务端自己记每个会话的上下文。
  - 返回 {"response": "agent 的回答", "session_id": "会话 id"}。
  - 第一轮 session_id 可能为空,服务端分配一个并回传,之后工具会带上它。

启动:python examples/http_stateful_agent.py [端口]   (默认 8766)
connect.md 里这样配:
    ## 类型
    HTTP有状态
    ## 配置
    端点:http://127.0.0.1:8766/

把 reply() 换成你自己的 agent 逻辑。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 会话 id -> 该会话到目前为止的用户话。服务端自己记上下文。
_SESSIONS: dict = {}


def reply(user_input: str, history: list) -> str:
    """样例逻辑:回显这一轮用户话。换成你的真 agent。"""
    return f"(第 {len(history)} 轮)我收到了:{user_input}"


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        sid = req.get("session_id") or f"s{len(_SESSIONS) + 1}"
        history = _SESSIONS.setdefault(sid, [])
        history.append(req.get("input", ""))
        body = json.dumps(
            {"response": reply(history[-1], history), "session_id": sid},
            ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # 安静点,不打访问日志
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    print(f"HTTP有状态 样例 agent:监听 http://127.0.0.1:{port}/", flush=True)
    HTTPServer(("127.0.0.1", port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
