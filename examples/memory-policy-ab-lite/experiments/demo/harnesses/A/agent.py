"""Harness A — eager memory injection.

A local_cli agent (stdin_json: {"input": ...} -> {"response": ...}). Its memory
policy is to inject EVERY memory item into the answer regardless of relevance or
sensitivity, and to answer confidently even with no relevant memory (it guesses).
So it leaks irrelevant/sensitive memory and hallucinates when memory is missing.
Deterministic, offline. This is the *baseline to beat*, not a good policy.
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
    # Eager: dump every memory item, relevant or not.
    parts = [m["text"] for m in memory]
    # Over-confident: invent an answer when nothing relevant is on file.
    if not any(m["kind"] == "relevant" for m in memory):
        parts.append("My best estimate is $4,200.")
    return "Here is everything I have on file: " + " ".join(p for p in parts if p)


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
