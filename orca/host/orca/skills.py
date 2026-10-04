"""What the agents actually do with the numbers: filter, balance, fact-check. Pure logic.

Plain rules and plain statistics, on purpose: every conclusion can be traced to a number and a
threshold, and a clinician can change either. THE THRESHOLDS BELOW ARE PLACEHOLDERS, NOT CLINICALLY
VALIDATED (the same stance as adapt.py). A result from here is a prompt to look, never a diagnosis.

  HandFilter   keeps only plausible hand readings, per hand, and summarises each 10 s window
  balance()    compares the two hands' windows (range of motion, smoothness)
  FaceFilter   keeps only readings with a face, tracks the person's own baseline discomfort
  factcheck()  tests a possible imbalance four ways before anyone is told it is real
"""
from __future__ import annotations

import math
import time
from collections import Counter, deque
from statistics import mean, median

CHECKS = {
    "window_s": 10.0,          # seconds of readings summarised together
    "min_readings": 3,         # kept readings a hand needs in a window for the window to count
    "jerk_max": 5000.0,        # a jerk above this is a sensor glitch, not movement
    "rom_max": 360.0,          # a range of motion over a full circle cannot be real
    "baseline_n": 10,          # accepted face readings that set the person's own calm level
    "pspi_rise": 1.0,          # discomfort "rising": this far above their own baseline
    "pspi_high": 2.5,          # "high"
    "face_q_min": 0.5,         # heart-rate quality below this is ignored
    "active_rom": 8.0,         # a hand that moves less than this (degrees) is not playing: a still
                               # hand is not a weak hand, so there is nothing to compare it with
    "balance_watch": 0.75,     # weaker hand's range under 75% of the stronger's is worth a look
    "min_windows": 3,          # balanced windows needed before any conclusion
    "persist_of": 5,           # look at the last 5 windows ...
    "persist_need": 3,         # ... and want at least 3 of them to show the same weaker hand
    "min_history": 3,          # earlier rounds needed to know what is usual for this person
    "z_flag": 2.0,             # how unusual (robust z-score) counts as unusual
    "pain_corroborate": 4,     # a 0-10 pain score at least this supports a finding
}

HANDS = ("left_hand", "right_hand")


def num(value):
    """A finite number, or None (booleans, text, nan and inf are not numbers here)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---- the hand agent's filter -------------------------------------------------------------------

def reject_hand(data: dict, cfg: dict = CHECKS):
    """Why a hand reading must be dropped, or None if it is plausible."""
    jerk = num(data.get("jerk_peak"))
    if jerk is None:
        return "no jerk value"
    if jerk < 0 or jerk > cfg["jerk_max"]:
        return "implausible jerk"
    if data.get("rom") is not None:
        rom = num(data.get("rom"))
        if rom is None or rom < 0 or rom > cfg["rom_max"]:
            return "implausible range"
    return None


class HandFilter:
    """Keeps the plausible readings of each hand and summarises them one window at a time."""

    def __init__(self, cfg: dict = CHECKS, clock=time.monotonic):
        self.cfg, self._clock = cfg, clock
        self._reset()

    def _reset(self) -> None:
        self._started = None
        self._seen: Counter = Counter()
        self._rows: dict = {}
        self._dropped: dict = {}

    def add(self, role: str, data: dict):
        """Offer one reading. Returns the reason it was dropped, or None if it was kept."""
        if self._started is None:
            self._started = self._clock()
        self._seen[role] += 1
        reason = reject_hand(data, self.cfg)
        if reason:
            self._dropped.setdefault(role, Counter())[reason] += 1
            return reason
        self._rows.setdefault(role, []).append(data)
        return None

    def window_done(self) -> bool:
        return self._started is not None and self._clock() - self._started >= self.cfg["window_s"]

    def summarize(self) -> dict:
        """role -> what the window held. Starts the next window."""
        out = {}
        for role in self._seen:
            rows = self._rows.get(role, [])

            def med(key):
                vals = [v for v in (num(r.get(key)) for r in rows) if v is not None]
                return median(vals) if vals else None

            out[role] = {"seen": self._seen[role], "kept": len(rows),
                         "dropped": dict(self._dropped.get(role, {})),
                         "rom": med("rom"), "jerk": med("jerk_peak"), "rom_ratio": med("rom_ratio")}
        self._reset()
        return out


def active_hands(summary: dict, cfg: dict = CHECKS) -> list:
    """The hands that were playing in this window: enough good readings AND moving enough.

    A resting hand still streams readings, so its presence proves nothing; only a hand that moved
    at least `active_rom` degrees counts as playing."""
    return [role for role in HANDS if role in summary
            and summary[role]["kept"] >= cfg["min_readings"]
            and summary[role]["rom"] is not None and summary[role]["rom"] >= cfg["active_rom"]]


def balance(summary: dict, cfg: dict = CHECKS):
    """Compare the two hands in one window: {"rom_ratio", "weaker", "smooth_ratio", "less_smooth", ...},
    or None unless BOTH hands were playing (see active_hands)."""
    left, right = summary.get("left_hand"), summary.get("right_hand")
    if not left or not right:
        return None
    if min(left["kept"], right["kept"]) < cfg["min_readings"]:
        return None
    if left["rom"] is None or right["rom"] is None or max(left["rom"], right["rom"]) <= 0:
        return None
    if min(left["rom"], right["rom"]) < cfg["active_rom"]:
        return None                                   # one hand sat still: nothing to compare
    hi, lo = max(left["rom"], right["rom"]), min(left["rom"], right["rom"])
    weaker = "equal" if left["rom"] == right["rom"] else (
        "left_hand" if left["rom"] < right["rom"] else "right_hand")
    smooth_ratio = less_smooth = None
    lj, rj = left["jerk"], right["jerk"]
    if lj is not None and rj is not None and max(lj, rj) > 0:
        smooth_ratio = min(lj, rj) / max(lj, rj)
        less_smooth = "equal" if lj == rj else ("left_hand" if lj > rj else "right_hand")
    return {"rom_ratio": round(lo / hi, 3), "weaker": weaker,
            "smooth_ratio": None if smooth_ratio is None else round(smooth_ratio, 3),
            "less_smooth": less_smooth, "left_rom": left["rom"], "right_rom": right["rom"],
            "left_jerk": lj, "right_jerk": rj}


# ---- the face agent's filter ----------------------------------------------------------------------

class FaceFilter:
    """Keeps readings that have a face and a discomfort number, and learns this person's calm level."""

    def __init__(self, cfg: dict = CHECKS, clock=time.monotonic):
        self.cfg, self._clock = cfg, clock
        self._baseline: list = []
        self._recent: deque = deque(maxlen=5)
        self._bpm: deque = deque(maxlen=5)
        self._reset()

    def _reset(self) -> None:
        self._started = None
        self._seen = self._kept = 0
        self._dropped: Counter = Counter()

    def add(self, data: dict):
        """Offer one face reading. Returns the reason it was dropped, or None if kept."""
        if self._started is None:
            self._started = self._clock()
        self._seen += 1
        if data.get("state") == "no_face":
            self._dropped["no face in view"] += 1
            return "no face in view"
        pspi = num(data.get("pspi_mean"))
        if pspi is None:
            self._dropped["still calibrating"] += 1
            return "still calibrating"
        self._kept += 1
        self._recent.append(pspi)
        if len(self._baseline) < self.cfg["baseline_n"]:
            self._baseline.append(pspi)
        bpm, q = num(data.get("bpm")), num(data.get("q"))
        if bpm is not None and (q is None or q >= self.cfg["face_q_min"]):
            self._bpm.append(bpm)                      # heart rate only when its own quality is fine
        return None

    def level(self) -> str:
        """"learning", "calm", "rising" or "high": the recent discomfort against their own baseline."""
        if len(self._baseline) < self.cfg["baseline_n"] or not self._recent:
            return "learning"
        diff = median(self._recent) - median(self._baseline)
        if diff >= self.cfg["pspi_high"]:
            return "high"
        return "rising" if diff >= self.cfg["pspi_rise"] else "calm"

    def window_done(self) -> bool:
        return self._started is not None and self._clock() - self._started >= self.cfg["window_s"]

    def summarize(self) -> dict:
        out = {"seen": self._seen, "kept": self._kept, "dropped": dict(self._dropped),
               "pspi": round(median(self._recent), 2) if self._recent else None,
               "baseline": round(median(self._baseline), 2) if self._baseline else None,
               "bpm": round(median(self._bpm)) if self._bpm else None, "level": self.level()}
        self._reset()
        return out


# ---- the orchestrator's fact-check ---------------------------------------------------------------------

def factcheck(windows: list, history: list, face_level, pain, cfg: dict = CHECKS) -> dict:
    """Test a possible imbalance between the hands four ways before calling it real.

    `windows` are this round's `balance()` results, `history` the earlier rounds' mean range ratios
    for the same person, `face_level` the face agent's latest level and `pain` the 0-10 score.
    Returns {"verdict", "level", "checks": [{"name", "passed", "evidence"}], "mean_ratio", "weaker"}.
    "passed" is True, False, or None when the test could not be run (for example no baseline yet).
    """
    n = len(windows)
    checks = [{"name": "enough data", "passed": n >= cfg["min_windows"],
               "evidence": f"{n} window(s) with both hands, need {cfg['min_windows']}"}]
    if n == 0:
        return {"verdict": "not enough data", "level": "info", "checks": checks,
                "mean_ratio": None, "weaker": None}

    ratios = [w["rom_ratio"] for w in windows]
    mean_ratio = mean(ratios)
    recent = windows[-cfg["persist_of"]:]
    weak = Counter(w["weaker"] for w in recent
                   if w["rom_ratio"] < cfg["balance_watch"] and w["weaker"] in HANDS)
    top_role, top_n = (weak.most_common(1)[0] if weak else (None, 0))
    checks.append({"name": "persists", "passed": top_n >= cfg["persist_need"],
                   "evidence": f"{top_n} of the last {len(recent)} windows show "
                               f"{(top_role or 'a weaker hand').replace('_', ' ')} under "
                               f"{cfg['balance_watch']:.2f}"})

    if len(history) >= cfg["min_history"]:
        centre = median(history)
        spread = max(1.4826 * median(abs(h - centre) for h in history), 0.05)
        z = (mean_ratio - centre) / spread
        checks.append({"name": "unusual for them", "passed": z <= -cfg["z_flag"],
                       "evidence": f"ratio {mean_ratio:.2f} against their usual {centre:.2f} "
                                   f"(z {z:+.1f}, flag at -{cfg['z_flag']:g})"})
    else:
        checks.append({"name": "unusual for them", "passed": None,
                       "evidence": f"no baseline yet ({len(history)} of {cfg['min_history']} "
                                   "earlier rounds)"})

    pain_ok = pain is not None and pain >= cfg["pain_corroborate"]
    face_ok = face_level in ("rising", "high")
    checks.append({"name": "other signals agree", "passed": bool(pain_ok or face_ok),
                   "evidence": f"face {face_level or 'n/a'}, pain "
                               f"{pain if pain is not None else 'n/a'} (supports at "
                               f"{cfg['pain_corroborate']}+ or a rising face)"})

    passed = sum(1 for c in checks if c["passed"] is True)
    if n < cfg["min_windows"]:
        verdict, level = "not enough data", "info"
    elif mean_ratio >= cfg["balance_watch"]:
        verdict, level = "balanced", "ok"
    elif passed == len(checks):
        verdict, level = "concerning (verified)", "alert"
    elif passed == len(checks) - 1:
        verdict, level = "watch", "warn"
    else:
        verdict, level = "noted, not verified", "info"
    return {"verdict": verdict, "level": level, "checks": checks,
            "mean_ratio": round(mean_ratio, 3), "weaker": top_role}
