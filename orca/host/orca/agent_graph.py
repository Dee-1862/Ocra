"""The agent network as data: its levels, its connections, and how alive each part is.

Pure logic, no uAgents and no drawing. The agents program (agents_main) records a "beat" each
time a part passes a message on; this turns the beats into a state per part (ok, idle, lost,
off) that the OG's Agents page draws.

The rows, top to bottom, are the path the data takes:
    Devices   the OG and the webcam. They are not agents: the OG cannot run one.
    Filtered  the Filter agent drops implausible readings and summarises what is left.
    Checked   the Check agent fact-checks a possible imbalance before calling it real.
    Decided   the Decide agent gives the verdict and the difficulty recommendation, with its rule.
    Did       the Act agent saves the results (and Supabase, beside it, is where they go).
The Filter agent also hands clean readings straight to the Act agent for saving; that link is
not drawn, because a line would run behind the Check and Decide boxes.
"""
from __future__ import annotations

import threading
import time
from collections import deque

LEVELS = ("Devices", "Filtered", "Checked", "Decided", "Did")

# key, label, level
NODES = (
    ("og", "OG hand", 0),
    ("cam", "Webcam", 0),
    ("filter", "Filter agent", 1),
    ("check", "Check agent", 2),
    ("decide", "Decide agent", 3),
    ("act", "Act agent", 4),
    ("db", "Supabase", 4),
)
# (from, to): data flows this way
EDGES = (("og", "filter"), ("cam", "filter"), ("filter", "check"), ("check", "decide"),
         ("decide", "act"), ("act", "db"))

OFF, OK, IDLE, LOST = "off", "ok", "idle", "lost"
OK_S = 3.0              # a part that passed something on in the last 3 s is "ok"
IDLE_S = 10.0           # up to 10 s: "idle" (nothing to pass on, or slow); beyond: "lost"
RATE_WINDOW_S = 5.0


def state_of(age) -> str:
    """The state of a part whose last beat was `age` seconds ago (None = never)."""
    if age is None:
        return OFF
    if age <= OK_S:
        return OK
    if age <= IDLE_S:
        return IDLE
    return LOST


class Registry:
    """Thread-safe record of when each part last passed something on."""

    def __init__(self, clock=time.time):
        self._clock = clock                  # wall clock: the status file is read by another process
        self._lock = threading.Lock()
        self._last: dict = {}
        self._alive: dict = {}               # when each part last said "I am running"
        self._count: dict = {}
        self._recent: dict = {}
        self._note: dict = {}

    def beat(self, key: str, note: str = None, now: float = None) -> None:
        t = self._clock() if now is None else now
        with self._lock:
            self._last[key] = t
            self._count[key] = self._count.get(key, 0) + 1
            self._recent.setdefault(key, deque()).append(t)
            if note is not None:
                self._note[key] = note

    def alive(self, key: str, now: float = None) -> None:
        """"I am running", without counting as a message. An agent that only works now and then
        (the Decide agent acts once per round) must not look dead in between, so a part counts as
        ok while either its last message or its last alive signal is recent."""
        t = self._clock() if now is None else now
        with self._lock:
            self._alive[key] = t

    def note(self, key: str, text: str) -> None:
        """A short remark shown under the part's name, without counting as activity."""
        with self._lock:
            self._note[key] = text

    def snapshot(self, now: float = None) -> dict:
        t = self._clock() if now is None else now
        nodes = {}
        with self._lock:
            for key, label, level in NODES:
                last = max((x for x in (self._last.get(key), self._alive.get(key))
                            if x is not None), default=None)
                age = None if last is None else max(0.0, t - last)
                recent = self._recent.get(key)
                if recent:
                    while recent and t - recent[0] > RATE_WINDOW_S:
                        recent.popleft()
                nodes[key] = {"label": label, "level": level, "state": state_of(age), "age": age,
                              "rate": (len(recent) / RATE_WINDOW_S) if recent else 0.0,
                              "count": self._count.get(key, 0), "note": self._note.get(key, "")}
        return {"generated_at": t, "nodes": nodes}


def age_snapshot(snap: dict, now: float) -> dict:
    """A snapshot read from the status file, aged to `now` (the file was written earlier)."""
    extra = max(0.0, now - snap.get("generated_at", now))
    out = dict(snap)
    out["nodes"] = {}
    for key, node in snap.get("nodes", {}).items():
        age = node.get("age")
        age = None if age is None else age + extra
        fresh = dict(node, age=age, state=state_of(age))
        if extra > RATE_WINDOW_S:
            fresh["rate"] = 0.0
        out["nodes"][key] = fresh
    return out


def edge_state(nodes: dict, source: str) -> str:
    """The state of a connection: whatever its sending end is doing."""
    return nodes.get(source, {}).get("state", OFF)
