"""User Simulator — drives the user side of a multi-turn case (v1.1).

`simulator.type` in experiment.yaml picks how the next user turn is produced
(docs/v1-spec/execution-model.md §14; experiment-yaml-schema.md §14a):

  role_play   an LLM plays the user from a four-section policy card
              (Persona / Background / Strategy / Stop — section names accepted
              in English or Chinese). Needs AHL_SIM_BASE_URL / AHL_SIM_MODEL /
              AHL_SIM_API_KEY (optional AHL_SIM_TIMEOUT, seconds — same shape
              as the AHL_JUDGE_* family).
  scripted    a deterministic playbook of follow-ups — a user-designed mock;
              zero LLM calls, zero keys.
  script      an external program decides the next turn: one subprocess per
              turn, stdin {"transcript": [...]} -> stdout {"next": str|null}
              (engine: auto._make_script_simulator, execution-model.md §14.8).

A simulator function takes the transcript-so-far ([{turn, user, agent}, ...])
and returns the next user message, or None to end the case ("the user is
done"). role_play also ends when the model's reply STARTS WITH either end
token — "结束" or "END" — the bilingual contract of v1.1 (spec §0.2-4; the
old single-Chinese-token contract made English personas unable to stop).

The no-key honesty contract: without AHL_SIM_API_KEY a role_play simulator is
never built — the dispatch layer records a `simulator_unconfigured` error
issue and skips dispatch instead (never a fabricated follow-up). AHL_SIM_STUB=1
forces the scripted playbook path (CI/smoke); the dispatch layer marks such
traces `forced: true` so playbook output cannot pass for real LLM data.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agent_harness_lab import llm, mdutil

# Schema default turn budget when simulator.max_turns is omitted
# (experiment-yaml-schema.md §14a).
DEFAULT_MAX_TURNS = 8

# Bilingual end tokens: a role_play reply starting with either one ends the case.
END_TOKENS = ("结束", "END")

# The built-in playbook AHL_SIM_STUB=1 falls back to when the experiment
# declares no playbook. Content-equal to the retired Stack A stub_simulator's
# two fixed follow-ups (pinned by tests/test_multiturn_parity.py).
DEFAULT_PLAYBOOK_FOLLOWUPS = [
    "这个能再具体点吗?给个数。",
    "那如果情况变了,你会怎么调整?",
]


class SimulatorError(Exception):
    """A simulator config artifact (policy card / playbook) cannot be used."""


# --- role_play: four-section policy card --------------------------------------

@dataclass
class PolicyCard:
    """A role_play policy card — the four designable sections plus the actor label."""

    path: Path
    actor: str = ""       # short actor label from experiment.yaml simulator.actor
    persona: str = ""     # who the simulated user is
    background: str = ""  # what the user knows / the situation
    strategy: str = ""    # follow-up strategy (free text guiding the LLM)
    stop: str = ""        # the "asked enough" criterion, beyond max_turns

# section -> accepted H2 headings (English / Chinese), schema §14a table.
POLICY_SECTIONS: dict[str, tuple[str, ...]] = {
    "persona": ("Persona", "人设"),
    "background": ("Background", "背景知识"),
    "strategy": ("Strategy", "追问策略"),
    "stop": ("Stop", "收尾条件"),
}


def parse_policy_card(path: str | Path, actor: str = "") -> PolicyCard:
    """Read a policy card, resolving each section bilingually (EN/CN H2 names).

    `actor` is the short label from experiment.yaml's `simulator.actor:` field
    and is embedded in the prompt so the simulated user persona is anchored."""
    path = Path(path)
    sections = mdutil.split_sections(path.read_text(encoding="utf-8"))
    by_name = {name.strip().casefold(): body for name, body in sections.items()}

    def pick(aliases: tuple[str, ...]) -> str:
        for alias in aliases:
            body = by_name.get(alias.casefold())
            if body is not None:
                return body.strip()
        return ""

    return PolicyCard(
        path=path,
        actor=actor,
        persona=pick(POLICY_SECTIONS["persona"]),
        background=pick(POLICY_SECTIONS["background"]),
        strategy=pick(POLICY_SECTIONS["strategy"]),
        stop=pick(POLICY_SECTIONS["stop"]),
    )


def transcript_text(transcript: list) -> str:
    lines = []
    for t in transcript:
        lines.append(f"[turn {t.get('turn', '?')}] user: {t.get('user', '')}")
        lines.append(f"         agent: {t.get('agent', '')}")
    return "\n".join(lines)


# Module-level alias for callers that used the underscore-prefixed name;
# kept for backward compatibility within the module only.
_transcript_text = transcript_text


def build_role_play_prompt(card: PolicyCard, transcript: list) -> str:
    """English prompt: have the model play the user and produce the next turn."""
    stop = card.stop or "(none — stop only when the conversation is clearly done)"
    actor_line = f"You are: {card.actor}\n\n" if card.actor else ""
    return (
        "You are playing the USER in a conversation with an AI agent under test. "
        "Follow the persona and follow-up strategy below and write the user's "
        "next message.\n\n"
        f"{actor_line}"
        f"[Persona]\n{card.persona}\n\n"
        f"[Background]\n{card.background or '(none)'}\n\n"
        f"[Follow-up strategy]\n{card.strategy}\n\n"
        f"[Stop criterion]\n{stop}\n\n"
        f"[Conversation so far]\n{_transcript_text(transcript)}\n\n"
        "Output ONLY the user's next message. If the conversation has covered "
        "enough (per the stop criterion), output exactly: END"
    )


def is_end_token(reply: str) -> bool:
    """True when the reply starts with either end token (结束 / END)."""
    r = reply.strip()
    return any(r.startswith(tok) for tok in END_TOKENS)


def sim_env() -> tuple[str, str, str]:
    """(base_url, model, api_key) from the AHL_SIM_* environment."""
    return (os.environ.get("AHL_SIM_BASE_URL", ""),
            os.environ.get("AHL_SIM_MODEL", ""),
            os.environ.get("AHL_SIM_API_KEY", ""))


def sim_configured() -> bool:
    """True when the role_play simulator model is fully configured."""
    return all(sim_env())


def _sim_timeout() -> float:
    try:
        return float(os.environ.get("AHL_SIM_TIMEOUT", "180"))
    except ValueError:
        return 180.0


def make_role_play_simulator(card: PolicyCard) -> Callable[[list], "str | None"]:
    """Build the LLM-backed role_play simulator. Raises RuntimeError when the
    AHL_SIM_* environment is not configured — never a fabricated follow-up
    (the dispatch layer checks `sim_configured()` first and skips dispatch)."""
    base, model, key = sim_env()
    if not (base and model and key):
        raise RuntimeError(
            "simulator model not configured — set AHL_SIM_BASE_URL / "
            "AHL_SIM_MODEL / AHL_SIM_API_KEY")
    timeout = _sim_timeout()

    def _sim(transcript: list) -> str | None:
        reply = llm.chat(base, model, key, build_role_play_prompt(card, transcript),
                         timeout=timeout).strip()
        if is_end_token(reply):
            return None
        return reply

    return _sim


# --- scripted: deterministic playbook engine -----------------------------------

@dataclass
class Playbook:
    """A scripted simulator's playbook: a designed, deterministic mock.

    `default` is the global follow-up sequence (one entry per turn, sent in
    order; the end of the sequence is the stop signal). `per_case` overrides
    the sequence for specific case ids. Zero LLM calls, zero keys."""

    path: Path | None
    default: list[str] = field(default_factory=list)
    per_case: dict[str, list[str]] = field(default_factory=dict)

    def sequence_for(self, case_id: str) -> list[str]:
        return self.per_case.get(case_id, self.default)


def _string_list(value, label: str, path: Path) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise SimulatorError(
            f"playbook {path}: `{label}` must be a list of strings")
    return list(value)


def load_playbook(path: str | Path) -> Playbook:
    """Parse a playbook.yaml. Raises SimulatorError on a missing/bad file."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        raise SimulatorError(f"cannot read playbook {path}: {e}") from e
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SimulatorError(f"invalid YAML in playbook {path}: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise SimulatorError(
            f"playbook {path} must be a mapping with `default:` (and optional `per_case:`)")
    default = _string_list(data.get("default") or [], "default", path)
    raw_per_case = data.get("per_case") or {}
    if not isinstance(raw_per_case, dict):
        raise SimulatorError(f"playbook {path}: `per_case` must be a mapping of case id -> list")
    per_case = {str(cid): _string_list(seq, f"per_case.{cid}", path)
                for cid, seq in raw_per_case.items()}
    return Playbook(path=path, default=default, per_case=per_case)


def default_playbook() -> Playbook:
    """The built-in fallback playbook (AHL_SIM_STUB=1 with no experiment playbook)."""
    return Playbook(path=None, default=list(DEFAULT_PLAYBOOK_FOLLOWUPS))


def make_scripted_simulator(sequence: list[str]) -> Callable[[list], "str | None"]:
    """Deterministic simulator: emit `sequence` in order, one entry per turn;
    the end of the sequence ends the case."""
    seq = list(sequence)

    def _sim(transcript: list) -> str | None:
        asked = max(0, len(transcript) - 1)  # follow-ups already sent
        if asked < len(seq):
            return seq[asked]
        return None

    return _sim
