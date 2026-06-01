"""Benchmark for the Auto Optimize example: passes iff a trace response contains
'GOOD'. The copy-only base only ever emits 'BASE:', so it fails every iteration —
demonstrating a bounded loop that records honest "not passed" iterations and never
promotes. Deterministic, no network.
"""
import json
import sys

ctx = json.load(open(sys.argv[1], encoding="utf-8"))
ok = any("GOOD" in (r.get("response") or "")
         for recs in ctx.get("traces", {}).values() for r in recs)
print(json.dumps({
    "passed": ok,
    "score": 1.0 if ok else 0.0,
    "detail": "passes iff a response contains GOOD",
}))
