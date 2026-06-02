"""Harness B — "concise alternative".

The same local_cli agent contract as Harness A, answering the same FAQ — but each
answer is short, direct, and free of filler while still containing the key term.
Same information, leaner delivery. Writes produced/answer.txt. Deterministic, no network.
"""
import json
import os
import sys

# Correct answers, short and direct, no filler.
ANSWERS = {
    "password": "Reset your password in Settings -> Security.",
    "hours": "Support is available 24/7.",
    "cancel": "Cancel anytime in Settings -> Billing.",
}


def answer(question):
    q = question.lower()
    if "password" in q or "reset" in q:
        return ANSWERS["password"]
    if "hour" in q or "support" in q:
        return ANSWERS["hours"]
    if "cancel" in q:
        return ANSWERS["cancel"]
    return "We will get back to you shortly."


os.makedirs("produced", exist_ok=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    ans = answer(msg.get("input", ""))
    with open("produced/answer.txt", "w", encoding="utf-8") as f:
        f.write(ans)
    sys.stdout.write(json.dumps({"response": ans}) + "\n")
    sys.stdout.flush()
