#!/usr/bin/env python3
"""Deterministic sample agent for the Agent Harness Lab product-flow demo.

Protocol (matches `examples/cli_agent.py` and connect.md "外部命令行"):
- stdin: one JSON line per turn: {"input": "<user message>"}
- stdout: one JSON line per turn: {"response": "<agent reply>"}

Behavior:
- Read `prompts/system.md` (relative to CWD, which is the materialized
  sandbox directory when launched by `ahl run`) once at startup.
- Prepend the stripped prompt content (in brackets) to every response.
- No randomness, no model calls — reproducible across runs.

Different system.md content → different responses → different stub_grader
hashes → measurable variant delta.
"""
import json
import sys
from pathlib import Path

for _s in (sys.stdin, sys.stdout):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

_PROMPT = ""
_PROMPT_PATH = Path("prompts") / "system.md"
if _PROMPT_PATH.exists():
    _PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()


def reply(user_input: str) -> str:
    return f"[{_PROMPT}] {user_input}"


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        out = {"response": reply(msg.get("input", ""))}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
