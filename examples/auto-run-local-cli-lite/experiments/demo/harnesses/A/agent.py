"""Harness A — "verbose baseline".

A local_cli agent (stdin_json protocol) that answers the FAQ *correctly* — every
answer contains the right key term — but pads each reply with filler phrases and
runs long. So its information is right; its delivery is bloated. It also writes its
answer to produced/answer.txt so the artifact is collected. Deterministic, no network.
"""
import json
import os
import sys

# Correct answers, but padded with filler and run long on purpose.
ANSWERS = {
    "password": ("Thank you so much for reaching out about this. Please note that to "
                 "reset your password you should kindly navigate to Settings, and rest "
                 "assured we truly appreciate your patience while you do so."),
    "hours": ("We genuinely appreciate your question. Please note that our support team "
              "is, as always, happy to help and is available 24/7, so rest assured you "
              "can kindly reach us at your earliest convenience."),
    "cancel": ("Thanks for asking, and we truly appreciate your loyalty. Please note that "
               "if you wish to cancel your subscription you may kindly do so in Settings, "
               "and rest assured we are sorry to see you go."),
}


def answer(question):
    q = question.lower()
    if "password" in q or "reset" in q:
        return ANSWERS["password"]
    if "hour" in q or "support" in q:
        return ANSWERS["hours"]
    if "cancel" in q:
        return ANSWERS["cancel"]
    return "Thank you so much for your message; please note that we will get back to you."


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
