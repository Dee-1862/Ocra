"""Rows for the hand and face tables, and the sampling that keeps them small. Pure logic.

Each agent writes its own Supabase table: the hand agent `hand_readings`, the face agent
`face_readings` (the orchestrator writes `rounds`, see orchestrator_core). A reading arrives about
once a second; only one per `interval` seconds is kept for each source, because a continuous
stream of face-derived numbers (expression, heart rate) is the most sensitive thing this system
holds, and a snapshot every few seconds is enough to see a trend. Set ORCA_SAMPLE_S to 1
for research that needs every reading.

A few columns are typed so they can be queried and plotted directly; the whole reading is also
kept in a `data` column (JSON), so nothing is lost if a measure is added later.
"""
from __future__ import annotations

import time


class Sampler:
    """Lets one reading through per `interval` seconds for each key (for example each hand)."""

    def __init__(self, interval: float, clock=time.monotonic):
        self.interval = interval
        self._clock = clock
        self._last: dict = {}

    def due(self, key) -> bool:
        now = self._clock()
        last = self._last.get(key)
        if last is None or now - last >= self.interval:
            self._last[key] = now
            return True
        return False


def _num(value):
    """A number, or None for anything that is not one (including booleans and text)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def hand_row(participant: str, msg: dict) -> dict:
    data = msg.get("data") or {}
    return {"participant": participant, "session_id": msg.get("session") or "",
            "role": msg.get("role") or "", "jerk_peak": _num(data.get("jerk_peak")),
            "rom": _num(data.get("rom")), "data": data}


def face_row(participant: str, msg: dict) -> dict:
    data = msg.get("data") or {}
    state = data.get("state")
    return {"participant": participant, "session_id": msg.get("session") or "",
            "pspi_mean": _num(data.get("pspi_mean")), "bpm": _num(data.get("bpm")),
            "state": state if isinstance(state, str) else None, "data": data}
