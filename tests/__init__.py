"""Agent Harness Lab 的单测。

跑:在项目根执行 `python -m unittest discover -s tests -t .`。

测试套件防挂起约定(canonical runner 必须可靠完成):
这个包在任何 test 模块导入前先跑,于是在这里给所有"会起子进程/调 git"的
集成测试设硬上限——保证整套件绝不无限挂起,哪怕在非交互 / 离线 / 受限 sandbox。
- AHL_AGENT_TIMEOUT:agent IPC 单轮上限(产品默认 600s,测试里压到 30s)。
- AHL_GIT_TIMEOUT :git 子进程上限(产品默认 120s,测试里压到 30s)。
- AHL_CONNECTOR_TIMEOUT:Auto Mode 连接器单 case 上限(产品默认 60s,测试里压到 30s)。
- GIT_TERMINAL_PROMPT=0:git 永不在凭据/终端提示上等待输入(CI 防卡的关键)。
用 setdefault:外部已显式设了就尊重外部值(例如想跑更长的真集成)。

自诊断:若整套件运行超过 SELF-DIAG 秒(远小于 CI 的 300s 上限),faulthandler 把
所有线程栈打到 stderr——一旦在某环境又挂住,这份 dump 会精确指出主线程卡在哪一行,
不必再靠猜。正常跑(~20s)进程早已退出,定时器随之取消,不会打印。
"""
import faulthandler
import os
import tempfile

os.environ.setdefault("AHL_AGENT_TIMEOUT", "30")
os.environ.setdefault("AHL_GIT_TIMEOUT", "30")
os.environ.setdefault("AHL_CONNECTOR_TIMEOUT", "30")
# Evaluation benchmark + Auto Optimize mutation subprocesses (product defaults 60s):
# bound them too. Earlier these were unbounded in tests, so a stalled/starved
# benchmark or mutation could run toward a 60s wall and stack across iterations —
# the 3.13 reviewer-env "evaluation/benchmarks/b.py high CPU" report.
os.environ.setdefault("AHL_EVAL_TIMEOUT", "30")
os.environ.setdefault("AHL_OPTIMIZE_TIMEOUT", "30")
os.environ.setdefault("AHL_AGENT_CLOSE_GRACE", "3")
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
os.environ.setdefault("GCM_INTERACTIVE", "never")

try:
    # 90s: fires a stack dump BEFORE a 120s targeted-combo timeout (the earlier 150s
    # never fired under a 120s runner kill) and well below the 300s full-suite kill.
    # A normal ~20s run cancels the timer on exit, so nothing prints.
    _SELF_DIAG = float(os.environ.get("AHL_TEST_HANG_DUMP_SECONDS", "90"))
except ValueError:
    _SELF_DIAG = 90.0
if _SELF_DIAG > 0:
    # Dump every interval while hung. Default to a FILE — stderr dumps were not visible
    # in a reviewer container — so a residual hang always leaves a capturable trace at
    # AHL_TEST_HANG_DUMP_FILE (default: <tempdir>/ahl_test_hang_dump.txt). A normal run
    # cancels the timer at exit and leaves the file empty.
    _dump_path = os.environ.get("AHL_TEST_HANG_DUMP_FILE") or os.path.join(
        tempfile.gettempdir(), "ahl_test_hang_dump.txt")
    try:
        _dump_file = open(_dump_path, "w", encoding="utf-8")  # kept open for the timer
        faulthandler.dump_traceback_later(_SELF_DIAG, repeat=True, file=_dump_file)
    except OSError:
        faulthandler.dump_traceback_later(_SELF_DIAG, repeat=True)
