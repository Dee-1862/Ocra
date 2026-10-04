"""The agents' visible work: one line for every step an agent takes. Pure logic.

There is one agent per stage, in a chain (Filter -> Check -> Decide -> Act), so a demo, a paper and
a doctor can all follow what happened:
    filter   what the Filter agent kept or dropped from what it was given, and why
    check    a test the Check agent applied to a finding, with the evidence for the result
    decide   what the Decide agent concluded, and the rule that made it conclude that
    act      what the Act agent then did (saved, recommended, ...)
In the screens these read as FILTERED, CHECKED, DECIDED and DID.

A step is a dict: {"t": time, "agent": "filter" | "check" | "decide" | "act", "stage": the same
word, "text": ..., "level": "info" | "ok" | "warn" | "alert"}. The log keeps the newest ones in memory (the agents
program writes them into the status file that the OG's Steps page and the ASI:One answers read) and
can append every step to a JSONL trace file, so a finished session can be audited line by line.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path

STAGES = ("filter", "check", "decide", "act")
LEVELS = ("info", "ok", "warn", "alert")
AGENTS = STAGES                    # one agent per stage, named after it
# How each stage is said on the screens and in the chat: what the agent has just done.
STAGE_WORDS = {"filter": "FILTERED", "check": "CHECKED", "decide": "DECIDED", "act": "DID"}
TRACE_FILE = Path(__file__).resolve().parents[1] / "agents_trace.jsonl"          # git-ignored


class StepLog:
    def __init__(self, path=None, keep: int = 80, clock=time.time):
        self._path = Path(path) if path else None
        self._clock = clock
        self._steps: deque = deque(maxlen=keep)
        self._lock = threading.Lock()

    def add(self, agent: str, stage: str, text: str, level: str = "info") -> dict:
        step = {"t": self._clock(), "agent": agent, "stage": stage, "text": text,
                "level": level if level in LEVELS else "info"}
        with self._lock:
            self._steps.append(step)
            if self._path is not None:
                try:
                    with open(self._path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(step, separators=(",", ":")) + "\n")
                except OSError:
                    pass                      # the trace is a convenience; never stop the agents for it
        return step

    def recent(self, n: int = 12) -> list:
        """The newest `n` steps, oldest first (so the newest is last, as in a log)."""
        with self._lock:
            return list(self._steps)[-n:]
