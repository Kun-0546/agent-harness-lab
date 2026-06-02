"""Benchmark evaluator — correctness AND conciseness, per (harness, case).

Reads the evaluation context JSON (argv[1]): `cases` (each with its required key
term in `expect`) and `traces` (every harness's response, tagged with harness_id +
case_id). An answer passes only if it is correct AND concise:

    passed = (required key term present)
             AND (response length <= MAX_CHARS)
             AND (filler-phrase count <= MAX_FILLER)

So a correct-but-bloated answer fails (too long / too much filler); a correct-and-
direct answer passes. Emits one record per (harness, case). Deterministic, no network.
"""
import json
import sys

MAX_CHARS = 120
MAX_FILLER = 1
FILLER = [
    "thank you so much", "thanks for asking", "we truly appreciate",
    "we genuinely appreciate", "please note that", "as always", "rest assured",
    "kindly", "at your earliest convenience",
]

ctx = json.load(open(sys.argv[1], encoding="utf-8"))
expect = {c.get("id"): str(c.get("expect", ""))
          for c in ctx.get("cases", []) if isinstance(c, dict)}

records = []
for recs in ctx.get("traces", {}).values():
    for r in recs:
        if not isinstance(r, dict):
            continue
        cid, hid = r.get("case_id"), r.get("harness_id")
        resp = r.get("response") or ""
        low = resp.lower()
        kw = expect.get(cid, "")
        kw_hit = (kw.lower() in low) if kw else False
        within = len(resp) <= MAX_CHARS
        fillers = sum(1 for f in FILLER if f in low)
        ok = kw_hit and within and fillers <= MAX_FILLER
        if ok:
            detail = f"correct & concise ({len(resp)} chars, {fillers} filler)"
        else:
            reasons = []
            if not kw_hit:
                reasons.append(f"missing key term '{kw}'")
            if not within:
                reasons.append(f"too long ({len(resp)} > {MAX_CHARS} chars)")
            if fillers > MAX_FILLER:
                reasons.append(f"{fillers} filler phrases (> {MAX_FILLER})")
            detail = "; ".join(reasons)
        records.append({"case_id": cid, "harness_id": hid,
                        "passed": ok, "score": 1.0 if ok else 0.0, "detail": detail})

print(json.dumps({"records": records}))
