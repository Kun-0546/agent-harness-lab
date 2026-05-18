#!/usr/bin/env python3
"""HTTP无状态 接入 —— 最小样例 agent。

协议:
  - 监听 HTTP,接受 POST。
  - 请求体 {"messages": [{"role", "content"}, ...]} 是到目前为止的完整对话
    ——"无状态"指服务端不记上下文,工具每轮把完整对话都发过来。
  - 返回 {"response": "agent 的回答"}。

启动:python examples/http_stateless_agent.py [端口]   (默认 8765)
connect.md 里这样配:
    ## 类型
    HTTP无状态
    ## 配置
    端点:http://127.0.0.1:8765/

把 reply() 换成你自己的 agent 逻辑。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def reply(messages: list) -> str:
    """样例逻辑:回显最后一句用户话。换成你的真 agent。"""
    last_user = ""
    for m in messages:
        if m.get("role") == "user":
            last_user = m.get("content", "")
    user_turns = sum(1 for m in messages if m.get("role") == "user")
    return f"(第 {user_turns} 轮)我收到了:{last_user}"


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        body = json.dumps({"response": reply(req.get("messages", []))},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # 安静点,不打访问日志
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"HTTP无状态 样例 agent:监听 http://127.0.0.1:{port}/", flush=True)
    HTTPServer(("127.0.0.1", port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
