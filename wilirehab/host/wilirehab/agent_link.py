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

load_env()          # so WILIREHAB_AGENT_PORT in .env reaches the games and the agents alike
PORT = int(os.environ.get("WILIREHAB_AGENT_PORT", "47800"))
STATUS_FILE = Path(__file__).resolve().parents[1] / "agents_status.json"      # git-ignored
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


def read_status(path=STATUS_FILE):
    """The last status snapshot, or None if there is none or it cannot be read."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and "nodes" in data and "generated_at" in data else None
