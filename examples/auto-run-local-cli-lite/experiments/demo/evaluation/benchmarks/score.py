"""Benchmark evaluator for the Auto Run example.

Reads the evaluation context JSON (argv[1]) — which includes the collected traces
for the track's evidence — and prints a JSON verdict to stdout. Passes iff there is
at least one trace record and every record reported ok. Deterministic, no network.
"""
import json
import sys

ctx = json.load(open(sys.argv[1], encoding="utf-8"))
records = [r for recs in ctx.get("traces", {}).values() for r in recs]
ok = bool(records) and all(r.get("ok") for r in records)
print(json.dumps({
    "passed": ok,
    "score": 1.0 if ok else 0.0,
    "detail": f"{len(records)} trace record(s); all_ok={ok}",
}))
