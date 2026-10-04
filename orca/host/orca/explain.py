"""Plain-language answers about what the agents did, for the ASI:One chat. Pure logic.

The Filter, Check, Decide and Act agents leave a step log and a latest verdict in the status
snapshot (agents_status.json). This turns them into short text answers, using only keywords (no AI
model): "what are you doing?" lists the latest steps by stage, "why?" gives the verdict with the
evidence for each of its four tests, "decision" gives the difficulty recommendation and the rule
behind it, "balance" gives how even the two hands were.

Privacy: answers contain only the agents' own step lines and numbers. They never contain the
participant code, session ids or raw readings. They are also OFF unless the operator turns them on
(ORCA_PUBLIC_ANSWERS=1), because the data behind them is a real person's.
"""
from __future__ import annotations

from .agent_steps import STAGE_WORDS

NOTE = ("(Research prototype: the thresholds are placeholders, not clinically validated, and this "
        "is not medical advice.)")
OFF_TEXT = ("Public answers are switched off on this Orca node. The person running it can "
            "turn them on.")
DOWN_TEXT = "The Orca agents are not running right now, so there is nothing to report."
HELP_TEXT = ("I am the Orca agent chain: Filter, Check, Decide, Act. Ask me: 'what are the "
             "agents doing?', 'why is the verdict that?', 'what did you decide?' or 'how balanced "
             "are the hands?'. " + NOTE)


def kind_of(question: str) -> str:
    """Which answer a question wants: "why", "balance", "decision", "help" or "steps"."""
    q = question.lower()
    if any(w in q for w in ("why", "justif", "evidence", "reason", "how do you know",
                            "fact check", "fact-check", "proof")):
        return "why"
    if any(w in q for w in ("balance", "imbalance", "left", "right", "both hands", "symmetr")):
        return "balance"
    if any(w in q for w in ("decid", "difficulty", "recommend", "next round", "harder", "easier")):
        return "decision"
    if any(w in q for w in ("help", "what can you", "who are you")):
        return "help"
    return "steps"


def _word(passed) -> str:
    return {True: "yes", False: "no", None: "unknown"}[passed]


OWNER = {"why": "check", "balance": "check", "decision": "decide"}      # who can answer what


def explain(question: str, status, public: bool = False, stage: str = None) -> str:
    """An answer to `question` from the status snapshot (or None when the agents are not running).

    `stage` is set when one stage agent is answering for itself: it then speaks only about its own
    steps, and for a question that belongs to another stage it says whose it is."""
    if not public:
        return OFF_TEXT
    kind = kind_of(question)
    if kind == "help":
        return HELP_TEXT if stage is None else (
            f"I am the Orca {stage.upper()} agent, one of four in a chain (Filter, Check, "
            f"Decide, Act). Ask me what I have been doing. " + NOTE)
    if status is None:
        return DOWN_TEXT
    verdict, decision = status.get("verdict"), status.get("decision")
    prefix = ""
    if stage is not None and kind in OWNER and OWNER[kind] != stage:
        prefix = f"That is the {OWNER[kind].upper()} agent's to answer. Here is what I did: "
        kind = "steps"

    if kind == "why":
        if not verdict:
            return "No round has finished yet, so there is no verdict to explain."
        lines = [f"Verdict: {verdict['verdict']}. Four separate tests were applied:"]
        for i, c in enumerate(verdict["checks"], 1):
            lines.append(f"{i}. {c['name']}: {_word(c['passed'])} ({c['evidence']})")
        lines.append("A finding only counts as 'concerning (verified)' if all four pass; one short "
                     "of that is 'watch'; and a finding that is not fully verified can never make "
                     "the game harder.")
        return "\n".join(lines + [NOTE])

    if kind == "balance":
        if not verdict or verdict.get("mean_ratio") is None:
            return "No round with both hands has finished yet, so there is no balance to report."
        return (f"Over the last round the weaker hand's range of motion was "
                f"{verdict['mean_ratio']:.0%} of the stronger hand's. Verdict: {verdict['verdict']}. "
                + NOTE)

    if kind == "decision":
        if not decision:
            return "No round has finished yet, so nothing has been decided."
        return (f"Difficulty recommendation: {decision['action']} "
                f"({round(decision['fraction'] * 100)}% of their range). Rule: {decision['reason']}. "
                + (f"Verdict behind it: {verdict['verdict']}. " if verdict else "") + NOTE)

    steps = status.get("steps") or []
    if stage is not None:
        steps = [s for s in steps if s.get("stage") == stage]
    steps = steps[-8:]
    if not steps:
        return prefix + ("I have not done anything yet." if stage else
                         "The agents are running but have not done anything yet.")
    head = f"My latest steps ({STAGE_WORDS.get(stage, stage)}):" if stage else "The agents' latest steps:"
    lines = [prefix + head] if prefix else [head]
    lines += [f"- {STAGE_WORDS.get(s.get('stage'), str(s.get('stage')).upper())}: {s.get('text', '')}"
              for s in steps]
    return "\n".join(lines)
