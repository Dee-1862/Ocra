"""How the games talk to the agents program, and how the OG screen reads its status.

The agents run in their own program (agents_main) so that a problem in them can never freeze
a game. The two sides meet in two simple places on this computer:
  - games -> agents: small JSON datagrams over UDP to 127.0.0.1 (fire and forget; if the agents
    program is not running they are simply dropped, and nothing in the game notices);
  - agents -> OG screen: a status file (agents_status.json) the agents program rewrites twice a
    second, which the OG shell reads once a second.
Nothing here leaves the computer, and everything sent is numbers or short text.
"""
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from .env import load_env

load_env()          # so ORCA_AGENT_PORT in .env reaches the games and the agents alike
PORT = int(os.environ.get("ORCA_AGENT_PORT", "47800"))
STATUS_FILE = Path(__file__).resolve().parents[1] / "agents_status.json"      # git-ignored (and the
# per-stage agents_status_<stage>.json files that agent_stage writes)
MAX_DATAGRAM = 60000


def _plain(value):
    """JSON fallback: numpy numbers become floats, anything else a string."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def encode(source: str, role, data: dict, now: float = None, session: str = "") -> bytes:
    """One message. Returns b"" when it would be too big to send."""
    msg = {"source": source, "role": role, "t": time.time() if now is None else now, "data": data}
    if session:
        msg["session"] = session          # which game session the numbers belong to
    raw = json.dumps(msg, separators=(",", ":"), default=_plain).encode("utf-8")
    return raw if len(raw) <= MAX_DATAGRAM else b""


def decode(raw: bytes):
    """A message dict, or None if the bytes are not a valid message."""
    try:
        msg = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return msg if isinstance(msg, dict) and isinstance(msg.get("source"), str) else None


class AgentIngress:
    """What a game uses to hand numbers to the agents. Never blocks, never raises."""

    def __init__(self, port: int = PORT):
        self._addr = ("127.0.0.1", port)
        self._sock = None
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setblocking(False)
        except OSError:
            self._sock = None

    def publish(self, source: str, role, data: dict, session: str = "") -> None:
        if self._sock is None:
            return
        payload = encode(source, role, data, session=session)
        if not payload:
            return
        try:
            self._sock.sendto(payload, self._addr)
        except OSError:
            pass


def write_status(snapshot: dict, path=STATUS_FILE) -> None:
    """Replace the status file in one step, so a reader never sees half of it."""
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, default=_plain), encoding="utf-8")
    os.replace(tmp, path)


# When the four stages run as separate programs (agent_stage), each writes its own status file; the
# readers (the OG shell, the gateway, the stage agents answering questions) merge them into one.
STAGE_STATUS_FILES = {s: STATUS_FILE.with_name(f"agents_status_{s}.json")
                      for s in ("filter", "check", "decide", "act")}


def write_stage_status(stage: str, snapshot: dict) -> None:
    write_status(snapshot, STAGE_STATUS_FILES[stage])


def _read_one(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and "nodes" in data and "generated_at" in data else None


def merge_status(snaps: list):
    """One status snapshot from the stages' own ones, or None if there are none.

    Every stage's snapshot lists every part, but only knows about its own, so for each part the
    entry with the most recent activity wins. Ages are brought to the time of the freshest file, so
    age_snapshot() can then age the merged snapshot like any other."""
    snaps = [s for s in snaps if s]
    if not snaps:
        return None
    newest = max(s["generated_at"] for s in snaps)
    nodes = {}
    for s in snaps:
        later = newest - s["generated_at"]             # how much older this file is than the freshest
        for key, node in s.get("nodes", {}).items():
            age = node.get("age")
            entry = dict(node, age=None if age is None else age + later)
            old = nodes.get(key)
            if old is None or (entry["age"] is not None
                               and (old["age"] is None or entry["age"] < old["age"])):
                nodes[key] = entry
    steps = sorted((st for s in snaps for st in s.get("steps", [])), key=lambda st: st.get("t", 0))
    merged = {"generated_at": newest, "nodes": nodes, "steps": steps[-14:]}
    for key in ("transport", "participant", "window_s", "decision", "verdict", "store"):
        for s in snaps:
            if s.get(key) is not None:
                merged[key] = s[key]
                break
    return merged


def read_status(path=STATUS_FILE, stage_paths=None):
    """The latest status snapshot (the one file, or the merged per-stage files, whichever is
    fresher), or None if there is none or it cannot be read."""
    if stage_paths is None:                            # the per-stage files go with the default path only
        stage_paths = tuple(STAGE_STATUS_FILES.values()) if Path(path) == STATUS_FILE else ()
    candidates = [_read_one(path), merge_status([_read_one(p) for p in stage_paths])]
    candidates = [c for c in candidates if c]
    return max(candidates, key=lambda s: s["generated_at"]) if candidates else None


def fresh_status(max_age: float = 10.0):
    """read_status(), or None when the agents have not written anything for `max_age` seconds."""
    status = read_status()
    if status is None or time.time() - status["generated_at"] > max_age:
        return None
    return status
