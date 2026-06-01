"""Deterministic local_cli agent for the Auto Optimize (copy-only) example.

Echoes "BASE:<input>". The benchmark wants "GOOD", so the base never passes — which
is the point: copy-only candidates are identical copies of the incumbent, so the
bounded loop runs to its stop condition without promoting anything. No network.
"""
import json
import sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    sys.stdout.write(json.dumps({"response": "BASE:" + msg.get("input", "")}) + "\n")
    sys.stdout.flush()
