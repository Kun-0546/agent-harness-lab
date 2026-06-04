"""Harness B — filtered memory retrieval.

The same local_cli contract as Harness A, but a disciplined memory policy: use only
memory tagged `relevant`; drop irrelevant, stale, and sensitive memory; never invent
an answer when nothing relevant is on file (decline instead); and note when sensitive
details were withheld. Deterministic, offline.

(The `kind` tags stand in for what a real retrieval + privacy filter would compute;
hardcoding them keeps this lite demo deterministic and reviewable.)
"""
import json
import os
import sys


def parse_input(raw):
    """Decode "<query> ||| <text>::<kind> || ..." into (query, [{text, kind}])."""
    query, _, mems = raw.partition("|||")
    memory = []
    for chunk in mems.split("||"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "::" in chunk:
            text, kind = chunk.rsplit("::", 1)
            memory.append({"text": text.strip(), "kind": kind.strip()})
        else:
            memory.append({"text": chunk, "kind": "relevant"})
    return query.strip(), memory


def respond(query, memory):
    relevant = [m["text"] for m in memory if m["kind"] == "relevant"]
    if not relevant:
        return "I don't have that information."
    answer = " ".join(relevant)
    if any(m["kind"] == "sensitive" for m in memory):
        answer += " (Sensitive details withheld.)"
    return answer


def main():
    os.makedirs("produced", exist_ok=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        query, memory = parse_input(str(json.loads(line).get("input", "")))
        answer = respond(query, memory)
        with open("produced/answer.txt", "w", encoding="utf-8") as f:
            f.write(answer)
        sys.stdout.write(json.dumps({"response": answer}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
