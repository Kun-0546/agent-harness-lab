"""接入 —— 把 connect 配置变成一个能逐轮对话的 agent 会话。

design-v0.3 §3.2 的四种接入方式,本模块都实现:
- 外部命令行:子进程 + JSON。
- 进程内库:import 一个 callable。
- HTTP无状态:每轮 POST 完整对话历史。
- HTTP有状态:服务端记上下文,只 POST 新一轮 + session id。
"""
from __future__ import annotations

import collections
import importlib
import json
import os
import queue
import shlex
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping

from agent_harness_lab.connect import Connect


class AgentSession:
    """一次跟被测 agent 的多轮会话。各接入方式给一个子类。"""

    def send(self, user_text: str) -> str:
        """发一句用户话,收一句 agent 回答。"""
        raise NotImplementedError

    def close(self) -> None:
        """收尾。"""


def _child_env() -> dict[str, str]:
    """子进程环境:强制 UTF-8,免得中文在 Windows 上炸。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _config_value(connect: Connect, key: str) -> str:
    """从 connect 配置里取 '键:值' 行的值;没有就取第一行非空。"""
    for line in connect.config.splitlines():
        s = line.strip()
        for sep in ("：", ":"):
            if s.startswith(key) and sep in s:
                return s.split(sep, 1)[1].strip()
    for line in connect.config.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _post_json(url: str, payload: dict, timeout: float = 120.0) -> dict:
    """给 url POST 一个 JSON,返回解析后的 JSON 回答。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"agent HTTP {exc.code}:{exc.reason}") from exc


def _extract_reply(data: dict) -> str:
    """从 agent 的 HTTP 回答里抠出回复文本(认 response 或 OpenAI choices 两种)。"""
    if "response" in data:
        return str(data["response"])
    if "choices" in data:
        return str(data["choices"][0]["message"]["content"])
    raise RuntimeError(f"agent 回答里没有 response / choices 字段:{str(data)[:120]}")


try:
    _TURN_TIMEOUT = float(os.environ.get("AHL_AGENT_TIMEOUT", "600"))
except ValueError:
    _TURN_TIMEOUT = 600.0


class _CliSession(AgentSession):
    """外部命令行:起一个子进程,逐轮交换 JSON。

    stdout、stderr 各由一个后台线程持续读:
    - stdout 进队列,send() 等队列,超过 timeout 秒没等到就判卡死、杀进程、抛错。
    - stderr 持续 drain —— 不读会填满 pipe、卡死子进程;留最近几行做报错用。
    timeout 默认 600 秒,可用环境变量 AHL_AGENT_TIMEOUT 改。
    """

    def __init__(self, command: str, timeout: float = _TURN_TIMEOUT):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            command, shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=_child_env(),
        )
        self._lines: queue.Queue = queue.Queue()
        self._stderr_tail: collections.deque = collections.deque(maxlen=20)
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        """后台线程:子进程 stdout 一行行塞进队列,EOF 塞 None。"""
        assert self.proc.stdout
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _drain_stderr(self) -> None:
        """后台线程:持续读 stderr —— 不读会填满 pipe、卡死子进程;留最近几行报错用。"""
        if self.proc.stderr is None:
            return
        for line in self.proc.stderr:
            self._stderr_tail.append(line)

    def send(self, user_text: str) -> str:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps({"input": user_text}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        try:
            line = self._lines.get(timeout=self.timeout)
        except queue.Empty:
            self.proc.kill()
            raise RuntimeError(
                f"agent 这一轮超过 {self.timeout:g} 秒没回话,判定卡死") from None
        if line is None:
            err = "".join(self._stderr_tail).strip()[:200]
            raise RuntimeError(f"agent 没回话(进程已退出):{err}")
        return str(json.loads(line).get("response", ""))

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.proc.kill()


class _SandboxCliSession(AgentSession):
    """Sandbox 子进程模式(C5 LocalPathAdapter 用)—— shell=False + 显式 cwd/env override。

    跟 _CliSession 区别:
    - shell=False:command 走 shlex.split,不走 shell expansion(避免 metachar 注入)
    - cwd 必填:子进程工作目录定为 sandbox path
    - env override:default _child_env merge override (override 值覆盖 default)
    - close():显式关 stdout/stderr pipes 避免 ResourceWarning(legacy _CliSession
      不动,本类 only)

    IPC 协议跟 _CliSession 等价:stdout 一行一个 JSON 回答,stderr drain。
    """

    def __init__(self, command: str, cwd: Path,
                 env_override: Mapping[str, str] | None = None,
                 timeout: float = _TURN_TIMEOUT):
        self.timeout = timeout
        args = shlex.split(command)
        if not args:
            raise RuntimeError(f"start_command 是空的:{command!r}")
        env = _child_env()
        if env_override:
            for k, v in env_override.items():
                env[k] = str(v)
        self.proc = subprocess.Popen(
            args, shell=False, cwd=str(cwd),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env,
        )
        self._lines: queue.Queue = queue.Queue()
        self._stderr_tail: collections.deque = collections.deque(maxlen=20)
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _drain_stderr(self) -> None:
        if self.proc.stderr is None:
            return
        for line in self.proc.stderr:
            self._stderr_tail.append(line)

    def send(self, user_text: str) -> str:
        assert self.proc.stdin
        self.proc.stdin.write(
            json.dumps({"input": user_text}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        try:
            line = self._lines.get(timeout=self.timeout)
        except queue.Empty:
            self.proc.kill()
            raise RuntimeError(
                f"agent 这一轮超过 {self.timeout:g} 秒没回话,判定卡死") from None
        if line is None:
            err = "".join(self._stderr_tail).strip()[:200]
            raise RuntimeError(f"agent 没回话(进程已退出):{err}")
        return str(json.loads(line).get("response", ""))

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.proc.kill()
        finally:
            # 显式关 stdout/stderr pipes —— 避免 ResourceWarning。
            # proc 退出后 stdout/stderr 自然 EOF,reader thread 也已 exit,
            # close 是 safe 的。defensive try/except 防止 race。
            for stream in (self.proc.stdout, self.proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:  # noqa: BLE001
                        pass


class _LibrarySession(AgentSession):
    """进程内库:import 一个 callable,逐轮把完整对话历史传给它。

    config 写 '模块:函数';函数签名 fn(history) -> str,
    history 是 [{"role": "user"/"assistant", "content": ...}, ...]。
    """

    def __init__(self, target: str):
        if ":" not in target:
            raise RuntimeError(f"进程内库配置要写 '模块:函数',收到:{target!r}")
        mod_name, _, fn_name = target.partition(":")
        mod = importlib.import_module(mod_name.strip())
        self.fn = getattr(mod, fn_name.strip())
        self.history: list[dict] = []

    def send(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        resp = str(self.fn(list(self.history)))
        self.history.append({"role": "assistant", "content": resp})
        return resp


class _HttpStatelessSession(AgentSession):
    """HTTP 无状态:每轮把完整对话历史 POST 过去。"""

    def __init__(self, url: str):
        self.url = url
        self.history: list[dict] = []

    def send(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        reply = _extract_reply(_post_json(self.url, {"messages": list(self.history)}))
        self.history.append({"role": "assistant", "content": reply})
        return reply


class _HttpStatefulSession(AgentSession):
    """HTTP 有状态:服务端记上下文,只发新一轮 + session id。"""

    def __init__(self, url: str):
        self.url = url
        self.session_id = ""

    def send(self, user_text: str) -> str:
        data = _post_json(self.url, {"input": user_text, "session_id": self.session_id})
        self.session_id = str(data.get("session_id", self.session_id))
        return _extract_reply(data)


def open_session(connect: Connect) -> AgentSession:
    """按 connect 的接入类型,开一个 agent 会话。"""
    t = connect.conn_type
    if t == "外部命令行":
        return _CliSession(_config_value(connect, "命令"))
    if t == "进程内库":
        return _LibrarySession(_config_value(connect, "模块"))
    if t == "HTTP无状态":
        return _HttpStatelessSession(_config_value(connect, "端点"))
    if t == "HTTP有状态":
        return _HttpStatefulSession(_config_value(connect, "端点"))
    raise ValueError(f"接入类型「{t}」识别不了")
