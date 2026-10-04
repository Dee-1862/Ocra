"""What the orchestrator agent does with the messages it gets. Pure logic, no uAgents.

Messages are dicts: {"source": "hand" | "face" | "round", "role": ..., "data": {...}}.
Hand and face messages are only remembered (the latest of each). A "round" message is a
finished round: it is turned into a database row, and the existing rule table
(adapt.AdaptationEngine) gives a difficulty recommendation for the next round.

The recommendation is logged and shown, not applied: the games do not read it yet. Today
it uses the hit rate and the 0-10 pain score only. The face strain scale (0..1) and the
heart-rate baseline that the rule table also understands are not fed in, because the face
monitor reports PSPI on a different scale and no resting baseline.
"""
from __future__ import annotations

from .adapt import AdaptationEngine, RoundResult


class Orchestrator:
    def __init__(self, participant: str = "P000", engine: AdaptationEngine = None):
        self.participant = participant            # a pseudonymous code, never a name
        self.engine = engine or AdaptationEngine()
        self.latest: dict = {}
        self.last_decision = None

    def ingest(self, msg: dict):
        """Remember a sensor message. For a finished round, return its database row."""
        source = msg.get("source")
        data = msg.get("data") or {}
        if source == "hand":
            self.latest[f"hand:{msg.get('role')}"] = data
        elif source == "face":
            self.latest["face"] = data
        elif source == "round":
            return self._round(msg.get("role"), data)
        return None

    def _round(self, role, d: dict) -> dict:
        hits, attempts = d.get("hits") or 0, d.get("attempts") or 0
        hit_rate = hits / attempts if attempts else 0.0
        decision = self.engine.update(RoundResult(hit_rate=hit_rate, pain=d.get("pain_score")))
        self.last_decision = {"action": decision.action,
                              "fraction": round(decision.target_fraction, 2),
                              "reason": decision.reason}
        return {
            "participant": self.participant,
            "session_id": d.get("session_id") or "",
            "game": d.get("game") or "unknown",
            "seconds": d.get("seconds"),
            "hits": hits, "attempts": attempts, "hit_rate": round(hit_rate, 3),
            "roll_range_deg": d.get("roll_range_deg"),
            "pitch_range_deg": d.get("pitch_range_deg"),
            "peak_dps": d.get("peak_dps"),
            "tremor_rms_mg": d.get("tremor_rms_mg"),
            "pain_events": d.get("pain_events"),
            "pain_score": d.get("pain_score"),
            "decision": decision.action,
            "decision_reason": decision.reason,
            "extra": {"role": role, "face_pspi": d.get("face_pspi"), "face_bpm": d.get("face_bpm")},
        }
