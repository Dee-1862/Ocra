"""Line up a fast hand event with the slower body signals it may be linked to.

The modalities do not react on the same clock. A flinch shows in the
accelerometer and the face within a fraction of a second; a change in
heart-rate variability, if there is one, comes later, and is also only
computed over a window of tens of seconds. Lining each hand event up with
the readings from the right window of the other streams, then reporting them
side by side, keeps the slow signal from being averaged into the fast one.

Method: lag-window late fusion. Each event gets a fast window for the face and
a delayed window for HRV; nothing is blended into one score.

Dynamic time warping is not used. DTW stretches one sequence to match the
shape of another, which suits two recordings of the same quantity at different
speeds. Here the streams are different quantities (jerk, a facial index,
RMSSD) with no shared shape to match, and the delay is a physiological
offset, not a speed difference.

The lag windows below are placeholders. The 3 to 10 s HRV delay comes from the
project notes, not from a paper we have read, so it is configurable and
unverified. The spike rule is relative to the player's own history, because no
absolute jerk figure for this sensor has been measured.
"""
from __future__ import annotations

from collections import deque
from statistics import median

FACE_BEFORE_S = 0.5            # face rows from this long before the hand event ...
FACE_AFTER_S = 1.5             # ... to this long after
HRV_DELAY_S = (3.0, 10.0)      # HRV rows from this window after the event
SPIKE_FACTOR = 3.0             # a hand row is an event if jerk_peak >= 3x the player's median
MIN_HISTORY = 10               # hand rows needed before an event can be called
MIN_JERK = 5.0                 # m/s^3: below this is sensor noise, never an event
COOLDOWN_S = 5.0               # one event per this long


class LagFusion:
    def __init__(self, face_before=FACE_BEFORE_S, face_after=FACE_AFTER_S,
                 hrv_delay=HRV_DELAY_S, spike_factor=SPIKE_FACTOR,
                 min_history=MIN_HISTORY, cooldown_s=COOLDOWN_S):
        self.face_before, self.face_after = face_before, face_after
        self.hrv_delay = hrv_delay
        self.spike_factor = spike_factor
        self.min_history = min_history
        self.cooldown_s = cooldown_s
        self._jerks: deque = deque(maxlen=120)
        self._face: deque = deque(maxlen=300)         # (t, row)
        self._pending: list = []
        self._last_event = -1e9

    def add_hand(self, t: float, row: dict) -> None:
        """A hand row stamped `t` (table seconds)."""
        jerk = row.get("jerk_peak")
        if jerk is None:
            return
        history = list(self._jerks)
        self._jerks.append(jerk)
        if (len(history) >= self.min_history and jerk >= MIN_JERK
                and jerk >= self.spike_factor * median(history)
                and t - self._last_event >= self.cooldown_s):
            self._last_event = t
            self._pending.append({"t": t, "jerk_peak": jerk,
                                  "jerk_median": median(history),
                                  "rom_ratio": row.get("rom_ratio")})

    def add_face(self, t: float, row: dict) -> None:
        """A face row stamped `t`. Rows summarise the second that ended at `t`."""
        self._face.append((t, row))

    def poll(self, now: float) -> list:
        """Events whose slow window has closed by `now`, each as a flat dict of numbers."""
        done, keep = [], []
        for ev in self._pending:
            if now >= ev["t"] + self.hrv_delay[1]:
                done.append(self._finish(ev))
            else:
                keep.append(ev)
        self._pending = keep
        return done

    def _finish(self, ev: dict) -> dict:
        t = ev["t"]
        fast = [r for tr, r in self._face
                if t - self.face_before < tr < t + self.face_after + 1.0]
        slow = [r for tr, r in self._face
                if t + self.hrv_delay[0] <= tr <= t + self.hrv_delay[1]]
        peaks = [r["pspi_peak"] for r in fast if r.get("pspi_peak") is not None]
        rmssd = [r["rmssd_ratio"] for r in slow if r.get("rmssd_ratio") is not None]
        lfhf = [r["lf_hf_ratio"] for r in slow if r.get("lf_hf_ratio") is not None]
        return {
            "event_t": round(t, 2),
            "jerk_peak": ev["jerk_peak"],
            "jerk_median": round(ev["jerk_median"], 1),
            "rom_ratio": ev["rom_ratio"],
            "fast_pspi_peak": max(peaks) if peaks else None,
            "fast_rows": len(fast),
            "lag_rmssd_ratio_min": round(min(rmssd), 2) if rmssd else None,
            "lag_lf_hf_ratio_max": round(max(lfhf), 2) if lfhf else None,
            "lag_rows": len(slow),
        }
