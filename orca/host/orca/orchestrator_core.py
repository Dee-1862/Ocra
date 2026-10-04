"""The Check, Decide and Act stages of the agent chain. Pure logic, no uAgents.

The chain is Filter -> Check -> Decide -> Act, one agent per stage (the Filter agent's logic is in
skills.py). Each stage says what it did through `say(stage, text, level)`, and passes a message on:

    Filter -> Check    "hand_window" / "face_window" (10 s summaries) and "round" (a finished round)
    Check  -> Decide   "finding": the round plus the four-way fact-check of the hands' balance
    Decide -> Act      "decision": the finding plus the difficulty recommendation and its rule
    Filter -> Act      "store": a clean reading to keep in the hand_readings / face_readings table

    Checker  keeps this round's windows and the history of earlier rounds; when a round ends it runs
             skills.factcheck and says each of the four tests with its evidence.
    Decider  gives the verdict, then the recommendation from the existing rule table
             (adapt.AdaptationEngine), made only SAFER by what was found: a verified concern forces
             "ease", and a finding that is still only "watch" cancels a "push".
    Actor    builds the database row, saves it, and says what it did.
The recommendation is logged, saved and shown, not yet applied to the games.

Messages are dicts: {"source": ..., "role": ..., "data": {...}}.
"""
from __future__ import annotations

import json
from pathlib import Path

from .adapt import EASE, HOLD, PUSH, AdaptationEngine, RoundResult
from .skills import CHECKS, factcheck

HISTORY_FILE = Path(__file__).resolve().parents[1] / "agents_history.json"      # git-ignored


def _quiet(stage, text, level="info"):
    return None


class RatioHistory:
    """The mean range-balance ratio of each earlier round, so "usual for this person" is known."""

    def __init__(self, path=None, keep: int = 50):
        self.path, self.keep = (Path(path) if path else None), keep
        self.values: list = []
        if self.path is not None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.values = [float(v) for v in data][-keep:]
            except (OSError, ValueError, TypeError):
                self.values = []

    def add(self, value: float) -> None:
        self.values = (self.values + [float(value)])[-self.keep:]
        if self.path is not None:
            try:
                self.path.write_text(json.dumps(self.values), encoding="utf-8")
            except OSError:
                pass


# ---- the Check agent ---------------------------------------------------------------------------------

class Checker:
    def __init__(self, history: RatioHistory = None, say=None, cfg: dict = CHECKS):
        self.history = history or RatioHistory()
        self.say, self.cfg = say or _quiet, cfg
        self.windows: list = []                   # this round's balance results
        self.face_level = None
        self.last_verdict = None

    def ingest(self, msg: dict):
        """Take a message from the Filter agent. When a round ends, return the finding for Decide."""
        source, data = msg.get("source"), msg.get("data") or {}
        if source == "hand_window":
            if data.get("balance"):
                self.windows.append(data["balance"])
        elif source == "face_window":
            self.face_level = data.get("level")
        elif source == "round":
            return self._round(msg.get("role"), data)
        return None

    def _round(self, role, d: dict) -> dict:
        say = self.say
        say("check", f"round over: {len(self.windows)} hand window(s) to check")
        result = factcheck(self.windows, self.history.values, self.face_level,
                           d.get("pain_score"), self.cfg)
        total = len(result["checks"])
        for i, c in enumerate(result["checks"], 1):
            word = {True: "yes", False: "no", None: "unknown"}[c["passed"]]
            say("check", f"{i}/{total} {c['name']}: {word} ({c['evidence']})",
                "ok" if c["passed"] else "info")
        if result["mean_ratio"] is not None:
            self.history.add(result["mean_ratio"])     # this round becomes part of "usual"
        self.last_verdict = result
        face_level, self.face_level, self.windows = self.face_level, None, []   # next round starts clean
        return {"round": d, "role": role, "result": result, "face_level": face_level}


# ---- the Decide agent -----------------------------------------------------------------------------------

class Decider:
    def __init__(self, engine: AdaptationEngine = None, say=None):
        self.engine = engine or AdaptationEngine()
        self.say = say or _quiet
        self.last_decision = None

    def decide(self, finding: dict) -> dict:
        """The verdict and the difficulty recommendation, each with the rule behind it."""
        say, d, result = self.say, finding["round"], finding["result"]
        verdict = result["verdict"]
        say("decide", f"verdict: {verdict}", result["level"])
        hits, attempts = d.get("hits") or 0, d.get("attempts") or 0
        hit_rate = hits / attempts if attempts else 0.0
        verified = verdict.startswith("concerning")
        decision = self.engine.update(RoundResult(
            hit_rate=hit_rate, pain=d.get("pain_score"),
            compensation_events=self.engine.comp_ease if verified else 0))
        if verified:
            decision.reason = f"{decision.reason}; verified imbalance"
        if verdict == "watch" and decision.action == PUSH:
            # Never make the game harder on a finding that is only half-checked.
            self.engine.fraction = self.engine._clamp(self.engine.fraction - self.engine.step)
            decision.action, decision.target_fraction = HOLD, self.engine.fraction
            decision.reason = "hold: imbalance not fully verified"
        self.last_decision = {"action": decision.action,
                              "fraction": round(decision.target_fraction, 2),
                              "reason": decision.reason}
        say("decide", f"difficulty: {decision.action} ({decision.reason})",
            "warn" if decision.action == EASE else "ok")
        return dict(finding, decision=self.last_decision)


# ---- the Act agent ----------------------------------------------------------------------------------------

def build_row(participant: str, decided: dict) -> dict:
    """The `rounds` row for a decided round."""
    d, result, decision = decided["round"], decided["result"], decided["decision"]
    hits, attempts = d.get("hits") or 0, d.get("attempts") or 0
    return {
        "participant": participant,
        "session_id": d.get("session_id") or "",
        "game": d.get("game") or "unknown",
        "seconds": d.get("seconds"),
        "hits": hits, "attempts": attempts,
        "hit_rate": round(hits / attempts, 3) if attempts else 0.0,
        "roll_range_deg": d.get("roll_range_deg"),
        "pitch_range_deg": d.get("pitch_range_deg"),
        "peak_dps": d.get("peak_dps"),
        "tremor_rms_mg": d.get("tremor_rms_mg"),
        "pain_events": d.get("pain_events"),
        "pain_score": d.get("pain_score"),
        "decision": decision["action"],
        "decision_reason": decision["reason"],
        "extra": {"role": decided.get("role"), "face_pspi": d.get("face_pspi"),
                  "face_bpm": d.get("face_bpm"), "verdict": result["verdict"],
                  "mean_ratio": result["mean_ratio"], "weaker": result["weaker"],
                  "face_level": decided.get("face_level"),
                  "checks": [{"name": c["name"], "passed": c["passed"]} for c in result["checks"]]},
    }


class ListStore:
    """A stand-in for round_store.RoundStore that just keeps the rows (for tests and dry runs)."""

    def __init__(self):
        self.rows: list = []

    def add(self, row: dict) -> None:
        self.rows.append(row)


class Actor:
    """Saves what the chain produced. `stores` maps a table name to something with .add(row)."""

    def __init__(self, participant: str, stores: dict, say=None):
        self.participant, self.stores, self.say = participant, stores, say or _quiet
        self.stored: dict = {}
        self._reported: dict = {}

    def handle(self, msg: dict):
        """A "decision" is turned into a round row and saved (the row is returned); a "store" is a
        clean reading from the Filter agent, kept for the table named in it."""
        source, data = msg.get("source"), msg.get("data") or {}
        if source == "store":
            self._keep(data.get("table"), data.get("row"))
            return None
        if source == "store_batch":                   # the Filter agent sends clean readings in bulk
            for item in data.get("items") or []:
                if isinstance(item, dict):
                    self._keep(item.get("table"), item.get("row"))
            return None
        if source != "decision":
            return None
        row = build_row(self.participant, data)
        self.stores["rounds"].add(row)
        self.stored["rounds"] = self.stored.get("rounds", 0) + 1
        dec = data["decision"]
        self.say("act", "round saved: local queue, then Supabase", "ok")
        self.say("act", f"recommendation: {dec['action']}, {round(dec['fraction'] * 100)}% of their range",
                 "ok")
        return row

    def _keep(self, table, row) -> None:
        if table in self.stores and isinstance(row, dict):
            self.stores[table].add(row)
            self.stored[table] = self.stored.get(table, 0) + 1

    def report(self):
        """A one-line summary of the readings saved since the last report, or None if nothing new."""
        new = {t: n - self._reported.get(t, 0) for t, n in self.stored.items()
               if t != "rounds" and n > self._reported.get(t, 0)}
        self._reported = dict(self.stored)
        if not new:
            return None
        return "saved " + ", ".join(f"{n} {t.replace('_readings', '')}" for t, n in new.items()) \
               + " reading(s)"


# ---- the whole chain in one process (tests, dry runs) ---------------------------------------------------------

class Pipeline:
    """Check -> Decide -> Act run one after the other in this process: what the agents do between
    them, without uAgents. The messages are the ones the real agents pass."""

    def __init__(self, participant: str = "P000", engine: AdaptationEngine = None,
                 history: RatioHistory = None, say=None, cfg: dict = CHECKS, stores: dict = None):
        self.participant = participant
        self.stores = stores or {"rounds": ListStore()}
        self.checker = Checker(history, say, cfg)
        self.decider = Decider(engine, say)
        self.actor = Actor(participant, self.stores, say)

    def ingest(self, msg: dict):
        """Feed a message to the Check stage. A finished round runs through all three and its row
        is returned; anything else returns None."""
        finding = self.checker.ingest(msg)
        if finding is None:
            return None
        return self.actor.handle({"source": "decision", "data": self.decider.decide(finding)})

    @property
    def last_decision(self):
        return self.decider.last_decision

    @property
    def last_verdict(self):
        return self.checker.last_verdict


Orchestrator = Pipeline          # the name this stage had before it was split in three
