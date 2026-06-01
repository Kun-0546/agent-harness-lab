"""Tiny deterministic local_cli agent for the Auto Run example.

Protocol (local_cli / stdin_json): read one JSON object per line from stdin
({"input": "..."}), write one JSON object per line to stdout ({"response": "..."}),
flushing after each. It also writes an artifact under produced/ so the example
exercises artifact collection. No network, no external dependencies.
"""
import json
import os
import sys

os.makedirs("produced", exist_ok=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    text = msg.get("input", "")
    with open("produced/out.txt", "w", encoding="utf-8") as f:
        f.write("handled:" + text)
    sys.stdout.write(json.dumps({"response": "echo:" + text}) + "\n")
    sys.stdout.flush()
