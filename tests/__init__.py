"""Agent Harness Lab 的单测。

跑:在项目根执行 `python -m unittest discover -s tests -t .`。

测试套件防挂起约定(canonical runner 必须可靠完成):
这个包在任何 test 模块导入前先跑,于是在这里给所有"会起子进程/调 git"的
集成测试设硬上限——保证整套件绝不无限挂起,哪怕在非交互 / 离线 / 受限 sandbox。
- AHL_AGENT_TIMEOUT:agent IPC 单轮上限(产品默认 600s,测试里压到 30s)。
- AHL_GIT_TIMEOUT :git 子进程上限(产品默认 120s,测试里压到 30s)。
- GIT_TERMINAL_PROMPT=0:git 永不在凭据/终端提示上等待输入(CI 防卡的关键)。
用 setdefault:外部已显式设了就尊重外部值(例如想跑更长的真集成)。
"""
import os

os.environ.setdefault("AHL_AGENT_TIMEOUT", "30")
os.environ.setdefault("AHL_GIT_TIMEOUT", "30")
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
os.environ.setdefault("GCM_INTERACTIVE", "never")
